"""Pruebas de la capa geográfica nacional (Misión 004, etapa 2).

País sintético con todos los casos difíciles:

- ADM0: MultiPolygon de DOS partes con un HUECO en la parte oeste.
- ADM1: dos departamentos ("Occidental" con hueco, "Oriental" la parte chica).
- ADM2: dos distritos dentro del departamento grande.

El punto (4,4) cae en el hueco (fuera del país), (5,5) sobre el borde del
hueco (dentro por convención ``covers``), (9.5, 2) cae en el vacío entre las
dos partes del multipolígono (fuera).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hotspots.geo.assign import (
    assign_observations,
    assigned_obs_ids,
    obs_geo_files,
)
from hotspots.geo.boundaries import BoundarySet, GeoError, _slug
from hotspots.storage.duckdb_store import DuckDBStore

# ------------------------------------------------------------------ fixtures geo

VER = "test-v1"


def _poly(coords):
    return {"type": "Polygon", "coordinates": coords}


def _feature(name, geom, shape_id):
    return {
        "type": "Feature",
        "properties": {"shapeName": name, "shapeID": shape_id},
        "geometry": geom,
    }


@pytest.fixture()
def synthetic_country(tmp_path: Path) -> dict:
    """GeoJSONs sintéticos de tres niveles."""
    # País: parte oeste 0-9 x 0-9 con hueco 3-5 x 3-5, más parte este 10-12 x 0-4
    adm0 = {
        "type": "FeatureCollection",
        "features": [
            _feature(
                "PAIS TEST",
                {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[0, 0], [9, 0], [9, 9], [0, 9], [0, 0]],
                         [[3, 3], [5, 3], [5, 5], [3, 5], [3, 3]]],
                        [[[10, 0], [12, 0], [12, 4], [10, 4], [10, 0]]],
                    ],
                },
                "PY-0",
            )
        ],
    }
    adm1 = {
        "type": "FeatureCollection",
        "features": [
            _feature(
                "OCCIDENTAL TEST",
                _poly([[[0, 0], [9, 0], [9, 9], [0, 9], [0, 0]],
                       [[3, 3], [5, 3], [5, 5], [3, 5], [3, 3]]]),
                "PY-1A",
            ),
            _feature(
                "ORIENTAL TEST",
                _poly([[[10, 0], [12, 0], [12, 4], [10, 4], [10, 0]]]),
                "PY-1B",
            ),
        ],
    }
    adm2 = {
        "type": "FeatureCollection",
        "features": [
            _feature("DISTRITO NORTE", _poly([[[0, 6], [4, 6], [4, 9], [0, 9], [0, 6]]]), "PY-2A"),
            _feature("DISTRITO SUR", _poly([[[0, 0], [3, 0], [3, 3], [0, 3], [0, 0]]]), "PY-2B"),
        ],
    }
    out = {}
    for lvl, data in (("ADM0", adm0), ("ADM1", adm1), ("ADM2", adm2)):
        p = tmp_path / f"PRY-{lvl}.geojson"
        p.write_text(json.dumps(data), encoding="utf-8")
        out[lvl] = p
    return out


@pytest.fixture()
def boundaries(synthetic_country) -> BoundarySet:
    bs = BoundarySet.from_geojson_files(
        VER, synthetic_country["ADM0"], synthetic_country["ADM1"], synthetic_country["ADM2"]
    )
    return bs


# ------------------------------------------------------------------ carga

def test_carga_y_conteos(boundaries):
    counts = boundaries.counts()
    assert counts == {"ADM0": 1, "ADM1": 2, "ADM2": 2}


def test_admin_ids_estables(boundaries):
    ids = {u.nombre: u.admin_id for u in boundaries.units}
    assert ids["OCCIDENTAL TEST"] == f"{VER}:ADM1:OCCIDENTAL-TEST"
    assert ids["DISTRITO NORTE"].startswith(f"{VER}:ADM2:")
    # el slug normaliza acentos: ÑEEMBUCU -> NEEMBUCU
    assert _slug("ÑEEMBUCÚ") == "NEEMBUCU"


def test_padres_derivados(boundaries):
    by_name = {u.nombre: u for u in boundaries.units}
    occ = by_name["OCCIDENTAL TEST"]
    assert by_name["DISTRITO NORTE"].padre_admin_id == occ.admin_id
    assert by_name["DISTRITO NORTE"].padre_derivado is True
    assert occ.padre_admin_id == by_name["PAIS TEST"].admin_id
    assert occ.padre_derivado is False


def test_validacion_conteo_falla(synthetic_country, tmp_path):
    # esperamos 18 departamentos pero el sintético tiene 2: debe reventar
    bs = BoundarySet.from_geojson_files(
        VER, synthetic_country["ADM0"], synthetic_country["ADM1"], synthetic_country["ADM2"]
    )
    with pytest.raises(GeoError, match="ADM1"):
        bs.validate({"ADM0": 1, "ADM1": 18})


# ------------------------------------------------------------------ point-in-polygon

def test_punto_interior(boundaries):
    r = boundaries.assign(1.0, 1.0)
    assert r["dentro_pais"] is True
    assert r["admin1_id"] == f"{VER}:ADM1:OCCIDENTAL-TEST"
    assert r["admin2_id"] == f"{VER}:ADM2:DISTRITO-SUR"


def test_punto_en_hueco_esta_fuera(boundaries):
    # (4,4) cae dentro del hueco del multipolígono: NO es país
    assert boundaries.inside_country(4.0, 4.0) is False
    r = boundaries.assign(4.0, 4.0)
    assert r == {"dentro_pais": False, "admin1_id": None, "admin2_id": None}


def test_punto_en_borde_cuenta_como_dentro(boundaries):
    # convención documentada: covers => el borde del hueco es país
    assert boundaries.inside_country(3.0, 4.0) is True


def test_punto_en_segunda_parte(boundaries):
    r = boundaries.assign(11.0, 2.0)
    assert r["dentro_pais"] is True
    assert r["admin1_id"] == f"{VER}:ADM1:ORIENTAL-TEST"
    assert r["admin2_id"] is None  # no hay distrito en la parte este


def test_punto_en_el_vacio_entre_partes(boundaries):
    # (9.5, 2) está entre las dos partes del multipolígono: fuera
    assert boundaries.inside_country(9.5, 2.0) is False


def test_punto_lejos(boundaries):
    r = boundaries.assign(-57.6, -25.3)
    assert r["dentro_pais"] is False


# ------------------------------------------------------------------ parquet roundtrip

def test_parquet_roundtrip(boundaries, tmp_path):
    p = boundaries.to_parquet(tmp_path / "unidades_admin.parquet")
    bs2 = BoundarySet.from_parquet(p)
    assert bs2.counts() == boundaries.counts()
    assert bs2.version == VER
    # misma asignación tras el roundtrip
    for lon, lat in [(1.0, 1.0), (11.0, 2.0), (4.0, 4.0), (2.0, 7.5)]:
        assert bs2.assign(lon, lat) == boundaries.assign(lon, lat)


# ------------------------------------------------------------------ asignación obs_geo

def _obs(oid, lon, lat):
    return {"obs_id": oid, "longitude": lon, "latitude": lat}


def test_asignacion_observaciones(boundaries, tmp_path):
    obs = [
        _obs("o1", 1.0, 1.0),   # dentro, depto grande, distrito sur
        _obs("o2", 11.0, 2.0),  # dentro, parte este, sin distrito
        _obs("o3", 4.0, 4.0),   # hueco: fuera del país
        _obs("o4", 25.0, 25.0), # afuera de todo
        _obs("o5", 2.0, 7.5),   # dentro, distrito norte
    ]
    s = assign_observations(
        boundaries, obs, run_id="run1", processed_root=tmp_path,
        assigned_at_utc="2026-01-01T00:00:00Z",
    )
    assert s.total_observaciones == 5
    assert s.asignadas_nuevas == 5
    assert s.dentro_pais == 3
    assert s.fuera_pais == 2
    assert s.con_departamento == 3
    assert s.con_distrito == 2
    files = obs_geo_files(tmp_path)
    assert len(files) == 1


def test_asignacion_idempotente(boundaries, tmp_path):
    obs = [_obs("o1", 1.0, 1.0)]
    assign_observations(
        boundaries, obs, run_id="run1", processed_root=tmp_path,
        assigned_at_utc="2026-01-01T00:00:00Z",
    )
    s2 = assign_observations(
        boundaries, obs, run_id="run2", processed_root=tmp_path,
        assigned_at_utc="2026-01-02T00:00:00Z",
    )
    assert s2.ya_asignadas == 1
    assert s2.asignadas_nuevas == 0
    assert len(obs_geo_files(tmp_path)) == 1  # nada nuevo escrito
    assert assigned_obs_ids(tmp_path, VER) == {"o1"}


def test_asignacion_versiones_coexisten(boundaries, tmp_path):
    """Cambiar de versión NO pisa la anterior: dos tandas, dos versiones."""
    obs = [_obs("o1", 1.0, 1.0)]
    assign_observations(
        boundaries, obs, run_id="run1", processed_root=tmp_path,
        assigned_at_utc="2026-01-01T00:00:00Z",
    )
    assign_observations(
        boundaries, obs, version="test-v2", run_id="run2",
        processed_root=tmp_path, assigned_at_utc="2026-01-02T00:00:00Z",
    )
    assert assigned_obs_ids(tmp_path, VER) == {"o1"}
    assert assigned_obs_ids(tmp_path, "test-v2") == {"o1"}
    assert len(obs_geo_files(tmp_path)) == 2


def test_obs_sin_coordenadas_no_se_asigna(boundaries, tmp_path):
    obs = [{"obs_id": "x", "longitude": None, "latitude": None}]
    s = assign_observations(
        boundaries, obs, run_id="run1", processed_root=tmp_path,
        assigned_at_utc="2026-01-01T00:00:00Z",
    )
    assert s.asignadas_nuevas == 0
    assert any("sin coordenadas" in n for n in s.notes)


# ------------------------------------------------------------------ vistas DuckDB

def test_vistas_geo_end_to_end(boundaries, synthetic_country, tmp_path):
    """Pipeline completo: ingesta fixture -> geo assign -> vistas geo."""
    from hotspots.config import Settings
    from hotspots.ingestion.pipeline import run_ingest

    settings = Settings.load(
        env={"FIRMS_MAP_KEY": None, "EARTHDATA_TOKEN": None},
        env_file=None,
        data_dir=tmp_path / "data",
    )
    (tmp_path / "data").mkdir(exist_ok=True)

    # fixture con un punto dentro del país sintético y otro fuera
    csv_text = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_ti5,frp,daynight\n"
        "1.5,1.5,300.1,0.4,0.4,2026-09-01,1305,N,VIIRS,h,2,290.5,12.3,D\n"
        "30.0,30.0,310.0,0.4,0.4,2026-09-01,1310,N,VIIRS,h,2,295.0,15.0,D\n"
    )
    fx = tmp_path / "fix.csv"
    fx.write_text(csv_text, encoding="utf-8")

    # la configuración default exige bbox de Paraguay real: el punto (1.5,1.5)
    # queda fuera y (30,30) fuera también — ambos SOFT, ambos válidos.
    s1 = run_ingest(
        settings, mode="fixture", product="VIIRS_NOAA20_NRT", fixture_path=fx
    )
    assert s1.rows_valid == 2

    # asignamos las observaciones REALES del almacén (obs_id deterministas)
    duck0 = DuckDBStore(
        tmp_path / "data" / "processed" / "hotspots.duckdb",
        tmp_path / "data" / "processed",
    )
    real_obs = duck0.query("SELECT obs_id, longitude, latitude FROM observations")
    assert len(real_obs) == 2

    s = assign_observations(
        boundaries,
        real_obs,
        run_id="geo1",
        processed_root=tmp_path / "data" / "processed",
        assigned_at_utc="2026-01-01T00:00:00Z",
    )
    assert s.dentro_pais == 1 and s.fuera_pais == 1

    pq = boundaries.to_parquet(tmp_path / "unidades_admin.parquet")
    duck = DuckDBStore(
        tmp_path / "data" / "processed" / "hotspots.duckdb",
        tmp_path / "data" / "processed",
    )
    duck.refresh(geo_version=VER, boundaries_parquet=pq)

    rows = duck.query("SELECT * FROM observations_geo ORDER BY longitude")
    assert len(rows) == 2
    assert rows[0]["dentro_pais"] is True
    assert rows[0]["departamento"] == "OCCIDENTAL TEST"
    assert rows[0]["distrito"] == "DISTRITO SUR"
    assert rows[1]["dentro_pais"] is False
    assert rows[1]["departamento"] is None

    # stats nacionales: solo cuenta lo que está dentro del país
    nac = duck.query("SELECT * FROM stats_nacional_dia")
    assert len(nac) == 1
    assert nac[0]["detecciones"] == 1

    # cobertura: 1 dentro, 1 fuera
    cob = {str(r["dentro_pais"]): r["n"] for r in duck.query("SELECT * FROM cobertura_area")}
    assert cob == {"True": 1, "False": 1}

    # refresh sin argumentos conserva las vistas geo (persistencia de config)
    duck.refresh()
    assert duck.geo_version_activa() == VER
    assert len(duck.query("SELECT * FROM observations_geo")) == 2


# ------------------------------------------------- esquema COD-AB (Misión 007)
#
# La redistribución OCHA COD-AB de la cartografía INE 2022 usa propiedades
# adm{N}_name / adm{N}_pcode y declara el padre de cada distrito en adm1_name.
# Estos tests cubren: padre explícito usado (no derivado), fallback espacial
# cuando el campo viene vacío, registro de inconsistencias explícito vs
# espacial, y rechazo de esquemas desconocidos.


def _codab_feature(nivel, name, pcode, geom, padre=None):
    props = {f"adm{nivel}_name": name, f"adm{nivel}_pcode": pcode}
    if nivel == 2:
        props["adm1_name"] = padre
    return {"type": "Feature", "properties": props, "geometry": geom}


@pytest.fixture()
def synthetic_country_codab(tmp_path: Path) -> dict:
    """Mismo país sintético que arriba, en el esquema COD-AB.

    - DISTRITO NORTE declara padre OCCIDENTAL TEST (correcto).
    - DISTRITO SUR declara padre vacío (forza fallback espacial).
    - DISTRITO EXTERNO declara padre ORIENTAL TEST pero su geometría cae en
      OCCIDENTAL TEST (inconsistencia explícito vs espacial).
    """
    adm0 = {
        "type": "FeatureCollection",
        "features": [
            _codab_feature(0, "PAIS TEST", "PY", _poly([[[0, 0], [9, 0], [9, 9], [0, 9], [0, 0]]]))
        ],
    }
    adm1 = {
        "type": "FeatureCollection",
        "features": [
            _codab_feature(
                1, "OCCIDENTAL TEST", "PY1",
                _poly([[[0, 0], [9, 0], [9, 9], [0, 9], [0, 0]]]),
            ),
            _codab_feature(
                1, "ORIENTAL TEST", "PY2",
                _poly([[[9, 0], [12, 0], [12, 4], [9, 4], [9, 0]]]),
            ),
        ],
    }
    adm2 = {
        "type": "FeatureCollection",
        "features": [
            _codab_feature(
                2, "DISTRITO NORTE", "PY1001",
                _poly([[[0, 6], [4, 6], [4, 9], [0, 9], [0, 6]]]),
                padre="OCCIDENTAL TEST",
            ),
            _codab_feature(
                2, "DISTRITO SUR", "PY1002",
                _poly([[[0, 0], [3, 0], [3, 3], [0, 3], [0, 0]]]),
                padre="",
            ),
            _codab_feature(
                2, "DISTRITO EXTERNO", "PY2001",
                _poly([[[5, 6], [8, 6], [8, 8], [5, 8], [5, 6]]]),
                padre="ORIENTAL TEST",
            ),
        ],
    }
    out = {}
    for lvl, data in (("ADM0", adm0), ("ADM1", adm1), ("ADM2", adm2)):
        p = tmp_path / f"codab-{lvl}.geojson"
        p.write_text(json.dumps(data), encoding="utf-8")
        out[lvl] = p
    return out


def _bs_codab(synthetic_country_codab) -> BoundarySet:
    return BoundarySet.from_geojson_files(
        VER,
        synthetic_country_codab["ADM0"],
        synthetic_country_codab["ADM1"],
        synthetic_country_codab["ADM2"],
        schema="codab",
    )


def test_codab_padre_explicito_no_derivado(synthetic_country_codab):
    bs = _bs_codab(synthetic_country_codab)
    by_name = {u.nombre: u for u in bs.units}
    norte = by_name["DISTRITO NORTE"]
    occ = by_name["OCCIDENTAL TEST"]
    # shape_id toma el pcode del fuente
    assert norte.shape_id == "PY1001"
    # el padre viene del campo adm1_name: NO derivado
    assert norte.padre_admin_id == occ.admin_id
    assert norte.padre_derivado is False
    assert bs.meta["padres_explicitos_usados"] == 2  # NORTE + EXTERNO
    assert bs.meta["padres_derivados_fallback"] == 1  # SUR (campo vacío)


def test_codab_fallback_espacial_marcado(synthetic_country_codab):
    bs = _bs_codab(synthetic_country_codab)
    by_name = {u.nombre: u for u in bs.units}
    sur = by_name["DISTRITO SUR"]
    occ = by_name["OCCIDENTAL TEST"]
    assert sur.padre_admin_id == occ.admin_id
    assert sur.padre_derivado is True


def test_codab_inconsistencia_registrada(synthetic_country_codab):
    bs = _bs_codab(synthetic_country_codab)
    by_name = {u.nombre: u for u in bs.units}
    externo = by_name["DISTRITO EXTERNO"]
    # se conserva el padre EXPLÍCITO declarado por la fuente…
    assert externo.padre_admin_id == by_name["ORIENTAL TEST"].admin_id
    # …y la divergencia espacial queda registrada, no descartada en silencio
    incons = bs.meta["inconsistencias_padre_explicito_vs_espacial"]
    assert len(incons) == 1
    assert incons[0]["nombre"] == "DISTRITO EXTERNO"
    assert incons[0]["padre_espacial"] == "OCCIDENTAL TEST"
    # y aparece como hallazgo en la auditoría
    reporte = bs.audit()
    tipos = {h["tipo"] for h in reporte["hallazgos"]}
    assert "padre_explicito_vs_espacial" in tipos


def test_codab_conteos_y_asignacion(synthetic_country_codab):
    bs = _bs_codab(synthetic_country_codab)
    assert bs.counts() == {"ADM0": 1, "ADM1": 2, "ADM2": 3}
    # punto dentro de DISTRITO NORTE
    res = bs.assign(2.0, 7.0)
    assert res["dentro_pais"] is True
    assert res["admin2_id"] == f"{VER}:ADM2:DISTRITO-NORTE"


def test_esquema_desconocido_rechazado(synthetic_country_codab):
    with pytest.raises(GeoError, match="Esquema de fuente desconocido"):
        BoundarySet.from_geojson_files(
            VER,
            synthetic_country_codab["ADM0"],
            synthetic_country_codab["ADM1"],
            synthetic_country_codab["ADM2"],
            schema="gadm",
        )


def test_geoboundaries_default_sigue_derivando(synthetic_country_codab, tmp_path):
    """El default geoboundaries no cambia: sin campo padre, deriva y marca."""
    # misma geometría pero con propiedades shapeName/shapeID en TODOS los niveles
    paths = {}
    for lvl in ("ADM0", "ADM1", "ADM2"):
        data = json.loads(synthetic_country_codab[lvl].read_text(encoding="utf-8"))
        n = lvl[-1]
        for f in data["features"]:
            props = f["properties"]
            f["properties"] = {
                "shapeName": props[f"adm{n}_name"],
                "shapeID": props[f"adm{n}_pcode"],
            }
        p = tmp_path / f"gb-{lvl}.geojson"
        p.write_text(json.dumps(data), encoding="utf-8")
        paths[lvl] = p
    bs = BoundarySet.from_geojson_files(VER, paths["ADM0"], paths["ADM1"], paths["ADM2"])
    for u in bs.units:
        if u.nivel == 2:
            assert u.padre_derivado is True


def test_ids_duplicados_desambiguados_por_padre(tmp_path: Path):
    """Dos distritos con el MISMO nombre en distintos departamentos (caso real
    INE 2022: Bella Vista en Amambay e Itapúa) reciben admin_ids distintos,
    calificados por el padre. Sin colisión, el ID simple no cambia."""
    # país: cuadrado 0-9; dos departamentos mitades; un Bella Vista en cada uno
    adm0 = {
        "type": "FeatureCollection",
        "features": [
            _codab_feature(0, "PAIS TEST", "PY", _poly([[[0, 0], [9, 0], [9, 9], [0, 9], [0, 0]]]))
        ],
    }
    adm1 = {
        "type": "FeatureCollection",
        "features": [
            _codab_feature(
                1, "NORTE TEST", "PY1", _poly([[[0, 5], [9, 5], [9, 9], [0, 9], [0, 5]]]),
            ),
            _codab_feature(
                1, "SUR TEST", "PY2", _poly([[[0, 0], [9, 0], [9, 5], [0, 5], [0, 0]]]),
            ),
        ],
    }
    adm2 = {
        "type": "FeatureCollection",
        "features": [
            _codab_feature(
                2, "Bella Vista", "PY1001",
                _poly([[[0, 6], [4, 6], [4, 9], [0, 9], [0, 6]]]),
                padre="NORTE TEST",
            ),
            _codab_feature(
                2, "Bella Vista", "PY2001",
                _poly([[[0, 0], [4, 0], [4, 5], [0, 5], [0, 0]]]),
                padre="SUR TEST",
            ),
            _codab_feature(
                2, "Único", "PY1002",
                _poly([[[5, 6], [8, 6], [8, 9], [5, 9], [5, 6]]]),
                padre="NORTE TEST",
            ),
        ],
    }
    out = {}
    for lvl, data in (("ADM0", adm0), ("ADM1", adm1), ("ADM2", adm2)):
        p = tmp_path / f"dup-{lvl}.geojson"
        p.write_text(json.dumps(data), encoding="utf-8")
        out[lvl] = p
    bs = BoundarySet.from_geojson_files(
        VER, out["ADM0"], out["ADM1"], out["ADM2"], schema="codab"
    )
    ids = sorted(u.admin_id for u in bs.units if u.nivel == 2)
    assert ids == [
        f"{VER}:ADM2:BELLA-VISTA--NORTE-TEST",
        f"{VER}:ADM2:BELLA-VISTA--SUR-TEST",
        f"{VER}:ADM2:UNICO",  # sin colisión: ID simple intacto
    ]
    # la auditoría ya no reporta admin_id duplicado (el nombre duplicado sí)
    reporte = bs.audit()
    tipos = [h["tipo"] for h in reporte["hallazgos"]]
    assert "admin_id_duplicado" not in tipos
    assert "nombre_duplicado_en_nivel" in tipos
