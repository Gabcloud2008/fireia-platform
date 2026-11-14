"""Pruebas de normalización de CSV de FIRMS."""

from __future__ import annotations

import pytest

from hotspots.normalization.firms_csv import (
    FirmsParseError,
    detect_family,
    parse_firms_csv,
)
from tests.conftest import FIXTURES

MODIS = FIXTURES / "synthetic_modis_nrt.csv"
VIIRS_N20 = FIXTURES / "synthetic_viirs_noaa20_nrt.csv"
VIIRS_SNPP = FIXTURES / "synthetic_viirs_snpp_nrt.csv"


def _parse(path, settings, product):
    return parse_firms_csv(
        path.read_text(encoding="utf-8"),
        product=product,
        settings=settings,
        run_id="run-test",
        manifest_id="mf-test",
        ingested_at_utc="2026-11-11T00:00:00Z",
    )


def test_detect_family(settings):
    assert detect_family(["latitude", "brightness", "bright_t31"]) == "modis"
    assert detect_family(["latitude", "bright_ti4", "bright_ti5"]) == "viirs"
    assert detect_family(["latitude", "longitude"]) is None


def test_parse_modis(settings):
    out = _parse(MODIS, settings, "MODIS_NRT")
    assert out.family == "modis"
    assert out.n_rows == 12
    assert len(out.records) == 12
    assert out.quarantined == []
    rec = out.records[0]
    assert rec.sensor == "MODIS"
    assert rec.satellite_name == "Terra"
    assert rec.acq_datetime_utc == "2026-09-15T13:45:00Z"
    # atributos originales intactos
    assert rec.confidence == "82"
    assert rec.brightness == 312.5
    assert rec.bright_t31 == 294.2
    assert rec.frp == 61.4


def test_obs_id_determinista(settings):
    a = _parse(MODIS, settings, "MODIS_NRT")
    b = _parse(MODIS, settings, "MODIS_NRT")
    assert [r.obs_id for r in a.records] == [r.obs_id for r in b.records]
    assert len({r.obs_id for r in a.records}) == len(a.records)  # únicos


def test_acq_time_con_segundos(settings):
    text = MODIS.read_text(encoding="utf-8").replace("1345,", "134515,")
    out = parse_firms_csv(
        text,
        product="MODIS_NRT",
        settings=settings,
        run_id="r",
        manifest_id="m",
        ingested_at_utc="2026-11-11T00:00:00Z",
    )
    assert out.records[0].acq_time == "134515"
    assert out.records[0].acq_datetime_utc == "2026-09-15T13:45:15Z"


def test_satellite_no_mapeado_pasa_con_flag(settings):
    out = _parse(VIIRS_N20, settings, "VIIRS_NOAA20_NRT")
    assert len(out.records) == 8
    # El código "NOAA-20" no está en el mapeo provisional: pasa tal cual + flag
    assert all(r.satellite == "NOAA-20" for r in out.records)
    assert all("satellite_code_unmapped" in r.quality_flags for r in out.records)
    assert all(r.satellite_name == "NOAA-20" for r in out.records)


def test_satellite_n_mapea_a_snpp(settings):
    out = _parse(VIIRS_SNPP, settings, "VIIRS_SNPP_NRT")
    assert all(r.satellite_name == "S-NPP" for r in out.records)
    assert all("satellite_code_unmapped" not in r.quality_flags for r in out.records)


def test_confianza_original_y_banda_derivada(settings):
    out = _parse(VIIRS_N20, settings, "VIIRS_NOAA20_NRT")
    confs = {r.confidence for r in out.records}
    assert confs == {"l", "n", "h"}
    bands = {r.confidence for r in out.records} | {r.confidence_band for r in out.records}
    assert {"low", "nominal", "high"} <= bands
    # MODIS: 0-100 se conserva; banda es convención propia
    out_m = _parse(MODIS, settings, "MODIS_NRT")
    rec82 = next(r for r in out_m.records if r.confidence == "82")
    assert rec82.confidence == "82" and rec82.confidence_band == "high"
    rec7 = next(r for r in out_m.records if r.confidence == "7")
    assert rec7.confidence_band == "low"


def test_familia_incompatible_con_producto(settings):
    with pytest.raises(FirmsParseError, match="familia"):
        _parse(MODIS, settings, "VIIRS_NOAA20_NRT")


def test_columnas_faltantes(settings):
    with pytest.raises(FirmsParseError, match="irreconocible|falta"):
        _parse(FIXTURES / "synthetic_wrong_columns.csv", settings, "MODIS_NRT")


def test_encabezado_solo_sin_detecciones(settings):
    out = _parse(FIXTURES / "synthetic_empty.csv", settings, "VIIRS_NOAA20_NRT")
    assert out.records == []
    assert out.n_rows == 0
    assert out.family == "viirs"


def test_cuerpo_vacio(settings):
    out = parse_firms_csv(
        "",
        product="MODIS_NRT",
        settings=settings,
        run_id="r",
        manifest_id="m",
        ingested_at_utc="2026-11-11T00:00:00Z",
    )
    assert out.records == []
    assert "empty_body" in out.notes


# ---------------------------------------- fila truncada (Misión 008, §5)

def test_fila_truncada_al_final_va_a_cuarentena_sin_crash(settings):
    """Respuesta parcial: la última línea llega cortada a mitad de campo.
    El parseo no debe romper: la fila incompleta va a cuarentena con sus
    errores y las filas completas se procesan normal."""
    from hotspots.normalization.firms_csv import parse_firms_csv

    completo = (FIXTURES / "synthetic_modis_nrt.csv").read_text(encoding="utf-8")
    lineas = completo.splitlines()
    truncada = lineas[-1][: len(lineas[-1]) // 2]  # cortar la última a mitad
    texto = "\n".join([*lineas[:-1], truncada]) + "\n"

    outcome = parse_firms_csv(
        texto,
        product="MODIS_NRT",
        settings=settings,
        run_id="test-trunc",
        manifest_id="m-trunc",
        ingested_at_utc="2026-11-11T00:00:00Z",
        source_kind="fixture",
    )
    # invariante del parseo: toda fila va a válidos o a cuarentena
    assert outcome.n_rows == len(outcome.records) + len(outcome.quarantined)
    # la fila truncada tiene campos faltantes → cuarentena (no desaparece)
    assert len(outcome.quarantined) >= 1
    errores = [e for q in outcome.quarantined for e in q.errors]
    assert any("missing" in e or "invalid" in e for e in errores)


def test_source_kind_se_propaga_del_modo(settings):
    """Misión 008 (integridad de procedencia): el source_kind de la corrida
    viaja hasta la observación — fixture nunca se etiqueta como firms_api."""
    from hotspots.normalization.firms_csv import parse_firms_csv

    texto = (FIXTURES / "synthetic_modis_nrt.csv").read_text(encoding="utf-8")
    comunes = dict(
        product="MODIS_NRT",
        settings=settings,
        run_id="test-kind",
        manifest_id="m-kind",
        ingested_at_utc="2026-11-11T00:00:00Z",
    )
    out_fixture = parse_firms_csv(texto, source_kind="fixture", **comunes)
    out_api = parse_firms_csv(texto, source_kind="firms_api", **comunes)
    assert all(r.source_kind == "fixture" for r in out_fixture.records)
    assert all(r.source_kind == "firms_api" for r in out_api.records)
