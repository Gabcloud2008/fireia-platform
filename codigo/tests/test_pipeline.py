"""Pruebas del pipeline de ingesta (offline: fixtures y dry-run)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hotspots.config import Settings
from hotspots.ingestion.firms import CredentialsError
from hotspots.ingestion.pipeline import PipelineBlocked, run_ingest
from hotspots.normalization.firms_csv import parse_firms_csv
from tests.conftest import FIXTURES, FakeTransport


def test_ingesta_fixture_end_to_end(settings):
    s = run_ingest(
        settings,
        mode="fixture",
        product="MODIS_NRT",
        fixture_path=FIXTURES / "synthetic_modis_nrt.csv",
        date="2026-09-15",
    )
    assert s.state == "success_with_detections"
    assert s.rows_raw == 12 and s.rows_valid == 12 and s.rows_quarantined == 0
    # artefactos reales en disco
    assert s.raw_path and Path(s.raw_path).exists()
    assert s.manifest_path and Path(s.manifest_path).exists()
    assert s.parquet_path and Path(s.parquet_path).exists()
    # el manifiesto referencia el RAW con hash correcto
    mf = json.loads(Path(s.manifest_path).read_text(encoding="utf-8"))
    raw_art = [a for a in mf["artifacts"] if a["role"] == "raw_csv"][0]
    assert raw_art["sha256"] == s.raw_sha256
    assert Path(raw_art["path"]).name == f"{s.raw_sha256}.csv"


def test_idempotencia_doble_ingesta(settings):
    kw = dict(
        mode="fixture",
        product="MODIS_NRT",
        fixture_path=FIXTURES / "synthetic_modis_nrt.csv",
        date="2026-09-15",
    )
    s1 = run_ingest(settings, **kw)
    s2 = run_ingest(settings, **kw)
    assert s1.state == "success_with_detections"
    assert s2.state == "skipped_already_ingested"
    # no se duplicó el RAW
    raws = list((settings.data_dir / "raw").rglob("*.csv"))
    assert len(raws) == 1
    # los conteos quedan iguales
    from hotspots.storage.duckdb_store import DuckDBStore

    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb",
        settings.data_dir / "processed",
    )
    assert duck.observation_count() == 12


def test_ingesta_fixture_con_cuarentena(settings):
    s = run_ingest(
        settings,
        mode="fixture",
        product="MODIS_NRT",
        fixture_path=FIXTURES / "synthetic_invalid_rows.csv",
        date="2026-09-15",
    )
    assert s.state == "success_with_detections"
    assert s.rows_raw == 8 and s.rows_valid == 1 and s.rows_quarantined == 7
    assert s.quarantine_path is not None


def test_ingesta_fixture_vacio_valido(settings):
    s = run_ingest(
        settings,
        mode="fixture",
        product="VIIRS_NOAA20_NRT",
        fixture_path=FIXTURES / "synthetic_empty.csv",
        date="2026-09-15",
    )
    # consulta exitosa sin detecciones: estado válido, NO es un error
    assert s.state == "success_no_detections"
    assert s.rows_raw == 0
    assert s.parquet_path is None  # nada que escribir


def test_ingesta_fixture_error_de_parseo(settings):
    s = run_ingest(
        settings,
        mode="fixture",
        product="MODIS_NRT",
        fixture_path=FIXTURES / "synthetic_wrong_columns.csv",
        date="2026-09-15",
    )
    assert s.state == "parse_failed"
    # la evidencia del fallo queda en RAW y manifiesto
    assert s.raw_path is not None
    assert s.manifest_path is not None


def test_dry_run_no_escribe_nada(settings):
    s = run_ingest(
        settings,
        mode="api",
        product="VIIRS_NOAA21_NRT",
        date="2026-09-15",
        day_range=2,
        dry_run=True,
    )
    assert s.state == "dry_run"
    assert s.planned_requests == 1
    assert "{MAP_KEY}" in s.planned_url  # URL redactada
    assert "VIIRS_NOAA21_NRT" in s.planned_url
    assert "-62.7,-27.6,-54.2,-19.3" in s.planned_url
    # no se creó ningún archivo
    assert not any(settings.data_dir.rglob("*")) if settings.data_dir.exists() else True


def test_dry_run_day_range_invalido(settings):
    with pytest.raises(ValueError, match="DAY_RANGE"):
        run_ingest(settings, mode="api", product="MODIS_NRT", day_range=9, dry_run=True)


def test_api_bloqueada_sin_allow_network(settings):
    with pytest.raises(PipelineBlocked, match="allow-network"):
        run_ingest(settings, mode="api", product="MODIS_NRT", dry_run=False)


def test_api_bloqueada_sin_credencial(settings):
    with pytest.raises(CredentialsError, match="FIRMS_MAP_KEY"):
        run_ingest(settings, mode="api", product="MODIS_NRT", allow_network=True)


def test_api_con_transport_falso_flujo_completo(settings, monkeypatch):
    """Simulación offline del flujo real: transport falso inyectado."""
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None)
    body = (FIXTURES / "synthetic_viirs_noaa20_nrt.csv").read_text(encoding="utf-8")
    transport = FakeTransport([(200, body)])
    s = run_ingest(
        s2,
        mode="api",
        product="VIIRS_NOAA20_NRT",
        date="2026-09-15",
        allow_network=True,
        transport=transport,
    )
    assert s.state == "success_with_detections"
    assert s.rows_valid == 8
    assert "KEY-TEST-999" not in (s.planned_url or "")
    # segunda corrida con la misma petición exacta: idempotente
    s_bis = run_ingest(
        s2,
        mode="api",
        product="VIIRS_NOAA20_NRT",
        date="2026-09-15",
        allow_network=True,
        transport=FakeTransport(),
    )
    assert s_bis.state == "skipped_already_ingested"


def test_api_error_autenticacion(settings, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None)
    transport = FakeTransport([(401, "Unauthorized")])
    s = run_ingest(
        s2,
        mode="api",
        product="MODIS_NRT",
        date="2026-09-15",
        allow_network=True,
        transport=transport,
    )
    assert s.state == "authentication_failed"
    assert s.parquet_path is None


# ============================================ contrato de manifiestos fallidos (M009)
def test_api_fallo_transporte_sin_artefacto_vacio(settings, monkeypatch):
    """Fallo de transporte (sin respuesta HTTP): el manifiesto declara el error
    explícitamente y NO fabrica un artefacto RAW vacío (Misión 009, §6)."""
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None)
    s = run_ingest(
        s2,
        mode="api",
        product="MODIS_NRT",
        date="2026-11-04",
        day_range=5,
        allow_network=True,
        transport=FakeTransport(),  # sin respuestas programadas: fallo de transporte
    )
    assert s.state == "download_failed"
    assert s.raw_path is None
    assert s.manifest_path and Path(s.manifest_path).exists()
    mf = json.loads(Path(s.manifest_path).read_text(encoding="utf-8"))
    assert mf["result_state"] == "download_failed"
    assert mf["processing_state"] == "failed"
    assert any(n.startswith("error=") for n in mf["notes"])
    assert any("no_hubo_cuerpo_de_respuesta" in n for n in mf["notes"])
    assert mf["artifacts"] == []


def test_api_fallo_http_conserva_cuerpo_real(settings, monkeypatch):
    """Fallo HTTP con cuerpo real (5xx): el cuerpo SÍ se conserva byte-exacto
    como evidencia raw_response."""
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None)
    s = run_ingest(
        s2,
        mode="api",
        product="MODIS_NRT",
        date="2026-11-04",
        allow_network=True,
        transport=FakeTransport([(500, "Internal Server Error")]),
    )
    assert s.state == "download_failed"
    assert s.raw_path is not None and Path(s.raw_path).exists()
    mf = json.loads(Path(s.manifest_path).read_text(encoding="utf-8"))
    assert any(n == "status=500" for n in mf["notes"])
    assert any(n == "raw_bytes=21" for n in mf["notes"])
    assert mf["artifacts"] and mf["artifacts"][0]["size"] == 21


def test_api_acquisition_period_cubre_day_range(settings, monkeypatch):
    """El manifiesto registra el período solicitado COMPLETO (date + day_range),
    no solo el día inicial (Misión 009: contrato §6 'período de adquisición')."""
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None)
    header = (FIXTURES / "synthetic_empty.csv").read_text(encoding="utf-8")
    s = run_ingest(
        s2,
        mode="api",
        product="MODIS_NRT",
        date="2026-11-04",
        day_range=5,
        allow_network=True,
        transport=FakeTransport([(200, header)]),
    )
    mf = json.loads(Path(s.manifest_path).read_text(encoding="utf-8"))
    assert mf["acquisition_period"] == {"from": "2026-11-04", "to": "2026-11-08"}


def test_api_respuesta_vacia_valida(settings, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None)
    header = (FIXTURES / "synthetic_empty.csv").read_text(encoding="utf-8")
    transport = FakeTransport([(200, header)])
    s = run_ingest(
        s2,
        mode="api",
        product="VIIRS_NOAA21_NRT",
        date="2026-09-15",
        allow_network=True,
        transport=transport,
    )
    # sin detecciones NO es error: distinción central del QC
    assert s.state == "success_no_detections"


# ============================================================== corrección A
def test_pipeline_coords_ausentes_no_contaminan_vista_valida(settings):
    """La fila sin coordenadas va a cuarentena; la vista válida queda limpia."""
    from hotspots.storage.duckdb_store import DuckDBStore

    s = run_ingest(
        settings,
        mode="fixture",
        product="MODIS_NRT",
        fixture_path=FIXTURES / "synthetic_missing_coords.csv",
        date="2026-09-15",
    )
    assert s.state == "success_with_detections"
    assert s.rows_raw == 4 and s.rows_valid == 1 and s.rows_quarantined == 3
    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb", settings.data_dir / "processed"
    )
    filas = duck.query("SELECT latitude, longitude FROM observations")
    assert len(filas) == 1
    assert filas[0]["latitude"] == -25.0 and filas[0]["longitude"] == -57.5
    # jamás aparece un punto (0,0) fabricado
    assert not any(r["latitude"] == 0.0 or r["longitude"] == 0.0 for r in filas)
    # la cuarentena conserva las 3 filas con sus motivos exactos
    q = duck.query("SELECT errors FROM quarantine")
    assert len(q) == 3
    # errors viaja como VARCHAR[] desde Parquet: aplanar a strings
    todos = " | ".join(
        e if isinstance(e, str) else " ".join(e) for e in (r["errors"] for r in q)
    )
    assert "missing_latitude" in todos and "missing_longitude" in todos


# ============================================================== corrección B
def test_api_cuerpo_vacio_es_unknown_no_success(settings, monkeypatch):
    """HTTP 200 + cuerpo vacío: anómalo e indeterminado, NO 'sin detecciones'."""
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None, data_dir=settings.data_dir)
    transport = FakeTransport([(200, "")])
    s = run_ingest(
        s2,
        mode="api",
        product="VIIRS_NOAA21_NRT",
        date="2026-09-15",
        allow_network=True,
        transport=transport,
    )
    assert s.state == "unknown"
    assert s.rows_raw == 0 and s.parquet_path is None
    # M011-C §3: un cuerpo vacío NO fabrica artefacto RAW vacío (la
    # anomalía se declara en el manifiesto; el hash e3b0c442... colisionaría
    # para TODAS las respuestas vacías).
    assert s.raw_path is None and s.raw_sha256 is None
    import json as _json
    from pathlib import Path as _Path

    mf = _json.loads(_Path(s.manifest_path).read_text(encoding="utf-8"))
    assert mf["artifacts"] == []
    assert any("cuerpo_vacio_anomalo" in n for n in mf["notes"])


def test_api_cuerpo_vacio_permite_reintento(settings, monkeypatch):
    """unknown NO salta la idempotencia: la misma petición se reintenta."""
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None, data_dir=settings.data_dir)
    kw = dict(
        mode="api",
        product="VIIRS_NOAA21_NRT",
        date="2026-09-15",
        allow_network=True,
    )
    s1 = run_ingest(s2, transport=FakeTransport([(200, "")]), **kw)
    assert s1.state == "unknown"
    s2nd = run_ingest(s2, transport=FakeTransport([(200, "latitude,longitude\n")]), **kw)
    assert s2nd.state != "skipped_already_ingested"


def test_api_exito_es_idempotente(settings, monkeypatch):
    """Idempotencia del orquestador (M011-C §5): la MISMA petición exitosa
    NO se repite en un relanzamiento del piloto (salto por request_key)."""
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None, data_dir=settings.data_dir)
    kw = dict(
        mode="api",
        product="VIIRS_NOAA21_NRT",
        date="2026-09-16",
        allow_network=True,
    )
    csv_ok = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_ti5,frp,daynight\n"
        "-23.9,-57.8,340.1,0.9,0.8,2026-09-16,1331,2,VIIRS,n,2.0,298.7,18.3,D\n"
    )
    s1 = run_ingest(s2, transport=FakeTransport([(200, csv_ok)]), **kw)
    assert s1.state == "success_with_detections"
    s2nd = run_ingest(s2, transport=FakeTransport([(200, csv_ok)]), **kw)
    assert s2nd.state == "skipped_already_ingested"


def test_api_html_es_parse_failed_con_razon_explicita(settings, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None, data_dir=settings.data_dir)
    html = (FIXTURES / "synthetic_html_response.html").read_text(encoding="utf-8")
    s = run_ingest(
        s2,
        mode="api",
        product="MODIS_NRT",
        date="2026-09-15",
        allow_network=True,
        transport=FakeTransport([(200, html)]),
    )
    assert s.state == "parse_failed"
    from hotspots.storage.duckdb_store import DuckDBStore

    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb", settings.data_dir / "processed"
    )
    razones = duck.query("SELECT reason FROM ingest_status")
    assert any("html_body" in r["reason"] for r in razones)


def test_api_json_es_parse_failed(settings, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None, data_dir=settings.data_dir)
    js = (FIXTURES / "synthetic_json_response.json").read_text(encoding="utf-8")
    s = run_ingest(
        s2,
        mode="api",
        product="MODIS_NRT",
        date="2026-09-15",
        allow_network=True,
        transport=FakeTransport([(200, js)]),
    )
    assert s.state == "parse_failed"


def test_api_texto_de_proveedor_no_csv_es_parse_failed(settings, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None, data_dir=settings.data_dir)
    s = run_ingest(
        s2,
        mode="api",
        product="MODIS_NRT",
        date="2026-09-15",
        allow_network=True,
        transport=FakeTransport([(200, "some unexpected provider text")]),
    )
    assert s.state == "parse_failed"


def test_api_csv_valido_con_detecciones_sigue_funcionando(settings, monkeypatch):
    """La corrección B no rompe el camino feliz: CSV con filas => success."""
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None, data_dir=settings.data_dir)
    body = (FIXTURES / "synthetic_viirs_noaa20_nrt.csv").read_text(encoding="utf-8")
    s = run_ingest(
        s2,
        mode="api",
        product="VIIRS_NOAA20_NRT",
        date="2026-09-15",
        allow_network=True,
        transport=FakeTransport([(200, body)]),
    )
    assert s.state == "success_with_detections"
    assert s.rows_valid == 8


def test_api_mensaje_error_firms_es_authentication_failed(settings, monkeypatch):
    """El texto de error clásico de FIRMS sigue clasificándose como auth (200)."""
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY-TEST-999")
    s2 = Settings.load(env_file=None, data_dir=settings.data_dir)
    s = run_ingest(
        s2,
        mode="api",
        product="MODIS_NRT",
        date="2026-09-15",
        allow_network=True,
        transport=FakeTransport([(200, "Invalid MAP_KEY: not authorized")]),
    )
    assert s.state == "authentication_failed"


# ============================================================== corrección C
def test_todas_las_filas_en_cuarentena_es_success_all_quarantined(settings):
    """CSV parseable con todas las filas rechazadas por QC ≠ parse_failed."""
    s = run_ingest(
        settings,
        mode="fixture",
        product="MODIS_NRT",
        fixture_path=FIXTURES / "synthetic_all_quarantined.csv",
        date="2026-09-15",
    )
    assert s.state == "success_all_quarantined"
    assert s.rows_raw == 3 and s.rows_valid == 0 and s.rows_quarantined == 3
    assert s.quarantine_path is not None  # la evidencia QC queda preservada
    # conteos coherentes en el manifiesto
    import json as _json
    from pathlib import Path as _Path

    mf = _json.loads(_Path(s.manifest_path).read_text(encoding="utf-8"))
    assert mf["counts"] == {"rows_raw": 3, "rows_valid": 0, "rows_quarantined": 3}
    assert mf["processing_state"] == "completed"  # procesado de punta a punta


def test_success_all_quarantined_es_idempotente(settings):
    kw = dict(
        mode="fixture",
        product="MODIS_NRT",
        fixture_path=FIXTURES / "synthetic_all_quarantined.csv",
        date="2026-09-15",
    )
    s1 = run_ingest(settings, **kw)
    assert s1.state == "success_all_quarantined"
    s2 = run_ingest(settings, **kw)
    assert s2.state == "skipped_already_ingested"


def test_parse_error_deja_un_solo_registro_de_estado(settings):
    """Corrección E1: antes un parse_failed en fixture duplicaba el registro."""
    from hotspots.storage.duckdb_store import DuckDBStore

    run_ingest(
        settings,
        mode="fixture",
        product="MODIS_NRT",
        fixture_path=FIXTURES / "synthetic_wrong_columns.csv",
        date="2026-09-15",
    )
    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb", settings.data_dir / "processed"
    )
    regs = duck.query("SELECT * FROM ingest_status WHERE state = 'parse_failed'")
    assert len(regs) == 1  # antes eran 2


def test_fixture_vacio_de_cero_bytes_es_unknown(settings, tmp_path):
    """Un fixture de 0 bytes es anómalo (no 'sin detecciones'): consistencia B.

    M011-C §3: además, NO se fabrica un artefacto RAW vacío.
    """
    f = tmp_path / "vacio.csv"
    f.write_bytes(b"")
    s = run_ingest(
        settings, mode="fixture", product="MODIS_NRT", fixture_path=f, date="2026-09-15"
    )
    assert s.state == "unknown"
    assert s.raw_path is None
    import json as _json
    from pathlib import Path as _Path

    mf = _json.loads(_Path(s.manifest_path).read_text(encoding="utf-8"))
    assert any("cuerpo_vacio_anomalo" in n for n in mf["notes"])


# ============================================================== corrección D
def test_products_distintos_ids_distintos_y_par_candidato(settings, tmp_path):
    """Mismo fuego visto por MODIS y VIIRS: identidades separadas + relación."""
    from hotspots.storage.duckdb_store import DuckDBStore
    from hotspots.storage.parquet_store import ParquetStore

    modis_csv = (
        "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_t31,frp,daynight\n"
        "-23.4000,-58.1000,330.0,1.0,1.0,2026-09-15,1330,T,MODIS,80,6.03,296.0,45.0,D\n"
    )
    viirs_csv = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_ti5,frp,daynight\n"
        "-23.4010,-58.1005,341.0,0.9,0.8,2026-09-15,1332,NOAA-20,VIIRS,h,2.0,298.0,38.0,D\n"
    )
    pq_store = ParquetStore(tmp_path)
    duck = DuckDBStore(tmp_path / "h.duckdb", tmp_path)
    for text, product in ((modis_csv, "MODIS_NRT"), (viirs_csv, "VIIRS_NOAA20_NRT")):
        out = parse_firms_csv(
            text,
            product=product,
            settings=settings,
            run_id="r",
            manifest_id="m",
            ingested_at_utc="2026-11-11T00:00:00Z",
        )
        pq_store.append_observations(out.records, product=product, year="2026", run_id="r")
    duck.refresh()

    # identidades separadas: obs_id distintos para el mismo fenómeno
    filas = duck.query(
        "SELECT obs_id, product, sensor FROM observations ORDER BY product"
    )
    assert len(filas) == 2
    assert filas[0]["obs_id"] != filas[1]["obs_id"]
    assert {f["product"] for f in filas} == {"MODIS_NRT", "VIIRS_NOAA20_NRT"}

    # y la relación candidata existe con métricas coherentes
    pares = duck.candidate_matches()
    assert len(pares) == 1
    par = pares[0]
    assert par["dt_seconds"] <= 600
    assert par["distance_m"] < 300  # ~130 m entre ambos puntos
    assert {par["product_a"], par["product_b"]} == {"MODIS_NRT", "VIIRS_NOAA20_NRT"}


def test_candidate_matches_respeta_ventanas(settings, tmp_path):
    """Fuera de la ventana temporal o espacial NO hay par candidato."""
    from hotspots.storage.duckdb_store import DuckDBStore
    from hotspots.storage.parquet_store import ParquetStore

    modis_csv = (
        "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_t31,frp,daynight\n"
        "-23.4000,-58.1000,330.0,1.0,1.0,2026-09-15,1330,T,MODIS,80,6.03,296.0,45.0,D\n"
    )
    viirs_lejano_tiempo = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_ti5,frp,daynight\n"
        "-23.4010,-58.1005,341.0,0.9,0.8,2026-09-15,1500,NOAA-20,VIIRS,h,2.0,298.0,38.0,D\n"
    )
    viirs_lejano_espacio = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_ti5,frp,daynight\n"
        "-24.5000,-58.1005,341.0,0.9,0.8,2026-09-15,1332,NOAA-20,VIIRS,h,2.0,298.0,38.0,D\n"
    )
    pq_store = ParquetStore(tmp_path)
    duck = DuckDBStore(tmp_path / "h.duckdb", tmp_path)
    for text, product, run in (
        (modis_csv, "MODIS_NRT", "r1"),
        (viirs_lejano_tiempo, "VIIRS_NOAA20_NRT", "r2"),
        (viirs_lejano_espacio, "VIIRS_NOAA20_NRT", "r3"),
    ):
        out = parse_firms_csv(
            text,
            product=product,
            settings=settings,
            run_id=run,
            manifest_id="m",
            ingested_at_utc="2026-11-11T00:00:00Z",
        )
        pq_store.append_observations(out.records, product=product, year="2026", run_id=run)
    duck.refresh()
    assert duck.observation_count() == 3
    assert duck.candidate_matches() == []  # ni por tiempo (90 min) ni por espacio (~120 km)


def test_filas_duplicadas_dentro_de_un_mismo_producto_colapsan(settings, tmp_path):
    """Duplicados exactos dentro de un archivo: observations_raw 2N, observations N."""
    from hotspots.storage.duckdb_store import DuckDBStore
    from hotspots.storage.parquet_store import ParquetStore

    fila = "-23.4000,-58.1000,330.0,1.0,1.0,2026-09-15,1330,T,MODIS,80,6.03,296.0,45.0,D\n"
    modis_csv = (
        "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_t31,frp,daynight\n" + fila + fila
    )
    out = parse_firms_csv(
        modis_csv,
        product="MODIS_NRT",
        settings=settings,
        run_id="r",
        manifest_id="m",
        ingested_at_utc="2026-11-11T00:00:00Z",
    )
    pq_store = ParquetStore(tmp_path)
    duck = DuckDBStore(tmp_path / "h.duckdb", tmp_path)
    pq_store.append_observations(out.records, product="MODIS_NRT", year="2026", run_id="r")
    duck.refresh()
    assert duck.observation_count() == 1  # dedup por obs_id determinista
    assert duck.query("SELECT count(*) AS n FROM observations_raw")[0]["n"] == 2


# ============================================================== verify (F7)
def test_verify_detecta_artefacto_corrupto(settings):
    from hotspots.cli.app import main as cli_main

    data = settings.data_dir
    s = run_ingest(
        settings,
        mode="fixture",
        product="MODIS_NRT",
        fixture_path=FIXTURES / "synthetic_modis_nrt.csv",
        date="2026-09-15",
    )
    assert s.state == "success_with_detections"
    # 1) verificación limpia
    rc = cli_main(["verify", "--data-dir", str(data)])
    assert rc == 0
    # 2) corromper un artefacto parquet (escribible: chmod temporal)
    p = Path(s.parquet_path)
    os.chmod(p, 0o644)
    p.write_bytes(b"corrupto")
    rc = cli_main(["verify", "--data-dir", str(data)])
    assert rc == 1


def test_verify_detecta_artefacto_ausente(settings):
    from hotspots.cli.app import main as cli_main

    s = run_ingest(
        settings,
        mode="fixture",
        product="MODIS_NRT",
        fixture_path=FIXTURES / "synthetic_modis_nrt.csv",
        date="2026-09-15",
    )
    os.chmod(Path(s.parquet_path), 0o644)
    Path(s.parquet_path).unlink()
    rc = cli_main(["verify", "--data-dir", str(settings.data_dir)])
    assert rc == 1
