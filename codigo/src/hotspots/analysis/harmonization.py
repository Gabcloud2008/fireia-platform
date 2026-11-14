"""Armonización MODIS–VIIRS sobre la base real (Misión B de la finalización).

Construye el dataset versionado de pares de co-detección entre sensores
MODIS (Terra/Aqua, resolución 1 km) y VIIRS (NOAA-20/NOAA-21, 375 m), con
sensibilidad de parámetros, discrepancias y evidencia para la decisión
científica de armonización.

Decisiones metodológicas:

- **Superconjunto y derivación.** Se calcula UNA vez el superconjunto de
  pares con los umbrales más laxos del análisis de sensibilidad
  (``dt <= 900 s`` y ``dist <= 3000 m``) y las 9 combinaciones
  (300/600/900 s × 1/2/3 km) se derivan por filtrado — determinista y sin
  recomputar joins.
- **Semántica de emparejamiento M014.** El join es por igualdad de
  ``acq_date`` (la medianoche UTC es irrelevante para Paraguay: los pasos
  satelitales sobre el país ocurren entre ~01:20 y ~18:00 UTC; se verifica
  empíricamente y se documenta). La distancia es haversine esférica.
- **Sin forzar coincidencias.** Terra (paso ~13:30/01:30 UTC) no tiene
  solape temporal con VIIRS (~16:40/04:40 UTC): sus pares no existen por
  física orbital, no por falta de datos, y así se reporta.
- **Campos originales preservados.** Los productos, escalas de confianza
  (0-100 MODIS vs banda l/n/h VIIRS) y FRP de cada sensor viajan por
  separado; JAMÁS se suman FRP de sensores distintos ni se convierte la
  confianza a una escala común.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HARMONIZATION_VERSION = "armonizacion_v1"
METODO = "join_igualdad_fecha+haversine+ventana_dt"

# Grilla de sensibilidad exigida por la orden maestra.
SENSIBILIDAD_DT = (300, 600, 900)
SENSIBILIDAD_DIST = (1000, 2000, 3000)

# Parámetros canónicos del proyecto (M014 / configurables).
DT_CANONICO_S = 600
DIST_CANONICA_M = 2000


class HarmonizationError(Exception):
    """Error del módulo de armonización."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


SQL_PARES = """
SELECT
    m.obs_id            AS obs_id_modis,
    v.obs_id            AS obs_id_viirs,
    m.product           AS product_modis,
    v.product           AS product_viirs,
    m.satellite         AS satellite_modis,
    v.satellite         AS satellite_viirs,
    m.satellite_name    AS satellite_modis_nombre,
    v.satellite_name    AS satellite_viirs_nombre,
    m.acq_datetime_utc  AS acq_modis,
    v.acq_datetime_utc  AS acq_viirs,
    abs(date_diff('second', m.acq_datetime_utc, v.acq_datetime_utc)) AS dt_seconds,
    6371000 * 2 * asin(sqrt(
        pow(sin(radians(v.latitude - m.latitude) / 2), 2) +
        cos(radians(m.latitude)) * cos(radians(v.latitude)) *
        pow(sin(radians(v.longitude - m.longitude) / 2), 2)
    ))                   AS distance_m,
    m.frp               AS frp_modis,
    v.frp               AS frp_viirs,
    CAST(m.confidence AS BIGINT) AS confidence_modis,
    v.confidence        AS confidence_viirs,
    m.confidence_band   AS confidence_band_modis,
    v.confidence_band   AS confidence_band_viirs,
    m.daynight          AS daynight_modis,
    v.daynight          AS daynight_viirs,
    m.departamento      AS departamento,
    m.dentro_pais AND v.dentro_pais AS dentro_pais,
    m.source_file       AS source_file_modis,
    v.source_file       AS source_file_viirs,
    m.source_sha256     AS source_sha256_modis,
    v.source_sha256     AS source_sha256_viirs,
    m.year              AS year
FROM observations m
JOIN observations v
  ON m.acq_date = v.acq_date
 AND m.year = ?
 AND v.year = ?
 AND m.sensor = 'MODIS'
 AND v.sensor = 'VIIRS'
 AND abs(date_diff('second', m.acq_datetime_utc, v.acq_datetime_utc)) <= ?
 AND 6371000 * 2 * asin(sqrt(
      pow(sin(radians(v.latitude - m.latitude) / 2), 2) +
      cos(radians(m.latitude)) * cos(radians(v.latitude)) *
      pow(sin(radians(v.longitude - m.longitude) / 2), 2))) <= ?
"""


