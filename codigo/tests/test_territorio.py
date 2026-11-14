"""Pruebas de integridad territorial (Misión 005).

Qué impiden estas pruebas:

- Que observaciones de Argentina/Brasil/Bolivia que caen dentro del
  rectángulo de consulta terminen contadas como nacionales.
- Que el bbox de consulta se use como frontera (no lo es: es un rectángulo
  de pedido a FIRMS).
- Que "día sin detecciones" se confunda con "día sin datos".
- Que las reparaciones de geometrías (make_valid) se cuenten DESPUÉS de
  reparar (bug de la Misión 004: el conteo vivía en 0).
- Que una versión de límites sin procedencia fichada pase en silencio.

País sintético en coordenadas REALES alrededor de Asunción, para que las
observaciones de países vecinos caigan dentro del bbox de consulta real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from hotspots.config import Settings  # noqa: E402
from hotspots.geo.assign import assign_observations  # noqa: E402
from hotspots.geo.boundaries import BoundarySet  # noqa: E402
from hotspots.ingestion.pipeline import run_ingest  # noqa: E402
from hotspots.storage.duckdb_store import DuckDBStore  # noqa: E402

VER = "test-territorio-v1"

# ------------------------------------------------------------------ país sintético


def _poly(coords):
    return {"type": "Polygon", "coordinates": [coords]}


_CUADRADO = [[-58.0, -26.0], [-57.0, -26.0], [-57.0, -25.0], [-58.0, -25.0], [-58.0, -26.0]]
_ASUNCION = [[-57.8, -25.5], [-57.2, -25.5], [-57.2, -25.0], [-57.8, -25.0], [-57.8, -25.5]]


def _feature(name, geom, shape_id):
    return {
        "type": "Feature",
        "properties": {"shapeName": name, "shapeID": shape_id},
        "geometry": geom,
    }


@pytest.fixture()
def pais_asuncion(tmp_path: Path) -> dict:
    """'País' sintético: cuadrado -58.0..-57.0 / -26.0..-25.0 (Asunción y alrededores)."""
    adm0 = {
        "type": "FeatureCollection",
        "features": [
            _feature("PAIS TEST", _poly(_CUADRADO), "T-0"),
        ],
    }
    adm1 = {
        "type": "FeatureCollection",
        "features": [
            _feature("CENTRAL TEST", _poly(_CUADRADO), "T-1"),
        ],
    }
    adm2 = {
        "type": "FeatureCollection",
        "features": [
            _feature(
                "ASUNCION TEST",
                _poly(_ASUNCION),
                "T-2",
            ),
        ],
    }
    out = {}
    for lvl, data in (("ADM0", adm0), ("ADM1", adm1), ("ADM2", adm2)):
        p = tmp_path / f"PRY-{lvl}.geojson"
        p.write_text(json.dumps(data), encoding="utf-8")
        out[lvl] = p
    return out


# ------------------------------------------------------------------ almacén territorial

# 2 detecciones dentro del país sintético + 1 Argentina + 1 Brasil + 1 Bolivia
# (las tres DENTRO del bbox de consulta real) + 1 Buenos Aires (FUERA del bbox:
# flag soft outside_query_bbox, fila igualmente válida).
MODIS_CSV = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_t31,frp,daynight\n"
    "-25.28,-57.63,320.1,1.2,1.2,2026-09-01,1330,T,MODIS,85,6.1,300.5,40.0,D\n"
    "-25.30,-57.60,315.0,1.1,1.1,2026-09-02,1335,T,MODIS,80,6.1,298.0,35.0,D\n"
    "-27.40,-58.00,330.0,1.3,1.3,2026-09-02,1340,T,MODIS,90,6.1,305.0,55.0,N\n"
)
VIIRS_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight\n"
    "-25.281,-57.632,305.0,0.4,0.4,2026-09-01,1332,1,VIIRS,h,2,290.5,25.0,D\n"
    "-20.50,-56.20,310.0,0.4,0.4,2026-09-02,0132,1,VIIRS,h,2,295.0,15.0,N\n"
    "-60.50,-20.80,311.0,0.4,0.4,2026-09-03,0135,1,VIIRS,h,2,295.0,11.0,N\n"
    "-34.60,-58.44,312.0,0.4,0.4,2026-09-03,0140,1,VIIRS,h,2,295.0,9.0,N\n"
)


@pytest.fixture(scope="module")
def almacen_territorial(tmp_path_factory):
    """Almacén real: ingesta + geo assign contra el país sintético."""
    tmp = tmp_path_factory.mktemp("terr")
    data_dir = tmp / "data"
    data_dir.mkdir()
    settings = Settings.load(env={}, env_file=None, data_dir=data_dir)

    (tmp / "m.csv").write_text(MODIS_CSV, encoding="utf-8")
    (tmp / "v.csv").write_text(VIIRS_CSV, encoding="utf-8")
    s1 = run_ingest(settings, mode="fixture", product="MODIS_NRT", fixture_path=tmp / "m.csv")
    s2 = run_ingest(
        settings, mode="fixture", product="VIIRS_NOAA20_NRT", fixture_path=tmp / "v.csv"
    )
    assert s1.rows_valid == 3 and s2.rows_valid == 4

    # país sintético en coords reales (mismo polígono que la fixture
    # pais_asuncion, pero en el tmp de ESTE módulo)
    pais = {}
    cuadrado = [[-58.0, -26.0], [-57.0, -26.0], [-57.0, -25.0], [-58.0, -25.0], [-58.0, -26.0]]
    for lvl, nombre, sid in (
        ("ADM0", "PAIS TEST", "T-0"),
        ("ADM1", "CENTRAL TEST", "T-1"),
        ("ADM2", "ASUNCION TEST", "T-2"),
    ):
        data = {
            "type": "FeatureCollection",
            "features": [_feature(nombre, _poly(cuadrado), sid)],
        }
        p = tmp / f"PRY-{lvl}.geojson"
        p.write_text(json.dumps(data), encoding="utf-8")
        pais[lvl] = p

    bs = BoundarySet.from_geojson_files(VER, pais["ADM0"], pais["ADM1"], pais["ADM2"])
    pq_path = bs.to_parquet(tmp / "unidades_admin.parquet")

    duck = DuckDBStore(data_dir / "processed" / "hotspots.duckdb", data_dir / "processed")
    obs = duck.query("SELECT obs_id, longitude, latitude FROM observations")
    summary = assign_observations(
        bs,
        obs,
        version=VER,
        run_id="geotest",
        processed_root=data_dir / "processed",
        assigned_at_utc="2026-01-01T00:00:00Z",
    )
    # 3 nacionales (2 MODIS Asunción + 1 VIIRS Asunción) + 4 vecinas
    assert summary.dentro_pais == 3
    assert summary.fuera_pais == 4
    duck.refresh(geo_version=VER, boundaries_parquet=pq_path)

    import os

    os.environ["HOTSPOTS_DATA_DIR"] = str(data_dir)
    import importlib

    import hotspots.api.app as api_app

    importlib.reload(api_app)
    with fastapi_testclient.TestClient(api_app.app) as c:
        yield c, duck, data_dir
    os.environ.pop("HOTSPOTS_DATA_DIR", None)


# ------------------------------------------------------------------ scope territorial


def test_vecinos_no_contaminan_estadisticas_nacionales(almacen_territorial):
    """La prueba central de la Misión 005, §5: el mismo endpoint, dos scopes."""
    cliente, duck, _ = almacen_territorial

    r = cliente.get("/api/statistics?by=product&scope=nacional")
    assert r.status_code == 200
    d = r.json()
    assert d["scope"] == "nacional"
    total_nac = sum(f["detecciones"] for f in d["datos"])
    assert total_nac == 3  # SOLO las detecciones de Asunción

    r2 = cliente.get("/api/statistics?by=product&scope=area_consulta")
    assert r2.status_code == 200
    d2 = r2.json()
    total_area = sum(f["detecciones"] for f in d2["datos"])
    # 3 MODIS + 4 VIIRS = 7: todas las filas válidas del almacén, incluidas
    # las 4 de Argentina/Brasil/Bolivia/Buenos Aires
    assert total_area == 7
    assert total_area > total_nac


def test_health_distingue_nacional_de_area_consulta(almacen_territorial):
    cliente, duck, _ = almacen_territorial
    d = cliente.get("/api/health").json()
    assert d["observaciones"] == 7  # área de consulta
    assert d["observaciones_nacionales"] == 3  # dentro del polígono ADM0
    assert d["observaciones_scope"] == "area_consulta"


def test_calendar_es_nacional(almacen_territorial):
    cliente, duck, _ = almacen_territorial
    r = cliente.get("/api/calendar?granularity=dia")
    assert r.status_code == 200
    d = r.json()
    assert d["scope"] == "nacional"
    assert "dentro_pais" in d["criterio"]
    total = sum(x["detecciones"] for x in d["datos"])
    assert total == 3  # las 4 detecciones vecinas NO entran al calendario


def test_coverage_estados(almacen_territorial):
    cliente, duck, _ = almacen_territorial
    r = cliente.get("/api/coverage")
    assert r.status_code == 200
    d = r.json()
    assert set(d["resumen"]) == {
        "con_detecciones",
        "cero_detecciones_asumido",
        "solo_rechazadas_qc",
        "sin_datos",
    }
    # 2026-09-01 y 09-02 y 09-03 con detecciones; el fixture no deja días
    # intermedios vacíos (de ser así, serían cero_asumido, no sin_datos)
    assert d["resumen"]["con_detecciones"] == 3
    estados = {dia["fecha"]: dia["estado"] for dia in d["dias"]}
    assert estados["2026-09-01"] == "con_detecciones"


def test_anomalias_con_calendario_422(almacen_territorial):
    """3 días de historia: el detector se niega honestamente (baseline 28)."""
    cliente, duck, _ = almacen_territorial
    r = cliente.get(
        "/api/anomalies?date_from=2026-09-02&date_to=2026-09-03&z=3.0"
    )
    assert r.status_code == 422
    assert "historia insuficiente" in r.json()["error"]["message"]


# ------------------------------------------------------------------ make_valid antes/después


def _write_fc(tmp_path: Path, nombre: str, data: dict) -> Path:
    p = tmp_path / nombre
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_make_valid_cuenta_antes_de_reparar(tmp_path):
    """El bug de la Misión 004: el conteo se hacía tras reparar → siempre 0."""
    bowtie = [[0, 0], [4, 0], [0, 4], [4, 4], [0, 0]]  # pajarita: inválida
    adm0 = {
        "type": "FeatureCollection",
        "features": [
            _feature("PAIS", _poly([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]), "B-0")
        ],
    }
    adm1 = {
        "type": "FeatureCollection",
        "features": [
            _feature("DEPTO", _poly([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]), "B-1")
        ],
    }
    adm2 = {
        "type": "FeatureCollection",
        "features": [
            _feature("DISTRITO PAJARITA", _poly(bowtie), "B-2"),
            _feature("DISTRITO OK", _poly([[0, 6], [4, 6], [4, 9], [0, 9], [0, 6]]), "B-3"),
        ],
    }
    bs = BoundarySet.from_geojson_files(
        "test-repair",
        _write_fc(tmp_path, "adm0.geojson", adm0),
        _write_fc(tmp_path, "adm1.geojson", adm1),
        _write_fc(tmp_path, "adm2.geojson", adm2),
    )
    # estado ORIGINAL contado ANTES de la reparación (no después)
    assert bs.meta["geometrias_invalidas_originales"] == 1
    assert bs.meta["geometrias_reparadas"] == 1
    assert len(bs.meta["detalle_reparaciones"]) == 1
    assert "DISTRITO PAJARITA" in bs.meta["detalle_reparaciones"][0]["nombre"]
    # estado FINAL: todas válidas
    assert all(u.geometry.is_valid for u in bs.units)

    # el registro sobrevive al roundtrip parquet (antes se perdía)
    pq_path = bs.to_parquet(tmp_path / "u.parquet")
    bs2 = BoundarySet.from_parquet(pq_path)
    assert bs2.meta.get("geometrias_reparadas") == 1
    assert bs2.meta.get("detalle_reparaciones")[0]["nivel"] == "ADM2"

    # y la auditoría lo reporta como hallazgo informativo
    rep = bs2.audit()
    tipos = {h["tipo"] for h in rep["hallazgos"]}
    assert "geometrias_reparadas_en_carga" in tipos


def test_audit_detecta_duplicados_y_superposiciones(tmp_path):
    """La auditoría reporta; no corrige silenciosamente."""
    cuadrado = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    adm0 = {
        "type": "FeatureCollection",
        "features": [_feature("PAIS", _poly(cuadrado), "D-0")],
    }
    # dos departamentos con el MISMO shape_id y solapados al 50%
    adm1 = {
        "type": "FeatureCollection",
        "features": [
            _feature("DEPTO A", _poly(cuadrado), "D-1"),
            _feature("DEPTO B", _poly([[5, 0], [15, 0], [15, 10], [5, 10], [5, 0]]), "D-1"),
        ],
    }
    adm2 = {
        "type": "FeatureCollection",
        "features": [
            _feature("DISTRITO", _poly([[0, 6], [4, 6], [4, 9], [0, 9], [0, 6]]), "D-2")
        ],
    }
    bs = BoundarySet.from_geojson_files(
        "test-audit",
        _write_fc(tmp_path, "adm0.geojson", adm0),
        _write_fc(tmp_path, "adm1.geojson", adm1),
        _write_fc(tmp_path, "adm2.geojson", adm2),
    )
    rep = bs.audit()
    tipos = {h["tipo"] for h in rep["hallazgos"]}
    assert "shape_id_duplicado" in tipos
    assert "superposicion" in tipos
    # B está a medias fuera del país: también se reporta
    assert "unidad_fuera_del_pais" in tipos or "diferencia_adm1_vs_adm0" in tipos


# ------------------------------------------------------------------ bbox ≠ frontera


def test_qc_bbox_no_es_frontera(settings):
    """Punto de Argentina DENTRO del bbox: QC dice 'contrato OK'; la frontera
    la decide la geometría, no el rectángulo."""
    from hotspots.models import NormalizedObservation
    from hotspots.quality.checks import check_record

    def obs(lat, lon):
        return NormalizedObservation(
            provider="firms",
            product="VIIRS_NOAA20_NRT",
            source_kind="fixture",
            run_id="qc-test",
            manifest_id="qc-test",
            ingested_at_utc="2026-01-01T00:00:00Z",
            latitude=lat,
            longitude=lon,
            acq_date="2026-09-01",
            acq_time="1300",
            acq_datetime_utc="2026-09-01T13:00:00Z",
            satellite="1",
            satellite_name="NOAA-20",
            instrument="VIIRS",
            confidence="h",
            frp=10.0,
            daynight="D",
            version="2",
        )

    # Formosa, Argentina: -26.2, -58.2 → DENTRO del bbox de consulta
    dentro_bbox = check_record(obs(-26.2, -58.2), settings)
    assert dentro_bbox.ok
    assert "outside_query_bbox" not in dentro_bbox.flags  # contrato cumplido

    # Buenos Aires: -34.6, -58.4 → FUERA del bbox (flag soft, fila válida)
    fuera_bbox = check_record(obs(-34.6, -58.4), settings)
    assert fuera_bbox.ok
    assert "outside_query_bbox" in fuera_bbox.flags


def test_punto_vecino_dentro_del_bbox_no_es_nacional(pais_asuncion):
    """La asignación territorial usa el polígono, jamás el rectángulo."""
    bs = BoundarySet.from_geojson_files(
        VER, pais_asuncion["ADM0"], pais_asuncion["ADM1"], pais_asuncion["ADM2"]
    )
    # vecinos DENTRO del bbox de consulta real
    assert bs.assign(-58.0, -27.4)["dentro_pais"] is False  # Argentina (Corrientes)
    assert bs.assign(-56.2, -20.5)["dentro_pais"] is False  # Brasil (MS)
    assert bs.assign(-60.5, -20.8)["dentro_pais"] is False  # Bolivia (SC)
    # punto nacional
    asu = bs.assign(-57.63, -25.28)
    assert asu["dentro_pais"] is True
    assert asu["admin1_id"] == f"{VER}:ADM1:CENTRAL-TEST"
    # punto en el borde: convención covers => dentro (documentada)
    assert bs.assign(-58.0, -25.5)["dentro_pais"] is True


# ------------------------------------------------------------------ calendario (unidad)


def test_calendario_distingue_cero_de_sin_datos():
    from hotspots.analysis.calendar import (
        build_coverage_calendar,
        serie_comparable,
    )

    cal = build_coverage_calendar(
        fechas_obs_por_producto={
            "MODIS_NRT": {"2026-01-01", "2026-01-03"},
            "VIIRS_NOAA20_NRT": {"2026-01-02"},
        },
        fechas_cuarentena_por_producto={"MODIS_NRT": {"2026-01-05"}},
        desde="2026-01-01",
        hasta="2026-01-07",
    )
    estados = {d["fecha"]: d["estado"] for d in cal["dias"]}
    assert estados["2026-01-01"] == "con_detecciones"
    assert estados["2026-01-04"] == "cero_detecciones_asumido"  # dentro del intervalo
    assert estados["2026-01-05"] == "solo_rechazadas_qc"  # cuarentena sin válidas
    assert estados["2026-01-06"] == "sin_datos"  # fuera del intervalo cubierto
    assert estados["2026-01-07"] == "sin_datos"
    # supuesto explícito: cobertura inferida (sin manifiestos con período)
    assert any("inferida" in s for s in cal["supuestos"])

    # la serie comparable: ceros adentro, huecos afuera
    conteos = {"2026-01-01": 5, "2026-01-02": 3, "2026-01-03": 1}
    serie, excluidos = serie_comparable(conteos, cal)
    como_dict = dict(serie)
    assert como_dict["2026-01-04"] == 0  # cero REAL entra a la serie
    assert "2026-01-06" not in como_dict  # sin datos queda afuera
    assert set(excluidos) == {"2026-01-05", "2026-01-06", "2026-01-07"}


def test_calendario_con_periodo_de_manifiesto():
    """Con acquisition_period real no se infiere: cobertura declarada."""
    from hotspots.analysis.calendar import build_coverage_calendar

    cal = build_coverage_calendar(
        fechas_obs_por_producto={"MODIS_NRT": {"2026-01-03"}},
        periodos_adquisicion={"MODIS_NRT": ("2026-01-01", "2026-01-05")},
        desde="2026-01-01",
        hasta="2026-01-07",
    )
    estados = {d["fecha"]: d["estado"] for d in cal["dias"]}
    assert estados["2026-01-01"] == "cero_detecciones_asumido"
    assert estados["2026-01-07"] == "sin_datos"
    assert cal["supuestos"] == []  # no hay supuestos: el período es explícito


# ------------------------------------------------------------------ registro cartográfico


def test_registro_cartografico_ficha_completa():
    from hotspots.geo.registry import cargar_registro, ficha_de, validar_ficha

    registro = cargar_registro(Path("configs"))
    # Misión 008: la capa 2012 es HISTÓRICA; la activa es la INE 2022 (COD-AB)
    historica = ficha_de(registro, "geoboundaries-gbOpen-PRY-9469f09")
    assert historica is not None
    assert historica["estado"] == "historica"
    assert historica["caracter"] == "estadistico"
    assert historica["anio_representado"] == 2012
    assert historica["sha256"]["ADM2"].startswith("78b4c1")
    assert validar_ficha(historica) == []  # todos los campos obligatorios

    activa = ficha_de(registro, "ine2022-codab-hdx")
    assert activa is not None
    assert activa["estado"] == "activa"
    assert activa["conteos"]["ADM2"] == 263

    # contrato de UNA sola capa activa en el registro
    estados_activos = [
        f.get("version") for f in registro.get("fuentes", []) if f.get("estado") == "activa"
    ]
    assert estados_activos == ["ine2022-codab-hdx"]
    # coherencia con el estado del sistema cuando el runtime existe (un clone
    # limpio regenera data/ con 'geo build': el archivo no está versionado)
    runtime_version = Path("data/geo/active_version.txt")
    if runtime_version.exists():
        assert runtime_version.read_text(encoding="utf-8").strip() == "ine2022-codab-hdx"

    # la discrepancia territorial queda fichada, no silenciada
    ine = ficha_de(registro, "ine-revision-2025")
    assert ine is not None
    assert ine["conteos"]["ADM2"] == 263
    assert ine["estado"] == "no_incorporada"
    assert ine["fecha_descarga"] is None  # honesto: aún no se descargó
