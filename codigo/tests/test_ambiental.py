"""Pruebas de inteligencia ambiental (Misión D)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hotspots.analysis.ambiental import (
    AMBIENTAL_VERSION,
    analizar_relaciones,
    catalogo_ambiental,
    construir_asociacion,
)

RAIZ = Path(__file__).resolve().parents[2]
ENV = RAIZ / "data" / "ENVIRONMENTAL_DATA"
DUCKDB_REAL = RAIZ / "data" / "PROCESADA" / "hotspots_real.duckdb"
EVENTOS = RAIZ / "data" / "PROCESADA" / "eventos_v1"
ASOC = RAIZ / "data" / "PROCESADA" / "ambiental_v1"

requires_real = pytest.mark.skipif(
    not DUCKDB_REAL.exists() or not (ASOC / "asociacion_celda_mes.parquet").exists(),
    reason="base real o asociación no disponible en este entorno",
)


# ------------------------------------------------------------------ catálogo
def test_catalogo_completo():
    cat = catalogo_ambiental()
    assert len(cat) == 7
    campos = {
        "fuente", "productor", "licencia", "resolucion", "frecuencia", "periodo",
        "variables", "unidades", "cobertura", "calidad", "incertidumbre",
        "estado_integracion",
    }
    for fuente in cat:
        faltan = campos - set(fuente)
        assert not faltan, f"{fuente['fuente']}: faltan {faltan}"
        assert fuente["variables"], "toda fuente declara variables"
    nombres = {f["fuente"] for f in cat}
    assert {
        "CHIRPS v2.0", "ERA5-Land", "FWI GFWED", "ESA WorldCover v200",
        "GOES ABI FDCF (GOES-16/19)", "MCD64A1 v6.1", "FireCCI51",
    } == nombres


def test_catalogo_serializable():
    json.dumps(catalogo_ambiental(), ensure_ascii=False)


# ------------------------------------------------------------------ asociación
@requires_real
class TestAsociacion:
    def test_manifiesto_y_conciliacion(self):
        man = json.loads((ASOC / "manifiesto_ambiental_v1.json").read_text(encoding="utf-8"))
        assert man["version"] == AMBIENTAL_VERSION
        # TODAS las observaciones reales quedaron asociadas a celda×mes
        assert man["conciliacion"]["observaciones_asociadas"] == 2_691_999
        assert man["celdas"] >= 3_737  # grilla + celdas de borde por obs fuera de país
        assert man["regla_antifuga"]

    def test_asociacion_coherente(self):
        import duckdb

        con = duckdb.connect()
        con.execute(
            f"CREATE TABLE a AS SELECT * FROM "
            f"read_parquet('{ASOC / 'asociacion_celda_mes.parquet'}')"
        )
        try:
            filas, celdas = con.execute(
                "SELECT COUNT(*), COUNT(DISTINCT celda) FROM a"
            ).fetchone()
            assert filas == 1_291_197
            # unicidad celda×mes
            dup = con.execute(
                "SELECT COUNT(*) - COUNT(DISTINCT (celda || mes)) FROM a"
            ).fetchone()[0]
            assert dup == 0
            # el fuego total asociado cuadra con la base real
            tot = con.execute("SELECT SUM(obs_modis) + SUM(obs_viirs) FROM a").fetchone()[0]
            assert tot == 2_691_999
            # las variables ambientales tienen cobertura sin duplicados
            for var in ("precip_mm", "temp_media_c", "fwi_medio", "quemado_mcd64_km2"):
                n = con.execute(f"SELECT COUNT({var}) FROM a").fetchone()[0]
                assert n > 0, f"{var} sin cobertura"
        finally:
            con.close()

    def test_celdas_fueras_de_pais_documentadas(self):
        """Las 3.739 celdas = 3.737 de la grilla + celdas de borde con
        observaciones fuera del ADM0 (conservadas con dentro_pais=false)."""
        import duckdb

        con = duckdb.connect()
        con.execute(
            f"CREATE TABLE a AS SELECT * FROM "
            f"read_parquet('{ASOC / 'asociacion_celda_mes.parquet'}')"
        )
        grilla = json.load(open(ENV / "GRILLA" / "grilla_PRY_0p1.geojson"))
        celdas_grilla = {f["properties"]["celda"] for f in grilla["features"]}
        celdas_asoc = {
            r[0]
            for r in con.execute("SELECT DISTINCT celda FROM a").fetchall()
        }
        extra = celdas_asoc - celdas_grilla
        assert len(extra) <= 5, f"celdas fuera de grilla inesperadas: {extra}"
        con.close()


# ------------------------------------------------------------------ análisis
@requires_real
class TestAnalisisRelaciones:
    def test_relaciones_sin_fuga(self):
        res = analizar_relaciones(ASOC / "asociacion_celda_mes.parquet", ASOC)
        assert res["meses_nacionales"] > 300
        # nota metodológica explícita
        assert "nunca del futuro" in res["nota_metodologica"]
        # lags presentes
        assert set(res["relaciones"]) == {"lag0", "lag1", "validacion_area_quemada"}
        # dirección física esperada: sequía (−humedad suelo, −precip, +VPD, +FWI) ↔ +fuego
        lag0 = res["relaciones"]["lag0"]
        assert lag0["humedad_suelo_vs_obs_viirs"]["rho"] < -0.2
        assert lag0["vpd_medio_vs_obs_viirs"]["rho"] > 0.1
        assert lag0["precip_media_vs_obs_viirs"]["rho"] < 0
        assert lag0["fwi_medio_vs_obs_viirs"]["rho"] > 0
        # validación cruzada de área quemada: productos independientes acuerdan
        val = res["relaciones"]["validacion_area_quemada"]["mcd64a1_vs_firecci51"]
        assert val["rho"] > 0.7
        # desglose por cobertura presente
        assert res["cobertura_dominante_fuego"]

    def test_analisis_determinista(self):
        r1 = analizar_relaciones(ASOC / "asociacion_celda_mes.parquet", ASOC)
        r2 = analizar_relaciones(ASOC / "asociacion_celda_mes.parquet", ASOC)
        assert r1["relaciones"] == r2["relaciones"]


def _huella_contenido(parquet: Path) -> tuple:
    """Huella SEMÁNTICA del parquet (independiente de metadatos de escritura)."""
    import duckdb

    con = duckdb.connect()
    con.execute(f"CREATE TABLE t AS SELECT * FROM read_parquet('{parquet}')")
    try:
        n = con.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        agregados = con.execute(
            """
            SELECT SUM(obs_modis), SUM(obs_viirs), SUM(eventos),
                   ROUND(SUM(precip_mm), 3), ROUND(SUM(temp_media_c), 3),
                   ROUND(SUM(quemado_mcd64_km2), 3)
            FROM t
            """
        ).fetchone()
        return (n, agregados)
    finally:
        con.close()


@requires_real
def test_reconstruccion_end_to_end(tmp_path: Path):
    """La asociación es reproducible de punta a punta en un directorio nuevo.

    El contenido (filas y agregados) debe ser idéntico; los bytes del parquet
    pueden variar por metadatos de escritura (grupos de filas/compresión),
    por eso se compara la huella semántica y no el SHA-256 del archivo.
    """
    man = construir_asociacion(DUCKDB_REAL, ENV, EVENTOS, tmp_path)
    assert man["conciliacion"]["observaciones_asociadas"] == 2_691_999
    original = _huella_contenido(ASOC / "asociacion_celda_mes.parquet")
    reconstruido = _huella_contenido(tmp_path / "asociacion_celda_mes.parquet")
    assert reconstruido == original
