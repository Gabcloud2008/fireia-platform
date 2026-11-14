"""Verificación del piloto nacional FIRMS de 7 días — Misión 007/008.

CONTRATO (Misión 008, corrección 4.3 — el verificador NO mezcla datos ajenos):

El **universo del piloto** está definido con precisión y TODA consulta se
limita a él:

1. **Período exacto**: solo observaciones con ``acq_date BETWEEN desde AND
   hasta`` (días UTC de la ventana del piloto).
2. **Producto**: solo los productos del piloto.
3. **Procedencia**: una observación pertenece al piloto SOLO si su
   ``manifest_id`` corresponde a un manifiesto ``firms_api`` cuya consulta
   exacta (product + date + day_range + bbox, vía ``request_key`` canónico)
   sea una de las consultas esperadas del piloto (split 5+2).
4. **Manifiestos**: se detectan faltantes (consulta esperada sin manifiesto),
   incompletos (estado no exitoso) e incompatibles (misma ventana pero
   parámetros distintos a los esperados).
5. **Correspondencia RAW ↔ procesado**: por manifiesto, el artefacto RAW
   existe en disco, su SHA256 y tamaño coinciden, y
   ``rows_raw == rows_valid + rows_quarantined``.
6. **Duplicados técnicos**: ``sum(rows_valid de los manifiestos del piloto)
   − observaciones distintas del piloto`` — dentro del universo correcto
   (Misión 007 conflareaba rows_raw con cuarentena: corregido).
7. **FRP**: sumado SOLO por producto dentro del universo (jamás entre
   sensores) y jamás mezclando períodos.
8. **Territorial / eventos / cuarentena**: restringidos a las observaciones
   (y corridas) del piloto.

Clasificación de procedencia (Misión 008, corrección 4.4) — valor
``clasificacion_datos`` en el reporte:

- ``real``     : observaciones del piloto respaldadas por manifiestos firms_api.
- ``fixture``  : datos sintéticos cargados con ``hotspots ingest --fixture``
                 (``source_kind='fixture'``).
- ``synthetic``: series sintéticas de experimentos (no viven en observations).
- ``unknown``  : procedencia no determinable.
- ``vacio``    : sin observaciones en la ventana (estado, no clase de dato).

Códigos de salida:

- 0: piloto real verificado, o ventana vacía con manifiestos completos y
     consistentes (un piloto real sin detecciones es un resultado válido).
- 3: ADVERTENCIA de procedencia — hay datos en la ventana que NO están
     respaldados por manifiestos del piloto (fixtures, corridas ajenas o
     desconocidas), o faltan manifiestos. El reporte se empite igual, con la
     clasificación y las advertencias explícitas.
- 1: error interno.

Uso::

    python verificar_piloto.py [DESDE [HASTA]] [--data-dir DIR] [--json SALIDA]

DESDE default 2026-11-04 (ventana objetivo del piloto: 2026-11-04..2026-11-10).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from hotspots.config import Settings
from hotspots.provenance.manifests import ManifestStore, request_key
from hotspots.quality.states import SUCCESS_STATES
from hotspots.storage.duckdb_store import DuckDBStore

REPO = Path(__file__).resolve().parents[2]
DATOS = REPO / "mision_007_datos_reales" / "datos"

#: SHA256 del contenido VACÍO (0 bytes): e3b0c442... Es la huella de TODO
#: artefacto RAW vacío — heredado de adquisiciones fallidas (M011-C §3).
#: No se borra la evidencia histórica: se identifica y clasifica.
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

#: Clasificación M011-C §3 de un artefacto RAW vacío (0 bytes).
NOTA_RAW_VACIO_FALLIDO = (
    "artefacto RAW vacío (0 bytes) de una adquisición FALLIDA: no es "
    "observación, no es CSV válido y NO cuenta como día sin detecciones"
)
NOTA_RAW_VACIO_EN_EXITO = (
    "artefacto RAW vacío (0 bytes) en un manifiesto EXITOSO: inconsistencia "
    "(un CSV válido de FIRMS nunca es de 0 bytes)"
)

#: Productos del piloto (Misión 007: MODIS C6.1 Terra+Aqua, VIIRS NOAA-20/21).
PILOTO_PRODUCTOS = ("MODIS_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")
#: Split de ventanas: (fecha relativa a DESDE, day_range). Cubre 5+2=7 días.
SPLIT = ((0, 5), (5, 2))
DESDE_DEFAULT = "2026-11-04"

EXIT_OK, EXIT_ERROR, EXIT_PROCEDENCIA = 0, 1, 3


def _dias(desde: str, hasta: str) -> list[str]:
    d0 = date.fromisoformat(desde)
    d1 = date.fromisoformat(hasta)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def consultas_esperadas(settings: Settings, desde: str) -> list[dict]:
    """Las consultas EXACTAS que el piloto debe ejecutar (split 5+2).

    El ``request_key`` se recalcula con la MISMA función canónica del
    pipeline, de modo que el emparejamiento con manifiestos es exacto:
    producto + fecha + day_range + bbox (el del settings del proyecto).
    """
    bbox = [float(x) for x in settings.firms_query_bbox]
    esperadas = []
    for producto in PILOTO_PRODUCTOS:
        for offset, day_range in SPLIT:
            fecha = (date.fromisoformat(desde) + timedelta(days=offset)).isoformat()
            params = {
                "bbox": bbox,
                "bbox_rol": "firms_query_bbox (rectángulo de consulta; no es territorio)",
                "day_range": day_range,
                "date": fecha,
                "contract": "area_csv_v1",
            }
            esperadas.append(
                {
                    "producto": producto,
                    "fecha_consulta": fecha,
                    "day_range": day_range,
                    "cubre_desde": fecha,
                    "cubre_hasta": (
                        date.fromisoformat(fecha) + timedelta(days=day_range - 1)
                    ).isoformat(),
                    "request_key": request_key("firms", "firms_api", producto, params),
                }
            )
    return esperadas


def _cargar_manifiesto(mstore: ManifestStore, key: str):
    m = mstore.find_by_request_key(key)
    return m


def _verificar_manifiesto(m, exitoso: bool) -> tuple[list[str], list[dict]]:
    """Correspondencia RAW ↔ procesado de un manifiesto del piloto.

    Devuelve (problemas, artefactos_raw_vacios). M011-C §3: los artefactos
    RAW de 0 bytes se identifican explícitamente — en un manifiesto fallido
    son evidencia de una adquisición fallida (ni observación, ni CSV válido,
    ni día sin detecciones); en uno exitoso son una inconsistencia.
    """
    problemas = []
    vacios: list[dict] = []
    counts = m.counts or {}
    rows_raw = counts.get("rows_raw") or 0
    rows_valid = counts.get("rows_valid") or 0
    rows_q = counts.get("rows_quarantined") or 0
    if rows_raw != rows_valid + rows_q:
        problemas.append(
            f"conteos inconsistentes: rows_raw={rows_raw} != "
            f"rows_valid={rows_valid} + rows_quarantined={rows_q}"
        )
    raws = [a for a in (m.artifacts or []) if a.role in ("raw_csv", "raw_response")]
    if not raws:
        problemas.append("sin artefacto RAW (raw_csv/raw_response)")
    for a in raws:
        p = Path(a.path)
        if not p.exists():
            problemas.append(f"RAW inexistente: {a.path}")
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest != a.sha256:
            problemas.append(f"SHA256 del RAW no coincide: {a.path}")
        if p.stat().st_size != a.size:
            problemas.append(f"tamaño del RAW no coincide: {a.path}")
        if a.size == 0 or a.sha256 == EMPTY_SHA256:
            vacios.append(
                {
                    "manifest_id": m.manifest_id,
                    "path": a.path,
                    "estado_manifiesto": m.result_state,
                    "clasificacion": (
                        "artefacto_vacio_de_adquisicion_fallida"
                        if not exitoso
                        else "artefacto_vacio_en_manifiesto_exitoso"
                    ),
                    "nota": NOTA_RAW_VACIO_FALLIDO if not exitoso else NOTA_RAW_VACIO_EN_EXITO,
                }
            )
            if not exitoso:
                problemas.append(NOTA_RAW_VACIO_FALLIDO)
            else:
                problemas.append(NOTA_RAW_VACIO_EN_EXITO)
    return problemas, vacios


def clasificar_source_kinds(kinds: list[str]) -> str:
    """Clasificación de un conjunto de source_kinds presentes."""
    unicos = {k for k in kinds if k}
    if not unicos:
        return "vacio"
    if unicos <= {"firms_api"}:
        return "real"
    if unicos <= {"fixture"}:
        return "fixture"
    if unicos <= {"firms_api", "fixture"}:
        return "mixto_real_fixture"
    if all(k in ("synthetic",) for k in unicos):
        return "synthetic"
    return "unknown"


def verificar(desde: str, hasta: str, data_dir: Path | None = None) -> tuple[dict, int]:
    """Ejecuta la verificación completa. Devuelve (reporte, código de salida)."""
    dias = _dias(desde, hasta)
    settings = Settings.load(data_dir=data_dir) if data_dir else Settings.load()
    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb", settings.data_dir / "processed"
    )
    mstore = ManifestStore(settings.data_dir / "manifests")

    esperadas = consultas_esperadas(settings, desde)
    reporte: dict = {
        "piloto": {
            "desde": desde,
            "hasta": hasta,
            "dias": dias,
            "zonahoraria": "UTC",
            "productos": list(PILOTO_PRODUCTOS),
            "split": [{"offset_dias": o, "day_range": d} for o, d in SPLIT],
            "consultas_esperadas": len(esperadas),
        },
        "capa_geo_activa": duck.geo_version_activa(),
        "manifiestos": {},
        "productos": {},
        "advertencias": [],
    }

    # ------------------------------------------------------------------ 1-4
    # Manifiestos del piloto: emparejamiento exacto por request_key.
    ids_piloto: set[str] = set()
    runs_piloto: set[str] = set()
    faltantes: list[dict] = []
    incompletos: list[dict] = []
    artefactos_raw_vacios: list[dict] = []  # M011-C §3
    por_producto_man: {str: list} = {p: [] for p in PILOTO_PRODUCTOS}

    for e in esperadas:
        m = _cargar_manifiesto(mstore, e["request_key"])
        if m is None:
            faltantes.append(
                {
                    k: e[k]
                    for k in (
                        "producto", "fecha_consulta", "day_range",
                        "cubre_desde", "cubre_hasta",
                    )
                }
            )
            continue
        ids_piloto.add(m.manifest_id)
        runs_piloto.add(m.run_id)
        entrada = {
            "manifest_id": m.manifest_id,
            "fecha_consulta": e["fecha_consulta"],
            "day_range": e["day_range"],
            "cubre": [e["cubre_desde"], e["cubre_hasta"]],
            "estado": m.result_state,
            "creado_en_utc": m.created_at_utc,
            "counts": m.counts,
        }
        if m.result_state not in SUCCESS_STATES:
            # M011-C §3: también se inspeccionan los artefactos de los
            # manifiestos fallidos, para identificar RAW vacíos heredados.
            problemas, vacios_m = _verificar_manifiesto(m, exitoso=False)
            problemas.insert(0, f"estado no exitoso: {m.result_state}")
            incompletos.append(entrada | {"problemas": problemas})
            artefactos_raw_vacios.extend(vacios_m)
        else:
            problemas, vacios_m = _verificar_manifiesto(m, exitoso=True)
            if problemas:
                incompletos.append(entrada | {"problemas": problemas})
            artefactos_raw_vacios.extend(vacios_m)
        entrada["problemas_raw_procesado"] = problemas
        por_producto_man[e["producto"]].append(entrada)

    # Incompatibles: manifiestos firms_api del mismo producto cuya fecha de
    # consulta cae en la ventana del piloto pero cuya consulta exacta NO es
    # ninguna de las esperadas (parámetros distintos: bbox, day_range, etc.).
    # En el mismo recorrido se identifican artefactos RAW vacíos (M011-C §3)
    # en CUALQUIER manifiesto firms_api de la ventana — incluidos los
    # históricos sustituidos: si una consulta se reintentó, el manifiesto
    # viejo con artefacto vacío queda sombreado por el más nuevo y también
    # debe quedar identificado (la evidencia histórica no se borra).
    incompatibles: list[dict] = []
    claves_esperadas = {e["request_key"] for e in esperadas}
    ids_ya_listados = {v["manifest_id"] for v in artefactos_raw_vacios}
    for entry in mstore.list_entries():
        try:
            m = json.loads(Path(entry["path"]).read_text(encoding="utf-8"))
        except (OSError, KeyError, json.JSONDecodeError):
            continue
        if m.get("source") != "firms_api" or m.get("product") not in PILOTO_PRODUCTOS:
            continue
        f = (m.get("acquisition_period") or {}).get("from", "")
        if not (f and desde <= f <= hasta):
            continue
        mid = m.get("manifest_id")
        if (
            m.get("result_state") not in SUCCESS_STATES
            and mid not in ids_ya_listados
        ):
            for a in m.get("artifacts") or []:
                if not str(a.get("role", "")).startswith("raw"):
                    continue
                if a.get("size") == 0 or a.get("sha256") == EMPTY_SHA256:
                    artefactos_raw_vacios.append(
                        {
                            "manifest_id": mid,
                            "path": a.get("path"),
                            "estado_manifiesto": m.get("result_state"),
                            "clasificacion": "artefacto_vacio_de_adquisicion_fallida",
                            "nota": NOTA_RAW_VACIO_FALLIDO,
                        }
                    )
                    ids_ya_listados.add(mid)
                    break
        if m.get("request_key") not in claves_esperadas:
            incompatibles.append(
                {
                    "manifest_id": mid,
                    "producto": m.get("product"),
                    "fecha_consulta": f,
                    "request_key": m.get("request_key"),
                    "nota": (
                        "consulta dentro de la ventana con parámetros distintos "
                        "de los esperados"
                    ),
                }
            )

    reporte["manifiestos"] = {
        "esperados": len(esperadas),
        "encontrados": len(esperadas) - len(faltantes),
        "faltantes": faltantes,
        "incompletos_o_con_problemas": incompletos,
        "incompatibles": incompatibles,
        # M011-C §3: artefactos RAW de 0 bytes identificados y clasificados
        # (evidencia histórica preservada; jamás interpretados como
        # observación, CSV válido o día sin detecciones).
        "artefactos_raw_vacios": artefactos_raw_vacios,
    }

    # ------------------------------------------------------------------ 5-8
    # Observaciones: SIEMPRE acotadas a ventana + producto.
    total_piloto = 0
    kinds_en_ventana: list[str] = []
    obs_piloto_ids: set[str] = set()
    for producto in PILOTO_PRODUCTOS:
        fila = (
            "SELECT obs_id, source_kind, manifest_id, satellite, satellite_name, "
            "acq_date, frp FROM observations "
            "WHERE product = ? AND acq_date >= ? AND acq_date <= ?"
        )
        obs = duck.query(fila, [producto, desde, hasta])
        piloto_obs = [o for o in obs if o["manifest_id"] in ids_piloto]
        fuera_piloto = [o for o in obs if o["manifest_id"] not in ids_piloto]
        kinds_en_ventana.extend(o["source_kind"] for o in obs)
        obs_piloto_ids.update(o["obs_id"] for o in piloto_obs)

        por_dia_piloto: dict[str, int] = {}
        for o in piloto_obs:
            por_dia_piloto[o["acq_date"]] = por_dia_piloto.get(o["acq_date"], 0) + 1

        # M011-C §3: un día cuenta como "sin detecciones" SOLO si estuvo
        # cubierto por una adquisición EXITOSA del piloto (período declarado
        # en un manifiesto success_*). Los días sin adquisición exitosa van a
        # "dias_sin_cobertura_exitosa": un fallo de descarga o un artefacto
        # vacío de adquisición fallida NO es un día sin fuego.
        dias_cubiertos: set[str] = set()
        for mm in por_producto_man[producto]:
            if mm["estado"] in SUCCESS_STATES:
                cubre = mm.get("cubre") or [None, None]
                if cubre[0] and cubre[1]:
                    dias_cubiertos.update(_dias(cubre[0], cubre[1]))
        dias_sin_detecciones = [
            d for d in dias if d in dias_cubiertos and d not in por_dia_piloto
        ]
        dias_sin_cobertura_exitosa = [
            d for d in dias if d not in dias_cubiertos
        ]

        sats_piloto: dict[str, int] = {}
        for o in piloto_obs:
            clave = f"{o['satellite']} ({o['satellite_name']})"
            sats_piloto[clave] = sats_piloto.get(clave, 0) + 1

        frp_piloto = sum(o["frp"] or 0 for o in piloto_obs)

        # duplicados técnicos: rows_valid sumados de manifiestos exitosos del
        # producto MENOS observaciones distintas del piloto (universo correcto)
        rows_valid_sum = sum(
            (mm["counts"] or {}).get("rows_valid") or 0
            for mm in por_producto_man[producto]
            if mm["estado"] in SUCCESS_STATES
        )
        n_piloto = len(piloto_obs)
        duplicados = rows_valid_sum - n_piloto if rows_valid_sum or n_piloto else 0

        reporte["productos"][producto] = {
            "observaciones_del_piloto": n_piloto,
            "por_dia": por_dia_piloto,
            "dias_sin_detecciones": dias_sin_detecciones,
            # M011-C §3: días de la ventana SIN adquisición exitosa que los
            # cubra (fallo de descarga, pendiente o detenida por saldo) —
            # estado de cobertura, NO ausencia de fuego.
            "dias_sin_cobertura_exitosa": dias_sin_cobertura_exitosa,
            "satelites": sats_piloto,
            "frp_total_del_sensor_solo_piloto": round(frp_piloto, 2),
            "duplicados_tecnicos_absorbidos": duplicados,
            "manifiestos": por_producto_man[producto],
            # transparencia: datos presentes en la ventana que NO son del piloto
            "observaciones_en_ventana_fuera_del_piloto": len(fuera_piloto),
            "source_kinds_fuera_del_piloto": sorted(
                {o["source_kind"] for o in fuera_piloto}
            ),
        }
        total_piloto += n_piloto

    # Territorial: SOLO observaciones del piloto.
    if total_piloto:
        ids_ph = ",".join("?" for _ in ids_piloto)
        productos_ph = ",".join("?" for _ in PILOTO_PRODUCTOS)
        params = [*PILOTO_PRODUCTOS, desde, hasta, *ids_piloto]
        try:
            obs_geo = duck.query(
                "SELECT og.dentro_pais, og.departamento, count(*) n "
                "FROM observations_geo og WHERE og.obs_id IN ("
                "  SELECT obs_id FROM observations"
                f"  WHERE product IN ({productos_ph}) AND acq_date >= ? AND acq_date <= ?"
                f"    AND manifest_id IN ({ids_ph})"
                ") GROUP BY 1, 2 ORDER BY n DESC",
                params,
            )
            dentro = sum(r["n"] for r in obs_geo if r["dentro_pais"])
            fuera = sum(r["n"] for r in obs_geo if not r["dentro_pais"])
            reporte["territorial"] = {
                "dentro_pais": dentro,
                "fuera_pais_descartadas_del_conjunto_nacional": fuera,
                "por_departamento": [r for r in obs_geo if r["dentro_pais"]],
            }
        except Exception:  # noqa: BLE001 — sin capa geo asignada
            reporte["territorial"] = None
            reporte["advertencias"].append(
                "Sin distribución territorial: la vista observations_geo no está "
                "disponible (correr 'hotspots geo assign' con la capa activa)."
            )

        # Eventos: SOLO los que referencian observaciones del piloto.
        try:
            eventos = duck.query(
                "SELECT DISTINCT e.event_id, e.n_observaciones, e.primera_obs_utc, "
                "e.ultima_obs_utc FROM events e "
                "JOIN event_observaciones eo ON e.event_id = eo.event_id "
                "WHERE eo.obs_id IN ("
                "  SELECT obs_id FROM observations"
                f"  WHERE product IN ({productos_ph}) AND acq_date >= ? AND acq_date <= ?"
                f"    AND manifest_id IN ({ids_ph})"
                ")",
                params,
            )
            reporte["eventos"] = {
                "n": len(eventos),
                "detalle": eventos,
                "nota": "solo eventos con al menos una observación del piloto",
            }
        except Exception as exc2:  # noqa: BLE001
            reporte["eventos"] = {
                "n": None,
                "nota": f"vista no disponible: {type(exc2).__name__}",
            }
    else:
        reporte["territorial"] = None
        reporte["eventos"] = {"n": 0, "nota": "sin observaciones del piloto"}

    # Cuarentena: SOLO corridas del piloto, dentro de la ventana.
    if runs_piloto:
        placeholders = ",".join("?" for _ in runs_piloto)
        productos_ph_q = ",".join("?" for _ in PILOTO_PRODUCTOS)
        try:
            q = duck.query(
                f"SELECT product, errors, count(*) n FROM quarantine "
                f"WHERE run_id IN ({placeholders}) AND product IN ({productos_ph_q}) "
                f"AND acq_date >= ? AND acq_date <= ? GROUP BY 1, 2 ORDER BY n DESC",
                [*runs_piloto, *PILOTO_PRODUCTOS, desde, hasta],
            )
            reporte["cuarentena"] = {
                "filas": sum(r["n"] for r in q),
                "por_motivo": q,
                "nota": "solo corridas del piloto (run_id de sus manifiestos)",
            }
        except Exception:  # noqa: BLE001 — sin vista de cuarentena = 0 filas
            reporte["cuarentena"] = {
                "filas": 0,
                "por_motivo": [],
                "nota": "vista quarantine no disponible (sin filas de cuarentena)",
            }
    else:
        reporte["cuarentena"] = {"filas": 0, "por_motivo": [], "nota": "sin manifiestos del piloto"}

    # ------------------------------------------------------------- clasificación
    # La clasificación describe los datos PRESENTES EN LA VENTANA:
    #   - con piloto real            -> 'real' (respaldado por manifiestos)
    #   - sin piloto y con fixtures  -> 'fixture' (NUNCA se ve como real)
    #   - ventana vacía              -> 'vacio'
    # El conteo observaciones_del_piloto distingue además qué parte de esos
    # datos está respaldada por los manifiestos del piloto.
    clasificacion = clasificar_source_kinds(kinds_en_ventana)
    reporte["clasificacion_datos"] = clasificacion
    reporte["observaciones_del_piloto"] = total_piloto
    reporte["observaciones_en_ventana_fuera_del_piloto"] = len(kinds_en_ventana) - total_piloto

    # Advertencias de procedencia (4.3: fallar o advertir).
    advertencias = reporte["advertencias"]
    if faltantes:
        advertencias.append(
            f"{len(faltantes)} de {len(esperadas)} consultas del piloto SIN manifiesto: "
            "el piloto no está completo o no se ejecutó."
        )
    if incompletos:
        advertencias.append(
            f"{len(incompletos)} manifiesto(s) del piloto con estado no exitoso o "
            "problemas RAW↔procesado (ver manifiestos.incompletos_o_con_problemas)."
        )
    if incompatibles:
        advertencias.append(
            f"{len(incompatibles)} manifiesto(s) firms_api dentro de la ventana con "
            "parámetros distintos de los esperados (ver manifiestos.incompatibles)."
        )
    if artefactos_raw_vacios:
        advertencias.append(
            f"{len(artefactos_raw_vacios)} artefacto(s) RAW de 0 bytes identificados "
            "(ver manifiestos.artefactos_raw_vacios): evidencia de adquisiciones "
            "fallidas preservada — no son observaciones, ni CSV válidos, ni días "
            "sin detecciones (M011-C §3)."
        )
    for producto, r in reporte["productos"].items():
        if r["dias_sin_cobertura_exitosa"]:
            advertencias.append(
                f"{producto}: {len(r['dias_sin_cobertura_exitosa'])} día(s) de la "
                "ventana SIN adquisición exitosa que los cubra (ver "
                "dias_sin_cobertura_exitosa): no se interpretan como días sin "
                "detecciones."
            )
    if total_piloto == 0 and kinds_en_ventana:
        advertencias.append(
            "Hay observaciones DENTRO de la ventana que NO pertenecen al piloto "
            f"(source_kinds: {sorted(set(kinds_en_ventana))}): este reporte NO verifica "
            "un piloto real. Los datos presentes están clasificados como "
            f"'{clasificacion}' y excluidos de los conteos del piloto."
        )
    if clasificacion == "mixto_real_fixture":
        advertencias.append(
            "Mezcla de procedencias en la ventana (firms_api y fixture): "
            "revisar antes de cualquier análisis."
        )

    # Código de salida.
    exit_code = EXIT_OK
    if faltantes or incompletos:
        # manifiesto faltante/incompleto: el piloto no se puede dar por verificado
        exit_code = EXIT_PROCEDENCIA
    if total_piloto == 0 and kinds_en_ventana:
        exit_code = EXIT_PROCEDENCIA
    if clasificacion in ("unknown", "mixto_real_fixture"):
        exit_code = EXIT_PROCEDENCIA

    return reporte, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("desde", nargs="?", default=DESDE_DEFAULT, help="YYYY-MM-DD (inicio)")
    parser.add_argument(
        "hasta",
        nargs="?",
        default=None,
        help="YYYY-MM-DD (fin, default: DESDE+6 — ventana de 7 días)",
    )
    parser.add_argument("--data-dir", default=None, help="Raíz de datos alternativa")
    parser.add_argument("--json", default=None, help="Ruta de salida del reporte JSON")
    args = parser.parse_args()

    hasta = args.hasta or (date.fromisoformat(args.desde) + timedelta(days=6)).isoformat()

    try:
        reporte, code = verificar(args.desde, hasta, data_dir=args.data_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR ({type(exc).__name__}): {exc}", file=sys.stderr)
        return EXIT_ERROR

    clasif = reporte["clasificacion_datos"]
    salida = (
        Path(args.json) if args.json else DATOS / f"reporte_piloto_{args.desde}_{clasif}.json"
    )
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(reporte, indent=2, ensure_ascii=False, default=str))

    print(
        f"== Piloto {args.desde}..{hasta} (UTC) · capa geo: "
        f"{reporte['capa_geo_activa']} =="
    )
    man = reporte["manifiestos"]
    print(
        f"  manifiestos: {man['encontrados']}/{man['esperados']} · "
        f"faltantes={len(man['faltantes'])} · "
        f"incompletos={len(man['incompletos_o_con_problemas'])} · "
        f"incompatibles={len(man['incompatibles'])} · "
        f"raw_vacíos={len(man['artefactos_raw_vacios'])}"
    )
    for producto, r in reporte["productos"].items():
        print(
            f"  {producto:18s} piloto={r['observaciones_del_piloto']:6d} "
            f"fuera_del_piloto={r['observaciones_en_ventana_fuera_del_piloto']:4d} "
            f"duplicados={r['duplicados_tecnicos_absorbidos']} "
            f"sin_cob={len(r['dias_sin_cobertura_exitosa'])}"
        )
    print(
        f"  clasificación de los datos en la ventana: {clasif} · "
        f"obs del piloto: {reporte['observaciones_del_piloto']}"
    )
    for a in reporte["advertencias"]:
        print(f"  ADVERTENCIA: {a}")
    print(f"reporte -> {salida}")
    if code == EXIT_PROCEDENCIA:
        print(
            "RESULTADO: PROCEDENCIA NO DEMOSTRABLE como piloto real "
            "(código 3). Véanse las advertencias."
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
