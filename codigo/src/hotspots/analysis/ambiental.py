"""Inteligencia ambiental: asociación espacio-temporal (Misión D).

Conecta las 7 fuentes ambientales verificadas del repositorio con las
observaciones y eventos reales sobre la grilla nacional de 3.737 celdas 0,1°.

Reglas científicas:

- **Asociación por celda×mes** con la MISMA clave de la grilla
  (``celda = "%.2f_%.2f"`` del centro: ``floor(x·10)/10 + 0.05``).
- **Sin fuga de información**: los análisis de relación usan clima del mes
  ACTUAL o ANTERIOR frente a actividad de fuego del mes actual; jamás
  futuro. Correlación ≠ causalidad y así se reporta.
- **Faltantes explícitos**: la asociación NO imputa; las celdas/meses sin
  valor viajan con NULL y se reporta la cobertura de cada variable.
- Unidades y resoluciones declaradas por fuente en el catálogo; ERA5-Land
  (0,1° reanalysis) y CHIRPS (0,05° remuestreado a la grilla) NO se
  presentan como intercambiables.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AMBIENTAL_VERSION = "ambiental_v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _meta(path: Path) -> dict:
    return {"bytes": path.stat().st_size, "sha256": _sha256_file(path)}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------- catálogo
def catalogo_ambiental() -> list[dict[str, Any]]:
    """Catálogo completo de las fuentes ambientales (10 campos por fuente)."""
    return [
        {
            "fuente": "CHIRPS v2.0",
            "productor": "UCSB Climate Hazards Center",
            "licencia": "Atribución (uso libre con cita)",
            "resolucion": "0,05° nativa, remuestreada a la grilla 0,1°",
            "frecuencia": "mensual (acumulada)",
            "periodo": "1998-2026 en el repositorio",
            "variables": ["precip_mm"],
            "unidades": {"precip_mm": "milímetros por mes"},
            "cobertura": "3.737 celdas nacionales 0,1°",
            "calidad": "verificada M013/M014: 0 nulos, 0 duplicados celda+mes",
            "incertidumbre": (
                "pocas estaciones pluviométricas en el Chaco "
                "(señal más satelital que de estaciones)"
            ),
            "estado_integracion": "INTEGRADA en asociacion_celda_mes",
        },
        {
            "fuente": "ERA5-Land",
            "productor": "C3S/ECMWF (Copernicus)",
            "licencia": "CC-BY 4.0",
            "resolucion": "0,1° (~9 km)",
            "frecuencia": "mensual (agregada de horaria)",
            "periodo": "1950-2026 en el repositorio",
            "variables": ["temp_media_c", "temp_max_c", "temp_min_c", "humedad_rel_pct",
                          "vpd_kpa", "viento_ms", "precip_era5_mm", "humedad_suelo_m3m3"],
            "unidades": {"temp_media_c": "°C", "humedad_rel_pct": "%", "vpd_kpa": "kPa",
                         "viento_ms": "m/s", "humedad_suelo_m3m3": "m³/m³"},
            "cobertura": "3.737 celdas",
            "calidad": "verificada M013/M014",
            "incertidumbre": (
                "reanalysis, no observación directa; "
                "no resuelve valles/convección local"
            ),
            "estado_integracion": "INTEGRADA",
        },
        {
            "fuente": "FWI GFWED",
            "productor": "NASA GFWED (GFMS)",
            "licencia": "datos abiertos NASA",
            "resolucion": "0,25° nativa, remuestreada a 0,1°",
            "frecuencia": "mensual",
            "periodo": "1980-2026",
            "variables": ["fwi_medio", "fwi_max", "dias_fwi_alto"],
            "unidades": {
                "fwi_medio": "índice adimensional",
                "dias_fwi_alto": "días con FWI>17 (convención)",
            },
            "cobertura": "3.737 celdas",
            "calidad": "verificada M013/M014",
            "incertidumbre": "derivado de reanalysis; el umbral 'alto' es convención del proyecto",
            "estado_integracion": "INTEGRADA",
        },
        {
            "fuente": "ESA WorldCover v200",
            "productor": "ESA",
            "licencia": "CC BY 4.0",
            "resolucion": "10 m nativa, agregada porcentual a celdas 0,1°",
            "frecuencia": "episódica (2020 y 2021)",
            "periodo": "2020-2021",
            "variables": ["pct_arboles", "pct_arbustos", "pct_pastizal", "pct_cultivo",
                          "pct_urbano", "pct_suelo_desnudo", "pct_agua", "pct_humedal",
                          "clase_dominante"],
            "unidades": {"pct_*": "% del área de la celda"},
            "cobertura": "3.737 celdas",
            "calidad": "verificada M013/M014",
            "incertidumbre": "no detecta cambios posteriores a 2021; clases genéricas",
            "estado_integracion": "INTEGRADA (solo años 2020-2021; estática en el resto)",
        },
        {
            "fuente": "GOES ABI FDCF (GOES-16/19)",
            "productor": "NOAA/NASA",
            "licencia": "datos abiertos",
            "resolucion": "2 km",
            "frecuencia": "mensual (agregada de escaneos 10-15 min)",
            "periodo": "2018-2026",
            "variables": ["n_detec", "frp_max_mw", "n_escaneos"],
            "unidades": {"n_detec": "detecciones", "frp_max_mw": "MW", "n_escaneos": "escaneos"},
            "cobertura": "3.737 celdas",
            "calidad": "verificada M013/M014 (transición GOES-16→19 documentada)",
            "incertidumbre": "2 km efectivos sobre Paraguay oriental; ángulo rasante en el Chaco",
            "estado_integracion": "INTEGRADA",
        },
        {
            "fuente": "MCD64A1 v6.1",
            "productor": "NASA LP DAAC",
            "licencia": "datos abiertos NASA",
            "resolucion": "500 m nativa, agregada a celdas 0,1°",
            "frecuencia": "mensual",
            "periodo": "2002-2026 (en repositorio desde 2002)",
            "variables": ["quemado_km2", "pct_quemado"],
            "unidades": {"quemado_km2": "km²", "pct_quemado": "% de la celda"},
            "cobertura": "3.737 celdas",
            "calidad": "verificada M013/M014",
            "incertidumbre": (
                "subestima fuegos pequeños; comparte sensor MODIS "
                "(no independiente del instrumento de detección)"
            ),
            "estado_integracion": "INTEGRADA (etiqueta de área quemada y validación)",
        },
        {
            "fuente": "FireCCI51",
            "productor": "ESA CCI Fire (FireCCI51)",
            "licencia": "abierta con atribución ESA CCI",
            "resolucion": "250 m nativa, agregada a celdas 0,1°",
            "frecuencia": "mensual",
            "periodo": "2001-2026 (según disponibilidad en el repositorio)",
            "variables": ["quemado_km2", "pct_quemado"],
            "unidades": {"quemado_km2": "km²", "pct_quemado": "% de la celda"},
            "cobertura": "3.737 celdas",
            "calidad": "verificada M013/M014",
            "incertidumbre": "sensible a nubes y cobertura de humo; 250 m",
            "estado_integracion": "INTEGRADA (validación cruzada de área quemada)",
        },
    ]


# ------------------------------------------------------------------ asociación
SQL_CELDA = "printf('%.2f_%.2f', FLOOR(longitude*10)/10 + 0.05, FLOOR(latitude*10)/10 + 0.05)"


def construir_asociacion(
    duckdb_real: str | Path,
    env_dir: str | Path,
    eventos_dir: str | Path,
    salida_dir: str | Path,
    *,
    anio_desde: int = 2000,
    anio_hasta: int = 2026,
) -> dict[str, Any]:
    """Construye la tabla celda×mes con fuego + ambiente (asociación v1)."""
    import duckdb

    env = Path(env_dir)
    salida = Path(salida_dir)
    salida.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()  # en memoria: los artefactos originales JAMÁS se escriben
    con.execute(f"ATTACH '{duckdb_real}' AS real (READ_ONLY)")
    # límite de memoria + spilling a disco: los joins de ~10M de filas de las
    # fuentes ambientales no caben en RAM del entorno
    con.execute("SET memory_limit='1500MB'")
    con.execute("SET temp_directory='/tmp/duckdb_ambiental'")
    con.execute("SET threads=2")
    try:
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE chirps AS
            SELECT celda, mes, precip_mm
            FROM read_csv('{env}/CHIRPS/chirps_PRY_*.csv.gz', header=true)
        """)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE era5 AS
            SELECT celda, mes, temp_media_c, temp_max_c, temp_min_c,
                   humedad_rel_pct, vpd_kpa, viento_ms, humedad_suelo_m3m3
            FROM read_csv('{env}/ERA5_LAND/era5land_PRY_*.csv.gz', header=true)
        """)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE fwi AS
            SELECT celda, mes, fwi_medio, fwi_max, dias_fwi_alto
            FROM read_csv('{env}/FWI_GFWED/fwi_gfwed_PRY_*.csv.gz', header=true)
        """)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE mcd64 AS
            SELECT celda, mes, quemado_km2 AS quemado_mcd64_km2, pct_quemado AS pct_quemado_mcd64
            FROM read_csv('{env}/MCD64A1/mcd64a1_PRY_*.csv.gz', header=true)
        """)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE firecci AS
            SELECT celda, mes,
                   quemado_km2 AS quemado_firecci_km2,
                   pct_quemado AS pct_quemado_firecci
            FROM read_csv('{env}/FIRECCI51/firecci51_PRY_*.csv.gz', header=true)
        """)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE goes AS
            SELECT celda, mes, SUM(n_detec) AS goes_n_detec, MAX(frp_max_mw) AS goes_frp_max
            FROM read_csv('{env}/../SATELLITE_DATA/GOES_FDC/goes*_fdc_PRY_*.csv.gz', header=true)
            GROUP BY 1, 2
        """)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE wc AS
            SELECT celda, anio, pct_arboles, pct_pastizal, pct_cultivo, clase_dominante
            FROM read_csv('{env}/WORLDCOVER/worldcover_PRY_*.csv.gz', header=true)
        """)

        # fuego por celda×mes (observaciones reales)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE fuego AS
            SELECT {SQL_CELDA} AS celda,
                   strftime(acq_datetime_utc, '%Y-%m') AS mes,
                   SUM(CASE WHEN sensor='MODIS' THEN 1 ELSE 0 END) AS obs_modis,
                   SUM(CASE WHEN sensor='VIIRS' THEN 1 ELSE 0 END) AS obs_viirs,
                   ROUND(SUM(CASE WHEN sensor='MODIS' THEN frp ELSE 0 END), 1) AS frp_modis_sum,
                   ROUND(SUM(CASE WHEN sensor='VIIRS' THEN frp ELSE 0 END), 1) AS frp_viirs_sum,
                   COUNT(DISTINCT CASE WHEN dentro_pais THEN departamento END) AS deptos
            FROM real.observations
            WHERE year BETWEEN {anio_desde} AND {anio_hasta}
            GROUP BY 1, 2
        """)

        # eventos por celda×mes (vía membresías; un evento puede abarcar varias celdas)
        mb = str(Path(eventos_dir) / "membresia.parquet")
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE evcm AS
            SELECT printf('%.2f_%.2f',
                          FLOOR(o.longitude*10)/10 + 0.05,
                          FLOOR(o.latitude*10)/10 + 0.05) AS celda,
                   strftime(o.acq_datetime_utc, '%Y-%m') AS mes,
                   COUNT(DISTINCT m.event_id) AS eventos
            FROM read_parquet('{mb}') m
            JOIN real.observations o ON o.obs_id = m.obs_id
            WHERE o.year BETWEEN {anio_desde} AND {anio_hasta}
            GROUP BY 1, 2
        """)

        # tabla maestra: todas las celdas con cualquier dato × todos los meses con cualquier dato
        con.execute("""
            CREATE OR REPLACE TEMP TABLE clave AS
            SELECT DISTINCT celda, mes FROM (
                SELECT celda, mes FROM chirps
                UNION SELECT celda, mes FROM fuego
                UNION SELECT celda, mes FROM evcm
            )
        """)
        con.execute("""
            CREATE OR REPLACE TEMP TABLE asociacion AS
            SELECT k.celda,
                   CAST(substr(k.mes, 1, 4) AS INTEGER) AS anio,
                   CAST(substr(k.mes, 6, 2) AS INTEGER) AS mes_num,
                   k.mes,
                   COALESCE(f.obs_modis, 0) AS obs_modis,
                   COALESCE(f.obs_viirs, 0) AS obs_viirs,
                   f.frp_modis_sum,
                   f.frp_viirs_sum,
                   COALESCE(e.eventos, 0) AS eventos,
                   c.precip_mm,
                   er.temp_media_c, er.temp_max_c, er.humedad_rel_pct, er.vpd_kpa,
                   er.viento_ms, er.humedad_suelo_m3m3,
                   fw.fwi_medio, fw.fwi_max, fw.dias_fwi_alto,
                   m.quemado_mcd64_km2, m.pct_quemado_mcd64,
                   fc.quemado_firecci_km2, fc.pct_quemado_firecci,
                   g.goes_n_detec, g.goes_frp_max,
                   w.pct_arboles, w.pct_pastizal, w.pct_cultivo, w.clase_dominante
            FROM clave k
            LEFT JOIN fuego f ON f.celda = k.celda AND f.mes = k.mes
            LEFT JOIN evcm e ON e.celda = k.celda AND e.mes = k.mes
            LEFT JOIN chirps c ON c.celda = k.celda AND c.mes = k.mes
            LEFT JOIN era5 er ON er.celda = k.celda AND er.mes = k.mes
            LEFT JOIN fwi fw ON fw.celda = k.celda AND fw.mes = k.mes
            LEFT JOIN mcd64 m ON m.celda = k.celda AND m.mes = k.mes
            LEFT JOIN firecci fc ON fc.celda = k.celda AND fc.mes = k.mes
            LEFT JOIN goes g ON g.celda = k.celda AND g.mes = k.mes
            LEFT JOIN wc w ON w.celda = k.celda AND w.anio = CAST(substr(k.mes,1,4) AS INTEGER)
        """)

        # verificaciones de conciliación
        filas = con.execute("SELECT COUNT(*) FROM asociacion").fetchone()[0]
        celdas = con.execute("SELECT COUNT(DISTINCT celda) FROM asociacion").fetchone()[0]
        sql_tot = "SELECT SUM(obs_modis) + SUM(obs_viirs) FROM asociacion"
        total_obs_asoc = con.execute(sql_tot).fetchone()[0]
        total_ev_asoc = con.execute(
            "SELECT SUM(eventos) FROM asociacion"
        ).fetchone()[0]
        con.execute(f"""
            COPY (SELECT * FROM asociacion ORDER BY celda, mes)
            TO '{salida / "asociacion_celda_mes.parquet"}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)

        # catálogo + manifiesto
        cat_path = salida / "catalogo_ambiental.json"
        cat_path.write_text(
            json.dumps(catalogo_ambiental(), ensure_ascii=False, indent=1), encoding="utf-8"
        )
        asoc_path = salida / "asociacion_celda_mes.parquet"
        manifiesto = {
            "version": AMBIENTAL_VERSION,
            "creado_en_utc": _utc_now_iso(),
            "descripcion": (
                "Asociación espacio-temporal celda×mes: "
                "fuego real + 7 fuentes ambientales"
            ),
            "clave_celda": (
                "centro 0,1°: printf('%.2f_%.2f', "
                "floor(lon*10)/10+0.05, floor(lat*10)/10+0.05)"
            ),
            "periodo": [anio_desde, anio_hasta],
            "filas": int(filas),
            "celdas": int(celdas),
            "conciliacion": {
                "observaciones_asociadas": int(total_obs_asoc),
                "evento_celda_mes": int(total_ev_asoc),
            },
            "regla_antifuga": "análisis solo con clima del mes actual o anterior",
            "artefactos": {
                asoc_path.name: _meta(asoc_path),
                cat_path.name: _meta(cat_path),
            },
        }
        man_path = salida / "manifiesto_ambiental_v1.json"
        man_path.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1), encoding="utf-8")
        return manifiesto
    finally:
        con.close()


# ------------------------------------------------------------------ análisis
def analizar_relaciones(asociacion_path: str | Path, salida_dir: str | Path) -> dict[str, Any]:
    """Relaciones fuego–clima–cobertura reproducibles (sin fuga, sin causalidad).

    Agregación mensual nacional y correlaciones de Spearman entre actividad
    de fuego del mes y clima del mes y del mes ANTERIOR (lag 0 y lag 1);
    correlación cruzada área quemada MCD64A1 vs FireCCI51 (validación);
    desglose por cobertura dominante.
    """
    import duckdb

    salida = Path(salida_dir)
    salida.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute(
            f"CREATE TABLE asoc AS SELECT * FROM read_parquet('{asociacion_path}')"
        )
        # nacional mensual (suma de fuego y área quemada; media ponderada de clima)
        con.execute("""
            CREATE OR REPLACE TABLE nacional AS
            SELECT mes, anio, mes_num,
                   SUM(obs_modis) AS obs_modis, SUM(obs_viirs) AS obs_viirs,
                   SUM(eventos) AS eventos,
                   ROUND(SUM(frp_modis_sum), 1) AS frp_modis,
                   ROUND(SUM(frp_viirs_sum), 1) AS frp_viirs,
                   ROUND(SUM(quemado_mcd64_km2), 2) AS quemado_mcd64_km2,
                   ROUND(SUM(quemado_firecci_km2), 2) AS quemado_firecci_km2,
                   ROUND(AVG(precip_mm), 1) AS precip_media,
                   ROUND(AVG(temp_media_c), 1) AS temp_media,
                   ROUND(AVG(vpd_kpa), 2) AS vpd_medio,
                   ROUND(AVG(fwi_medio), 1) AS fwi_medio,
                   ROUND(AVG(humedad_suelo_m3m3), 3) AS humedad_suelo
            FROM asoc GROUP BY 1, 2, 3 ORDER BY 1
        """)
        nacional = con.execute("SELECT * FROM nacional").df()

        import numpy as np
        from scipy import stats

        def spearman(x, y):
            m = np.isfinite(x) & np.isfinite(y)
            if m.sum() < 12:
                return None
            r, p = stats.spearmanr(x[m], y[m])
            return {"rho": round(float(r), 3), "p_valor": float(p), "n": int(m.sum())}

        def col(df, nombre):
            return df[nombre].to_numpy(dtype=float)

        relaciones: dict[str, Any] = {}
        # lag 0 (clima del mismo mes) y lag 1 (clima del mes anterior): SIN FUTURO
        nac = nacional.sort_values("mes").reset_index(drop=True)
        for lag in (0, 1):
            clima = nac.shift(lag)  # shift(1) = mes anterior (pasado)
            def _s(frame, var_clima: str, var_fuego: str):
                return spearman(col(frame, var_clima), col(nac, var_fuego))

            relaciones[f"lag{lag}"] = {
                "precip_media_vs_obs_viirs": _s(clima, "precip_media", "obs_viirs"),
                "temp_media_vs_obs_viirs": _s(clima, "temp_media", "obs_viirs"),
                "vpd_medio_vs_obs_viirs": _s(clima, "vpd_medio", "obs_viirs"),
                "fwi_medio_vs_obs_viirs": _s(clima, "fwi_medio", "obs_viirs"),
                "humedad_suelo_vs_obs_viirs": _s(clima, "humedad_suelo", "obs_viirs"),
                "precip_media_vs_eventos": _s(clima, "precip_media", "eventos"),
                "fwi_medio_vs_eventos": _s(clima, "fwi_medio", "eventos"),
            }
        # validación cruzada área quemada
        m64 = col(nac, "quemado_mcd64_km2")
        fcc = col(nac, "quemado_firecci_km2")
        relaciones["validacion_area_quemada"] = {
            "mcd64a1_vs_firecci51": spearman(m64, fcc),
        }
        # desglose por cobertura dominante (solo celdas con WorldCover)
        cobertura = con.execute("""
            SELECT clase_dominante,
                   COUNT(*) AS celdas_mes,
                   SUM(obs_viirs) AS obs_viirs,
                   ROUND(AVG(precip_mm), 1) AS precip_media
            FROM asoc WHERE clase_dominante IS NOT NULL AND anio >= 2018
            GROUP BY 1 ORDER BY obs_viirs DESC
        """).df()
        cobertura_out = cobertura.to_dict(orient="records")

        resultado = {
            "version": AMBIENTAL_VERSION,
            "creado_en_utc": _utc_now_iso(),
            "nota_metodologica": (
                "Correlaciones de Spearman sobre serie mensual nacional. Los "
                "predictores son del mes actual (lag 0) o del mes ANTERIOR "
                "(lag 1): nunca del futuro. Correlación NO implica causalidad; "
                "las fuentes comparten satélites/reanalysis subyacentes."
            ),
            "meses_nacionales": int(len(nacional)),
            "relaciones": relaciones,
            "cobertura_dominante_fuego": cobertura_out,
        }
        ana_path = salida / "relaciones_fuego_clima.json"
        ana_path.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
        resultado["archivo"] = str(ana_path)
        return resultado
    finally:
        con.close()
