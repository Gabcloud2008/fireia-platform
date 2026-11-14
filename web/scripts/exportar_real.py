"""Exporta los datos REALES de FIREIA a JSON para la plataforma web (Misión F).

Origen (solo lectura, nunca se modifican):
  - data/PROCESADA/hotspots_real.duckdb      (Misión A — 2.691.999 obs)
  - data/PROCESADA/eventos_v1/               (Misión C — 19.747 eventos)
  - data/PROCESADA/armonizacion_v1/          (Misión B — 277.933 pares canónicos)
  - data/PROCESADA/ambiental_v1/             (Misión D — asociación celda×mes)
  - data/PROCESADA/ia_v1/                    (Misión E — modelos evaluados)
  - data/PROCESADA/base_real_v1/             (M014 — manifiesto con SHA-256)

Salida: web/src/data/real/ (JSON con data_source="real" y manifiesto SHA-256).

Política de tamaño: la web NUNCA recibe millones de puntos. Se exportan
muestras operativas etiquetadas + series agregadas completas.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

REPO = Path("/home/z/my-project/modis-viirs-hotspots-paraguay")
OUT = REPO / "web" / "src" / "data" / "real"
OUT.mkdir(parents=True, exist_ok=True)

DB = REPO / "data" / "PROCESADA" / "hotspots_real.duckdb"
EV = REPO / "data" / "PROCESADA" / "eventos_v1"
AR = REPO / "data" / "PROCESADA" / "armonizacion_v1"
AM = REPO / "data" / "PROCESADA" / "ambiental_v1"
IA = REPO / "data" / "PROCESADA" / "ia_v1"
BR = REPO / "data" / "PROCESADA" / "base_real_v1"

# Parámetros de muestra operativa (documentados en meta)
DIAS_MUESTRA_OBS = 30
CAP_OBS = 8_000
CAP_EVENTOS = 800
CAP_MIEMBROS_EVENTO = 25
DIAS_SERIE_DIARIA = 366


def rows(con: duckdb.DuckDBPyConnection, sql: str, params=None) -> list[dict]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _json_default(o):
    if isinstance(o, (datetime,)):
        return o.isoformat(timespec="seconds")
    if hasattr(o, "isoformat"):  # date
        return o.isoformat()
    if isinstance(o, (bytes,)):
        return o.hex()
    raise TypeError(f"no serializable: {type(o)}")


def jdump(nombre: str, data) -> Path:
    p = OUT / nombre
    p.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=_json_default),
        encoding="utf-8",
    )
    print(f"  {nombre}: {p.stat().st_size / 1024:.0f} KB")
    return p


def man_fuentes() -> dict:
    man = json.loads((BR / "manifiesto_base_real.json").read_text(encoding="utf-8"))
    return man.get("fuentes", {})


# --------------------------------------------------------------------- almacén
def exportar_almacen() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    rango = con.execute(
        "SELECT MIN(acq_date), MAX(acq_date), COUNT(*), COUNT(DISTINCT acq_date) FROM observations"
    ).fetchone()

    # --- muestra operativa: últimos 30 días, cap 12.000 estratificado
    fecha_max = datetime.strptime(rango[1], "%Y-%m-%d").date()
    fecha_desde = (fecha_max - timedelta(days=DIAS_MUESTRA_OBS - 1)).isoformat()
    n_rec = con.execute(
        "SELECT COUNT(*) FROM observations WHERE acq_date >= ?", [fecha_desde]
    ).fetchone()[0]
    if n_rec <= CAP_OBS:
        obs = rows(
            con,
            """SELECT obs_id, product, sensor, satellite, satellite_name, instrument,
                      latitude, longitude, acq_date, acq_time, acq_datetime_utc,
                      confidence, confidence_band, frp, brightness, bright_t31,
                      bright_ti4, bright_ti5, scan, track, daynight, version,
                      dentro_pais, departamento
               FROM observations WHERE acq_date >= ? ORDER BY acq_datetime_utc""",
            [fecha_desde],
        )
    else:
        obs = rows(
            con,
            f"""SELECT * FROM (
                    SELECT obs_id, product, sensor, satellite, satellite_name, instrument,
                           latitude, longitude, acq_date, acq_time, acq_datetime_utc,
                           confidence, confidence_band, frp, brightness, bright_t31,
                           bright_ti4, bright_ti5, scan, track, daynight, version,
                           dentro_pais, departamento
                    FROM observations WHERE acq_date >= ?
                    ORDER BY hash(obs_id) LIMIT {CAP_OBS}
                ) ORDER BY acq_datetime_utc""",
            [fecha_desde],
        )
    for o in obs:
        o["distrito"] = None
        o["version_limites"] = "geoBoundaries gbOpen PRY-9469f09 (ADM1)"
        o["latitude"] = round(float(o["latitude"]), 5)
        o["longitude"] = round(float(o["longitude"]), 5)
        for c in ("frp", "brightness", "bright_t31", "bright_ti4", "bright_ti5", "scan", "track"):
            if o.get(c) is not None:
                o[c] = round(float(o[c]), 2)

    # --- series estadísticas
    fecha_serie = (fecha_max - timedelta(days=DIAS_SERIE_DIARIA - 1)).isoformat()
    nacional_dia = rows(
        con,
        """SELECT acq_date, product, COUNT(*) AS detecciones, SUM(frp) AS frp_total
           FROM observations WHERE acq_date >= ? GROUP BY 1, 2 ORDER BY 1, 2""",
        [fecha_serie],
    )
    nacional_mes = rows(
        con,
        """SELECT substr(acq_date, 1, 7) AS mes,
                  CASE WHEN sensor='MODIS' THEN 'MODIS' ELSE 'VIIRS' END AS sensor,
                  COUNT(*) AS detecciones, SUM(frp) AS frp_total
           FROM observations GROUP BY 1, 2 ORDER BY 1, 2""",
    )
    nacional_semana = rows(
        con,
        """SELECT date_trunc('week', CAST(acq_date AS DATE)) AS semana, product,
                  COUNT(*) AS detecciones, SUM(frp) AS frp_total
           FROM observations WHERE acq_date >= ?
           GROUP BY 1, 2 ORDER BY 1, 2""",
        [(fecha_max - timedelta(days=90)).isoformat()],
    )
    departamento = rows(
        con,
        """SELECT departamento, CASE WHEN sensor='MODIS' THEN 'MODIS' ELSE 'VIIRS' END AS sensor,
                  COUNT(*) AS detecciones, SUM(frp) AS frp_total
           FROM observations WHERE departamento IS NOT NULL
           GROUP BY 1, 2 ORDER BY detecciones DESC""",
    )
    departamento_dia = rows(
        con,
        """SELECT acq_date, departamento, CASE WHEN sensor='MODIS' THEN 'MODIS' ELSE 'VIIRS' END AS sensor,
                  COUNT(*) AS detecciones, SUM(frp) AS frp_total
           FROM observations WHERE acq_date >= ? AND departamento IS NOT NULL
           GROUP BY 1, 2, 3 ORDER BY 1, 2""",
        [fecha_serie],
    )

    # --- cobertura por día×producto (todo el periodo, con estado)
    # estados con el vocabulario del almacén: con_detecciones /
    # cero_detecciones_asumido / sin_datos (los archivos FIRMS de M014 son
    # anuales por producto: un día cubierto por algún archivo es cero asumido)
    dias = rows(
        con,
        """SELECT acq_date, product, COUNT(*) AS detecciones
           FROM observations GROUP BY 1, 2 ORDER BY 1, 2""",
    )
    por_fecha: dict[str, dict] = {}
    for d in dias:
        f = por_fecha.setdefault(d["acq_date"], {})
        f[d["product"]] = d["detecciones"]
    productos = [p[0] for p in con.execute(
        "SELECT DISTINCT product FROM observations ORDER BY 1").fetchall()]
    # archivos fuente anuales por producto (manifiesto M014)
    anos_por_producto: dict[str, set[int]] = {}
    for nombre, info in man_fuentes().items():
        producto = info.get("producto", "")
        anio = info.get("anio")
        if anio is None and nombre.endswith(".csv.gz"):
            try:
                anio = int(nombre.rsplit("_", 1)[1].split(".")[0])
            except ValueError:
                anio = None
        if producto and anio is not None:
            anos_por_producto.setdefault(producto, set()).add(int(anio))
    dias_lista = []
    d0 = datetime.strptime(rango[0], "%Y-%m-%d").date()
    d1 = fecha_max
    while d0 <= d1:
        iso = d0.isoformat()
        regs = por_fecha.get(iso, {})
        total = sum(regs.values())
        if total > 0:
            estado = "con_detecciones"
        else:
            cubierto = any(
                d0.year in anos_por_producto.get(p, set()) for p in productos
            )
            estado = "cero_detecciones_asumido" if cubierto else "sin_datos"
        dias_lista.append({
            "fecha": iso, "estado": estado, "detecciones": total,
            "modis": regs.get("MODIS_SP", 0) + regs.get("MODIS_NRT", 0),
            "viirs": sum(v for k, v in regs.items() if k.startswith("VIIRS")),
        })
        d0 += timedelta(days=1)

    # --- resumen nacional
    tot = con.execute(
        """SELECT COUNT(*) FILTER (WHERE sensor='MODIS'),
                  COUNT(*) FILTER (WHERE sensor='VIIRS'),
                  COUNT(*) FILTER (WHERE dentro_pais)
           FROM observations"""
    ).fetchone()
    deptos_afectados = [r[0] for r in con.execute(
        "SELECT DISTINCT departamento FROM observations WHERE departamento IS NOT NULL ORDER BY 1"
    ).fetchall()]
    por_anio = rows(
        con,
        """SELECT year, COUNT(*) AS detecciones FROM observations
           GROUP BY 1 ORDER BY 1""",
    )

    # --- eventos (top por tamaño, con miembros capados)
    eventos = rows(
        con,
        f"""SELECT event_id, metodo, parametros, n_observaciones, productos, sensores,
                   satelites, primera_obs_utc, ultima_obs_utc, duracion_segundos,
                   lat_centroide, lon_centroide, dispersion_metros, diametro_metros,
                   alerta_encadenamiento, frp_total, frp_max, frp_por_producto,
                   year(CAST(primera_obs_utc AS TIMESTAMP)) AS year
            FROM eventos ORDER BY n_observaciones DESC LIMIT {CAP_EVENTOS}""",
    )
    ids = [e["event_id"] for e in eventos]
    membresias: dict[str, list] = {}
    if ids:
        placeholders = ", ".join("?" for _ in ids)
        mem = rows(
            con,
            f"""SELECT m.event_id, o.obs_id, o.product, o.sensor, o.satellite_name,
                       ROUND(o.latitude, 5) AS latitude, ROUND(o.longitude, 5) AS longitude,
                       o.acq_datetime_utc, o.confidence_band, o.frp, o.daynight,
                       o.departamento
                FROM membresia m JOIN observations o USING (obs_id)
                WHERE m.event_id IN ({placeholders})
                ORDER BY m.event_id, o.acq_datetime_utc""",
            ids,
        )
        for m in mem:
            eid = m.pop("event_id")  # la lista ya cuelga de la clave del evento
            m["event_id"] = eid  # el contrato MiembroEvento incluye event_id
            if m.get("frp") is not None:
                m["frp"] = round(float(m["frp"]), 2)
            lst = membresias.setdefault(eid, [])
            if len(lst) < CAP_MIEMBROS_EVENTO:
                lst.append(m)
    total_eventos = con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
    for e in eventos:
        e["miembros"] = membresias.get(e["event_id"], [])
        e["miembros_truncados"] = e["n_observaciones"] > len(e["miembros"])
        e.pop("parametros", None)  # constante del run; viaja en meta
        # DuckDB devuelve structs anidados como string JSON: normalizar
        for campo in ("productos", "sensores", "satelites"):
            if isinstance(e.get(campo), str):
                e[campo] = json.loads(e[campo])
        if isinstance(e.get("frp_por_producto"), str):
            e["frp_por_producto"] = {
                k: round(float(v), 2)
                for k, v in json.loads(e["frp_por_producto"]).items()
            }

    # --- calidad (del manifiesto M014 + verificación de la Misión A)
    fuentes = man_fuentes()
    calidad = {
        "estados": [
            {"state": "verificado", "registros": rango[2]},
        ],
        "corridas": [
            {
                "provider": "NASA FIRMS (archivo histórico, M014)",
                "product": info.get("producto", "—"),
                "state": "sha256_verificado",
                "reason": nombre,
                "occurred_at_utc": "2026-11-13T00:38:38Z",
            }
            for nombre, info in list(fuentes.items())[:60]
        ],
        "cuarentena_registros": 0,
        "pares_candidatos": 277_933,
        "verificacion_sha256": "256/256 OK (M014)",
        "dedup_nrt_sp": 93_936,
        "nota": "Dedup exacta NRT sobre SP conservando la fila SP-prioritaria; sin cuarentena en la base final.",
    }

    almacen = {
        "meta": {
            "exportado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_source": "real",
            "data_source_nota": (
                "BASE REAL NACIONAL M014: 2.691.999 observaciones FIRMS 2000-2026 "
                "(MODIS Terra/Aqua + VIIRS NOAA-20/21, SP+NRT), normalizadas, QC, "
                "geo ADM1, dedup verificada SHA-256. Muestra web: últimos "
                f"{DIAS_MUESTRA_OBS} días (cap {CAP_OBS:,}) + series agregadas completas."
            ),
            "almacen": "hotspots_real.duckdb (Misión A) + eventos_v1 (C) + armonizacion_v1 (B)",
            "cobertura": {"desde": rango[0], "hasta": rango[1], "dias": rango[3]},
            "muestra": {
                "observaciones": {"desde": fecha_desde, "hasta": rango[1], "filas": len(obs), "cap": CAP_OBS},
                "eventos": {"seleccion": f"top {CAP_EVENTOS} por n_observaciones", "total": total_eventos},
                "serie_diaria": {"dias": DIAS_SERIE_DIARIA},
            },
        },
        "observaciones": obs,
        "stats": {
            "nacional_dia": nacional_dia,
            "nacional_semana": nacional_semana,
            "nacional_mes": nacional_mes,
            "departamento": departamento,
            "departamento_dia": departamento_dia,
            "nacional_anual": por_anio,
        },
        "resumen": {
            "total": rango[2],
            "modis": tot[0],
            "viirs": tot[1],
            "dentro_pais": tot[2],
            "eventos": total_eventos,
            "eventos_muestra": len(eventos),
            "departamentos_afectados": deptos_afectados,
            "pares_candidatos": 277_933,
            "por_anio": por_anio,
        },
        "eventos": eventos,
        "cobertura": {
            "desde": rango[0],
            "hasta": rango[1],
            "dias": dias_lista,
            "resumen": {
                "con_detecciones": sum(1 for d in dias_lista if d["estado"] == "con_detecciones"),
                "cero_detecciones_asumido": sum(1 for d in dias_lista if d["estado"] == "cero_detecciones_asumido"),
                "solo_rechazadas_qc": 0,
                "sin_datos": sum(1 for d in dias_lista if d["estado"] == "sin_datos"),
                "total_dias": len(dias_lista),
            },
            "cobertura_por_producto": {
                p: {
                    "primer_dato": next(
                        (f for f in sorted(por_fecha) if por_fecha[f].get(p, 0) > 0), None
                    ),
                    "ultimo_dato": next(
                        (f for f in sorted(por_fecha, reverse=True) if por_fecha[f].get(p, 0) > 0), None
                    ),
                    "dias_con_datos": sum(1 for f in por_fecha if por_fecha[f].get(p, 0) > 0),
                }
                for p in productos
            },
            "supuestos": [
                "Un día sin archivo fuente es un día SIN DATOS: no se cuenta como día sin fuego.",
                "La ausencia de detecciones no demuestra ausencia de incendios (resolución y paso orbital).",
            ],
        },
        "calidad": calidad,
    }
    con.close()
    jdump("almacen.json", almacen)


# --------------------------------------------------------------- armonización
def exportar_armonizacion() -> None:
    con = duckdb.connect()
    con.execute(f"CREATE TABLE p AS SELECT * FROM read_parquet('{AR / 'pares_modis_viirs.parquet'}')")
    canon = rows(
        con,
        """SELECT obs_id_modis, obs_id_viirs, product_modis, product_viirs,
                  satellite_modis_nombre, satellite_viirs_nombre,
                  acq_modis, acq_viirs, dt_seconds, distance_m,
                  frp_modis, frp_viirs, confidence_band_modis, confidence_band_viirs,
                  departamento, year
           FROM p WHERE dt_seconds <= 600 AND distance_m <= 2000
           USING SAMPLE 5000 ROWS""",
    )
    hist_dt = rows(con, "SELECT LEAST(FLOOR(dt_seconds / 30), 29) AS b, COUNT(*) AS n FROM p WHERE dt_seconds<=900 GROUP BY 1 ORDER BY 1")
    hist_dist = rows(con, "SELECT LEAST(FLOOR(distance_m / 100), 29) AS b, COUNT(*) AS n FROM p WHERE distance_m<=3000 GROUP BY 1 ORDER BY 1")
    por_anio = rows(con, "SELECT year, COUNT(*) AS pares FROM p WHERE dt_seconds<=600 AND distance_m<=2000 GROUP BY 1 ORDER BY 1")
    frp = rows(con, """SELECT median(frp_modis) AS med_modis, median(frp_viirs) AS med_viirs,
                              quantile_cont(frp_modis, 0.75) AS p75_modis,
                              quantile_cont(frp_viirs, 0.75) AS p75_viirs
                       FROM p WHERE dt_seconds<=600 AND distance_m<=2000 AND frp_modis IS NOT NULL AND frp_viirs IS NOT NULL""")
    con.close()

    sens = list(csv.DictReader((AR / "sensibilidad_9_combinaciones.csv").open(encoding="utf-8")))
    analisis = json.loads((AR / "analisis_pares.json").read_text(encoding="utf-8"))
    disc = json.loads((AR / "discrepancias.json").read_text(encoding="utf-8"))
    data = {
        "data_source": "real",
        "nota": (
            "Pares MODIS-VIIRS sobre la base real M014. Una coincidencia NO es "
            "una confirmación de incendio ni dos observaciones idénticas; las "
            "escalas de confianza no se mezclan y la FRP de sensores distintos "
            "no se suma como medición física única."
        ),
        "canonico": {"dt_segundos": 600, "distancia_metros": 2000, "pares": 277_933},
        "muestra_pares": canon,
        "sensibilidad": sens,
        "por_anio": por_anio,
        "hist_dt": hist_dt,
        "hist_dist": hist_dist,
        "frp_mediana": frp[0] if frp else {},
        "analisis": analisis,
        "discrepancias": disc,
    }
    jdump("armonizacion.json", data)


# ------------------------------------------------------------------ ambiental
def exportar_ambiental() -> None:
    con = duckdb.connect()
    con.execute(f"CREATE TABLE a AS SELECT * FROM read_parquet('{AM / 'asociacion_celda_mes.parquet'}')")
    serie = rows(
        con,
        """SELECT mes,
                  SUM(obs_modis) AS obs_modis, SUM(obs_viirs) AS obs_viirs,
                  SUM(eventos) AS eventos,
                  AVG(precip_mm) AS precip_mm, AVG(temp_media_c) AS temp_media_c,
                  AVG(vpd_kpa) AS vpd_kpa, AVG(fwi_medio) AS fwi_medio,
                  AVG(humedad_suelo_m3m3) AS humedad_suelo,
                  SUM(quemado_mcd64_km2) AS quemado_mcd64_km2
           FROM a WHERE precip_mm IS NOT NULL GROUP BY 1 ORDER BY 1""",
    )
    por_dept = rows(
        con,
        """SELECT substr(mes,1,4) AS anio,
                  SUM(obs_modis) AS obs_modis, SUM(obs_viirs) AS obs_viirs
           FROM a GROUP BY 1 ORDER BY 1""",
    )
    cobertura = rows(
        con,
        """SELECT clase_dominante, COUNT(DISTINCT celda) AS celdas,
                  SUM(obs_viirs) AS obs_viirs
           FROM a GROUP BY 1 ORDER BY obs_viirs DESC""",
    )
    con.close()
    data = {
        "data_source": "real",
        "nota": "Asociación espacio-temporal celda×mes (Misión D) sobre la grilla nacional 0,1° (3.737 celdas). Sin imputación: los meses sin cobertura de una variable quedan excluidos de esa serie.",
        "catalogo": json.loads((AM / "catalogo_ambiental.json").read_text(encoding="utf-8")),
        "relaciones": json.loads((AM / "relaciones_fuego_clima.json").read_text(encoding="utf-8")),
        "serie_nacional_mensual": serie,
        "obs_por_anio": por_dept,
        "cobertura_terrestre": cobertura,
    }
    jdump("ambiental.json", data)


# ------------------------------------------------------------------------ IA
def exportar_ia() -> None:
    metricas = json.loads((IA / "metricas_ia.json").read_text(encoding="utf-8"))
    curvas = json.loads((IA / "curvas_evaluacion.json").read_text(encoding="utf-8"))
    data = {
        "data_source": "real",
        "nota": (
            "Modelo VALIDADO CON LIMITACIONES DECLARADAS: etiqueta = ≥1 detección "
            "VIIRS en la celda el mes siguiente (agrupación inferida, NO un incendio "
            "confirmado). Partición temporal estricta 2020-23 / 2024 / 2025-26. "
            "exp_001 (anomalías) es SINTÉTICO y no forma parte de esta validación."
        ),
        "version": metricas.get("version"),
        "semilla": metricas.get("semilla"),
        "dataset": metricas.get("dataset"),
        "particiones": metricas.get("particiones"),
        "modelos": metricas.get("modelos"),
        "mejor_modelo": metricas.get("mejor_modelo_por_validacion"),
        "importancia": metricas.get("importancia_variables_random_forest"),
        "validacion_geografica": metricas.get("validacion_geografica_gbm"),
        "curvas": curvas,
    }
    jdump("ia.json", data)


# -------------------------------------------------------------------- anexos
def exportar_anexos() -> None:
    shutil.copy(REPO / "web" / "src" / "data" / "mvp" / "anomalias_exp001.json", OUT / "anomalias_exp001.json")
    shutil.copy(REPO / "web" / "src" / "data" / "mvp" / "departamentos.geojson", OUT / "departamentos.geojson")
    print("  anomalias_exp001.json + departamentos.geojson copiados (anomalías: SINTÉTICO exp_001; geometrías: REALES)")


def manifiesto() -> None:
    arts = {}
    for p in sorted(OUT.iterdir()):
        if p.name != "manifiesto_web_real.json":
            arts[p.name] = {"bytes": p.stat().st_size, "sha256": sha256(p)}
    man = {
        "version": "web_real_v1",
        "creado_en_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "origen": {
            "base_real": "M014 — 2.691.999 obs, 256/256 SHA-256",
            "eventos": "Misión C — 19.747 eventos (600 s / 2 km, sensores distintos)",
            "armonizacion": "Misión B — 277.933 pares canónicos",
            "ambiental": "Misión D — asociación celda×mes 1.291.197 filas",
            "ia": "Misión E — RF ROC-AUC 0,797 (evaluación temporal)",
        },
        "artefactos": arts,
    }
    jdump("manifiesto_web_real.json", man)



def exportar_actualizacion() -> None:
    """Estado del ciclo de actualización (Misión C FIREIA 2.0).

    Lee data/PROCESADA/estado_actualizacion.json + cola del registro JSONL.
    Si no existen (primera ejecución), declara COBERTURA_DESCONOCIDA honesto.
    Regla científica: un fallo de adquisición NO es cero detecciones.
    """
    est = REPO / "data" / "PROCESADA" / "estado_actualizacion.json"
    reg = REPO / "data" / "PROCESADA" / "registro_actualizaciones.jsonl"
    estado = {"estado": "COBERTURA_DESCONOCIDA",
              "nota": "sin ejecución registrada del ciclo de actualización"}
    if est.exists():
        estado = json.loads(est.read_text(encoding="utf-8"))
    registro: list[dict] = []
    if reg.exists():
        lineas = reg.read_text(encoding="utf-8").strip().splitlines()
        registro = [json.loads(l) for l in lineas[-10:]]
    jdump("actualizacion.json", {
        "meta": {"data_source": "real"},
        "estado": estado,
        "registro_reciente": registro,
        "estados_posibles": ["ACTUALIZADO", "SIN_NUEVOS_DATOS", "ACTUALIZANDO",
                             "RETRASADO", "ERROR", "COBERTURA_DESCONOCIDA",
                             "ADQUISICION_NO_DISPONIBLE"],
        "regla": "un fallo de adquisición no significa cero detecciones; "
                 "la ausencia de datos no significa ausencia de incendios",
    })
    print("  actualizacion.json exportado (estado ciclo de actualización)")


def main() -> int:
    print("Exportando datos REALES para la web…")
    exportar_almacen()
    exportar_armonizacion()
    exportar_ambiental()
    exportar_ia()
    exportar_anexos()
    exportar_actualizacion()
    manifiesto()
    total = sum(p.stat().st_size for p in OUT.iterdir())
    print(f"Total: {total / 1e6:.1f} MB en {len(list(OUT.iterdir()))} archivos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
