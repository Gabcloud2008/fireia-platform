"""Pruebas de la API (Misión 004, etapa 12).

Monta un almacén real con fixtures (ingesta -> geo -> eventos) y consulta cada
endpoint. Verifica contratos: paginación, filtros, errores honestos (404 con
mensaje útil) y el flag de origen de datos.
"""

from __future__ import annotations

import importlib

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from hotspots.config import Settings  # noqa: E402
from hotspots.ingestion.pipeline import run_ingest  # noqa: E402

MODIS_CSV = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_t31,frp,daynight\n"
    "-25.28,-57.63,320.1,1.2,1.2,2026-09-01,1330,T,MODIS,85,6.1,300.5,40.0,D\n"
    "-25.30,-57.60,315.0,1.1,1.1,2026-09-02,1335,T,MODIS,80,6.1,298.0,35.0,D\n"
    "-22.50,-58.20,330.0,1.3,1.3,2026-09-02,1340,A,MODIS,90,6.1,305.0,55.0,N\n"
)
VIIRS_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight\n"
    "-25.281,-57.632,305.0,0.4,0.4,2026-09-01,1332,1,VIIRS,h,2,290.5,25.0,D\n"
    "-27.40,-58.00,310.0,0.4,0.4,2026-09-03,0132,2,VIIRS,h,2,295.0,15.0,N\n"
)


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("api")
    data_dir = tmp / "data"
    data_dir.mkdir()
    settings = Settings.load(env={}, env_file=None, data_dir=data_dir)

    # almacén real: ingesta de fixtures
    (tmp / "m.csv").write_text(MODIS_CSV, encoding="utf-8")
    (tmp / "v.csv").write_text(VIIRS_CSV, encoding="utf-8")
    s1 = run_ingest(settings, mode="fixture", product="MODIS_NRT", fixture_path=tmp / "m.csv")
    s2 = run_ingest(
        settings, mode="fixture", product="VIIRS_NOAA20_NRT", fixture_path=tmp / "v.csv"
    )
    assert s1.rows_valid == 3 and s2.rows_valid == 2

    # eventos sobre el almacén
    from hotspots.events.engine import build_events
    from hotspots.storage.duckdb_store import DuckDBStore

    duck = DuckDBStore(data_dir / "processed" / "hotspots.duckdb", data_dir / "processed")
    obs = duck.query(
        "SELECT obs_id, product, sensor, satellite, acq_datetime_utc, "
        "latitude, longitude, frp, confidence FROM observations"
    )
    build_events(obs, processed_root=data_dir / "processed", run_id="apitest")
    duck.refresh()

    import os

    os.environ["HOTSPOTS_DATA_DIR"] = str(data_dir)
    import hotspots.api.app as api_app

    importlib.reload(api_app)  # recarga con el data_dir del test
    with fastapi_testclient.TestClient(api_app.app) as c:
        yield c
    os.environ.pop("HOTSPOTS_DATA_DIR", None)


# ------------------------------------------------------------------ health

def test_health(cliente):
    r = cliente.get("/api/health")
    assert r.status_code == 200
    d = r.json()
    assert d["observaciones"] == 5
    assert d["observaciones_scope"] == "area_consulta"
    # sin capa geo activa en este almacén: lo nacional es indeterminado (None),
    # nunca un número que aparente saberlo
    assert d["observaciones_nacionales"] is None
    assert d["eventos"] == 1
    assert d["data_source"] == "fixture"  # honesto: se ve que es sintético
    assert d["pais"] == "Paraguay"


# ------------------------------------------------------------------ observations

def test_observations_paginado_y_filtro(cliente):
    r = cliente.get("/api/observations?limit=2")
    assert r.status_code == 200
    page = r.json()
    assert page["total"] == 5
    assert len(page["items"]) == 2
    assert page["limit"] == 2

    r2 = cliente.get("/api/observations?product=MODIS_NRT")
    assert r2.json()["total"] == 3

    r3 = cliente.get("/api/observations?date_from=2026-09-02&date_to=2026-09-02")
    assert r3.json()["total"] == 2

    r4 = cliente.get("/api/observations?order=no_existe")
    assert r4.status_code == 422


