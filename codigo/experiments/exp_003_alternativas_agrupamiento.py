"""Experimento 003: alternativas de agrupamiento frente al encadenamiento.

QUÉ COMPARA (Misión 006, Objetivo E):
  A) Método vigente (motor v2): componentes conexas de pares co-detectados
     (encadenamiento transitivo: A-B, B-C unen aunque A-C no sea par).
  B) Variante "diámetro máximo": tras A, se re-agrupa cada evento ordenando
     por tiempo y admitiendo una observación solo si queda a <= D_max de TODOS
     los miembros actuales (complete-linkage aproximado). Las observaciones
     que no caben arrancan un sub-evento nuevo.

QUÉ DEMUESTRA: el trade-off cuantitativo entre conservar la cadena completa
(A: 1 evento con alerta) y partirla por diámetro (B: N sub-eventos sin
alerta) sobre tres escenarios sintéticos controlados.

QUÉ NO DEMUESTRA: nada sobre fuegos reales ni "cuál método es correcto".
La elección sigue siendo una convención del proyecto; este experimento la
vuelve explícita y medible para una futura decisión de engine v3.

Reproducible: PRNG con semilla fija; no usa red ni credenciales.
"""

from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

from hotspots.events.engine import build_events

SEMILLA = 20261111
LAT_BASE, LON_BASE = -25.28, -57.63  # centro sintético
M_POR_DEG = 111320.0
DT_PROYECTO = 600
DIST_PROYECTO = 2000.0