def compute_pairs(
    duckdb_real: str | Path,
    *,
    dt_max_s: int = 900,
    dist_max_m: int = 3000,
    con=None,
) -> tuple[Any, dict[str, Any]]:
    """Computa el superconjunto de pares MODIS×VIIRS año por año.

    Devuelve ``(tabla_duckdb_resultante, resumen)``. La tabla vive en la
    conexión ``con`` (transitoria) como ``pares_superconjunto``.
    """
    import duckdb

    own = con is None
    if own:
        con = duckdb.connect(str(duckdb_real), read_only=True)
    con.execute("DROP TABLE IF EXISTS pares_superconjunto")
    con.execute(
        """
        CREATE TEMP TABLE pares_superconjunto AS
        SELECT
            CAST('' AS VARCHAR) AS obs_id_modis, CAST('' AS VARCHAR) AS obs_id_viirs,
            CAST('' AS VARCHAR) AS product_modis, CAST('' AS VARCHAR) AS product_viirs,
            CAST('' AS VARCHAR) AS satellite_modis, CAST('' AS VARCHAR) AS satellite_viirs,
            CAST('' AS VARCHAR) AS satellite_modis_nombre,
            CAST('' AS VARCHAR) AS satellite_viirs_nombre,
            CAST(now() AS TIMESTAMP) AS acq_modis, CAST(now() AS TIMESTAMP) AS acq_viirs,
            CAST(0 AS INTEGER) AS dt_seconds, CAST(0.0 AS DOUBLE) AS distance_m,
            CAST(0.0 AS DOUBLE) AS frp_modis, CAST(0.0 AS DOUBLE) AS frp_viirs,
            CAST(0 AS BIGINT) AS confidence_modis,
            CAST('' AS VARCHAR) AS confidence_viirs,
            CAST('' AS VARCHAR) AS confidence_band_modis,
            CAST('' AS VARCHAR) AS confidence_band_viirs,
            CAST('' AS VARCHAR) AS daynight_modis, CAST('' AS VARCHAR) AS daynight_viirs,
            CAST('' AS VARCHAR) AS departamento, true AS dentro_pais,
            CAST('' AS VARCHAR) AS source_file_modis,
            CAST('' AS VARCHAR) AS source_file_viirs,
            CAST('' AS VARCHAR) AS source_sha256_modis,
            CAST('' AS VARCHAR) AS source_sha256_viirs,
            CAST(0 AS INTEGER) AS year
        WHERE false
        """
    )
    anios = [
        int(r[0])
        for r in con.execute("SELECT DISTINCT year FROM observations ORDER BY year").fetchall()
    ]
    detalle: dict[int, int] = {}
    for anio in anios:
        con.execute(
            f"INSERT INTO pares_superconjunto {SQL_PARES}",
            [anio, anio, dt_max_s, dist_max_m],
        )
        detalle[anio] = int(
            con.execute(
                "SELECT COUNT(*) FROM pares_superconjunto WHERE year = ?", [anio]
            ).fetchone()[0]
        )
        logger.info("pares %s: %s", anio, detalle[anio])
    total = int(con.execute("SELECT COUNT(*) FROM pares_superconjunto").fetchone()[0])
    resumen = {
        "version": HARMONIZATION_VERSION,
        "metodo": METODO,
        "parametros_superconjunto": {"dt_max_s": dt_max_s, "dist_max_m": dist_max_m},
        "anios": anios,
        "pares_por_anio": {str(k): v for k, v in detalle.items()},
        "total_pares": total,
    }
    if own:
        con.close()
    return "pares_superconjunto", resumen


