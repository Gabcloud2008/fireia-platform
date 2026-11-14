"""Pruebas del motor analítico DuckDB: vistas y deduplicación idempotente."""

from __future__ import annotations

from hotspots.normalization.firms_csv import parse_firms_csv
from hotspots.storage.duckdb_store import DuckDBStore
from hotspots.storage.parquet_store import ParquetStore
from tests.conftest import FIXTURES


def _records(settings, fixture="synthetic_modis_nrt.csv", product="MODIS_NRT"):
    return parse_firms_csv(
        (FIXTURES / fixture).read_text(encoding="utf-8"),
        product=product,
        settings=settings,
        run_id="r",
        manifest_id="m",
        ingested_at_utc="2026-11-11T00:00:00Z",
    ).records


def test_vacio_sin_archivos(settings, tmp_path):
    duck = DuckDBStore(tmp_path / "hotspots.duckdb", tmp_path)
    duck.refresh()
    assert duck.observation_count() == 0
    assert duck.counts_by_product() == []
    assert duck.quarantine_count() == 0


def test_conteos_por_producto(settings, tmp_path):
    pq_store = ParquetStore(tmp_path)
    duck = DuckDBStore(tmp_path / "hotspots.duckdb", tmp_path)
    pq_store.append_observations(
        _records(settings), product="MODIS_NRT", year="2026", run_id="run-1"
    )
    pq_store.append_observations(
        _records(settings, "synthetic_viirs_noaa20_nrt.csv", "VIIRS_NOAA20_NRT"),
        product="VIIRS_NOAA20_NRT",
        year="2026",
        run_id="run-2",
    )
    duck.refresh()
    por_producto = {row["product"]: row["n"] for row in duck.counts_by_product()}
    assert por_producto == {"MODIS_NRT": 12, "VIIRS_NOAA20_NRT": 8}
    assert duck.observation_count() == 20


def test_deduplicacion_por_obs_id(settings, tmp_path):
    """Re-ingestar los mismos registros NO infla conteos (idempotencia)."""
    pq_store = ParquetStore(tmp_path)
    duck = DuckDBStore(tmp_path / "hotspots.duckdb", tmp_path)
    recs = _records(settings)
    pq_store.append_observations(recs, product="MODIS_NRT", year="2026", run_id="run-1")
    pq_store.append_observations(recs, product="MODIS_NRT", year="2026", run_id="run-2")
    pq_store.append_observations(recs, product="MODIS_NRT", year="2026", run_id="run-3")
    duck.refresh()
    assert duck.observation_count() == 12  # no 36
    # la vista sin deduplicar documenta las corridas
    raw = duck.query("SELECT count(*) AS n FROM observations_raw")
    assert raw[0]["n"] == 36


def test_consulta_por_satelite(settings, tmp_path):
    pq_store = ParquetStore(tmp_path)
    duck = DuckDBStore(tmp_path / "hotspots.duckdb", tmp_path)
    pq_store.append_observations(
        _records(settings), product="MODIS_NRT", year="2026", run_id="run-1"
    )
    duck.refresh()
    rows = duck.query(
        "SELECT satellite_name, count(*) AS n FROM observations "
        "WHERE product = 'MODIS_NRT' GROUP BY satellite_name ORDER BY n DESC"
    )
    nombres = {r["satellite_name"] for r in rows}
    assert nombres == {"Terra", "Aqua"}


def test_columnas_de_sensor_se_conservan(settings, tmp_path):
    """La vista nunca funde MODIS y VIIRS: sensor/satélite/producto siempre presentes."""
    pq_store = ParquetStore(tmp_path)
    duck = DuckDBStore(tmp_path / "hotspots.duckdb", tmp_path)
    pq_store.append_observations(
        _records(settings), product="MODIS_NRT", year="2026", run_id="run-1"
    )
    duck.refresh()
    cols = {
        r["column_name"]
        for r in duck.query(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'observations'"
        )
    }
    for obligatoria in (
        "sensor",
        "satellite",
        "satellite_name",
        "instrument",
        "product",
        "confidence",
        "confidence_band",
        "frp",
        "brightness",
        "bright_ti4",
        "obs_id",
        "manifest_id",
        "quality_flags",
        "geometry",
    ):
        assert obligatoria in cols, f"falta columna {obligatoria}"
