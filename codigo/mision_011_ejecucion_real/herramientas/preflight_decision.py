"""Lógica de decisión del preflight FIRMS — Misión 011 / correcciones M011-C.

Módulo puro (sin red, sin dependencias del repo) para que las pruebas
offline verifiquen las reglas duras del encargo M011 y las correcciones
M011-C:

1. NO confundir el límite documentado (``transaction_limit``, 5000
   transacciones / ventana de 10 minutos) con el saldo disponible
   (``transaction_limit - current_transactions``).
2. Política conservadora de transacciones (M011-C §2): seis peticiones NO
   equivalen necesariamente a seis transacciones (NASA advierte que las
   consultas grandes pueden contar como varias). No se inventa un coste
   fijo por consulta; se registra el saldo inicial, las consultas son
   independientes e idempotentes, y el orquestador verifica el consumo
   real cuando es posible deteniéndose si la cuota restante no permite
   continuar con seguridad.
3. Una MAP_KEY cuya huella pública (``sha256[:16]``) coincida con una clave
   expuesta en conversaciones se RECHAZA: debe regenerarse en el sitio
   oficial y vivir solo en el ``.env`` local (permisos 600).
4. La ventana del piloto (2026-11-04..2026-11-10) debe estar cubierta por
   los tres productos NRT en ``data_availability``; si no, se informa y se
   detiene (NO se sustituye la ventana en silencio).
5. Clasificación de la respuesta de ``mapkey_status`` (M011-C §4): un error
   de cuota NO se clasifica como clave inválida, y una página informativa
   (HTML) NO se clasifica como clave inválida ni como respuesta válida del
   API.

Huellas públicas: ``sha256(clave)[:16]`` es información no sensible (M010 ya
publicó la de su clave en evidencias) y permite RECHAZAR claves quemadas sin
conocerlas.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os

# Huellas públicas (sha256[:16]) de MAP_KEYS expuestas en conversaciones.
# La clave de M010 (validada vía endpoint) fue pegada por el propietario en
# el chat de esa misión: queda marcada como quemada (M011, regla 2).
# FIREIA_CLAVES_EXPUESTAS_FP_EXTRA (env): huellas ADICIONALES a rechazar —
# solo añade rechazos, nunca los quita; se usa en las pruebas e2e del
# preflight para simular una clave quemada sin conocer la original.
CLAVES_EXPUESTAS_FP: frozenset[str] = frozenset(
    {
        "92e0e8c1984aa80d",  # MAP_KEY validada en M010, expuesta en chat
        *(
            h.strip()
            for h in (os.environ.get("FIREIA_CLAVES_EXPUESTAS_FP_EXTRA", "")).split(",")
            if h.strip()
        ),
    }
)

PRODUCTOS_PILOTO = ("MODIS_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")
PRODUCTO_RETIRADO = "VIIRS_SNPP_NRT"
CONSULTAS_PILOTO = 6  # 3 productos × ventanas 5d + 2d (DAY_RANGE máx 5)


def fingerprint(map_key: str) -> str:
    """Huella pública sha256[:16] de la clave (segura de registrar)."""
    return hashlib.sha256(map_key.encode("utf-8")).hexdigest()[:16]


def decision_clave(huella: str) -> dict:
    """Regla M011 #2: una clave expuesta no se reutiliza."""
    quemada = huella in CLAVES_EXPUESTAS_FP
    return {
        "huella": huella,
        "expuesta": quemada,
        "decision": "RECHAZAR_REGENERAR" if quemada else "ACEPTAR",
    }


def parse_mapkey_status(texto: str) -> dict:
    """Parsea la respuesta de ``mapserver/mapkey_status/?MAP_KEY=...``.

    Formato documentado (Fire Data Academy, verificado M011)::

        {"transaction_limit": 5000, "current_transactions": 46,
         "transaction_interval": "10 minutes"}

    Se admiten variantes de nombres (``max_transactions``,
    ``transactions_available``, ``transaction_time_window``) por si el
    servidor cambia el esquema. Lanza ``ValueError`` si no hay campos
    suficientes para decidir.
    """
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ValueError(f"respuesta no es JSON válido: {exc}") from exc
    if not isinstance(datos, dict):
        raise ValueError("respuesta JSON sin objeto raíz")

    limite = datos.get("transaction_limit", datos.get("max_transactions"))
    actuales = datos.get("current_transactions")
    intervalo = datos.get(
        "transaction_interval",
        str(datos.get("transaction_time_window", "")) + (
            " minutes" if "transaction_time_window" in datos else ""
        ),
    )
    if limite is None or actuales is None:
        raise ValueError(
            "faltan transaction_limit/current_transactions en mapkey_status"
        )
    try:
        limite = int(limite)
        actuales = int(actuales)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit/current no numéricos") from exc

    if "transactions_available" in datos:
        disponible = int(datos["transactions_available"])
    else:
        disponible = limite - actuales
    return {
        "transaction_limit": limite,
        "current_transactions": actuales,
        "transactions_available": disponible,
        "transaction_interval": intervalo,
    }