def test_observation_por_id(cliente):
    page = cliente.get("/api/observations?limit=1").json()
    oid = page["items"][0]["obs_id"]
    r = cliente.get(f"/api/observations/{oid}")
    assert r.status_code == 200
    assert r.json()["obs_id"] == oid
    assert "geometry" not in r.json()  # WKB no viaja por JSON

    r404 = cliente.get("/api/observations/innexistente")
    assert r404.status_code == 404
    assert "error" in r404.json()


# ------------------------------------------------------------------ events

def test_events(cliente):
    r = cliente.get("/api/events")
    assert r.status_code == 200
    page = r.json()
    assert page["total"] == 1
    ev = page["items"][0]
    assert ev["n_observaciones"] == 2
    assert set(ev["productos"]) == {"MODIS_NRT", "VIIRS_NOAA20_NRT"}

    detalle = cliente.get(f"/api/events/{ev['event_id']}").json()
    assert len(detalle["observaciones"]) == 2
    # el evento NO inventa perímetro: solo dispersión
    assert "dispersion_metros" in detalle


# ------------------------------------------------------------------ calendar/statistics

def test_calendar_requiere_geo(cliente):
    # sin capa geo activa: 404 honesto, no array vacío que finja contenido
    r = cliente.get("/api/calendar")
    assert r.status_code == 404
    msg = r.json()["error"]["message"]
    assert "observations_geo" in msg or "vista" in msg


def test_statistics_by_product_area_consulta(cliente):
    # scope del área de consulta: TODAS las observaciones del almacén
    r = cliente.get("/api/statistics?by=product&scope=area_consulta")
    assert r.status_code == 200
    d = r.json()
    assert d["scope"] == "area_consulta"
    assert "vecinos" in d["criterio"]
    assert {f["product"] for f in d["datos"]} == {"MODIS_NRT", "VIIRS_NOAA20_NRT"}
    total = sum(f["detecciones"] for f in d["datos"])
    assert total == 5  # incluye la detección "argentina" del fixture


def test_statistics_nacional_sin_geo_404(cliente):
    # scope nacional sin capa geo asignada: 404 honesto, no números falsos
    r = cliente.get("/api/statistics?by=product&scope=nacional")
    assert r.status_code == 404
    assert "observations_geo" in r.json()["error"]["message"]


def test_statistics_departamento_area_consulta_422(cliente):
    r = cliente.get("/api/statistics?by=departamento&scope=area_consulta")
    assert r.status_code == 422


# ------------------------------------------------------------------ quality

def test_quality(cliente):
    r = cliente.get("/api/quality")
    assert r.status_code == 200
    d = r.json()
    assert d["data_source"] == "fixture"
    assert d["manifiestos"] >= 2
    assert d["pares_candidatos"] == 1


# ------------------------------------------------------------------ geo

def test_geo_sin_capa_404_honrado(cliente):
    r = cliente.get("/api/geo/departamentos")
    assert r.status_code == 404  # no se exportó la capa: honesto
    r2 = cliente.get("/api/geo/units?nivel=1")
    assert r2.status_code == 404


# ------------------------------------------------------------------ anomalías

def test_anomalies_sin_geo_404(cliente):
    # sin asignación territorial no hay serie nacional: 404 honesto
    r = cliente.get(
        "/api/anomalies?date_from=2026-09-02&date_to=2026-09-03&z=3.0"
    )
    assert r.status_code == 404
    # 404 honesto del guard de vistas: sin capa geo no hay serie nacional
    assert "observations_geo" in r.json()["error"]["message"]


def test_dashboard_html(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert "Paraguay Fire Intelligence" in r.text
    assert "DATOS SINTÉTICOS" in r.text  # el aviso existe en la UI
