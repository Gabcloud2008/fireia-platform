"""Pruebas de QC: taxonomía de estados y validación por registro."""

from __future__ import annotations

from hotspots.ingestion.base import FetchResult
from hotspots.ingestion.firms import classify_response, header_only_csv, sniff_body
from hotspots.normalization.firms_csv import parse_firms_csv
from hotspots.quality.checks import check_record
from hotspots.quality.states import ALL_STATES, IngestState, processing_state_of
from tests.conftest import FIXTURES


def test_taxonomia_tiene_los_10_estados():
    # Corrección C: se suma success_all_quarantined (antes conflado en parse_failed)
    assert set(ALL_STATES) == {
        "success_with_detections",
        "success_no_detections",
        "success_all_quarantined",
        "no_coverage",
        "provider_missing_data",
        "cloud_obscured",
        "download_failed",
        "parse_failed",
        "authentication_failed",
        "unknown",
    }


def test_success_states_y_processing_state():
    from hotspots.quality.states import SUCCESS_STATES

    assert SUCCESS_STATES == (
        "success_with_detections",
        "success_no_detections",
        "success_all_quarantined",
    )
    # completed: procesado de punta a punta
    assert processing_state_of(IngestState.SUCCESS_WITH_DETECTIONS) == "completed"
    assert processing_state_of(IngestState.SUCCESS_ALL_QUARANTINED) == "completed"
    assert processing_state_of(IngestState.NO_COVERAGE) == "completed"
    # raw_only: bytes preservados pero no interpretables
    assert processing_state_of(IngestState.PARSE_FAILED) == "raw_only"
    assert processing_state_of(IngestState.UNKNOWN) == "raw_only"
    # failed: fallo de transacción HTTP
    assert processing_state_of(IngestState.DOWNLOAD_FAILED) == "failed"
    assert processing_state_of(IngestState.AUTHENTICATION_FAILED) == "failed"


def _fetch(status=None, body=None, error=None):
    return FetchResult(
        ok=(status is not None and 200 <= status < 300 and error is None),
        status_code=status,
        body=body.encode() if isinstance(body, str) else body,
        url_redacted="https://firms.example/api/area/csv/{MAP_KEY}/X/1",
        error=error,
    )


def test_clasificacion_http():
    assert classify_response(_fetch(status=401)) is IngestState.AUTHENTICATION_FAILED
    assert classify_response(_fetch(status=403)) is IngestState.AUTHENTICATION_FAILED
    assert classify_response(_fetch(status=429)) is IngestState.DOWNLOAD_FAILED
    assert classify_response(_fetch(status=500)) is IngestState.DOWNLOAD_FAILED
    assert classify_response(_fetch(status=404)) is IngestState.DOWNLOAD_FAILED
    assert classify_response(_fetch(error="ConnectionError")) is IngestState.DOWNLOAD_FAILED


def test_clasificacion_texto_de_error_firms():
    assert (
        classify_response(_fetch(status=200, body="Invalid MAP_KEY: not authorized"))
        is IngestState.AUTHENTICATION_FAILED
    )
    # 200 con CSV válido: hay que parsear (None)
    assert classify_response(_fetch(status=200, body="latitude,longitude\n1,2\n")) is None


def test_header_only_csv():
    # Corrección B: un cuerpo VACÍO ya no cuenta como "encabezado sin filas".
    assert header_only_csv("") is False
    assert header_only_csv("   \n  \n") is False
    assert header_only_csv("latitude,longitude,brightness\n") is True
    assert header_only_csv("latitude,longitude\n-25.0,-57.0\n") is False
    assert header_only_csv("\ufefflatitude,longitude\n") is True  # BOM tolerado
    assert header_only_csv("Invalid MAP_KEY") is False


def test_sniff_body_clasifica_los_cinco_tipos():
    # Corrección B: la clasificación del cuerpo es explícita.
    assert sniff_body("") == "empty"
    assert sniff_body("\n  \n") == "empty"
    assert sniff_body("<!DOCTYPE html><html><body>x</body></html>") == "html"
    assert sniff_body("<html>maintenance</html>") == "html"
    assert sniff_body('{"error": 1}') == "json"
    assert sniff_body("[1,2,3]\n") == "json"
    assert sniff_body("latitude,longitude\n1,2\n") == "csv"
    assert sniff_body("latitude,longitude,brightness\n") == "csv"
    assert sniff_body("Invalid MAP_KEY: not authorized") == "non_csv"
    assert sniff_body("Some unexpected provider text") == "non_csv"


def test_filas_invalidas_van_a_cuarentena(settings):
    out = parse_firms_csv(
        (FIXTURES / "synthetic_invalid_rows.csv").read_text(encoding="utf-8"),
        product="MODIS_NRT",
        settings=settings,
        run_id="r",
        manifest_id="m",
        ingested_at_utc="2026-11-11T00:00:00Z",
    )
    assert out.n_rows == 8
    assert len(out.records) == 1  # solo la primera fila es válida
    assert len(out.quarantined) == 7
    todos_los_errores = [e for q in out.quarantined for e in q.errors]
    assert "latitude_out_of_range" in todos_los_errores
    assert "longitude_out_of_range" in todos_los_errores
    assert "invalid_acq_date" in todos_los_errores
    assert "invalid_acq_time" in todos_los_errores
    assert any(e.startswith("confidence_out_of_range") for e in todos_los_errores)
    assert "frp_below_min" in todos_los_errores
    assert any(e.startswith("invalid_daynight") for e in todos_los_errores)