def decision_saldo(estado: dict, consultas: int = CONSULTAS_PILOTO) -> dict:
    """Regla M011 #6/#7 + política conservadora M011-C §2.

    Piso mínimo: ``disponible >= consultas`` (cada petición cuesta AL MENOS
    una transacción). NO se inventa un coste fijo por consulta: NASA advierte
    que una consulta de área multi-día puede contar como VARIAS transacciones,
    por lo que el saldo inicial queda registrado, las consultas son
    independientes e idempotentes, y el orquestador verifica el consumo real
    durante la ejecución (deteniéndose si la cuota no alcanza).
    """
    disponible = estado["transactions_available"]
    limite = estado["transaction_limit"]
    suficiente = disponible >= consultas
    return {
        "transaction_limit": limite,
        "current_transactions": estado["current_transactions"],
        "transactions_available": disponible,
        "consultas_requeridas": consultas,
        "saldo_suficiente": suficiente,
        "decision": "GO" if suficiente else "DETENER_SALDO_INSUFICIENTE",
        "politica_transacciones": {
            # M011-C §2: seis peticiones ≠ seis transacciones. Documentado;
            # sin coste fijo inventado.
            "peticiones": consultas,
            "coste_por_peticion": (
                "no_fijado: una consulta multi-día puede contar como varias "
                "transacciones (advertencia NASA); no se asume 1:1"
            ),
            "saldo_inicial": disponible,
            "verificacion_de_consumo": (
                "el orquestador consulta el saldo real entre consultas "
                "(tras fallos; configurable) y detiene nuevas peticiones si "
                "la cuota restante no permite continuar con seguridad"
            ),
            "servicios_pagos": "prohibidos (M011/M011-C)",
        },
        "nota": (
            "transaction_limit es el tope por ventana de 10 minutos "
            "(documentado); NO es el saldo disponible. OJO: el GO con saldo "
            f">= {consultas} es un PISO, no una garantía: cada petición "
            "puede contar como varias transacciones; el consumo real se "
            "verifica durante la ejecución."
            if suficiente
            else "Esperar el reinicio automático de la ventana (10 minutos, "
            "gratuito) y repetir el preflight; si persiste, solicitar "
            "aumento de límite a FIRMS (gratuito). No se usan servicios "
            "pagos ni se improvisa cuota."
        ),
    }


def decision_continuar(estado: dict, pendientes: int) -> dict:
    """M011-C §2: ¿la cuota permite lanzar `pendientes` consultas más?

    Usada por el orquestador ENTRE consultas con el saldo observado en ese
    momento. Conservadora: exige ``disponible >= pendientes`` (cada petición
    cuesta al menos una transacción y puede costar más). Si no alcanza, la
    decisión es detener el lanzamiento de nuevas peticiones — las consultas
    restantes quedan pendientes (no fallidas) y pueden reintentarse tras el
    reinicio de la ventana de 10 minutos, sin repetir las ya exitosas.
    """
    disponible = estado["transactions_available"]
    continuar = pendientes <= 0 or disponible >= pendientes
    return {
        "transactions_available": disponible,
        "pendientes": pendientes,
        "decision": "CONTINUAR" if continuar else "DETENER_SALDO_INSUFICIENTE",
        "nota": (
            "saldo suficiente para las consultas pendientes (piso: 1 "
            "transacción por petición; puede ser más)"
            if continuar
            else "detener: la cuota restante no cubre con seguridad las "
            "consultas pendientes; esperar el reinicio de la ventana "
            "(10 minutos, gratuito) y relanzar — las ya exitosas no se repiten"
        ),
    }


