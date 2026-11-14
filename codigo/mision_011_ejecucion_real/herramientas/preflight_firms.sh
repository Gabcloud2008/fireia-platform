#!/usr/bin/env bash
# ============================================================================
# FIREIA — Preflight del piloto FIRMS (Misión 011, correcciones M011-C)
#
# Controles ANTES de descargar nada (orden del encargo M011, §"Antes de
# ejecutar"): huella de la MAP_KEY (rechazo de claves expuestas) →
# conectividad de TRANSPORTE HTTPS → saldo real de transacciones
# (mapkey_status, con clasificación correcta de errores: la cuota NO es una
# clave inválida, una página HTML NO es una respuesta válida del API) →
# disponibilidad NRT de la ventana en los 3 productos.
#
# SEGURIDAD M011-C §1 (prioridad máxima):
#   - NINGUNA llamada HTTP pone la MAP_KEY en argumentos de procesos (argv,
#     visible con ps): todas las consultas van por firms_http.py, que lee la
#     clave SOLO del entorno y construye las URLs dentro del proceso.
#   - No hay ningún `curl` con la clave en la URL; la clave no se imprime,
#     no se registra y se redacta de cualquier texto persistido.
#   - La redacción de archivos se hace con operaciones internas de bash
#     (sin grep con la clave como patrón, que también exponía la clave en argv).
#
# POLÍTICA DE TRANSACCIONES M011-C §2 (conservadora):
#   - El GO con saldo >= 6 es un PISO (cada petición cuesta al menos una
#     transacción), NO una garantía: NASA advierte que consultas multi-día
#     pueden contar como varias. No se inventa coste fijo por consulta.
#   - El saldo inicial queda registrado en el resultado; el orquestador
#     verifica el consumo real entre consultas y se detiene si no alcanza.
#
# URLS OFICIALES (Fire Data Academy, verificadas M011; visitadas por
# firms_http.py — clave SOLO por entorno):
#   estado de clave : {FIRMS_BASE}/mapserver/mapkey_status/?MAP_KEY=...
#   disponibilidad  : {FIRMS_BASE}/api/data_availability/csv/{KEY}/ALL
#   transporte      : {FIRMS_BASE}/api/area/  (sin clave; sondeo de red)
#
# VARIABLES DE ENTORNO:
#   FIRMS_MAP_KEY      (obligatoria; .env del repo como fallback)
#   FIREIA_ENV_FILE    (ruta del .env alternativo, default .env — pruebas)
#   DESDE              (default 2026-11-04; ventana ..+6 días)
#   FIRMS_BASE         (default https://firms.modaps.eosdis.nasa.gov;
#                       http:// SOLO se admite en localhost para pruebas)
#   DIR_EVIDENCIAS     (default mision_011_ejecucion_real/evidencias)
#   PREFLIGHT_RESULTADO_JSON  (ruta del resumen; default <DIR>/preflight_result.json)
#   PREFLIGHT_AVAIL_DEST      (si está definido, copia del CSV de disponibilidad
#                              para el orquestador; contrato con piloto_firms_7dias.sh)
#
# CÓDIGOS DE SALIDA:
#   0 GO  — todo verificado, se puede ejecutar el piloto
#   1     — error de infraestructura (deps, respuesta no válida del API,
#           fallo al entregar el CSV de disponibilidad al orquestador)
#   2     — sin salida HTTPS directa a FIRMS (bloqueo de transporte)
#   3     — MAP_KEY rechazada (inválida ante el endpoint o EXPUESTA: regenerar)
#   4     — saldo insuficiente para las 6 consultas (no se descarga)
#   5     — ventana del piloto no disponible en algún producto (no se descarga)
# ============================================================================
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"
HERR="mision_011_ejecucion_real/herramientas"
FIRMS_HTTP="$HERR/firms_http.py"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    sed -n '2,70p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
fi

# --- dependencias ------------------------------------------------------------
for cmd in python3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: falta el comando '$cmd' en PATH." >&2
        exit 1
    fi