def test_flags_soft_en_fixture_modis(settings):
    out = parse_firms_csv(
        (FIXTURES / "synthetic_modis_nrt.csv").read_text(encoding="utf-8"),
        product="MODIS_NRT",
        settings=settings,
        run_id="r",
        manifest_id="m",
        ingested_at_utc="2026-11-11T00:00:00Z",
    )
    fuera = [r for r in out.records if "outside_query_bbox" in r.quality_flags]
    alto = [r for r in out.records if "implausible_high_frp" in r.quality_flags]
    assert len(fuera) == 1  # lat -30 (fuera del bbox con margen)
    assert len(alto) == 1  # frp 6000.5
    # Los registros con flag SIGUEN siendo válidos (no van a cuarentena)
    assert len(out.quarantined) == 0


def test_dominio_confianza_por_familia(settings):
    out = parse_firms_csv(
        (FIXTURES / "synthetic_viirs_noaa20_nrt.csv").read_text(encoding="utf-8"),
        product="VIIRS_NOAA20_NRT",
        settings=settings,
        run_id="r",
        manifest_id="m",
        ingested_at_utc="2026-11-11T00:00:00Z",
    )
    assert all(r.confidence in {"l", "n", "h"} for r in out.records)


# ============================================================== corrección A
def _parse_text(text, settings, product="MODIS_NRT"):
    return parse_firms_csv(
        text,
        product=product,
        settings=settings,
        run_id="r",
        manifest_id="m",
        ingested_at_utc="2026-11-11T00:00:00Z",
    )


def test_latitud_ausente_a_cuarentena_con_error_exacto(settings):
    out = _parse_text(
        (FIXTURES / "synthetic_missing_coords.csv").read_text(encoding="utf-8"), settings
    )
    assert out.n_rows == 4
    assert len(out.records) == 1  # solo la fila con coordenadas completas
    assert len(out.quarantined) == 3
    errores = [q.errors for q in out.quarantined]
    assert "missing_latitude" in errores[0]  # fila 2: lat vacía
    assert "missing_longitude" in errores[1]  # fila 3: lon vacía
    assert errores[2] == ["missing_latitude", "missing_longitude"]  # fila 4: ambas


def test_coordenada_ausente_nunca_es_cero(settings):
    """(0,0) es el golfo de Guinea: no puede aparecer como valor de relleno."""
    out = _parse_text(
        (FIXTURES / "synthetic_missing_coords.csv").read_text(encoding="utf-8"), settings
    )
    for rec in out.records:
        assert rec.latitude == -25.0 and rec.longitude == -57.5
    for q in out.quarantined:
        # la fila original se conserva tal como llegó (campos vacíos = vacíos)
        assert q.raw["latitude"] in ("", "-25.0000")
        assert "0.0" not in (q.raw["latitude"], q.raw["longitude"])


def test_coordenadas_fuera_de_rango_global(settings):
    out = _parse_text(
        (FIXTURES / "synthetic_invalid_rows.csv").read_text(encoding="utf-8"), settings
    )
    errores = {e for q in out.quarantined for e in q.errors}
    assert "latitude_out_of_range" in errores  # lat 95
    assert "longitude_out_of_range" in errores  # lon -200


def test_coordenadas_validas_fuera_de_paraguay_siguen_siendo_validas(settings):
    """Estar fuera del área de estudio NO invalida la coordenada (decisión
    científica: el bbox es ámbito de estudio, no criterio de validez)."""
    out = _parse_text(
        (FIXTURES / "synthetic_modis_nrt.csv").read_text(encoding="utf-8"), settings
    )
    fuera = [r for r in out.records if "outside_query_bbox" in r.quality_flags]
    assert len(fuera) == 1  # lat -30.0
    assert fuera[0].latitude == -30.0  # se conserva el valor original
    assert len(out.quarantined) == 0  # sigue siendo válida: solo flag soft


def test_check_record_missing_lat_lon_defensa_en_profundidad(settings):
    """check_record también distingue None (ausente) de no-numérico (corrección A)."""
    from hotspots.models import NormalizedObservation

    def _rec(lat, lon):
        return NormalizedObservation(
            provider="firms",
            product="MODIS_NRT",
            source_kind="test",
            run_id="r",
            manifest_id="m",
            ingested_at_utc="2026-11-11T00:00:00Z",
            latitude=lat,
            longitude=lon,
            acq_date="2026-09-15",
            acq_time="1330",
            acq_datetime_utc="2026-09-15T13:30:00Z",
            satellite="T",
            instrument="MODIS",
            confidence="50",
            frp=30.0,
            daynight="D",
        )

    r1 = _rec(None, -57.5)
    errs1 = check_record(r1, settings).errors
    assert "missing_latitude" in errs1
    r2 = _rec(-25.0, None)
    assert "missing_longitude" in check_record(r2, settings).errors
    r3 = _rec(-25.0, -57.5)
    assert check_record(r3, settings).ok


def test_bom_utf8_no_rompe_el_encabezado(settings):
    text = "\ufeff" + (FIXTURES / "synthetic_empty.csv").read_text(encoding="utf-8")
    out = _parse_text(text, settings, product="VIIRS_NOAA20_NRT")
    assert out.family == "viirs"
    assert out.n_rows == 0