#: Códigos que el endpoint de estado puede devolver y su clasificación
#: M011-C §4 (los errores de cuota NO son claves inválidas; una página
#: informativa NO es una respuesta válida del API).
def clasificar_respuesta_mapkey(http_code: int | str | None, cuerpo: str) -> dict:
    """Clasifica la respuesta de ``mapserver/mapkey_status``.

    Devuelve ``{"tipo": ..., "detalle": ...}`` donde ``tipo`` es uno de:

    - ``esquema_valido``   : 200 + JSON con transaction_limit y
                             current_transactions (el API responde de verdad).
    - ``clave_invalida``   : 401/403, o texto del proveedor que menciona una
                             MAP_KEY inválida/no autorizada.
    - ``cuota``            : 429 (rate/cuota agotada) — NUNCA clave inválida.
    - ``pagina_informativa``: 200 con HTML — el transporte funciona pero el
                             API no respondió como API (mantenimiento,
                             portal, redirección). No es culpa de la clave.
    - ``error_proveedor``  : 404/5xx — el servicio no está disponible ahora.
    - ``esquema_desconocido``: 200 con JSON sin los campos documentados.
    """
    try:
        codigo = int(http_code) if http_code is not None else 0
    except (TypeError, ValueError):
        codigo = 0
    texto = (cuerpo or "").strip()
    lowered = texto.lower()

    if codigo in (401, 403):
        return {"tipo": "clave_invalida", "detalle": f"HTTP {codigo}"
                " (endpoint rechaza la credencial)"}
    if codigo == 429:
        return {
            "tipo": "cuota",
            "detalle": "HTTP 429: cuota/transacciones agotadas (NO es una "
            "clave inválida); esperar el reinicio de la ventana de 10 minutos",
        }
    if codigo == 404 or codigo >= 500:
        return {"tipo": "error_proveedor", "detalle": f"HTTP {codigo}"
                " (servicio no disponible o endpoint movido)"}
    if codigo != 200:
        return {"tipo": "error_proveedor", "detalle": f"HTTP {codigo} inesperado"}

    # 200: el cuerpo decide si es el API de verdad (M011-C §4).
    if lowered.startswith("<!") or "<html" in lowered[:512] or "</html>" in lowered[-512:]:
        return {
            "tipo": "pagina_informativa",
            "detalle": "200 con HTML: el host responde pero NO es una "
            "respuesta válida del API (página informativa, mantenimiento o "
            "portal); no se clasifica como clave inválida",
        }
    if "map_key" in lowered and ("invalid" in lowered or "not valid" in lowered):
        return {"tipo": "clave_invalida", "detalle": "el proveedor reporta "
                "una MAP_KEY inválida"}
    if lowered.startswith("invalid") or "not authorized" in lowered:
        return {"tipo": "clave_invalida", "detalle": "respuesta de credencial "
                "rechazada"}
    try:
        parse_mapkey_status(texto)
    except ValueError as exc:
        return {
            "tipo": "esquema_desconocido",
            "detalle": f"200 con JSON que no sigue el esquema documentado: {exc}",
        }
    return {"tipo": "esquema_valido", "detalle": "esquema documentado presente"}


def validar_disponibilidad_csv(
    texto_csv: str, desde: str, hasta: str
) -> dict:
    """Valida la cobertura de la ventana del piloto en data_availability.

    Devuelve por producto: ``min_date``/``max_date`` y ``cubre_ventana``
    (min_date <= desde y max_date >= hasta). El producto retirado
    (VIIRS_SNPP_NRT) se reporta solo como referencia de exclusión.
    Lanza ``ValueError`` si el CSV no tiene el formato oficial.
    """
    lector = csv.DictReader(io.StringIO(texto_csv))
    if lector.fieldnames is None or "data_id" not in lector.fieldnames:
        raise ValueError("CSV sin cabecera oficial (falta 'data_id')")
    filas = {f["data_id"]: f for f in lector if f.get("data_id")}
    faltantes = [p for p in PRODUCTOS_PILOTO if p not in filas]
    if faltantes:
        raise ValueError(f"productos del piloto ausentes en CSV: {faltantes}")

    productos: dict[str, dict] = {}
    cubre_todos = True
    for prod in PRODUCTOS_PILOTO:
        fila = filas[prod]
        min_d = (fila.get("min_date") or "").strip()
        max_d = (fila.get("max_date") or "").strip()
        cubre = bool(min_d) and bool(max_d) and min_d <= desde and max_d >= hasta
        cubre_todos = cubre_todos and cubre
        productos[prod] = {
            "min_date": min_d,
            "max_date": max_d,
            "cubre_ventana": cubre,
        }
    retirado: dict | None = None
    if PRODUCTO_RETIRADO in filas:
        retirado = {
            "min_date": (filas[PRODUCTO_RETIRADO].get("min_date") or "").strip(),
            "max_date": (filas[PRODUCTO_RETIRADO].get("max_date") or "").strip(),
            "nota": "producto retirado (cese oficial); excluido del piloto",
        }
    return {
        "ventana": {"desde": desde, "hasta": hasta},
        "productos": productos,
        "producto_retirado": retirado,
        "ventana_disponible": cubre_todos,
        "decision": "GO" if cubre_todos else "DETENER_VENTANA_NO_DISPONIBLE",
    }
