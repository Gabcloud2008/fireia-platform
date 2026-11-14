"""Pruebas offline del preflight FIRMS — Misión 011.

Sin red: se verifica la lógica de decisión (`preflight_decision.py`), la
sintaxis de los scripts bash y las reglas duras del encargo M011:

1. El saldo disponible NO es el límite documentado (5000/10 min): se
   calcula transaction_limit - current_transactions (o el campo
   transactions_available si el servidor lo entrega).
2. Saldo < 6 consultas ⇒ DETENER (no se descarga); la nota explica cómo
   obtener cuota documentada y gratuita (ventana de 10 minutos / aumento de
   límite vía FIRMS). Nada de servicios pagos.
3. Una huella pública de clave expuesta en conversaciones ⇒ RECHAZAR.
4. La ventana 2026-11-04..2026-11-10 debe estar cubierta por los 3
   productos NRT; si no, DETENER (sin sustituir la ventana en silencio).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HERR_M011 = RAIZ / "mision_011_ejecucion_real/herramientas"
sys.path.insert(0, str(HERR_M011))

import preflight_decision as pd  # noqa: E402

CSV_COMPLETO = (
    "data_id,min_date,max_date,day_range_nrt\n"
    "MODIS_NRT,2026-09-01,2026-11-11,1\n"
    "VIIRS_NOAA20_NRT,2026-08-01,2026-11-11,1\n"
    "VIIRS_NOAA21_NRT,2024-01-17,2026-11-11,1\n"
    "VIIRS_SNPP_NRT,2024-01-17,2026-11-02,1\n"
    "MODIS_SP,2026-09-01,2026-11-11,8\n"
)

CSV_RECORTADO = CSV_COMPLETO.replace(
    "VIIRS_NOAA21_NRT,2024-01-17,2026-11-11,1",
    "VIIRS_NOAA21_NRT,2024-01-17,2026-11-09,1",
)


# ---------------------------------------------------------------------------
# huella pública y rechazo de claves expuestas (M011 #2)
# ---------------------------------------------------------------------------

def test_fingerprint_es_sha256_16_y_determinista():
    huella = pd.fingerprint("cualquier-valor-de-clave")
    assert len(huella) == 16
    assert all(c in "0123456789abcdef" for c in huella)
    assert huella == pd.fingerprint("cualquier-valor-de-clave")


def test_clave_expuesta_en_conversaciones_se_rechaza():
    # huella pública de la MAP_KEY validada en M010 y expuesta en el chat
    assert "92e0e8c1984aa80d" in pd.CLAVES_EXPUESTAS_FP
    decision = pd.decision_clave("92e0e8c1984aa80d")
    assert decision["expuesta"] is True
    assert decision["decision"] == "RECHAZAR_REGENERAR"


def test_clave_nueva_se_acepta():
    decision = pd.decision_clave(pd.fingerprint("STUBKEYNOREAL1234"))
    assert decision["expuesta"] is False
    assert decision["decision"] == "ACEPTAR"


def test_los_scripts_bash_no_embeden_ninguna_huella():
    """Las huellas viven SOLO en el registro público del módulo de decisión."""
    for script in (
        HERR_M011 / "preflight_firms.sh",
        RAIZ / "mision_007_datos_reales/herramientas/piloto_firms_7dias.sh",
    ):
        contenido = script.read_text(encoding="utf-8")
        for fp in pd.CLAVES_EXPUESTAS_FP:
            assert fp not in contenido, f"{script.name} embede la huella {fp}"


# ---------------------------------------------------------------------------
# mapkey_status: saldo ≠ límite (M011 #6)
# ---------------------------------------------------------------------------

def test_parse_formato_documentado_del_endpoint():
    """Formato exacto documentado en la Fire Data Academy."""
    estado = pd.parse_mapkey_status(
        '{"transaction_limit": 5000, "current_transactions": 46, '
        '"transaction_interval": "10 minutes"}'
    )
    assert estado["transaction_limit"] == 5000
    assert estado["current_transactions"] == 46
    assert estado["transactions_available"] == 5000 - 46


def test_parse_variantes_de_campos():
    estado = pd.parse_mapkey_status(
        '{"max_transactions": 5000, "current_transactions": 10, '
        '"transactions_available": 4990}'
    )
    assert estado["transactions_available"] == 4990


def test_parse_acepta_y_rechaza_entradas():
    assert pd.parse_mapkey_status(
        '{"transaction_limit": "5000", "current_transactions": "5"}'
    )["transactions_available"] == 4995
    for malo in ("not json", '["lista"]', '{"current_transactions": 1}',
                 '{"transaction_limit": 5000}',
                 '{"transaction_limit": "x", "current_transactions": 1}'):
        try:
            pd.parse_mapkey_status(malo)
        except ValueError:
            continue
        raise AssertionError(f"aceptó entrada inválida: {malo!r}")


def test_saldo_suficiente_y_regla_no_confundir_limite_con_saldo():
    estado = pd.parse_mapkey_status(
        '{"transaction_limit": 5000, "current_transactions": 46}'
    )
    decision = pd.decision_saldo(estado)
    assert decision["saldo_suficiente"] is True
    assert decision["decision"] == "GO"
    assert decision["transactions_available"] == 4954
    # el límite documentado (5000/10 min) NO es el saldo
    assert decision["transaction_limit"] != decision["transactions_available"]
    assert "NO es el saldo" in decision["nota"]


def test_saldo_insuficiente_detiene_sin_descargar():
    estado = pd.parse_mapkey_status(
        '{"transaction_limit": 5000, "current_transactions": 4997}'
    )
    decision = pd.decision_saldo(estado)
    assert decision["transactions_available"] == 3
    assert decision["saldo_suficiente"] is False
    assert decision["decision"] == "DETENER_SALDO_INSUFICIENTE"
    # cómo obtener cuota: documentado y gratuito, sin improvisar
    assert "10 minutos" in decision["nota"]
    assert "gratuito" in decision["nota"]


def test_umbral_exacto_seis_consultas():
    estado = pd.parse_mapkey_status(
        '{"transaction_limit": 10, "current_transactions": 4}'
    )
    assert pd.decision_saldo(estado)["decision"] == "GO"          # 6 == 6
    estado2 = pd.parse_mapkey_status(
        '{"transaction_limit": 10, "current_transactions": 5}'
    )
    assert pd.decision_saldo(estado2)["decision"] == "DETENER_SALDO_INSUFICIENTE"


# ---------------------------------------------------------------------------
# política conservadora de transacciones (M011-C §2)
# ---------------------------------------------------------------------------

def test_go_de_saldo_es_piso_no_garantia():
    """El GO documenta que 6 peticiones ≠ 6 transacciones y registra el
    saldo inicial; no se inventa coste fijo por consulta."""
    estado = pd.parse_mapkey_status(
        '{"transaction_limit": 5000, "current_transactions": 4990}'
    )  # disponible = 10: alcanza el piso de 6, pero puede no alcanzar
    decision = pd.decision_saldo(estado)
    assert decision["saldo_suficiente"] is True
    politica = decision["politica_transacciones"]
    assert politica["peticiones"] == 6
    assert politica["saldo_inicial"] == 10
    assert "no_fijado" in politica["coste_por_peticion"]
    assert "varias" in politica["coste_por_peticion"].lower()
    assert "PISO" in decision["nota"]


def test_decision_continuar_detiene_con_cuota_ajustada():
    """Entre consultas: si el saldo no cubre las pendientes, se detiene el
    lanzamiento de nuevas peticiones (quedan pendientes, no fallidas)."""
    saldo_ok = pd.parse_mapkey_status(
        '{"transaction_limit": 5000, "current_transactions": 100}'
    )
    assert pd.decision_continuar(saldo_ok, 5)["decision"] == "CONTINUAR"
    saldo_justo = pd.parse_mapkey_status(
        '{"transaction_limit": 5000, "current_transactions": 4996}'
    )  # disponible = 4 < 5 pendientes
    decision = pd.decision_continuar(saldo_justo, 5)
    assert decision["decision"] == "DETENER_SALDO_INSUFICIENTE"
    assert "no se repiten" in decision["nota"]
    # sin pendientes no hay nada que decidir: continuar
    assert pd.decision_continuar(saldo_justo, 0)["decision"] == "CONTINUAR"


# ---------------------------------------------------------------------------
# clasificación de la respuesta de mapkey_status (M011-C §4)
# ---------------------------------------------------------------------------

def test_cuota_no_se_clasifica_como_clave_invalida():
    """HTTP 429 = cuota agotada, NO clave inválida."""
    clasif = pd.clasificar_respuesta_mapkey(429, "too many transactions")
    assert clasif["tipo"] == "cuota"
    assert "NO es una clave inválida" in clasif["detalle"]


def test_pagina_informativa_no_es_respuesta_valida_del_api():
    """200 con HTML: el host responde pero NO es el API; tampoco es culpa de
    la clave (antes se clasificaba erróneamente como clave rechazada)."""
    clasif = pd.clasificar_respuesta_mapkey(
        200, "<html><body>maintenance</body></html>"
    )
    assert clasif["tipo"] == "pagina_informativa"
    assert "no se clasifica como clave inválida" in clasif["detalle"]


def test_clasificaciones_restantes_de_mapkey_status():
    valido = '{"transaction_limit": 5000, "current_transactions": 1}'
    assert pd.clasificar_respuesta_mapkey(200, valido)["tipo"] == "esquema_valido"
    assert pd.clasificar_respuesta_mapkey(403, "forbidden")["tipo"] == "clave_invalida"
    assert pd.clasificar_respuesta_mapkey(
        200, "MAP_KEY is invalid"
    )["tipo"] == "clave_invalida"
    assert pd.clasificar_respuesta_mapkey(503, "upstream")["tipo"] == "error_proveedor"
    assert pd.clasificar_respuesta_mapkey(404, "")["tipo"] == "error_proveedor"
    assert pd.clasificar_respuesta_mapkey(
        200, '{"otro": "esquema"}'
    )["tipo"] == "esquema_desconocido"


def test_huellas_extra_del_entorno_solo_agregan_rechazos():
    """FIREIA_CLAVES_EXPUESTAS_FP_EXTRA (pruebas): añadir huellas NUNCA
    permite aceptar una clave quemada (solo puede rechazar más)."""
    import importlib
    import os

    huella_nueva = pd.fingerprint("CLAVE-EXTRA-PRUEBA")
    assert huella_nueva not in pd.CLAVES_EXPUESTAS_FP
    os.environ["FIREIA_CLAVES_EXPUESTAS_FP_EXTRA"] = huella_nueva
    try:
        importlib.reload(pd)
        assert huella_nueva in pd.CLAVES_EXPUESTAS_FP
        assert "92e0e8c1984aa80d" in pd.CLAVES_EXPUESTAS_FP  # la original queda
        assert pd.decision_clave(huella_nueva)["decision"] == "RECHAZAR_REGENERAR"
    finally:
        os.environ.pop("FIREIA_CLAVES_EXPUESTAS_FP_EXTRA", None)
        importlib.reload(pd)


# ---------------------------------------------------------------------------
# disponibilidad de la ventana en los 3 productos (M011 ejecución #1)
# ---------------------------------------------------------------------------

def test_ventana_completa_disponible():
    resultado = pd.validar_disponibilidad_csv(CSV_COMPLETO, "2026-11-04", "2026-11-10")
    assert resultado["ventana_disponible"] is True
    assert resultado["decision"] == "GO"
    assert all(v["cubre_ventana"] for v in resultado["productos"].values())
    retirado = resultado["producto_retirado"]
    assert retirado is not None and retirado["max_date"] == "2026-11-02"
    assert "excluido" in retirado["nota"]


def test_ventana_recortada_en_un_producto_detiene():
    resultado = pd.validar_disponibilidad_csv(CSV_RECORTADO, "2026-11-04", "2026-11-10")
    assert resultado["ventana_disponible"] is False
    assert resultado["decision"] == "DETENER_VENTANA_NO_DISPONIBLE"
    assert resultado["productos"]["VIIRS_NOAA21_NRT"]["cubre_ventana"] is False
    assert resultado["productos"]["MODIS_NRT"]["cubre_ventana"] is True


def test_csv_malformado_o_incompleto_rechazado():
    for malo in ("", "otra,cabecera\n1,2\n", "fecha\n2026-01-01\n"):
        try:
            pd.validar_disponibilidad_csv(malo, "2026-11-04", "2026-11-10")
        except ValueError:
            continue
        raise AssertionError(f"aceptó CSV inválido: {malo!r}")
    sin_noaa21 = "data_id,min_date,max_date\nMODIS_NRT,2026-09-01,2026-11-11\n"
    try:
        pd.validar_disponibilidad_csv(sin_noaa21, "2026-11-04", "2026-11-10")
    except ValueError as exc:
        assert "VIIRS_NOAA21_NRT" in str(exc)
    else:
        raise AssertionError("aceptó CSV sin un producto del piloto")


# ---------------------------------------------------------------------------
# sintaxis y contratos de los scripts bash
# ---------------------------------------------------------------------------

def test_sintaxis_bash_de_preflight_y_orquestador():
    for script in (
        HERR_M011 / "preflight_firms.sh",
        RAIZ / "mision_007_datos_reales/herramientas/piloto_firms_7dias.sh",
    ):
        subprocess.run(
            ["bash", "-n", str(script)], check=True,
            capture_output=True, text=True, timeout=30,
        )


def test_contrato_preflight_orquestador_variables():
    """El orquestador pasa PREFLIGHT_AVAIL_DEST y PREFLIGHT_RESULTADO_JSON;
    el preflight los documenta y honra (contrato M011)."""
    preflight = (HERR_M011 / "preflight_firms.sh").read_text(encoding="utf-8")
    orquestador = (RAIZ / "mision_007_datos_reales/herramientas"
                   / "piloto_firms_7dias.sh").read_text(encoding="utf-8")
    for var in ("PREFLIGHT_AVAIL_DEST", "PREFLIGHT_RESULTADO_JSON"):
        assert var in preflight
        assert var in orquestador
    # el orquestador propaga el código del preflight y no lanza consultas
    assert "Ninguna consulta del piloto fue lanzada" in orquestador
    # el preflight nunca imprime el valor de la clave
    assert 'echo "$FIRMS_MAP_KEY"' not in preflight


def test_preflight_sin_clave_en_urls_ni_en_argv_de_procesos():
    """M011-C §1: la clave JAMÁS viaja en argumentos de procesos.

    El preflight ya no llama a ``curl`` con URLs que embeben
    ``${FIRMS_MAP_KEY}``: todo HTTP con clave va por ``firms_http.py``, que
    la lee del entorno. Estático + dinámico (el dinámico vive en
    test_seguridad_m011c.py); aquí, el contrato estático del script.
    """
    import re

    preflight = (HERR_M011 / "preflight_firms.sh").read_text(encoding="utf-8")
    orquestador = (RAIZ / "mision_007_datos_reales/herramientas"
                   / "piloto_firms_7dias.sh").read_text(encoding="utf-8")
    # patrón de INVOCACIÓN real de curl (posición de comando), no menciones
    # en comentarios: ``curl`` al inicio de línea o tras ; & | $( ` `
    patron_comando = re.compile(r"(^|[;&|(]\s*|\$\(\s*)curl[\s\n]")
    for nombre, texto in (("preflight", preflight), ("orquestador", orquestador)):
        for num, linea in enumerate(texto.splitlines(), 1):
            if linea.lstrip().startswith("#"):
                continue  # comentarios pueden mencionar curl (documentación)
            assert not patron_comando.search(linea), (
                f"{nombre}:{num}: invocación de curl prohibida (M011-C §1): "
                f"{linea.strip()}"
            )
        # la clave solo aparece en formas SEGURAS: (a) comentario,
        # (b) asignación de ENTORNO a un proceso hijo
        #     (FIRMS_MAP_KEY="$FIRMS_MAP_KEY" python3 ...), o
        # (c) operaciones INTERNAS de bash (test [ -z/-n "${FIRMS_MAP_KEY:-}" ],
        #     patrón case *"$FIRMS_MAP_KEY"*, sustitución
        #     ${contenido//"$FIRMS_MAP_KEY"/...}) — nada de esto la pone en
        #     argv de un proceso hijo.
        for linea in texto.splitlines():
            if "${FIRMS_MAP_KEY" not in linea and "$FIRMS_MAP_KEY" not in linea:
                continue
            pelada = linea.strip()
            if pelada.startswith("#"):
                continue
            formas_seguras = (
                'FIRMS_MAP_KEY="$FIRMS_MAP_KEY"' in linea,      # (b)
                '[ -z "${FIRMS_MAP_KEY:-}" ]' in linea,          # (c)
                '[ -n "${FIRMS_MAP_KEY:-}" ]' in linea,          # (c)
                '*"$FIRMS_MAP_KEY"*' in linea,                   # (c) case
                '${contenido//"$FIRMS_MAP_KEY"' in linea,        # (c) sustitución
            )
            assert any(formas_seguras), (
                f"{nombre}: uso de la clave fuera de las formas seguras "
                f"(entorno/internas): {pelada}"
            )
        # la redacción de archivos no usa grep con la clave en argv
        assert 'grep -q "$FIRMS_MAP_KEY"' not in texto
        assert 'grep "$FIRMS_MAP_KEY"' not in texto


def test_firms_http_no_admite_clave_por_argumento():
    """El cliente HTTP rechaza cualquier intento de pasar la clave por argv."""
    resultado = subprocess.run(
        [sys.executable, str(HERR_M011 / "firms_http.py"),
         "mapkey-status", "--map-key", "CLAVE-FICTICIA"],
        capture_output=True, text=True, timeout=30,
    )
    assert resultado.returncode == 2
    assert "entorno" in resultado.stderr


def test_firms_http_rechaza_base_no_https():
    """HTTPS obligatorio: una base http:// ajena a localhost se rechaza."""
    resultado = subprocess.run(
        [sys.executable, str(HERR_M011 / "firms_http.py"),
         "probe", "--base", "http://firms.example.com"],
        capture_output=True, text=True, timeout=30,
    )
    assert resultado.returncode == 2
    assert "https" in resultado.stderr
