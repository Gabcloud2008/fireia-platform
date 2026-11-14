"""Benchmark 001: escalabilidad del emparejamiento de observaciones.

QUÉ MIDE: cómo se comporta ``build_events`` (el paso de pares) al crecer N
observaciones en ventanas temporales de 1 día / 1 mes / 1 año. Registra
tiempo de pared, memoria pico (tracemalloc), pares encontrados y la razón
tiempo(N×2)/tiempo(N) como indicador de complejidad empírica.

QUÉ NO MIDE: nada sobre fuegos reales. Las observaciones son sintéticas con
semilla fija, en el bbox de consulta real de Paraguay.

Reproducible: PRNG con semilla fija; misma N => mismo input => mismos pares.
"""

from __future__ import annotations

import json
import random
import tempfile
import time
import tracemalloc
from datetime import datetime, timedelta
from pathlib import Path

from hotspots.events.engine import build_events

SEMILLA = 20261111
BBOX = (-62.7, -27.6, -54.2, -19.3)  # bbox de CONSULTA (no territorio)


def generar_obs(n: int, dias: int) -> list[dict]:
    """n observaciones distribuidas en `dias` días dentro del bbox, con mezcla
    de productos (para que existan pares MODIS×VIIRS)."""
    rng = random.Random(SEMILLA)
    base = datetime(2026, 1, 1, 0, 0, 0)
    obs = []
    for i in range(n):
        prod = "MODIS_NRT" if i % 2 == 0 else "VIIRS_NOAA20_NRT"
        seg = rng.random() * dias
        t = base + timedelta(days=seg)
        obs.append(
            {
                "obs_id": f"b{i:07d}",
                "product": prod,
                "sensor": "MODIS" if i % 2 == 0 else "VIIRS",
                "satellite": "T" if i % 2 == 0 else "1",
                "acq_datetime_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "latitude": rng.uniform(BBOX[1], BBOX[3]),
                "longitude": rng.uniform(BBOX[0], BBOX[2]),
                "frp": rng.uniform(5, 80),
                "confidence": "h",
            }
        )
    return obs


def correr(obs: list[dict]) -> dict:
    with tempfile.TemporaryDirectory() as td:
        tracemalloc.start()
        t0 = time.perf_counter()
        r = build_events(obs, processed_root=td, run_id="bench")
        dt = time.perf_counter() - t0
        _, pico = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "n_obs": len(obs),
            "segundos": round(dt, 3),
            "memoria_pico_mb": round(pico / 1e6, 1),
            "pares": r.pares_candidatos,
            "eventos": r.eventos,
        }


def main() -> dict:
    out_dir = Path(__file__).resolve().parents[1] / "data" / "experiments"
    out_dir.mkdir(parents=True, exist_ok=True)

    casos = []
    for etiqueta, dias in (("1_dia", 1), ("1_mes", 30), ("1_anio", 365)):
        for n in (500, 1000, 2000, 4000, 8000):
            casos.append((etiqueta, dias, n))

    resultados = []
    for etiqueta, dias, n in casos:
        obs = generar_obs(n, dias)
        r = correr(obs)
        r["escenario"] = etiqueta
        resultados.append(r)

    # complejidad empírica: razón de tiempos al doblar N (mismo escenario)
    razones = []
    for etiqueta in ("1_dia", "1_mes", "1_anio"):
        serie = [r for r in resultados if r["escenario"] == etiqueta]
        for a, b in zip(serie, serie[1:], strict=False):
            if a["segundos"] > 0:
                razones.append(
                    {
                        "escenario": etiqueta,
                        "de_n": a["n_obs"],
                        "a_n": b["n_obs"],
                        "razon_tiempo": round(b["segundos"] / a["segundos"], 2),
                        "razon_n": round(b["n_obs"] / a["n_obs"], 2),
                    }
                )

    salida = {
        "benchmark": "bench_001_pares",
        "datos": "SINTETICOS (semilla fija, bbox de consulta real)",
        "parametros": {"dt_seconds": 600, "distance_m": 2000.0},
        "casos": resultados,
        "complejidad_empirica": razones,
        "lectura": (
            "El bucle interno corta por ventana temporal (observaciones "
            "ordenadas por tiempo): el costo crece con N x (densidad en la "
            "ventana), no con N² puro. En 1 día la ventana concentra todo; en "
            "1 año cada instante tiene pocos vecinos. La razón de tiempos al "
            "doblar N se acerca a 2 cuando la densidad se mantiene y cae por "
            "debajo cuando el tiempo se diluye."
        ),
    }

    (out_dir / "bench_001_resultado.json").write_text(
        json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return salida


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
