"""Motor de reconstrucción de eventos: detecciones -> fenómenos.

Qué es un "evento" acá (definición explícita, nivel 1):

Un **evento de co-detección** es una componente conexa del grafo de pares
candidatos entre productos (``candidate_matches``): un conjunto de ≥2
observaciones de ≥2 productos distintos que comparten ventana temporal corta
y proximidad espacial. Es la unidad mínima de armonización MODIS–VIIRS: "esto
que vio MODIS y esto que vio VIIRS es, con la evidencia disponible,
plausiblemente el mismo fenómeno".

Qué NO es (límites documentados):

- NO es un incendio confirmado. Un punto caliente es una anomalía térmica
  detectada por satélite; el evento agrupa observaciones, no certifica fuego.
- NO tiene perímetro. Con puntos calientes no existe geometría de área
  quemada; el campo ``dispersion_metros`` mide la dispersión de las
  detecciones alrededor del centroide, no un tamaño de incendio. El perímetro
  real, si algún día hace falta, viene de productos independientes de área
  quemada (p. ej. MCD64A1), no de acá.
- NO fusiona observaciones: cada observación conserva su ``obs_id`` y su
  fila. La relación es N:M (``event_observations``) y es un HECHO DERIVADO,
  versionado por método y parámetros.

Semántica de snapshots: cada corrida construye el conjunto COMPLETO de eventos
a partir de las observaciones actuales y escribe un snapshot nuevo
(``part-<ts>-<run>.parquet``). Las vistas DuckDB leen solo el último snapshot;
los anteriores quedan como evidencia auditable. Reconstruir es barato y evita
merge incremental frágil.

La fórmula de distancia es la misma equirectangular documentada de la vista
``candidate_matches`` (~1% de error a latitudes de Paraguay: suficiente para
agrupar; una prueba de consistencia verifica que ambos caminos producen los
mismos pares).

ENCADENAMIENTO TRANSITIVO (Misión 005, §7 — conocido y cuantificado):

Las componentes conexas agrupan por REACHABILIDAD, no por cohesión: si A
empareja con B y B con C, A/B/C forman un solo evento AUNQUE A y C estén
más lejos entre sí que el umbral. Con 600 s / 2000 m esto puede producir
eventos cuyo diámetro espacial y duración superan holgadamente los
parámetros nominales. NO cambiamos el agrupamiento (los umbrales son
convención experimental del proyecto, no estándar NASA); en su lugar, cada
evento v2 lleva diagnósticos explícitos:

- ``diametro_metros``: distancia máxima entre DOS miembros cualesquiera
  (cota superior de la extensión espacial del evento).
- ``alerta_encadenamiento``: True cuando el diámetro supera 2×distance_m o
  la duración supera 2×dt_seconds — señal de que el evento creció por
  encadenamiento y conviene mirarlo antes de interpretarlo como un
  fenómeno compacto. El factor 2 es una convención de DIAGNÓSTICO, no un
  umbral científico.
- ``frp_por_producto``: FRP desglosado por producto. ``frp_total`` suma
  detecciones de sensores distintos sobre (probablemente) el mismo fuego:
  NO es la potencia física del incendio — es un indicador de energía
  detectada agregada, con doble conteo esperable entre MODIS y VIIRS.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

#: Versión del método: cambia si cambia el algoritmo de agrupamiento.
#: v2 (Misión 005): agrupamiento IDÉNTICO a v1; se agregan diagnósticos por
#: evento (diametro_metros, alerta_encadenamiento, frp_por_producto). Los
#: snapshots v1 previos quedan como evidencia; los event_id cambian porque
#: el hash incluye la versión del método.
EVENTS_METHOD = "co_detection_component_v2"

#: Factor de diagnóstico para el flag de encadenamiento (convención propia).
CHAIN_ALERT_FACTOR = 2.0

EARTH_M_PER_DEG = 111320.0

_EVENTS_SCHEMA = [
    ("event_id", pa.string()),
    ("metodo", pa.string()),
    ("parametros", pa.string()),  # JSON: {"dt_seconds":..,"distance_m":..}
    ("n_observaciones", pa.int32()),
    ("productos", pa.list_(pa.string())),
    ("sensores", pa.list_(pa.string())),
    ("satelites", pa.list_(pa.string())),
    ("primera_obs_utc", pa.string()),
    ("ultima_obs_utc", pa.string()),
    ("duracion_segundos", pa.int64()),
    ("lat_centroide", pa.float64()),
    ("lon_centroide", pa.float64()),
    ("dispersion_metros", pa.float64()),
    ("diametro_metros", pa.float64()),
    ("alerta_encadenamiento", pa.bool_()),
    ("frp_total", pa.float64()),
    ("frp_max", pa.float64()),
    ("frp_por_producto", pa.string()),  # JSON: {producto: frp}
    ("confianzas", pa.list_(pa.string())),
    ("creado_en_utc", pa.string()),
    ("run_id", pa.string()),
]

_EVENT_OBS_SCHEMA = [
    ("event_id", pa.string()),
    ("obs_id", pa.string()),
    ("creado_en_utc", pa.string()),
    ("run_id", pa.string()),
]


@dataclass
class EventBuildResult:
    method: str
    parameters: dict
    total_observaciones: int = 0
    pares_candidatos: int = 0
    eventos: int = 0
    observaciones_en_eventos: int = 0
    escritas: bool = False
    events_path: str | None = None
    membership_path: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def equirect_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia equirectangular en metros (idéntica a la de candidate_matches)."""
    dy = lat1 - lat2
    dx = (lon1 - lon2) * math.cos(math.radians((lat1 + lat2) / 2.0))
    return math.sqrt(dy * dy + dx * dx) * EARTH_M_PER_DEG