def sensibilidad(con, tabla_pares: str = "pares_superconjunto") -> list[dict[str, Any]]:
    """Deriva las 9 combinaciones (300/600/900 s × 1/2/3 km) del superconjunto."""
    filas = []
    for dt in SENSIBILIDAD_DT:
        for dist in SENSIBILIDAD_DIST:
            r = con.execute(
                f"""
                SELECT COUNT(*) AS pares,
                       COUNT(DISTINCT obs_id_modis) AS modis_cubiertas,
                       COUNT(DISTINCT obs_id_viirs) AS viirs_cubiertas,
                       ROUND(AVG(distance_m), 1) AS dist_media,
                       ROUND(AVG(dt_seconds), 1) AS dt_medio
                FROM {tabla_pares}
                WHERE dt_seconds <= ? AND distance_m <= ?
                """,
                [dt, dist],
            ).fetchone()
            filas.append(
                {
                    "dt_seconds": dt,
                    "distance_m": dist,
                    "pares": int(r[0]),
                    "modis_cubiertas": int(r[1]),
                    "viirs_cubiertas": int(r[2]),
                    "dist_media_m": float(r[3] or 0),
                    "dt_medio_s": float(r[4] or 0),
                }
            )
    return filas


def cobertura_por_satelite(con, tabla_pares: str = "pares_superconjunto") -> list[dict]:
    return [
        {
            "satellite_modis": r[0],
            "satellite_viirs": r[1],
            "pares": int(r[2]),
            "dist_media_m": float(r[3] or 0),
            "dt_medio_s": float(r[4] or 0),
        }
        for r in con.execute(
            f"""
            SELECT satellite_modis, satellite_viirs, COUNT(*) n,
                   ROUND(AVG(distance_m),1), ROUND(AVG(dt_seconds),1)
            FROM {tabla_pares}
            WHERE dt_seconds <= {DT_CANONICO_S} AND distance_m <= {DIST_CANONICA_M}
            GROUP BY 1,2 ORDER BY n DESC
            """
        ).fetchall()
    ]