done
if [ ! -f "$FIRMS_HTTP" ]; then
    echo "ERROR: no se encuentra $FIRMS_HTTP (cliente HTTP seguro M011-C)." >&2
    exit 1
fi
if ! date -u -d "2026-11-04 +5 days" +%F >/dev/null 2>&1; then
    echo "ERROR: se requiere GNU date (Linux/WSL o coreutils en macOS)." >&2
    exit 1
fi

# --- credenciales (entorno > .env; jamás impresas) ----------------------------
# FIREIA_ENV_FILE permite apuntar a otro archivo (o a uno inexistente) en las
# pruebas offline; en producción siempre es .env del repo.
ENV_FILE="${FIREIA_ENV_FILE:-.env}"
if [ -f "$ENV_FILE" ] && [ -z "${FIRMS_MAP_KEY:-}" ]; then
    set -a; . "./$ENV_FILE"; set +a
fi
if [ -z "${FIRMS_MAP_KEY:-}" ]; then
    echo "ERROR: FIRMS_MAP_KEY no configurada." >&2
    echo "  1) Generá una clave NUEVA en https://firms.modaps.eosdis.nasa.gov/api/map_key/" >&2
    echo "  2) Colocala SOLO en .env del repo (cp .env.example .env && chmod 600 .env)." >&2
    echo "  3) NO la pegues en chat, logs ni tickets." >&2
    exit 1
fi
if [ -f "$ENV_FILE" ]; then
    perms="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo '???')"
    if [ "$perms" != "600" ]; then
        echo "AVISO: $ENV_FILE tiene permisos $perms (se recomienda 600)." >&2
        chmod 600 "$ENV_FILE" 2>/dev/null || true
    fi
fi

DESDE="${DESDE:-2026-11-04}"
HASTA="$(date -u -d "$DESDE +6 days" +%F)"
FIRMS_BASE="${FIRMS_BASE:-https://firms.modaps.eosdis.nasa.gov}"
DIR_EVIDENCIAS="${DIR_EVIDENCIAS:-mision_011_ejecucion_real/evidencias}"
RESULTADO_JSON="${PREFLIGHT_RESULTADO_JSON:-$DIR_EVIDENCIAS/preflight_result.json}"

RUN_ID="preflight-$(date -u +%Y%m%dT%H%M%SZ)-$$"
EV_DIR="$DIR_EVIDENCIAS/$RUN_ID"
mkdir -p "$EV_DIR"

# Redacta la MAP_KEY de un archivo antes de persistirlo (higiene M011-C §1).
# SIN subprocess: grep con la clave como PATRÓN también la ponía en argv del
# proceso grep; la comparación se hace dentro del propio shell bash.
redactar_archivo() {
    local f="$1" contenido
    [ -f "$f" ] || return 0
    contenido="$(<"$f")" || return 0
    if [ -n "${FIRMS_MAP_KEY:-}" ]; then
        case "$contenido" in
            *"$FIRMS_MAP_KEY"*)
                printf '%s' "${contenido//"$FIRMS_MAP_KEY"/\{MAP_KEY\}}" > "$f"
                ;;
        esac
    fi
}

echo "== Preflight M011-C | ventana ${DESDE}..${HASTA} (UTC) | run_id ${RUN_ID} =="

# --- 1) huella pública vs claves expuestas (M011 #2) --------------------------
# La clave viaja por el ENTORNO del proceso (nunca en argv, visible con ps).
HUELLA="$(FIRMS_MAP_KEY="$FIRMS_MAP_KEY" python3 -c "
import sys, os, json
sys.path.insert(0, '$HERR')
from preflight_decision import fingerprint, decision_clave
print(json.dumps(decision_clave(fingerprint(os.environ['FIRMS_MAP_KEY']))))
")"
HUELLA_FP="$(echo "$HUELLA" | python3 -c "import json,sys; print(json.load(sys.stdin)['huella'])")"
if echo "$HUELLA" | grep -q '"expuesta": true'; then
    echo "ERROR: la MAP_KEY cargada tiene la huella de una clave EXPUESTA en" >&2
    echo "conversaciones (huella pública ${HUELLA_FP}). Regenerala en" >&2
    echo "https://firms.modaps.eosdis.nasa.gov/api/map_key/ y usá solo .env local." >&2
    exit 3