def _ts(minutos: float) -> str:
    return (datetime(2026, 9, 20, 12, 0, 0) + timedelta(minutes=minutos)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _obs(oid: str, prod: str, t_min: float, lat: float, lon: float, frp: float):
    sensor = "MODIS" if prod.startswith("MODIS") else "VIIRS"
    return {
        "obs_id": oid,
        "product": prod,
        "sensor": sensor,
        "satellite": "T" if sensor == "MODIS" else "1",
        "acq_datetime_utc": _ts(t_min),
        "latitude": lat,
        "longitude": lon,
        "frp": frp,
        "confidence": "h",
    }


def _dist_m(a: dict, b: dict) -> float:
    dlat = (a["latitude"] - b["latitude"]) * M_POR_DEG
    dlon = (a["longitude"] - b["longitude"]) * M_POR_DEG * math.cos(
        math.radians(LAT_BASE)
    )
    return math.hypot(dlat, dlon)


def escenario_cadena(eslabones: int = 6) -> list[dict]:
    """Eslabones consecutivos a 500 m / 480 s: pares ok, extremos desbordan."""
    obs = []
    for k in range(eslabones):
        prod = "MODIS_NRT" if k % 2 == 0 else "VIIRS_NOAA20_NRT"
        obs.append(
            _obs(f"c{k}", prod, k * 8.0, LAT_BASE + (k * 500.0) / M_POR_DEG,
                 LON_BASE, 10.0)
        )
    return obs


def escenario_dos_focos_cercanos() -> list[dict]:
    """Dos focos separados 3 km (>2 km umbral de par): caso SIN ambigüedad,
    ambos métodos deben separarlos (control positivo del experimento)."""
    obs = []
    for lat_off, etiqueta in [(0.0, "a"), (3000.0, "b")]:
        for k, (prod, dt, d_m) in enumerate(
            [("MODIS_NRT", 0.0, 0.0), ("VIIRS_NOAA20_NRT", 3.0, 400.0)]
        ):
            obs.append(
                _obs(
                    f"{etiqueta}{k}", prod, dt,
                    LAT_BASE + (lat_off + d_m) / M_POR_DEG, LON_BASE, 12.0,
                )
            )
    return obs


def escenario_dispersion(n: int = 30) -> list[dict]:
    """Detecciones dispersas (uniformes en 8 km): pares casuales, sin estructura."""
    rng = random.Random(SEMILLA)
    obs = []
    for k in range(n):
        prod = "MODIS_NRT" if k % 2 == 0 else "VIIRS_NOAA20_NRT"
        obs.append(
            _obs(
                f"d{k}",
                prod,
                rng.uniform(0, 40),
                LAT_BASE + rng.uniform(-0.04, 0.04),  # ±4.4 km
                LON_BASE + rng.uniform(-0.04, 0.04),
                rng.uniform(5, 30),
            )
        )
    return obs


def correr_metodo_a(obs: list[dict], root: Path) -> dict:
    """Motor v2 tal cual (componentes conexas)."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        r = build_events(
            obs, dt_seconds=DT_PROYECTO, distance_m=DIST_PROYECTO,
            processed_root=td, run_id="exp003a",
        )
        return {
            "metodo": "A_componentes_conexas (vigente)",
            "eventos": r.eventos,
            "obs_en_eventos": r.observaciones_en_eventos,
        }


def _miembros_por_evento(obs: list[dict]) -> dict[str, list[dict]]:
    """Reconstruye los eventos del método A SIN DuckDB: mismas componentes
    conexas de pares (dt<=600 s, dist<=2000 m) — espejo minimal del motor
    para poder re-agrupar dentro del experimento."""
    n = len(obs)
    padre = list(range(n))

    def find(x: int) -> int:
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            padre[rb] = ra

    t = [datetime.fromisoformat(o["acq_datetime_utc"].replace("Z", "+00:00")) for o in obs]
    for i in range(n):
        for j in range(i + 1, n):
            dt_s = abs((t[i] - t[j]).total_seconds())
            if dt_s <= DT_PROYECTO and _dist_m(obs[i], obs[j]) <= DIST_PROYECTO:
                union(i, j)

    grupos: dict[str, list[dict]] = {}
    for i in range(n):
        grupos.setdefault(str(find(i)), []).append(obs[i])
    return grupos


def correr_metodo_b(obs: list[dict], d_max_m: float) -> dict:
    """A + re-agrupamiento por diámetro máximo (complete-linkage aprox.).

    Dentro de cada componente: ordenar por tiempo; admitir la siguiente obs
    solo si dista <= d_max_m de TODOS los miembros ya admitidos.
    """
    sub_eventos: list[list[dict]] = []
    for _, miembros in _miembros_por_evento(obs).items():
        ordenados = sorted(miembros, key=lambda o: o["acq_datetime_utc"])
        actual: list[dict] = []
        for o in ordenados:
            if not actual or all(_dist_m(o, m) <= d_max_m for m in actual):
                actual.append(o)
            else:
                sub_eventos.append(actual)
                actual = [o]
        if actual:
            sub_eventos.append(actual)

    diametros = []
    for ev in sub_eventos:
        if len(ev) > 1:
            diametros.append(
                round(max(_dist_m(a, b) for a in ev for b in ev), 1)
            )
    return {
        "metodo": f"B_diametro_maximo (D_max={d_max_m:g} m)",
        "eventos": len(sub_eventos),
        "obs_en_eventos": sum(len(e) for e in sub_eventos if len(e) > 1),
        "sub_eventos_con_una_obs": sum(1 for e in sub_eventos if len(e) == 1),
        "diametros_por_evento_m": diametros,
    }


def main() -> dict:
    out_dir = Path(__file__).resolve().parents[1] / "data" / "experiments"
    out_dir.mkdir(parents=True, exist_ok=True)

    escenarios = {
        "cadena_6_eslabones": escenario_cadena(6),
        "dos_focos_cercanos_3km": escenario_dos_focos_cercanos(),
        "dispersion_uniforme_30": escenario_dispersion(30),
    }
    d_max_candidatos = [1500.0, 2500.0, 4000.0]

    resultado = {
        "experimento": "exp_003_alternativas_agrupamiento",
        "datos": "SINTETICOS (semilla fija; no representan fuegos reales)",
        "umbral_proyecto": {"dt_seconds": DT_PROYECTO, "distance_m": DIST_PROYECTO},
        "pregunta": (
            "¿Cuánto cambia el agrupamiento si se corta el encadenamiento "
            "transitivo con un diámetro máximo por evento?"
        ),
        "escenarios": {},
        "lectura": "",
    }

    for nombre, obs in escenarios.items():
        fila = {
            "n_obs": len(obs),
            "A_vigente": correr_metodo_a(obs, out_dir),
            "B_diametro_maximo": {
                str(d): correr_metodo_b(obs, d) for d in d_max_candidatos
            },
        }
        resultado["escenarios"][nombre] = fila

    cadena = resultado["escenarios"]["cadena_6_eslabones"]
    dos_focos = resultado["escenarios"]["dos_focos_cercanos_3km"]
    dispersion = resultado["escenarios"]["dispersion_uniforme_30"]
    resultado["lectura"] = (
        f"Cadena: A da {cadena['A_vigente']['eventos']} evento con alerta de "
        "encadenamiento (la cadena queda VISIBLE, no oculta); B con D_max=1500 "
        f"la parte en {cadena['B_diametro_maximo']['1500.0']['eventos']} sub-eventos. "
        f"Dos focos a 3 km (control): ambos métodos separan "
        f"(A={dos_focos['A_vigente']['eventos']}, "
        f"B(2500)={dos_focos['B_diametro_maximo']['2500.0']['eventos']}). "
        f"Dispersión (el costo de B): A={dispersion['A_vigente']['eventos']} "
        f"eventos vs B(2500)={dispersion['B_diametro_maximo']['2500.0']['eventos']} "
        "— B FRAGMENTA estructuras de pares legítimas en sub-eventos y singles. "
        "Ninguna variante es 'la correcta': A conserva toda la co-detección con "
        "alerta; B gana control del diámetro al precio de romper pares válidos. "
        "La decisión de engine v3 queda documentada con números, no tomada."
    )

    (out_dir / "exp_003_resultado.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return resultado


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
