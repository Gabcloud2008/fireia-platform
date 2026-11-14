"""Pruebas del subsistema de análisis (Misión 004, etapa 7).

Serie sintética controlada: ciclo semanal + ruido determinista + anomalías
inyectadas. Verifica split temporal, guardas de suficiencia, determinismo del
experimento y comportamiento de los baselines.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta

import pytest

from experiments.exp_001_anomalias_sinteticas import (
    EVAL_DESDE,
    EVAL_HASTA,
    generar_serie,
    main,
)
from hotspots.analysis.anomaly import (
    AnomalyReport,
    InsufficientDataError,
    detect_anomalies,
)
from hotspots.analysis.baselines import (
    climatology_forecast,
    mae,
    persistence_forecast,
)


def _serie_simple(n=60, base=20, ruido=0.0, semilla=1):
    rng = random.Random(semilla)
    inicio = date(2026, 1, 1)
    return [
        ((inicio + timedelta(days=i)).isoformat(), max(0, round(base + rng.gauss(0, ruido))))
        for i in range(n)
    ]


# ------------------------------------------------------------------ anomalías

def test_detecta_pico_inyectado():
    serie = _serie_simple(60, ruido=1.0)
    d = date(2026, 2, 15)
    i = (d - date(2026, 1, 1)).days
    serie[i] = (d.isoformat(), 200)  # pico brutal
    rep = detect_anomalies(
        serie, eval_from="2026-02-15", eval_to="2026-02-15", z_threshold=3.0
    )
    assert len(rep.anomalias) == 1
    assert rep.anomalias[0].direccion == "alto"
    assert rep.anomalias[0].valor == 200
    # explicabilidad: el reporte sabe decir por qué
    assert "z=+" in rep.anomalias[0].explain()


def test_detecta_caida_inyectada():
    serie = _serie_simple(60, ruido=1.0)
    d = date(2026, 2, 15)
    i = (d - date(2026, 1, 1)).days
    serie[i] = (d.isoformat(), 0)
    rep = detect_anomalies(
        serie, eval_from="2026-02-15", eval_to="2026-02-15", z_threshold=3.0
    )
    assert len(rep.anomalias) == 1
    assert rep.anomalias[0].direccion == "bajo"


def test_split_temporal_sin_fuga():
    """El día evaluado NO puede estar en su propio baseline."""
    serie = _serie_simple(60, ruido=1.0)
    # si el baseline incluyera el día evaluado, un pico único sesgaría la mediana
    d = date(2026, 2, 15)
    i = (d - date(2026, 1, 1)).days
    serie[i] = (d.isoformat(), 500)
    rep = detect_anomalies(
        serie, eval_from="2026-02-15", eval_to="2026-02-15", z_threshold=3.0
    )
    # mediana del pasado ~20, no ~20+(500/28): el pico sigue siendo anómalo
    assert rep.anomalias[0].esperado_mediana < 30


def test_guarda_de_historia_insuficiente():
    serie = _serie_simple(30)
    # el día 20 tiene solo 19 días de historia => debe quedar no evaluable
    rep2 = detect_anomalies(
        serie, eval_from="2026-01-20", eval_to="2026-01-20", z_threshold=3.0
    )
    assert rep2.dias_evaluados == 1
    assert any("historia" in n for n in rep2.no_evaluables)


def test_serie_plana_mad_cero_no_explota():
    serie = [(f"2026-01-{d:02d}", 10) for d in range(1, 29)]
    serie.append(("2026-01-29", 10))  # igual => nada
    rep = detect_anomalies(
        serie, eval_from="2026-01-29", eval_to="2026-01-29", z_threshold=3.0
    )
    assert rep.anomalias == []

    serie[-1] = ("2026-01-29", 30)  # distinto en serie plana => anómalo
    rep2 = detect_anomalies(
        serie, eval_from="2026-01-29", eval_to="2026-01-29", z_threshold=3.0
    )
    assert len(rep2.anomalias) == 1


def test_serie_vacia_rechazada():
    with pytest.raises((InsufficientDataError, ValueError)):
        detect_anomalies([], eval_from="2026-01-01", eval_to="2026-01-02")


# ------------------------------------------------------------------ baselines

def test_persistencia():
    serie = [("2026-01-01", 5), ("2026-01-02", 7), ("2026-01-03", 9)]
    pred = persistence_forecast(serie, for_date="2026-01-04")
    assert pred.valor_estimado == 9.0
    assert pred.metodo == "persistence"


def test_climatologia_requiere_dos_anos():
    serie = [(f"2025-{m:02d}-15", 10 * m) for m in range(1, 13)]
    with pytest.raises(InsufficientDataError, match="años"):
        climatology_forecast(serie, for_date="2026-01-15")


def test_climatologia_con_dos_anos():
    serie = []
    for año in (2024, 2025):
        for m in range(1, 13):
            serie.append((f"{año}-{m:02d}-15", 10 * m))
    pred = climatology_forecast(serie, for_date="2026-03-15")
    # mediana de mar-2024 y mar-2025 (30, 30) => 30
    assert pred.valor_estimado == 30.0
    assert pred.metodo == "climatology_doy"


def test_mae():
    assert mae([10, 20], [12, 18]) == pytest.approx(2.0)


# ------------------------------------------------------------------ experimento

def test_experimento_001_determinista_y_detecta():
    r1 = main()
    r2 = main()
    assert r1 == r2  # determinista: misma semilla, mismo resultado

    # las 4 anomalías inyectadas deben aparecer (recall 1.0 en sintético)
    assert r1["recall"] == 1.0
    # y sin falsos positivos en la serie controlada
    assert r1["falsos_positivos"] == 0
    # marcado como sintético SIEMPRE
    assert r1["datos"].startswith("SINTETICOS")
    # baseline de persistencia presente
    assert r1["mae_persistencia_baseline"] > 0


def test_experimento_marca_datos_sinteticos():
    rep = detect_anomalies(
        generar_serie(),
        eval_from=EVAL_DESDE.isoformat(),
        eval_to=EVAL_HASTA.isoformat(),
    )
    assert isinstance(rep, AnomalyReport)
    # el flag solo lo puede encender el caller (nosotros), nunca el detector
    assert rep.datos_sinteticos is False



# ------------------------------------------------------------------ MAD = 0 (Misión 005)


def _serie_plana(n=40, base=10):
    return [
        (f"2026-01-{d:02d}" if d <= 31 else f"2026-02-{d - 31:02d}", base)
        for d in range(1, n + 1)
    ]


def test_mad_cero_valor_igual_es_normal():
    serie = _serie_plana()
    serie.append(("2026-02-10", 10))  # mismo valor: normal
    rep = detect_anomalies(serie, eval_from="2026-02-10", eval_to="2026-02-10", z_threshold=3.0)
    assert rep.anomalias == []


def test_mad_cero_valor_distinto_es_anomalia_sin_z():
    """Serie plana + desvío: anómalo por definición, z NO computable (None).

    El bug de la Misión 004: esto emitía z=Infinity → JSON inválido.
    """
    serie = _serie_plana()
    serie.append(("2026-02-10", 40))  # el cuádruple en un baseline plano
    rep = detect_anomalies(serie, eval_from="2026-02-10", eval_to="2026-02-10", z_threshold=3.0)
    assert len(rep.anomalias) == 1
    a = rep.anomalias[0]
    assert a.z is None
    assert a.motivo == "dispersion_cero"
    assert a.direccion == "alto"
    assert "no computable" in a.explain()


def test_to_dict_serializacion_estrita():
    """JSON estricto (allow_nan=False): nunca Infinity ni NaN en la respuesta."""
    serie = _serie_plana()
    serie.append(("2026-02-10", 40))
    rep = detect_anomalies(serie, eval_from="2026-02-10", eval_to="2026-02-10")
    d = rep.to_dict()
    # si hubiera Infinity/NaN acá, dumps con allow_nan=False explota
    texto = json.dumps(d, allow_nan=False)
    assert "Infinity" not in texto and "NaN" not in texto
    assert d["anomalias"][0]["z"] is None
    assert d["anomalias"][0]["motivo"] == "dispersion_cero"
