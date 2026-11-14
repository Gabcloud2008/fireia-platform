"""Motor de eventos sobre la base real (Misión C de la finalización).

Ejecuta la semántica EXACTA del motor ``co_detection_component`` v2
(``events/engine.py``) sobre los 2,69 M de observaciones reales, con una
implementación vectorizada que encuentra los pares en SQL (DuckDB) y arma
las componentes conexas en Python — equivalencia demostrada por prueba
automatizada contra el motor original en días reales completos.

Equivalencia con ``build_events``:

1. Los eventos no pueden cruzar días: la base no tiene observaciones entre
   23:50-23:59 UTC (verificado, 0 filas) y la ventana máxima es 900 s, así
   que ningún par puede unir el final de un día con el comienzo del otro.
2. Los pares del motor son exactamente ``producto_a != producto_b`` y
   ``|Δt| <= dt`` y ``dist_equirect <= dist`` dentro del mismo día; SQL
   reproduce la MISMA distancia equirectangular del motor (no haversine).
3. Las componentes conexas se arman con union-find sobre esos pares; los
   eventos requieren ≥2 miembros y ≥2 productos (garantizado por
   construcción: toda unión nace de un par multi-producto).
4. El ``event_id`` usa la misma fórmula SHA-256 del motor (método,
   parámetros y observaciones ordenadas).

Entregables en ``data/PROCESADA/eventos_v1/``: ``eventos.parquet``,
``membresia.parquet``, ``calendario_nacional.csv`` y manifiesto SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from hotspots.events.engine import _EVENT_OBS_SCHEMA, _EVENTS_SCHEMA, EVENTS_METHOD

logger = logging.getLogger(__name__)

EVENTOS_VERSION = "eventos_v1"
CHAIN_ALERT_FACTOR = 2.0  # idéntico al motor v2


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


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


# Distancia equirectangular IDÉNTICA a events/engine.py, en SQL.
# ``requiere_sensores_distintos``: la base real contiene los productos NRT y
# SP del MISMO satélite (p. ej. VIIRS_NOAA21_NRT × VIIRS_NOAA21_SP comparten
# 2024-2026). Emparejarlos produciría "co-detecciones" de un satélite consigo
# mismo (artefacto de doble procesamiento, no física). El historial nacional
# exige por defecto SENSORES distintos (MODIS×VIIRS), que es la definición
# científica del proyecto; con ``False`` reproduce la semántica literal del
# motor (productos distintos) para la prueba de equivalencia.
SQL_PARES_DIA = """
SELECT a.rowid_i, b.rowid_i AS rowid_j
FROM a JOIN b
  ON a.product != b.product
 {cond_sensor}
 AND abs(date_diff('second', a.acq_datetime_utc, b.acq_datetime_utc)) <= ?
 AND sqrt(
       pow(a.latitude - b.latitude, 2)
       + pow((a.longitude - b.longitude)
             * cos(radians((a.latitude + b.latitude) / 2.0)), 2)
 ) * 111320.0 <= ?
"""


def _tabla_dia(con, fecha: str) -> int:
    """Crea la tabla temporal ``a`` del día con índices estables 0..n-1.

    Devuelve la cantidad de observaciones. ``b`` es un alias de ``a``;
    los índices de los pares refieren SIEMPRE a esta única materialización
    (sin riesgo de desalineación entre consultas).
    """
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE a AS
        SELECT row_number() OVER (ORDER BY acq_datetime_utc, obs_id) - 1 AS rowid_i,
               obs_id, product, sensor, satellite, acq_datetime_utc,
               latitude, longitude, frp, confidence
        FROM observations WHERE acq_date = ?
        """,
        [fecha],
    )
    con.execute("DROP TABLE IF EXISTS b")
    con.execute(
        "CREATE TEMP TABLE b AS SELECT rowid_i, product, sensor,"
        " acq_datetime_utc, latitude, longitude FROM a"
    )
    return int(con.execute("SELECT COUNT(*) FROM a").fetchone()[0])


