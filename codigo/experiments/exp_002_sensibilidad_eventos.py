"""Experimento 002: sensibilidad del motor de eventos a sus parámetros.

QUÉ DEMUESTRA: cómo cambian el número de eventos y sus tamaños (miembros,
diámetro, duración) al variar los umbrales de ventana temporal y distancia.
Incluye un escenario de CADENA diseñado para exponer el encadenamiento
transitivo: eslabones consecutivos dentro del umbral cuyo extremo a extremo
lo desborda.

QUÉ NO DEMUESTRA: nada sobre fuegos reales. Las series son sintéticas con
semilla fija; los umbrales siguen siendo convenciones experimentales del
proyecto (600 s / 2000 m), no estándares de NASA.

Reproducible: PRNG con semilla fija; dos corridas dan el mismo JSON.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from hotspots.events.engine import build_events

SEMILLA = 20261111
LAT_BASE, LON_BASE = -25.28, -57.63  # Asunción (solo como centro sintético)
M_POR_DEG = 111320.0


def _ts(minutos: float) -> str:
    return (datetime(2026, 9, 20, 12, 0, 0) + timedelta(minutes=minutos)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _obs(oid: str, prod: str, t_min: float, lat: float, lon: float, frp: float):
    sensor = "MODIS" if prod.startswith("MODIS") else "VIIRS"
    sat = "T" if sensor == "MODIS" else "1"
    return {
        "obs_id": oid,
        "product": prod,
        "sensor": sensor,
        "satellite": sat,
        "acq_datetime_utc": _ts(t_min),
        "latitude": lat,
        "longitude": lon,
        "frp": frp,
        "confidence": "h",
    }


def escenario_fuegos(n_fuegos: int) -> list[dict]:
    """n_fuegos focos sintéticos bien separados (>10 km entre sí, 3 obs c/u)."""
    rng = random.Random(SEMILLA)
    obs = []
    for f in range(n_fuegos):
        lat = LAT_BASE + (rng.uniform(-1.5, 1.5))
        lon = LON_BASE + (rng.uniform(-1.5, 1.5))
        for k, (prod, dt, d_m) in enumerate(
            [("MODIS_NRT", 0.0, 0.0), ("VIIRS_NOAA20_NRT", 3.0, 600.0), ("MODIS_NRT", 7.0, 1100.0)]
        ):
            obs.append(
                _obs(f"f{f}-{k}", prod, dt + f * 60.0, lat + d_m / M_POR_DEG, lon, 10.0 + k)
            )
    return obs


def escenario_cadena(eslabones: int = 6) -> list[dict]:
    """Cadena: eslabones consecutivos a 500 m y 8 min; extremo a extremo desborda."""
    obs = []
    for k in range(eslabones):
        prod = "MODIS_NRT" if k % 2 == 0 else "VIIRS_NOAA20_NRT"
        obs.append(
            _obs(
                f"c{k}",
                prod,
                k * 8.0,  # 480 s entre eslabones: < 600 s
                LAT_BASE + (k * 500.0) / M_POR_DEG,  # 500 m entre eslabones: < 2000 m
                LON_BASE,
                10.0,
            )
        )
    return obs


def _correr(obs: list[dict], dt: int, dist: float, root: Path):
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        r = build_events(
            obs, dt_seconds=dt, distance_m=dist, processed_root=td, run_id="sens"
        )
        # métricas de tamaño desde el resultado (sin releer parquet)
        return {
            "dt_s": dt,
            "dist_m": dist,
            "pares": r.pares_candidatos,
            "eventos": r.eventos,
            "obs_en_eventos": r.observaciones_en_eventos,
        }


def main() -> dict:
    out_dir = Path(__file__).resolve().parents[1] / "data" / "experiments"
    out_dir.mkdir(parents=True, exist_ok=True)

    fuegos = escenario_fuegos(12)
    cadena = escenario_cadena(6)

    grilla = []
    for dt in (300, 600, 1200, 2400):
        for dist in (500.0, 1000.0, 2000.0, 5000.0):
            grilla.append((dt, dist))

    resultado = {
        "experimento": "exp_002_sensibilidad_eventos",
        "datos": "SINTETICOS (generadores con semilla fija; no representan fuegos reales)",
        "metodo": "co_detection_component_v2",
        "umbral_proyecto": {"dt_seconds": 600, "distance_m": 2000.0},
        "nota_umbral": (
            "600 s / 2000 m son convenciones experimentales del proyecto, "
            "no estándares de NASA. Esta grilla documenta la sensibilidad, "
            "no 'calibra' nada."
        ),
        "escenario_fuegos": {
            "descripcion": "12 focos sintéticos separados (>10 km), 3 obs c/u",
            "grilla": [_correr(fuegos, dt, d, out_dir) for dt, d in grilla],
        },
        "escenario_cadena": {
            "descripcion": (
                "6 eslabones de 500 m y 480 s: cada PAR consecutivo cumple "
                "600 s / 2000 m, pero extremo a extremo son 2,5 km y 40 min. "
                "Expone el encadenamiento transitivo de las componentes conexas."
            ),
            "grilla": [_correr(cadena, dt, d, out_dir) for dt, d in grilla],
        },
        "nota": (
            "En el escenario cadena, con los umbrales del proyecto la cadena "
            "entera colapsa en UN evento (diámetro ~2,5 km, duración ~2400 s) "
            "con alerta_encadenamiento=true. Con dt=300 s la cadena se parte. "
            "La alerta no cambia el agrupamiento: lo hace visible."
        ),
    }

    (out_dir / "exp_002_resultado.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return resultado


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