fi
echo "1) clave aceptada (huella pública ${HUELLA_FP}; el valor no se registra)"

# --- 2) transporte HTTPS directo (M011 #4; M011-C §4) -------------------------
# Sondeo de TRANSPORTE (sin clave en la URL): mide que el host de FIRMS
# responde por HTTPS. NO valida el API: la validez real del API la confirma
# el paso 3 con el esquema documentado de mapkey_status (M011-C §4: no se
# confunde una página informativa con una respuesta válida del API).
HTTP_AREA="$(python3 "$FIRMS_HTTP" probe --base "$FIRMS_BASE" --timeout 25 \
    --err-out "$EV_DIR/conexion_stderr.txt" 2>/dev/null || echo 000)"
[ -n "$HTTP_AREA" ] || HTTP_AREA=000
redactar_archivo "$EV_DIR/conexion_stderr.txt"
if [ "$HTTP_AREA" = "000" ]; then
    {
        echo "sondeo de transporte: firms_http.py probe --base \$FIRMS_BASE"
        echo "resultado: sin respuesta HTTPS (000 = sin conexión TCP/TLS)"
        date -u +"ts_utc: %Y-%m-%dT%H:%M:%SZ"
        cat "$EV_DIR/conexion_stderr.txt" 2>/dev/null
    } > "$EV_DIR/conexion_diagnostico.txt"
    echo "ERROR: sin salida HTTPS directa a FIRMS (transporte bloqueado)." >&2
    echo "Evidencia: $EV_DIR/conexion_diagnostico.txt" >&2
    exit 2
fi
echo "2) transporte HTTPS directo OK (HTTP ${HTTP_AREA} en $FIRMS_BASE; la"
echo "   validez del API se confirma en el paso 3 con el esquema documentado)"

# --- 3) saldo real de transacciones (M011 #5, #6; M011-C §2 y §4) -------------
# La clave viaja SOLO por el entorno hacia firms_http.py; la URL se construye
# dentro de ese proceso. El error de transporte queda redactado en evidencia.
HTTP_KEY="$(FIRMS_MAP_KEY="$FIRMS_MAP_KEY" python3 "$FIRMS_HTTP" mapkey-status \
    --base "$FIRMS_BASE" --timeout 60 --out "$EV_DIR/mapkey_status.json" \
    --err-out "$EV_DIR/mapkey_status_stderr.txt" 2>/dev/null || echo 000)"
[ -n "$HTTP_KEY" ] || HTTP_KEY=000
redactar_archivo "$EV_DIR/mapkey_status_stderr.txt"
redactar_archivo "$EV_DIR/mapkey_status.json"
if [ "$HTTP_KEY" = "000" ]; then
    echo "ERROR: sin respuesta del endpoint de estado (transporte)." >&2
    exit 2
fi

# Clasificación M011-C §4: cuota ≠ clave inválida; HTML ≠ clave inválida.
CLASIF="$(python3 -c "
import sys; sys.path.insert(0, '$HERR')
from preflight_decision import clasificar_respuesta_mapkey
import json
cuerpo = open('$EV_DIR/mapkey_status.json', encoding='utf-8', errors='replace').read()
print(json.dumps(clasificar_respuesta_mapkey('$HTTP_KEY', cuerpo)))
")"
TIPO="$(echo "$CLASIF" | python3 -c "import json,sys; print(json.load(sys.stdin)['tipo'])")"
echo "$CLASIF" > "$EV_DIR/clasificacion_mapkey.json"
case "$TIPO" in
    esquema_valido)
        ;;
    clave_invalida)
        echo "ERROR: el endpoint rechazó la MAP_KEY." >&2
        echo "Si la clave es nueva, esperá ~5 min tras generarla; si persiste, regenerála." >&2
        exit 3
        ;;
    cuota)
        echo "ERROR: cuota de transacciones agotada (NO es un problema de la clave)." >&2
        echo "La ventana se reinicia sola cada 10 minutos (gratuito): esperá y" >&2
        echo "repetí el preflight. Sin servicios pagos." >&2
        exit 4
        ;;
    pagina_informativa|error_proveedor|esquema_desconocido)
        echo "ERROR: FIRMS respondió pero NO con el servicio esperado (${TIPO})." >&2
        echo "Detalle: $(echo "$CLASIF" | python3 -c "import json,sys; print(json.load(sys.stdin)['detalle'])")" >&2
        echo "Esto NO se clasifica como clave inválida (M011-C §4)." >&2
        exit 1
        ;;
    *)
        echo "ERROR: clasificación desconocida (${TIPO})." >&2
        exit 1
        ;;