def discrepancias(
    con,
    tabla_pares: str = "pares_superconjunto",
    *,
    dt_s: int = DT_CANONICO_S,
    dist_m: int = DIST_CANONICA_M,
) -> dict[str, Any]:
    """Observaciones no emparejadas y análisis de discrepancias.

    Restringe el análisis de "no emparejadas" al periodo con ambos sensores
    activos (VIIRS desde 2018): un MODIS de 2005 sin par NO es una
    discrepancia, es historia pre-VIIRS.
    """
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE pares_canonicos AS
        SELECT * FROM {tabla_pares} WHERE dt_seconds <= {dt_s} AND distance_m <= {dist_m}
        """
    )
    # MODIS no emparejadas (2018+, año del primer VIIRS en la base)
    modis_total, modis_cub = con.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM observations WHERE sensor='MODIS' AND year >= 2018),
            (SELECT COUNT(DISTINCT obs_id_modis) FROM pares_canonicos)
        """
    ).fetchone()
    viirs_total, viirs_cub = con.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM observations WHERE sensor='VIIRS'),
            (SELECT COUNT(DISTINCT obs_id_viirs) FROM pares_canonicos)
        """
    ).fetchone()
    # perfil de las no emparejadas (por qué se pierden)
    perfil_modis = [
        {"satelite": r[0], "banda": r[1], "daynight": r[2], "n": int(r[3])}
        for r in con.execute(
            """
            SELECT m.satellite_name, m.confidence_band, m.daynight, COUNT(*) n
            FROM observations m
            WHERE m.sensor='MODIS' AND m.year >= 2018
              AND m.obs_id NOT IN (SELECT obs_id_modis FROM pares_canonicos)
            GROUP BY 1,2,3 ORDER BY n DESC LIMIT 30
            """
        ).fetchall()
    ]
    perfil_viirs = [
        {"satelite": r[0], "banda": r[1], "daynight": r[2], "n": int(r[3])}
        for r in con.execute(
            """
            SELECT v.satellite_name, v.confidence_band, v.daynight, COUNT(*) n
            FROM observations v
            WHERE v.sensor='VIIRS'
              AND v.obs_id NOT IN (SELECT obs_id_viirs FROM pares_canonicos)
            GROUP BY 1,2,3 ORDER BY n DESC LIMIT 30
            """
        ).fetchall()
    ]
    return {
        "parametros": {"dt_s": dt_s, "dist_m": dist_m},
        "modis": {
            "total_2018_mas": int(modis_total),
            "emparejadas": int(modis_cub),
            "no_emparejadas": int(modis_total - modis_cub),
            "pct_emparejadas": round(100 * modis_cub / modis_total, 2) if modis_total else 0,
        },
        "viirs": {
            "total": int(viirs_total),
            "emparejadas": int(viirs_cub),
            "no_emparejadas": int(viirs_total - viirs_cub),
            "pct_emparejadas": round(100 * viirs_cub / viirs_total, 2) if viirs_total else 0,
        },
        "perfil_no_emparejadas_modis": perfil_modis,
        "perfil_no_emparejadas_viirs": perfil_viirs,
    }


def analizar_pares(con, tabla_pares: str = "pares_superconjunto") -> dict[str, Any]:
    """Estadísticas de pares canónicos: dt, distancia, FRP, confianza."""
    q = con.execute(
        f"""
        SELECT
            COUNT(*),
            ROUND(AVG(dt_seconds),1), ROUND(median(dt_seconds),1),
            ROUND(AVG(distance_m),1), ROUND(median(distance_m),1),
            ROUND(AVG(frp_modis),2), ROUND(AVG(frp_viirs),2),
            ROUND(median(frp_modis),2), ROUND(median(frp_viirs),2),
            ROUND(AVG(CASE WHEN frp_modis > 0 AND frp_viirs > 0
                      THEN frp_modis / frp_viirs END),3),
            ROUND(median(CASE WHEN frp_modis > 0 AND frp_viirs > 0
                      THEN frp_modis / frp_viirs END),3)
        FROM {tabla_pares}
        WHERE dt_seconds <= {DT_CANONICO_S} AND distance_m <= {DIST_CANONICA_M}
        """
    ).fetchone()
    # distribución conjunta de bandas de confianza
    bandas = con.execute(
        f"""
        SELECT confidence_band_modis, confidence_band_viirs, COUNT(*) n
        FROM {tabla_pares}
        WHERE dt_seconds <= {DT_CANONICO_S} AND distance_m <= {DIST_CANONICA_M}
        GROUP BY 1,2 ORDER BY n DESC
        """
    ).fetchall()
    # decaimiento de pares por anillo de distancia (riesgo de emparejamiento falso)
    anillos = con.execute(
        f"""
        SELECT CAST(distance_m / 250 AS INTEGER) * 250 AS anillo_m, COUNT(*) n
        FROM {tabla_pares}
        WHERE dt_seconds <= {DT_CANONICO_S}
        GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    # día vs noche
    dn = con.execute(
        f"""
        SELECT daynight_modis, COUNT(*) n, ROUND(AVG(distance_m),1)
        FROM {tabla_pares}
        WHERE dt_seconds <= {DT_CANONICO_S} AND distance_m <= {DIST_CANONICA_M}
        GROUP BY 1
        """
    ).fetchall()
    return {
        "pares": int(q[0]),
        "dt": {"media_s": float(q[1]), "mediana_s": float(q[2])},
        "dist": {"media_m": float(q[3]), "mediana_m": float(q[4])},
        "frp": {
            "media_modis_mw": float(q[5]),
            "media_viirs_mw": float(q[6]),
            "mediana_modis_mw": float(q[7]),
            "mediana_viirs_mw": float(q[8]),
            "razon_media_modis_sobre_viirs": float(q[9] or 0),
            "razon_mediana_modis_sobre_viirs": float(q[10] or 0),
        },
        "bandas_confianza": [
            {"modis": b[0], "viirs": b[1], "n": int(b[2])} for b in bandas
        ],
        "anillos_distancia_250m": [
            {"anillo_m": int(a[0]), "pares": int(a[1])} for a in anillos
        ],
        "dia_noche": [
            {"daynight": d[0], "pares": int(d[1]), "dist_media_m": float(d[2])} for d in dn
        ],
    }


