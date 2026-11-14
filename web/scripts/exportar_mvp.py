"""Exporta el almacén del pipeline (Misión 004) a JSON para el MVP Next.js.

Lee el DuckDB del repositorio (solo lectura), las capas GeoJSON y el
generador del experimento 001, y escribe todo a src/data/mvp/ del proyecto
web. Los datos del almacén son FIXTURES (identificados como tales en cada
capa); el MVP debe mostrar ese origen sin excepciones.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb

REPO = Path("/home/z/my-project/modis-viirs-hotspots-paraguay")
DB = REPO / "data" / "processed" / "hotspots.duckdb"
OUT = Path("/home/z/my-project/src/data/mvp")
sys.path.insert(0, str(REPO / "src"))

FECHA_EXPORT = "2026-11-11"


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def exportar_almacen() -> dict:
    con = duckdb.connect(str(DB), read_only=True)

    # Observaciones con asignación geográfica (sin WKB)
    observaciones = rows(
        con,
        """
        SELECT obs_id, product, sensor, satellite, satellite_name, instrument,
               latitude, longitude, acq_date, acq_time, acq_datetime_utc,
               confidence, confidence_band, frp, brightness, bright_t31,
               bright_ti4, bright_ti5, scan, track, daynight, version,
               dentro_pais, departamento, distrito, version_limites
        FROM observations_geo
        ORDER BY acq_datetime_utc
        """,
    )

    stats_nacional_dia = rows(
        con, "SELECT acq_date, product, detecciones, frp_total FROM stats_nacional_dia ORDER BY acq_date"
    )
    stats_nacional_semana = rows(con, "SELECT * FROM stats_nacional_semana ORDER BY 1")
    stats_nacional_mes = rows(con, "SELECT * FROM stats_nacional_mes ORDER BY 1")
    stats_departamento = rows(
        con,
        """
        SELECT departamento, product, sum(detecciones) AS detecciones,
               sum(frp_total) AS frp_total
        FROM stats_departamento_dia
        GROUP BY departamento, product
        ORDER BY detecciones DESC
        """,
    )
    stats_departamento_dia = rows(
        con, "SELECT * FROM stats_departamento_dia ORDER BY acq_date"
    )

    eventos = rows(
        con,
        """
        SELECT event_id, metodo, n_observaciones, productos, sensores, satelites,
               primera_obs_utc, ultima_obs_utc, duracion_segundos,
               lat_centroide, lon_centroide, dispersion_metros,
               diametro_metros, alerta_encadenamiento,
               frp_total, frp_max, frp_por_producto
        FROM events
        ORDER BY primera_obs_utc
        """,
    )
    # frp_por_producto llega como string JSON: parsear para la UI
    import json as _json
    for ev in eventos:
        try:
            ev["frp_por_producto"] = _json.loads(ev["frp_por_producto"])
        except (TypeError, ValueError):
            ev["frp_por_producto"] = {}
    miembros = rows(
        con,
        """
        SELECT m.event_id, o.obs_id, o.product, o.sensor, o.satellite_name,
               o.latitude, o.longitude, o.acq_datetime_utc, o.confidence,
               o.confidence_band, o.frp, o.daynight, g.departamento, g.distrito
        FROM event_observations m
        JOIN observations o ON o.obs_id = m.obs_id
        LEFT JOIN observations_geo g ON g.obs_id = m.obs_id
        ORDER BY m.event_id, o.acq_datetime_utc
        """,
    )
    for ev in eventos:
        ev["miembros"] = [m for m in miembros if m["event_id"] == ev["event_id"]]

    estados_ingesta = rows(
        con,
        """
        SELECT state, count(*) AS registros
        FROM ingest_status
        GROUP BY state
        ORDER BY registros DESC
        """,
    )
    corridas = rows(
        con,
        """
        SELECT provider, product, state, reason, occurred_at_utc
        FROM ingest_status
        ORDER BY occurred_at_utc
        """,
    )
    cuarentena = rows(con, "SELECT count(*) AS n FROM quarantine")[0]["n"]
    pares_candidatos = rows(con, "SELECT count(*) AS n FROM candidate_matches")[0]["n"]

    # calendario de cobertura (Misión 005): cero detecciones ≠ sin datos
    sys.path.insert(0, str(REPO / "src"))
    from hotspots.analysis.calendar import build_coverage_calendar

    fechas_obs: dict[str, set[str]] = {}
    for r in rows(con, "SELECT DISTINCT product, acq_date FROM observations"):
        fechas_obs.setdefault(r["product"], set()).add(str(r["acq_date"]))
    fechas_cuar: dict[str, set[str]] = {}
    for r in rows(
        con, "SELECT DISTINCT product, acq_date FROM quarantine WHERE acq_date IS NOT NULL"
    ):
        fechas_cuar.setdefault(r["product"], set()).add(str(r["acq_date"]))
    fechas_todas = sorted(f for s in fechas_obs.values() for f in s)
    cobertura = build_coverage_calendar(
        fechas_obs_por_producto=fechas_obs,
        fechas_cuarentena_por_producto=fechas_cuar,
        desde=fechas_todas[0],
        hasta=fechas_todas[-1],
    )

    con.close()

    fechas = sorted({o["acq_date"] for o in observaciones})
    departamentos_afectados = sorted(
        {o["departamento"] for o in observaciones if o["dentro_pais"]}
    )

    return {
        "meta": {
            "exportado_en": FECHA_EXPORT,
            "data_source": "fixture",
            "data_source_nota": (
                "Almacén cargado con fixtures sintéticos de FIRMS. "
                "Cero datos reales consumidos (Fase 1B bloqueada por compuerta)."
            ),
            "almacen": "hotspots.duckdb (Misión 004)",
            "cobertura": {"desde": fechas[0], "hasta": fechas[-1], "dias": len(fechas)},
        },
        "observaciones": observaciones,
        "stats": {
            "nacional_dia": stats_nacional_dia,
            "nacional_semana": stats_nacional_semana,
            "nacional_mes": stats_nacional_mes,
            "departamento": stats_departamento,
            "departamento_dia": stats_departamento_dia,
        },
        "resumen": {
            "total": len(observaciones),
            "modis": sum(1 for o in observaciones if o["sensor"] == "MODIS"),
            "viirs": sum(1 for o in observaciones if o["sensor"] == "VIIRS"),
            "dentro_pais": sum(1 for o in observaciones if o["dentro_pais"]),
            "eventos": len(eventos),
            "departamentos_afectados": departamentos_afectados,
            "pares_candidatos": pares_candidatos,
        },
        "eventos": eventos,
        "cobertura": cobertura,
        "calidad": {
            "estados": estados_ingesta,
            "corridas": corridas,
            "cuarentena_registros": cuarentena,
            "pares_candidatos": pares_candidatos,
        },
    }


def exportar_anomalias() -> dict:
    """Regenera la serie sintética del exp_001 con el detalle por día.

    Misma semilla y misma lógica que experiments/exp_001_anomalias_sinteticas.py
    (que queda como fuente canónica); acá agregamos la serie completa para
    graficarla en el MVP.
    """
    import random

    from hotspots.analysis.anomaly import detect_anomalies
    from hotspots.analysis.baselines import mae, persistence_forecast

    semilla = 20260911
    eval_desde, eval_hasta = date(2026, 3, 1), date(2026, 3, 31)
    inyectadas = {
        date(2026, 3, 5): 9.0,
        date(2026, 3, 12): 10.0,
        date(2026, 3, 18): 0.05,
        date(2026, 3, 24): 8.5,
    }

    rng = random.Random(semilla)
    serie: list[tuple[str, int]] = []
    d = eval_desde - timedelta(days=120)
    while d <= eval_hasta:
        base = 40.0
        semanal = [1.0, 0.95, 1.05, 1.1, 1.15, 1.4, 1.3][d.weekday()]
        valor = base * semanal * rng.gauss(1.0, 0.08)
        if d in inyectadas:
            valor = base * inyectadas[d]
        serie.append((d.isoformat(), max(0, round(valor))))
        d += timedelta(days=1)

    reporte = detect_anomalies(
        serie,
        eval_from=eval_desde.isoformat(),
        eval_to=eval_hasta.isoformat(),
        z_threshold=3.0,
    )
    detectadas = {a.fecha for a in reporte.anomalias}  # set[date]
    esperadas = set(inyectadas)  # set[date]
    tp = len(detectadas & esperadas)
    fp = len(detectadas - esperadas)
    detectadas_iso = sorted(x.isoformat() for x in detectadas)

    errores, reales = [], []
    for f, v in serie:
        if eval_desde <= date.fromisoformat(f) <= eval_hasta:
            errores.append(persistence_forecast(serie, for_date=f).valor_estimado)
            reales.append(float(v))

    fechas_inyectadas = {x.isoformat() for x in inyectadas}
    detalle = [
        {
            "fecha": a.fecha.isoformat() if hasattr(a.fecha, "isoformat") else str(a.fecha),
            "valor": a.valor,
            "esperado": a.esperado_mediana,
            "z": round(float(a.z), 2),
            "direccion": str(getattr(a.direccion, "value", a.direccion)),
            "es_anomalia": a.fecha in detectadas,
            "inyectada": (a.fecha.isoformat() if hasattr(a.fecha, "isoformat") else str(a.fecha)) in fechas_inyectadas,
        }
        for a in reporte.anomalias
    ]

    return {
        "experimento": "exp_001_anomalias_sinteticas",
        "datos": "SINTETICOS (generador con semilla fija; no representan Paraguay)",
        "metodo": reporte.metodo,
        "umbral_z": reporte.umbral_z,
        "dias_evaluados": reporte.dias_evaluados,
        "anomalias_inyectadas": sorted(x.isoformat() for x in inyectadas),
        "anomalias_detectadas": detectadas_iso,
        "verdaderos_positivos": tp,
        "falsos_positivos": fp,
        "recall": round(tp / len(inyectadas), 3),
        "precision": round(tp / len(detectadas), 3) if detectadas else None,
        "mae_persistencia_baseline": round(mae(errores, reales), 2),
        "detalle": detalle,
        "serie_completa": [
            {"fecha": f, "valor": v, "en_evaluacion": eval_desde.isoformat() <= f <= eval_hasta.isoformat()}
            for f, v in serie
        ],
        "nota": (
            "El recall/precision aplica SOLO a la serie sintética. La persistencia "
            "queda como baseline a vencer cuando existan modelos reales; su MAE "
            "también es sintético."
        ),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    almacen = exportar_almacen()
    (OUT / "almacen.json").write_text(
        json.dumps(almacen, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    anomalias = exportar_anomalias()
    (OUT / "anomalias_exp001.json").write_text(
        json.dumps(anomalias, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    shutil.copy(
        REPO / "data" / "capas" / "departamentos.geojson",
        OUT / "departamentos.geojson",
    )

    print("Exportado a", OUT)
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name}: {f.stat().st_size // 1024} KB")
    print("resumen:", json.dumps(almacen["resumen"], ensure_ascii=False))
    print(
        "anomalias:",
        anomalias["verdaderos_positivos"],
        "TP /",
        anomalias["falsos_positivos"],
        "FP",
    )


if __name__ == "__main__":
    main()
