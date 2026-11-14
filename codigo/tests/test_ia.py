"""Pruebas de la IA predictiva (Misión E): dataset, anti-fuga, métricas, modelos."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hotspots.analysis.prediccion import (
    ETIQUETA,
    FEATURES,
    _metricas,
    construir_dataset,
    entrenar_evaluar,
    exportar_artefactos,
    particiones,
)

RAIZ = Path(__file__).resolve().parents[2]
ASOC = RAIZ / "data" / "PROCESADA" / "ambiental_v1" / "asociacion_celda_mes.parquet"

requires_real = pytest.mark.skipif(
    not ASOC.exists(), reason="asociación ambiental no disponible en este entorno",
)


# ------------------------------------------------------------------ fixtures
def _mini_asociacion(path: Path) -> Path:
    """Asociación sintética: 4 celdas × 48 meses (2022-01..2025-12).

    Fuego determinista en temporada seca (agos-oct) de celdas pares;
    clima correlacionado con la temporada. Esquema = asociación real.
    """
    rng = np.random.default_rng(42)
    celdas = ["-57.65_-27.30", "-57.55_-27.20", "-58.15_-24.10", "-58.05_-24.00"]
    meses = pd.period_range("2022-01", "2025-12", freq="M")
    filas = []
    for celda in celdas:
        quema = int(celda.split("_")[1].split(".")[1][0]) % 2 == 0
        for p in meses:
            m = p.month
            seca = m in (8, 9, 10)
            fuego = quema and seca
            filas.append({
                "celda": celda, "anio": p.year, "mes_num": m, "mes": str(p),
                "obs_modis": float(fuego * 3), "obs_viirs": float(fuego * 10),
                "frp_modis_sum": float(fuego * 30), "frp_viirs_sum": float(fuego * 9),
                "eventos": int(fuego),
                "precip_mm": (5.0 if seca else 120.0) + rng.normal(0, 2),
                "temp_media_c": (24.0 if seca else 19.0) + rng.normal(0, 0.5),
                "temp_max_c": 31.0, "humedad_rel_pct": 40.0,
                "vpd_kpa": (1.8 if seca else 0.6) + rng.normal(0, 0.05),
                "viento_ms": 3.0, "humedad_suelo_m3m3": (0.18 if seca else 0.35),
                "fwi_medio": (9.0 if seca else 1.5) + rng.normal(0, 0.3),
                "fwi_max": 12.0, "dias_fwi_alto": float(fuego * 10),
                "quemado_mcd64_km2": 0.0, "pct_quemado_mcd64": 0.0,
                "quemado_firecci_km2": 0.0, "pct_quemado_firecci": 0.0,
                "goes_n_detec": 0.0, "goes_frp_max": 0.0,
                "pct_arboles": 15.0, "pct_pastizal": 45.0, "pct_cultivo": 30.0,
                "clase_dominante": "Pastizal",
            })
    df = pd.DataFrame(filas)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


@pytest.fixture(scope="module")
def mini_ds(tmp_path_factory):
    p = _mini_asociacion(tmp_path_factory.mktemp("ia") / "mini_asoc.parquet")
    ds = construir_dataset(p)
    return {"ds": ds, "origen": p}


# ------------------------------------------------------------------ dataset
class TestDataset:
    def test_estructura(self, mini_ds):
        df, meta = mini_ds["ds"]["df"], mini_ds["ds"]["meta"]
        assert set(FEATURES).issubset(df.columns)
        assert ETIQUETA in df.columns
        assert df[FEATURES].isna().sum().sum() == 0
        assert set(df[ETIQUETA].unique()).issubset({0, 1})
        assert meta["filas"] == len(df)
        assert meta["celdas"] == 4
        assert meta["positivos"] == int(df[ETIQUETA].sum())
        assert 0 < meta["tasa_positivos"] < 1
        assert "regla_antifuga" in meta

    def test_antifuga_etiqueta_es_t_mas_1(self, mini_ds):
        """Etiqueta(t) == 1 sii obs_viirs(t+1) > 0, reconstruido desde el parquet."""
        df = mini_ds["ds"]["df"]
        fuente = pd.read_parquet(mini_ds["origen"]).set_index(["celda", "mes"])
        for _, fila in df.iterrows():
            prox = fuente.loc[(fila["celda"], _mes_siguiente(fila["mes"]))]
            esperado = 1 if float(prox["obs_viirs"]) > 0 else 0
            assert int(fila[ETIQUETA]) == esperado, (
                f"fuga en {fila['celda']} {fila['mes']}"
            )

    def test_ultima_fila_excluida_por_etiqueta_desconocida(self, mini_ds):
        d = mini_ds["ds"]["df"]
        assert d["mes"].max() < "2025-12"

    def test_particiones(self, mini_ds):
        partes = particiones(mini_ds["ds"]["df"])
        ent, val, tst = partes["entrenamiento"], partes["validacion"], partes["evaluacion"]
        assert ent["mes"].max() <= "2023-12"
        assert val["mes"].min() >= "2024-01" and val["mes"].max() <= "2024-12"
        assert tst["mes"].min() >= "2025-01"
        assert len(ent) > 0 and len(val) > 0 and len(tst) > 0
        # sin solape temporal
        assert set(ent["celda"] + ent["mes"]).isdisjoint(set(val["celda"] + val["mes"]))
        assert set(val["celda"] + val["mes"]).isdisjoint(set(tst["celda"] + tst["mes"]))
        assert set(partes["grupo_geografico"]).issubset({0, 1, 2, 3, 4})


# ------------------------------------------------------------------ métricas
class TestMetricas:
    def test_clasificador_perfecto(self):
        y = np.array([0, 0, 1, 1, 1, 0])
        p = np.array([0.01, 0.2, 0.9, 0.95, 0.8, 0.05])
        m = _metricas(y, p)
        assert m["roc_auc"] == 1.0
        assert m["pr_auc"] == 1.0
        assert m["matriz_confusion"] == [[3, 0], [0, 3]]

    def test_aleatorio(self):
        y = np.array([0, 1, 0, 1, 0, 1])
        p = np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
        m = _metricas(y, p)
        assert abs(m["roc_auc"] - 0.5) < 1e-9
        assert abs(m["brier"] - 0.25) < 1e-9

    def test_calibracion_bins_suma_n(self):
        rng = np.random.default_rng(1)
        y = rng.integers(0, 2, 500)
        p = rng.random(500)
        m = _metricas(y, p)
        assert sum(b["n"] for b in m["calibracion_bins"]) == 500
        assert 0 <= m["ece"] <= 1


# ------------------------------------------------------------------ modelos
class TestEntrenamiento:
    def test_cinco_modelos_evaluados(self, mini_ds):
        res = entrenar_evaluar(mini_ds["ds"])
        esperados = {
            "baseline_climatologia", "baseline_persistencia",
            "regresion_logistica", "random_forest", "gradient_boosting",
        }
        assert esperados == set(res["modelos"])
        for nombre, r in res["modelos"].items():
            for parte in ("validacion", "evaluacion"):
                mtr = r[parte]
                assert np.isfinite(mtr["roc_auc"]), nombre
                assert np.isfinite(mtr["pr_auc"]), nombre
                assert np.isfinite(mtr["brier"]), nombre
                assert 0 <= mtr["roc_auc"] <= 1
                assert mtr["n"] > 0
        assert res["mejor_modelo_por_validacion"] in res["modelos"]
        assert len(res["importancia_variables_random_forest"]) == len(FEATURES)
        assert "_modelos_ajustados" in res

    def test_semilla_reproducible(self, mini_ds):
        r1 = entrenar_evaluar(mini_ds["ds"], seed=7)
        r2 = entrenar_evaluar(mini_ds["ds"], seed=7)
        a1 = r1["modelos"]["random_forest"]["evaluacion"]["roc_auc"]
        a2 = r2["modelos"]["random_forest"]["evaluacion"]["roc_auc"]
        assert a1 == a2


# ------------------------------------------------------------------ export
class TestExport:
    def test_artefactos_y_manifiesto(self, mini_ds, tmp_path):
        res = entrenar_evaluar(mini_ds["ds"])
        man = exportar_artefactos(res, mini_ds["ds"], tmp_path / "ia_v1", mini_ds["origen"])
        salida = tmp_path / "ia_v1"
        for nombre in (
            "metricas_ia.json", "dataset_riesgo_celda_mes.parquet",
            "modelo_random_forest.joblib", "modelo_gradient_boosting.joblib",
        ):
            assert (salida / nombre).exists(), f"falta {nombre}"
            reg = man["artefactos"][nombre]
            h = hashlib.sha256((salida / nombre).read_bytes()).hexdigest()
            assert reg["sha256"] == h, f"sha256 no coincide para {nombre}"
            assert reg["bytes"] == (salida / nombre).stat().st_size
        # el manifiesto existe pero no se auto-hasha (auto-referencia imposible)
        assert (salida / "manifiesto_ia_v1.json").exists()
        assert "manifiesto_ia_v1.json" not in man["artefactos"]
        met = json.loads((salida / "metricas_ia.json").read_text(encoding="utf-8"))
        assert met["version"] == man["version"]
        assert met["semilla"] == man["semilla"]


# ------------------------------------------------------------------ reales
@requires_real
class TestDatasetReal:
    def test_dataset_real_trafactable(self):
        out = construir_dataset(ASOC)
        df, meta = out["df"], out["meta"]
        assert meta["celdas"] == 3_737  # grilla completa; 2 celdas de borde sin FWI
        # 81 meses × 3.739 celdas − filas con clima incompleto (FWI termina
        # 2026-04; sin imputación) − etiquetas desconocidas del último mes
        assert meta["filas"] == 284_012
        assert meta["filas_excluidas"]["clima_o_etiqueta_incompletos"] > 0
        assert 0 < meta["tasa_positivos"] < 0.5
        assert df[FEATURES].isna().sum().sum() == 0

    def test_antifuga_en_datos_reales(self):
        """Etiqueta reconstruida a mano coincide con la del dataset (fuga=0)."""
        import duckdb

        out = construir_dataset(ASOC)
        df = out["df"]
        con = duckdb.connect()
        con.execute(f"CREATE TABLE a AS SELECT * FROM read_parquet('{ASOC}')")
        muestra = df.sample(min(200, len(df)), random_state=0)
        for _, fila in muestra.iterrows():
            prox = con.execute(
                "SELECT obs_viirs FROM a WHERE celda=? AND mes=?",
                [fila["celda"], _mes_siguiente(fila["mes"])],
            ).fetchone()
            esperado = 1 if (prox and prox[0] and prox[0] > 0) else 0
            assert int(fila[ETIQUETA]) == esperado
        con.close()


def _mes_siguiente(mes: str) -> str:
    anio, m = int(mes[:4]), int(mes[5:7])
    return f"{anio + 1}-01" if m == 12 else f"{anio}-{m + 1:02d}"