def verificar_medianoche_utc(con) -> dict[str, int]:
    """Observaciones a ±10 min de la medianoche UTC (posibles cruces de fecha)."""
    antes = con.execute(
        """
        SELECT COUNT(*) FROM observations
        WHERE EXTRACT(HOUR FROM acq_datetime_utc) = 23
          AND EXTRACT(MINUTE FROM acq_datetime_utc) >= 50
        """
    ).fetchone()[0]
    despues = con.execute(
        """
        SELECT COUNT(*) FROM observations
        WHERE EXTRACT(HOUR FROM acq_datetime_utc) = 0
          AND EXTRACT(MINUTE FROM acq_datetime_utc) <= 10
        """
    ).fetchone()[0]
    return {"obs_23_50_a_23_59_utc": int(antes), "obs_00_00_a_00_10_utc": int(despues)}


def exportar_armonizacion(
    duckdb_real: str | Path,
    salida_dir: str | Path,
    *,
    con=None,
) -> dict[str, Any]:
    """Pipeline completo: pares + sensibilidad + discrepancias + manifiesto.

    Escribe en ``salida_dir``:
    - ``pares_modis_viirs.parquet`` (superconjunto 900 s/3 km, particionado por año)
    - ``sensibilidad_9_combinaciones.csv``
    - ``discrepancias.json``
    - ``analisis_pares.json``
    - ``manifiesto_armonizacion_v1.json`` (SHA-256 de todo)
    """
    import duckdb

    salida = Path(salida_dir)
    salida.mkdir(parents=True, exist_ok=True)
    own = con is None
    if own:
        con = duckdb.connect(str(duckdb_real), read_only=True)
    try:
        _, resumen = compute_pairs(duckdb_real, con=con)
        sens = sensibilidad(con)
        disc = discrepancias(con)
        analisis = analizar_pares(con)
        medianoche = verificar_medianoche_utc(con)
        cobertura_sat = cobertura_por_satelite(con)

        # exportaciones
        pares_path = salida / "pares_modis_viirs.parquet"
        con.execute(
            f"""
            COPY (SELECT * FROM pares_superconjunto ORDER BY year, acq_modis)
            TO '{pares_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
        import csv

        sens_path = salida / "sensibilidad_9_combinaciones.csv"
        with sens_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(sens[0].keys()))
            w.writeheader()
            w.writerows(sens)
        disc_path = salida / "discrepancias.json"
        disc_path.write_text(json.dumps(disc, ensure_ascii=False, indent=1), encoding="utf-8")
        ana_path = salida / "analisis_pares.json"
        ana_path.write_text(
            json.dumps(
                {**analisis, "cobertura_por_satelite": cobertura_sat},
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        manifiesto = {
            "version": HARMONIZATION_VERSION,
            "creado_en_utc": _utc_now_iso(),
            "descripcion": (
                "Dataset versionado de pares y discrepancias MODIS-VIIRS"
                " (base real M014)"
            ),
            "metodo": METODO,
            "parametros_superconjunto": {"dt_max_s": 900, "dist_max_m": 3000},
            "parametros_canonicos": {"dt_s": DT_CANONICO_S, "dist_m": DIST_CANONICA_M},
            "grilla_sensibilidad": {
                "dt_s": list(SENSIBILIDAD_DT),
                "dist_m": list(SENSIBILIDAD_DIST),
            },
            "resumen": resumen,
            "medianoche_utc": medianoche,
            "artefactos": {},
        }
        for p in (pares_path, sens_path, disc_path, ana_path):
            manifiesto["artefactos"][p.name] = {
                "bytes": p.stat().st_size,
                "sha256": _sha256_file(p),
            }
        man_path = salida / "manifiesto_armonizacion_v1.json"
        man_path.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1), encoding="utf-8")
        return manifiesto
    finally:
        if own:
            con.close()