esac

SALDO="$(python3 -c "
import sys; sys.path.insert(0, '$HERR')
from preflight_decision import parse_mapkey_status, decision_saldo
import json
estado = parse_mapkey_status(open('$EV_DIR/mapkey_status.json').read())
print(json.dumps(decision_saldo(estado)))
")"
if [ -z "$SALDO" ]; then
    echo "ERROR: mapkey_status devolvió algo no interpretable." >&2
    exit 1
fi
echo "$SALDO" > "$EV_DIR/decision_saldo.json"
DISPONIBLE="$(echo "$SALDO" | python3 -c "import json,sys; print(json.load(sys.stdin)['transactions_available'])")"
echo "3) API responde con el esquema documentado (HTTP ${HTTP_KEY}). Saldo"
echo "   disponible: ${DISPONIBLE} transacciones (límite por ventana: $(echo "$SALDO" | python3 -c "import json,sys; print(json.load(sys.stdin)['transaction_limit'])"))."
if echo "$SALDO" | grep -q '"saldo_suficiente": false'; then
    echo "ERROR: saldo insuficiente para las 6 consultas (M011 #7). NO se descarga." >&2
    echo "Cómo obtener cuota (documentado, gratuito): esperar el reinicio" >&2
    echo "automático de la ventana (10 minutos) y repetir el preflight; si" >&2
    echo "persiste, solicitar aumento de límite a FIRMS. Sin servicios pagos." >&2
    exit 4
fi
echo "   GO de saldo es un PISO (>= 6): cada consulta multi-día puede contar"
echo "   como VARIAS transacciones (NASA); no se asume 1:1. El saldo inicial"
echo "   queda registrado y el orquestador verifica el consumo real entre"
echo "   consultas, deteniéndose si la cuota no alcanza (M011-C §2)."

# --- 4) disponibilidad NRT de la ventana (M011 Ejecución #1) ------------------
# Re-verificación de la ventana JUSTO ANTES de ejecutar (M011-C §4). Clave,
# otra vez, solo por el entorno hacia firms_http.py.
HTTP_AV="$(FIRMS_MAP_KEY="$FIRMS_MAP_KEY" python3 "$FIRMS_HTTP" data-availability \
    --base "$FIRMS_BASE" --timeout 120 --out "$EV_DIR/data_availability_ALL.csv" \
    --err-out "$EV_DIR/avail_stderr.txt" 2>/dev/null || echo 000)"
[ -n "$HTTP_AV" ] || HTTP_AV=000
redactar_archivo "$EV_DIR/avail_stderr.txt"
redactar_archivo "$EV_DIR/data_availability_ALL.csv"
if [ "$HTTP_AV" != "200" ] || ! head -n1 "$EV_DIR/data_availability_ALL.csv" 2>/dev/null | grep -q '^data_id'; then
    if [ "$HTTP_AV" = "000" ]; then
        echo "ERROR: data_availability sin respuesta de transporte." >&2
        exit 2
    fi
    echo "ERROR: data_availability falló o devolvió algo no-CSV (HTTP ${HTTP_AV})." >&2
    exit 1