def pares_dia(con, fecha: str, dt_seconds: int, distance_m: float,
              *, requiere_sensores_distintos: bool = True) -> list[tuple[int, int]]:
    """Pares (índices locales) del día con la semántica del motor."""
    _tabla_dia(con, fecha)
    cond = "AND a.sensor != b.sensor" if requiere_sensores_distintos else ""
    sql = SQL_PARES_DIA.format(cond_sensor=cond)
    filas = con.execute(sql, [dt_seconds, distance_m]).fetchall()
    return [(int(r[0]), int(r[1])) for r in filas]


def _armar_eventos_del_dia(
    obs_dia: list[dict],
    pares: list[tuple[int, int]],
    *,
    dt_seconds: int,
    distance_m: float,
    created: str,
    run_id: str,
) -> tuple[list[dict], list[dict]]:
    """Componentes conexas + estadísticas por evento (semántica motor v2)."""
    n = len(obs_dia)
    uf = _UnionFind(n)
    for i, j in pares:
        uf.union(i, j)
    comp: dict[int, list[int]] = {}
    for i in range(n):
        comp.setdefault(uf.find(i), []).append(i)

    params = {"dt_seconds": int(dt_seconds), "distance_m": float(distance_m)}
    events_rows: list[dict] = []
    member_rows: list[dict] = []
    for members in comp.values():
        if len(members) < 2:
            continue
        products = {obs_dia[i]["product"] for i in members}
        if len(products) < 2:
            continue
        ids = sorted(obs_dia[i]["obs_id"] for i in members)
        event_id = hashlib.sha256(
            ("|".join([EVENTS_METHOD, str(sorted(params.items())), *ids])).encode("utf-8")
        ).hexdigest()[:24]

        lats = [obs_dia[i]["latitude"] for i in members]
        lons = [obs_dia[i]["longitude"] for i in members]
        lat_c, lon_c = sum(lats) / len(lats), sum(lons) / len(lons)
        diametro = _diametro(lats, lons)
        times = [obs_dia[i]["ts"] for i in members]
        duracion = int(max(times) - min(times))
        alerta = (
            diametro > CHAIN_ALERT_FACTOR * distance_m
            or duracion > CHAIN_ALERT_FACTOR * dt_seconds
        )
        frp_prod: dict[str, float] = {}
        frps = []
        for i in members:
            f = obs_dia[i].get("frp")
            if f is not None:
                frps.append(float(f))
                frp_prod[obs_dia[i]["product"]] = round(
                    frp_prod.get(obs_dia[i]["product"], 0.0) + float(f), 2
                )
        events_rows.append(
            {
                "event_id": event_id,
                "metodo": EVENTS_METHOD,
                "parametros": str(params).replace("'", '"'),
                "n_observaciones": len(members),
                "productos": sorted(products),
                "sensores": sorted({obs_dia[i]["sensor"] for i in members}),
                "satelites": sorted({obs_dia[i]["satellite"] for i in members}),
                "primera_obs_utc": datetime.fromtimestamp(
                    min(times), tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "ultima_obs_utc": datetime.fromtimestamp(
                    max(times), tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "duracion_segundos": duracion,
                "lat_centroide": lat_c,
                "lon_centroide": lon_c,
                "dispersion_metros": round(
                    max(
                        _equirect(lat_c, lon_c, la, lo)
                        for la, lo in zip(lats, lons, strict=True)
                    ),
                    1,
                ),
                "diametro_metros": round(diametro, 1),
                "alerta_encadenamiento": bool(alerta),
                "frp_total": round(sum(frps), 2) if frps else None,
                "frp_max": round(max(frps), 2) if frps else None,
                "frp_por_producto": json.dumps(frp_prod),
                "confianzas": sorted({str(obs_dia[i].get("confidence", "")) for i in members}),
                "creado_en_utc": created,
                "run_id": run_id,
            }
        )
        for i in members:
            member_rows.append(
                {
                    "event_id": event_id,
                    "obs_id": obs_dia[i]["obs_id"],
                    "creado_en_utc": created,
                    "run_id": run_id,
                }
            )
    return events_rows, member_rows


def _equirect(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dy = lat1 - lat2
    dx = (lon1 - lon2) * math.cos(math.radians((lat1 + lat2) / 2.0))
    return math.sqrt(dy * dy + dx * dx) * 111320.0


def _diametro(lats: list[float], lons: list[float]) -> float:
    """Máxima distancia entre dos miembros (O(n²) solo dentro del evento)."""
    mejor = 0.0
    n = len(lats)
    for a in range(n):
        for b in range(a + 1, n):
            d = _equirect(lats[a], lons[a], lats[b], lons[b])
            if d > mejor:
                mejor = d
    return mejor


def eventos_dia(con, fecha: str, *, dt_seconds: int = 600, distance_m: float = 2000.0,
                created: str | None = None, run_id: str = "real",
                requiere_sensores_distintos: bool = True) -> tuple[list[dict], list[dict]]:
    """Eventos de un día: pares SQL + componentes Python (semántica motor v2)."""
    created = created or _utc_now_iso()
    n = _tabla_dia(con, fecha)
    if n == 0:
        return [], []
    filas = con.execute(
        """
        SELECT rowid_i, obs_id, product, sensor, satellite,
               strftime(acq_datetime_utc, '%Y-%m-%dT%H:%M:%SZ') AS acq_iso,
               epoch(acq_datetime_utc) AS ts_epoch,
               latitude, longitude, frp, confidence
        FROM a ORDER BY rowid_i
        """
    ).fetchall()
    obs_dia = [None] * n
    for r in filas:
        obs_dia[int(r[0])] = {
            "obs_id": r[1],
            "product": r[2],
            "sensor": r[3],
            "satellite": r[4],
            "acq_datetime_utc": r[5],
            "ts": float(r[6]),
            "latitude": r[7],
            "longitude": r[8],
            "frp": r[9],
            "confidence": r[10],
        }
    cond = "AND a.sensor != b.sensor" if requiere_sensores_distintos else ""
    pares = con.execute(SQL_PARES_DIA.format(cond_sensor=cond), [dt_seconds, distance_m]).fetchall()
    pares = [(int(r[0]), int(r[1])) for r in pares]
    return _armar_eventos_del_dia(
        obs_dia, pares, dt_seconds=dt_seconds, distance_m=distance_m, created=created, run_id=run_id
    )


def dias_candidatos(con, dt_seconds: int = 600, *,
                     por_sensor: bool = True) -> tuple[set[str], dict[str, int]]:
    """Días donde dos productos/sensores distintos tienen pases cercanos.

    Prefiltro barato (agregado por minuto): condición NECESARIA (superset)
    para que existan pares. Con ``por_sensor=True`` compara las familias
    MODIS vs VIIRS (los pares NRT×SP del mismo satélite no generan eventos
    en el historial nacional); con ``False`` compara todos los pares de
    productos distintos.
    """
    col = "sensor" if por_sensor else "product"
    filas = con.execute(
        f"""
        SELECT acq_date, {col},
               CAST(epoch(acq_datetime_utc) / 60 AS INTEGER) AS minuto_epoch
        FROM observations
        GROUP BY 1, 2, 3
        """
    ).fetchall()
    por_dia: dict[str, dict[str, set[int]]] = {}
    for fecha, grupo, minuto in filas:
        por_dia.setdefault(fecha, {}).setdefault(grupo, set()).add(int(minuto))
    umbral_min = dt_seconds // 60 + 1  # margen por truncamiento a minutos
    candidatos: set[str] = set()
    for fecha, grupos in por_dia.items():
        if len(grupos) < 2:
            continue
        nombres = list(grupos)
        encontro = False
        for i in range(len(nombres)):
            for j in range(i + 1, len(nombres)):
                if any(
                    abs(m - v) <= umbral_min
                    for m in grupos[nombres[i]]
                    for v in grupos[nombres[j]]
                ):
                    encontro = True
                    break
            if encontro:
                break
        if encontro:
            candidatos.add(fecha)
    stats = {
        "dias_totales": len(por_dia),
        "dias_con_solape_orbital": len(candidatos),
        "dias_sin_solape": len(por_dia) - len(candidatos),
    }
    return candidatos, stats


def construir_eventos_nacionales(
    duckdb_real: str | Path,
    salida_dir: str | Path,
    *,
    dt_seconds: int = 600,
    distance_m: float = 2000.0,
    run_id: str | None = None,
    requiere_sensores_distintos: bool = True,
) -> dict[str, Any]:
    """Historial nacional completo: eventos de todos los días + calendario + manifiesto."""
    import duckdb

    salida = Path(salida_dir)
    salida.mkdir(parents=True, exist_ok=True)
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-real"
    created = _utc_now_iso()
    con = duckdb.connect(str(duckdb_real), read_only=True)

    candidatos, stats_prefiltro = dias_candidatos(
        con, dt_seconds, por_sensor=requiere_sensores_distintos
    )
    fechas = [r[0] for r in con.execute(
        "SELECT DISTINCT acq_date FROM observations ORDER BY acq_date"
    ).fetchall()]
    logger.info(
        "días con datos: %s | con solape orbital: %s | sin solape: %s",
        len(fechas), len(candidatos), stats_prefiltro["dias_sin_solape"],
    )

    # calendario: un renglón por día CON datos (los días sin solape orbital
    # llevan eventos=0; se excluyen del join costoso por el pre-filtro)
    conteo_dias = {
        r[0]: (int(r[1]), int(r[2] or 0), int(r[3] or 0))
        for r in con.execute(
            """
            SELECT acq_date, COUNT(*),
                   SUM(CASE WHEN sensor='MODIS' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN sensor='VIIRS' THEN 1 ELSE 0 END)
            FROM observations GROUP BY 1
            """
        ).fetchall()
    }

    todos_eventos: list[dict] = []
    toda_membresia: list[dict] = []
    calendario: list[dict] = []
    for fecha in fechas:
        n_obs, n_modis, n_viirs = conteo_dias[fecha]
        if fecha in candidatos:
            ev, mb = eventos_dia(
                con, fecha, dt_seconds=dt_seconds, distance_m=distance_m,
                created=created, run_id=run_id,
                requiere_sensores_distintos=requiere_sensores_distintos,
            )
        else:
            ev, mb = [], []
        todos_eventos.extend(ev)
        toda_membresia.extend(mb)
        calendario.append(
            {
                "fecha": fecha,
                "observaciones": n_obs,
                "modis": n_modis,
                "viirs": n_viirs,
                "eventos": len(ev),
                "obs_en_eventos": len(mb),
            }
        )
    con.close()

    eventos_path = salida / "eventos.parquet"
    membresia_path = salida / "membresia.parquet"
    _escribir(todos_eventos, _EVENTS_SCHEMA, eventos_path)
    _escribir(toda_membresia, _EVENT_OBS_SCHEMA, membresia_path)

    import csv

    cal_path = salida / "calendario_nacional.csv"
    with cal_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(calendario[0].keys()))
        w.writeheader()
        w.writerows(calendario)

    manifiesto = {
        "version": EVENTOS_VERSION,
        "creado_en_utc": created,
        "run_id": run_id,
        "descripcion": "Eventos de co-detección sobre la base real M014 (semántica motor v2)",
        "metodo": EVENTS_METHOD,
        "parametros": {
            "dt_seconds": dt_seconds,
            "distance_m": distance_m,
            "requiere_sensores_distintos": requiere_sensores_distintos,
        },
        "dias_con_datos": len(fechas),
        "prefiltro_orbital": stats_prefiltro,
        "total_eventos": len(todos_eventos),
        "total_membresias": len(toda_membresia),
        "artefactos": {},
    }
    for p in (eventos_path, membresia_path, cal_path):
        manifiesto["artefactos"][p.name] = {
            "bytes": p.stat().st_size,
            "sha256": _sha256_file(p),
        }
    man_path = salida / "manifiesto_eventos_v1.json"
    man_path.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifiesto


def _escribir(rows: list[dict], schema: list[tuple], path: Path) -> None:
    import os

    arrays = {name: [r.get(name) for r in rows] for name, _ in schema}
    tbl = pa.Table.from_pydict(
        arrays, schema=pa.schema([pa.field(n, t) for n, t in schema])
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(tbl, tmp)
    os.replace(tmp, path)
