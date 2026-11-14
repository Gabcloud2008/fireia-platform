"""Experimento 001: detección de anomalías sobre serie sintética.

QUÉ DEMUESTRA: que el método (mediana móvil + MAD, split temporal estricto)
detecta días anómalos inyectados en una serie controlada, y que el baseline
de persistencia se comporta como se espera en esa misma serie.

QUÉ NO DEMUESTRA: nada sobre la actividad real de fuegos en Paraguay. La
serie es sintética (generador con ciclo semanal + ruido + anomalías
inyectadas). Cuando el piloto de Fase 1B produzca datos reales, el mismo
método correrá sobre los datos reales y recién ahí habrá conclusiones reales.

Reproducible: PRNG con semilla fija; dos corridas dan el mismo JSON.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from hotspots.analysis.anomaly import (
    AnomalyReport,
    detect_anomalies,
)
from hotspots.analysis.baselines import mae, persistence_forecast

SEMILLA = 20260911
EVAL_DESDE = date(2026, 3, 1)
EVAL_HASTA = date(2026, 3, 31)  # 31 días de evaluación
ANOMALIAS_INYECTADAS = {
    date(2026, 3, 5): 9.0,   # pico alto
    date(2026, 3, 12): 10.0,  # pico alto
    date(2026, 3, 18): 0.05,  # caída (p. ej. cobertura nublada masiva)
    date(2026, 3, 24): 8.5,   # pico alto
}


def generar_serie() -> list[tuple[str, int]]:
    """Serie sintética: nivel base + ciclo semanal + ruido + anomalías."""
    rng = random.Random(SEMILLA)
    inicio = EVAL_DESDE - timedelta(days=120)  # 120 días de baseline
    serie: list[tuple[str, int]] = []
    d = inicio
    while d <= EVAL_HASTA:
        base = 40.0
        semanal = [1.0, 0.95, 1.05, 1.1, 1.15, 1.4, 1.3][d.weekday()]  # finde más activo
        valor = base * semanal * rng.gauss(1.0, 0.08)
        if d in ANOMALIAS_INYECTADAS:
            valor = base * ANOMALIAS_INYECTADAS[d]
        serie.append((d.isoformat(), max(0, round(valor))))
        d += timedelta(days=1)
    return serie


def main() -> dict:
    serie = generar_serie()

    # --- detección de anomalías (split temporal estricto) ---
    reporte: AnomalyReport = detect_anomalies(
        serie,
        eval_from=EVAL_DESDE.isoformat(),
        eval_to=EVAL_HASTA.isoformat(),
        z_threshold=3.0,
    )
    reporte.unidad = "serie-sintetica-departamento-demo"
    reporte.datos_sinteticos = True

    detectadas = {a.fecha for a in reporte.anomalias}
    esperadas = set(ANOMALIAS_INYECTADAS)
    tp = len(detectadas & esperadas)
    fp = len(detectadas - esperadas)

    # --- baseline persistencia sobre el mismo período ---
    errores_p, reales = [], []
    for f, v in serie:
        if EVAL_DESDE <= date.fromisoformat(f) <= EVAL_HASTA:
            pred = persistence_forecast(serie, for_date=f)
            errores_p.append(pred.valor_estimado)
            reales.append(float(v))
    mae_persistencia = mae(errores_p, reales)

    resultado = {
        "experimento": "exp_001_anomalias_sinteticas",
        "datos": "SINTETICOS (generador con semilla fija; no representan Paraguay)",
        "metodo": reporte.metodo,
        "dias_evaluados": reporte.dias_evaluados,
        "anomalias_inyectadas": sorted(str(d) for d in ANOMALIAS_INYECTADAS),
        "anomalias_detectadas": sorted(str(d) for d in detectadas),
        "verdaderos_positivos": tp,
        "falsos_positivos": fp,
        "recall": round(tp / len(ANOMALIAS_INYECTADAS), 3),
        "precision": round(tp / len(detectadas), 3) if detectadas else None,
        "no_evaluables": reporte.no_evaluables,
        "mae_persistencia_baseline": round(mae_persistencia, 2),
        "nota": (
            "El recall/precision aplica SOLO a la serie sintética. La persistencia "
            "queda como baseline a vencer cuando existan modelos reales; su MAE "
            "también es sintético."
        ),
    }

    # --- guarda resultados reproducibles ---
    out_dir = Path(__file__).resolve().parents[1] / "data" / "experiments"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "exp_001_resultado.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return resultado


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