fi
DISPO="$(python3 -c "
import sys; sys.path.insert(0, '$HERR')
from preflight_decision import validar_disponibilidad_csv
import json
print(json.dumps(validar_disponibilidad_csv(open('$EV_DIR/data_availability_ALL.csv').read(), '$DESDE', '$HASTA')))
")"
if [ -z "$DISPO" ]; then
    echo "ERROR: no se pudo validar la disponibilidad." >&2
    exit 1
fi
echo "$DISPO" > "$EV_DIR/decision_disponibilidad.json"
echo "4) disponibilidad NRT de la ventana (re-verificada justo antes de ejecutar):"
echo "$DISPO" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for p, v in d['productos'].items():
    print(f\"   {p}: {v['min_date']}..{v['max_date']} cubre={v['cubre_ventana']}\")
r = d.get('producto_retirado')
if r:
    print(f\"   VIIRS_SNPP_NRT (retirado, excluido): {r['min_date']}..{r['max_date']}\")
"
if echo "$DISPO" | grep -q '"ventana_disponible": false'; then
    echo "ERROR: algún producto NRT no cubre ${DESDE}..${HASTA} (M011: no se" >&2
    echo "sustituye la ventana en silencio). Alternativas: verificar fechas" >&2
    echo "por producto arriba, elegir una ventana NRT ACTUAL cubierta por los" >&2
    echo "3 productos CON APROBACIÓN EXPLÍCITA del propietario, o usar Archive" >&2
    echo "Download. Ninguna sustitución es automática." >&2
    exit 5
fi
# Contrato con el orquestador: copia estable del CSV de disponibilidad.
# M011-C §4: un fallo de esta copia NO se oculta — sin el CSV en el destino
# el orquestador no tendría la evidencia de disponibilidad: se detiene (1).
if [ -n "${PREFLIGHT_AVAIL_DEST:-}" ]; then
    if ! cp "$EV_DIR/data_availability_ALL.csv" "$PREFLIGHT_AVAIL_DEST"; then
        echo "ERROR: no se pudo copiar el CSV de disponibilidad a" >&2
        echo "$PREFLIGHT_AVAIL_DEST (contrato con el orquestador). NO se descarga." >&2
        exit 1
    fi
fi
# Copia estable para consulta humana (última ejecución del preflight).
if ! cp "$EV_DIR/data_availability_ALL.csv" "$DIR_EVIDENCIAS/data_availability_ALL.csv"; then
    echo "AVISO: no se pudo actualizar la copia humana del CSV en $DIR_EVIDENCIAS." >&2
fi

# --- 5) resumen GO ------------------------------------------------------------
python3 - "$EV_DIR" "$RUN_ID" "$DESDE" "$HASTA" "$HTTP_AREA" "$HUELLA_FP" "$RESULTADO_JSON" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ev_dir, run_id, desde, hasta, http_area, huella, salida = sys.argv[1:8]
saldo = json.loads(Path(ev_dir, "decision_saldo.json").read_text())
dispo = json.loads(Path(ev_dir, "decision_disponibilidad.json").read_text())
clasif = json.loads(Path(ev_dir, "clasificacion_mapkey.json").read_text())
resumen = {
    "run_id": run_id,
    "ts_utc": datetime.now(timezone.utc).isoformat(),
    "ventana": {"desde": desde, "hasta": hasta},
    "conexion": {
        "ok": True,
        "http_code": http_area,
        "nota": "sondeo de TRANSPORTE (sin clave); la validez del API la "
        "confirma mapkey_status con el esquema documentado (M011-C §4)",
    },
    "map_key": {"huella_publica": huella, "valor": "NO REGISTRADO"},
    "mapkey_status": {"clasificacion": clasif["tipo"]},
    "saldo_transacciones": saldo,
    "politica_transacciones": saldo["politica_transacciones"],
    "disponibilidad_ventana": dispo,
    "decision": "GO",
}
Path(salida).write_text(json.dumps(resumen, indent=2, ensure_ascii=False))
print(json.dumps(resumen, indent=2, ensure_ascii=False))
PYEOF
echo ""
echo "== GO: preflight completo. Ejecutar el piloto: bash mision_007_datos_reales/herramientas/piloto_firms_7dias.sh ${DESDE} =="
exit 0