def _parse_ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def build_events(
    observations: list[dict],
    *,
    dt_seconds: int = 600,
    distance_m: float = 2000.0,
    processed_root: str | Path,
    run_id: str,
    created_at_utc: str | None = None,
) -> EventBuildResult:
    """Construye eventos de co-detección desde las observaciones actuales.

    ``observations``: filas con obs_id, product, sensor, satellite,
    acq_datetime_utc, latitude, longitude, frp, confidence (la vista
    deduplicada). Escribe un snapshot completo (events + membership).
    """
    created = created_at_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {"dt_seconds": int(dt_seconds), "distance_m": float(distance_m)}
    result = EventBuildResult(method=EVENTS_METHOD, parameters=params)
    result.total_observaciones = len(observations)

    obs = sorted(observations, key=lambda o: (o["acq_datetime_utc"], o["obs_id"]))
    n = len(obs)
    uf = _UnionFind(n)

    # Benchmark 001 (Misión 005): parsear timestamps UNA vez por observación
    # (antes se re-parseaba dentro del bucle interno: O(n·k) strptime → cuello
    # de botella dominante a 8k obs/día). Misma semántica, mismos pares.
    ts_epoch = [t.timestamp() for t in map(_parse_ts, (o["acq_datetime_utc"] for o in obs))]

    # pares candidatos entre productos (misma regla que la vista SQL:
    # productos distintos, ventana temporal y distancia por debajo del umbral)
    n_pares = 0
    for i in range(n):
        ti = ts_epoch[i]
        for j in range(i + 1, n):
            dt = ts_epoch[j] - ti
            if dt > dt_seconds:
                break  # ordenado por tiempo: nadie más entra en la ventana
            if obs[i]["product"] == obs[j]["product"]:
                continue
            d = equirect_distance_m(
                obs[i]["latitude"], obs[i]["longitude"],
                obs[j]["latitude"], obs[j]["longitude"],
            )
            if d <= distance_m:
                uf.union(i, j)
                n_pares += 1
    result.pares_candidatos = n_pares

    # componentes con >= 2 miembros y >= 2 productos
    comp: dict[int, list[int]] = {}
    for i in range(n):
        comp.setdefault(uf.find(i), []).append(i)

    events_rows: list[dict] = []
    member_rows: list[dict] = []
    for members in comp.values():
        if len(members) < 2:
            continue
        products = {obs[i]["product"] for i in members}
        if len(products) < 2:
            continue  # por construcción no pasa, defensa en profundidad
        ids = sorted(obs[i]["obs_id"] for i in members)
        event_id = hashlib.sha256(
            ("|".join([EVENTS_METHOD, str(sorted(params.items())), *ids])).encode("utf-8")
        ).hexdigest()[:24]

        lats = [obs[i]["latitude"] for i in members]
        lons = [obs[i]["longitude"] for i in members]
        lat_c, lon_c = sum(lats) / len(lats), sum(lons) / len(lons)
        disp = max(
            equirect_distance_m(lat_c, lon_c, la, lo) for la, lo in zip(lats, lons, strict=True)
        )
        # diámetro: distancia máxima entre DOS miembros (cota de extensión
        # espacial). O(n²) SOLO dentro del evento (los eventos son chicos);
        # los eventos gigantes por encadenamiento quedan visibles justo acá.
        diametro = 0.0
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                d_ab = equirect_distance_m(lats[a], lons[a], lats[b], lons[b])
                if d_ab > diametro:
                    diametro = d_ab
        times = [_parse_ts(obs[i]["acq_datetime_utc"]) for i in members]
        duracion = int((max(times) - min(times)).total_seconds())
        alerta = (
            diametro > CHAIN_ALERT_FACTOR * distance_m
            or duracion > CHAIN_ALERT_FACTOR * dt_seconds
        )
        frps = [obs[i].get("frp") for i in members if obs[i].get("frp") is not None]
        # FRP por producto: el desglose que no miente — sumar entre sensores
        # NO da la potencia física del fuego (doble conteo esperable).
        frp_prod: dict[str, float] = {}
        for i in members:
            frp_i = obs[i].get("frp")
            if frp_i is not None:
                frp_prod[obs[i]["product"]] = round(
                    frp_prod.get(obs[i]["product"], 0.0) + float(frp_i), 2
                )

        events_rows.append(
            {
                "event_id": event_id,
                "metodo": EVENTS_METHOD,
                "parametros": str(params).replace("'", '"'),
                "n_observaciones": len(members),
                "productos": sorted(products),
                "sensores": sorted({obs[i]["sensor"] for i in members}),
                "satelites": sorted({obs[i]["satellite"] for i in members}),
                "primera_obs_utc": min(times).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ultima_obs_utc": max(times).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "duracion_segundos": duracion,
                "lat_centroide": lat_c,
                "lon_centroide": lon_c,
                "dispersion_metros": round(disp, 1),
                "diametro_metros": round(diametro, 1),
                "alerta_encadenamiento": bool(alerta),
                "frp_total": round(sum(frps), 2) if frps else None,
                "frp_max": round(max(frps), 2) if frps else None,
                "frp_por_producto": json.dumps(frp_prod),
                "confianzas": sorted({str(obs[i].get("confidence", "")) for i in members}),
                "creado_en_utc": created,
                "run_id": run_id,
            }
        )
        for i in members:
            member_rows.append(
                {
                    "event_id": event_id,
                    "obs_id": obs[i]["obs_id"],
                    "creado_en_utc": created,
                    "run_id": run_id,
                }
            )

    result.eventos = len(events_rows)
    result.observaciones_en_eventos = len(member_rows)

    if events_rows:
        ts = created.replace(":", "").replace("-", "")[:15] + "Z"
        base = Path(processed_root) / "events"
        base.mkdir(parents=True, exist_ok=True)
        ev_path = base / f"part-{ts}-{run_id[:8]}.parquet"
        _write(events_rows, _EVENTS_SCHEMA, ev_path)
        mb_path = base / f"membership-{ts}-{run_id[:8]}.parquet"
        _write(member_rows, _EVENT_OBS_SCHEMA, mb_path)
        result.escritas = True
        result.events_path = str(ev_path)
        result.membership_path = str(mb_path)
    else:
        result.notes.append("Sin eventos: no hay pares entre productos con estos umbrales.")
    return result


def _write(rows: list[dict], schema: list[tuple], path: Path) -> None:
    import os

    arrays = {name: [r.get(name) for r in rows] for name, _ in schema}
    tbl = pa.Table.from_pydict(
        arrays, schema=pa.schema([pa.field(n, t) for n, t in schema])
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(tbl, tmp)
    os.replace(tmp, path)


def events_files(processed_root: str | Path) -> list[Path]:
    base = Path(processed_root) / "events"
    if not base.exists():
        return []
    return sorted(p for p in base.glob("part-*.parquet") if p.is_file())


def membership_files(processed_root: str | Path) -> list[Path]:
    base = Path(processed_root) / "events"
    if not base.exists():
        return []
    return sorted(p for p in base.glob("membership-*.parquet") if p.is_file())


def latest_events_file(processed_root: str | Path) -> Path | None:
    files = events_files(processed_root)
    return files[-1] if files else None


def latest_membership_file(processed_root: str | Path) -> Path | None:
    files = membership_files(processed_root)
    return files[-1] if files else None
