"""Pruebas del módulo de armonización MODIS–VIIRS (Misión B)."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from hotspots.analysis.harmonization import (
    DIST_CANONICA_M,
    DT_CANONICO_S,
    HARMONIZATION_VERSION,
    analizar_pares,
    compute_pairs,
    discrepancias,
    exportar_armonizacion,
    sensibilidad,
    verificar_medianoche_utc,
)


def _crear_duckdb_prueba(ruta: Path) -> Path:
    """DuckDB mínimo con observaciones de pares CONOCIDOS.

    Geometría: Aqua detecta a (−23.0, −58.0) 12:00; N20 detecta a 600 m y
    300 s (par válido al umbral canónico), otra a 2,5 km y 700 s (solo
    superconjunto), otra a 5 km (fuera de todo), y Terra sin solape temporal.
    """
    con = duckdb.connect(str(ruta))
    con.execute(
        """
        CREATE TABLE observations AS
        SELECT * FROM (VALUES
          -- MODIS Aqua: la observación de referencia y una lejana
          ('aqua-1', 'MODIS_SP', 'Aqua', 'Aqua', 'MODIS', -23.0, -58.0,
           TIMESTAMP '2020-09-10 12:00:00', 100.0, '80', 'high', 'D',
           'BOQUERON', true, 2020, '2020-09-10',
           'modis_sp_mini.csv.gz', repeat('a', 64)),
          ('aqua-2', 'MODIS_SP', 'Aqua', 'Aqua', 'MODIS', -23.05, -58.05,
           TIMESTAMP '2020-09-10 12:00:00', 20.0, '50', 'nominal', 'D',
           'BOQUERON', true, 2020, '2020-09-10',
           'modis_sp_mini.csv.gz', repeat('a', 64)),
          -- MODIS Terra: sin solape temporal con VIIRS (tarde del día previo)
          ('terra-1', 'MODIS_SP', 'Terra', 'Terra', 'MODIS', -23.0, -58.0,
           TIMESTAMP '2020-09-09 13:30:00', 90.0, '70', 'high', 'D',
           'BOQUERON', true, 2020, '2020-09-09',
           'modis_sp_mini.csv.gz', repeat('a', 64)),
          -- VIIRS N20: par canónico (600 m, 300 s)
          ('n20-1', 'VIIRS_NOAA20_SP', 'N20', 'NOAA-20', 'VIIRS', -23.0054, -58.0,
           TIMESTAMP '2020-09-10 12:05:00', 30.0, 'n', 'nominal', 'D',
           'BOQUERON', true, 2020, '2020-09-10',
           'viirs_n20_mini.csv.gz', repeat('b', 64)),
          -- VIIRS N20: par solo-superconjunto (2,5 km, 700 s)
          ('n20-2', 'VIIRS_NOAA20_SP', 'N20', 'NOAA-20', 'VIIRS', -23.0225, -58.0,
           TIMESTAMP '2020-09-10 12:11:40', 10.0, 'l', 'low', 'D',
           'BOQUERON', true, 2020, '2020-09-10',
           'viirs_n20_mini.csv.gz', repeat('b', 64)),
          -- VIIRS N21: fuera de distancia (5 km)
          ('n21-1', 'VIIRS_NOAA21_SP', 'N21', 'NOAA-21', 'VIIRS', -23.045, -58.0,
           TIMESTAMP '2020-09-10 12:06:00', 15.0, 'h', 'high', 'N',
           'BOQUERON', true, 2020, '2020-09-10',
           'viirs_n21_mini.csv.gz', repeat('c', 64))
        ) AS t(obs_id, product, satellite, satellite_name, sensor, latitude, longitude,
               acq_datetime_utc, frp, confidence, confidence_band, daynight,
               departamento, dentro_pais, year, acq_date, source_file, source_sha256)
        """
    )
    con.close()
    return ruta


@pytest.fixture()
def db_prueba(tmp_path: Path) -> Path:
    return _crear_duckdb_prueba(tmp_path / "mini.duckdb")


def test_compute_pairs_estructura_y_conteos(db_prueba):
    con = duckdb.connect(str(db_prueba), read_only=True)
    tabla, resumen = compute_pairs(db_prueba, con=con)
    # superconjunto 900s/3km: aqua-1×n20-1 y aqua-1×n20-2 (n21-1 queda a ~5 km, fuera)
    assert resumen["total_pares"] == 2
    assert resumen["pares_por_anio"] == {"2020": 2}
    assert resumen["version"] == HARMONIZATION_VERSION
    assert resumen["metodo"]
    sql = (f"SELECT obs_id_modis, obs_id_viirs, dt_seconds, distance_m "
           f"FROM {tabla} ORDER BY dt_seconds")
    filas = con.execute(sql).fetchall()
    assert filas[0][0] == "aqua-1" and filas[0][1] == "n20-1"
    assert filas[0][2] == 300
    assert 550 < filas[0][3] < 650  # haversine ~600 m
    assert filas[1][1] == "n20-2" and filas[1][2] == 700
    assert 2400 < filas[1][3] < 2600
    con.close()


def test_sensibilidad_derivada_del_superconjunto(db_prueba):
    con = duckdb.connect(str(db_prueba), read_only=True)
    compute_pairs(db_prueba, con=con)
    sens = sensibilidad(con)
    assert len(sens) == 9  # 3 dt × 3 dist
    por_combo = {(s["dt_seconds"], s["distance_m"]): s["pares"] for s in sens}
    assert por_combo[(300, 1000)] == 1   # solo el par cercano
    assert por_combo[(600, 2000)] == 1   # el cercano; el lejano excede dt
    assert por_combo[(900, 3000)] == 2   # ambos
    assert por_combo[(900, 1000)] == 1
    # monotonía: agrandar umbrales nunca reduce pares
    for dt in (300, 600, 900):
        assert por_combo[(dt, 1000)] <= por_combo[(dt, 2000)] <= por_combo[(dt, 3000)]
    con.close()


def test_discrepancias_respetan_periodo(db_prueba):
    con = duckdb.connect(str(db_prueba), read_only=True)
    compute_pairs(db_prueba, con=con)
    disc = discrepancias(con)
    # MODIS 2018+: 3 en total, 1 emparejada al canónico
    assert disc["modis"]["total_2018_mas"] == 3
    assert disc["modis"]["emparejadas"] == 1
    assert disc["viirs"]["total"] == 3
    assert disc["viirs"]["emparejadas"] == 1
    con.close()


def test_analizar_pares_y_medianoche(db_prueba):
    con = duckdb.connect(str(db_prueba), read_only=True)
    compute_pairs(db_prueba, con=con)
    ana = analizar_pares(con)
    assert ana["pares"] == 1  # canónico 600/2000
    assert ana["dt"]["mediana_s"] == 300.0
    med = verificar_medianoche_utc(con)
    assert med["obs_23_50_a_23_59_utc"] == 0
    assert med["obs_00_00_a_00_10_utc"] == 0
    con.close()


def test_exportar_armonizacion_artefactos(db_prueba, tmp_path: Path):
    salida = tmp_path / "armonizacion_v1"
    man = exportar_armonizacion(db_prueba, salida)
    assert (salida / "pares_modis_viirs.parquet").exists()
    assert (salida / "sensibilidad_9_combinaciones.csv").exists()
    assert (salida / "discrepancias.json").exists()
    assert (salida / "analisis_pares.json").exists()
    ruta_man = salida / "manifiesto_armonizacion_v1.json"
    man_guardado = json.loads(ruta_man.read_text(encoding="utf-8"))
    assert man_guardado["version"] == HARMONIZATION_VERSION
    esperados = {
        "pares_modis_viirs.parquet",
        "sensibilidad_9_combinaciones.csv",
        "discrepancias.json",
        "analisis_pares.json",
    }
    assert set(man_guardado["artefactos"]) == esperados
    # el manifiesto registra parámetros canónicos y grilla completa
    pc = {"dt_s": DT_CANONICO_S, "dist_m": DIST_CANONICA_M}
    assert man_guardado["parametros_canonicos"] == pc
    assert man_guardado["grilla_sensibilidad"]["dt_s"] == [300, 600, 900]
    assert man_guardado["grilla_sensibilidad"]["dist_m"] == [1000, 2000, 3000]
    # determinismo: reexportar produce hashes idénticos
    man2 = exportar_armonizacion(db_prueba, salida / "rerun")
    h1 = man["artefactos"]["pares_modis_viirs.parquet"]["sha256"]
    h2 = man2["artefactos"]["pares_modis_viirs.parquet"]["sha256"]
    assert h2 == h1


@pytest.mark.skipif(
    not Path(
        "/home/z/my-project/modis-viirs-hotspots-paraguay"
        "/data/PROCESADA/hotspots_real.duckdb"
    ).exists(),
    reason="base real no disponible",
)
def test_reproduccion_m014_canonica():
    """Reproduce exactamente las 277.933 co-detecciones de M014."""
    import pandas as pd

    ruta = ("/home/z/my-project/modis-viirs-hotspots-paraguay"
            "/data/PROCESADA/armonizacion_v1/pares_modis_viirs.parquet")
    pares = pd.read_parquet(ruta)
    canon = pares[(pares.dt_seconds <= 600) & (pares.distance_m <= 2000)]
    assert len(canon) == 277_933
    # hallazgo estructural M014: solo Aqua tiene solape temporal con VIIRS
    assert set(canon.satellite_modis.unique()) == {"Aqua"}
    assert set(canon.satellite_viirs.unique()) == {"N20", "N21"}
