#!/usr/bin/env bash
# ============================================================================
# FIREIA — Piloto nacional FIRMS de 7 días (orquestador robusto, Misión 010/011)
#
# CAMBIO M010 (§9.4 del encargo): las 6 consultas se ejecutan de forma
# INDEPENDIENTE — el fallo de una NO cancela las restantes. Cada intento de
# cada consulta queda registrado (JSONL por ejecución) y al final se escribe
# un resumen con run_id y estado final por consulta. Reintentos de script con
# espera progresiva; reintentos de transporte (backoff exponencial) ya viven
# en el pipeline desde M004.
#
# CAMBIO M011-C §1 (seguridad): NINGUNA llamada HTTP pone la MAP_KEY en
# argumentos de procesos. Las consultas de descarga van por el paquete
# ``hotspots`` (clave leída del entorno, URLs construidas dentro del proceso
# y redactadas en toda evidencia) y los controles de saldo van por
# ``firms_http.py`` (misma regla). El script ya no usa curl para nada con
# clave, y la redacción de archivos se hace con operaciones internas de bash
# (antes grep con la clave como patrón también exponía la clave en argv).
#
# CAMBIO M011-C §2 (política conservadora de transacciones): el GO del
# preflight con saldo >= 6 es un PISO, no una garantía (una consulta
# multi-día puede contar como VARIAS transacciones; NASA lo advierte y no
# se inventa coste fijo). Por eso el orquestador: registra el saldo inicial,
# ejecuta las 6 consultas de forma independiente e idempotente, verifica el
# consumo REAL entre consultas (CONTROL_SALDO, default tras_fallo) y NO
# lanza más peticiones si la cuota restante no permite continuar con
# seguridad: las consultas restantes quedan PENDIENTES (detenida_saldo.json,
# código 4), no fallidas, y al relanzar no se repiten las exitosas.
#
# DÓNDE CORRER (portabilidad, verificación Misión 008):
#   - Linux (bash + GNU coreutils): soportado.
#   - Windows 10/11 mediante WSL (cualquier distro con bash): soportado.
#   - macOS nativo: NO soportado sin ajustes (BSD date; usar gdate o WSL).
#
# DEPENDENCIAS (se verifican al arrancar):
#   - bash >= 4, GNU date (coreutils), python3 (HTTP con clave SOLO por
#     entorno: firms_http.py; ya no se requiere curl para nada con clave).
#   - Python >= 3.10 con el paquete `hotspots` instalado
#     (pip install -e ".[dev,api]") y en PATH, o invocable como
#     `python -m hotspots.cli.app` desde la raíz del repo.
#   - Variable de entorno FIRMS_MAP_KEY (en .env del repo o ya exportada).
#     El script JAMÁS imprime la clave y la redacta de cualquier texto
#     persistido (stdout/stderr de los intentos).
#
# VARIABLES DE ENTORNO (opcionales, salvo FIRMS_MAP_KEY):
#   FIRMS_MAP_KEY          (obligatoria; REGENERADA en el sitio oficial y
#                          guardada SOLO en .env local (600); las claves
#                          expuestas en conversaciones las rechaza el
#                          preflight por huella pública)
#   DESDE                  (default 2026-11-04 = ventana 2026-11-04..10 UTC;
#                          también acepta $1)
#   PREFLIGHT_SCRIPT       (default mision_011_ejecucion_real/herramientas/
#                          preflight_firms.sh; vacío = omitir — solo para
#                          pruebas offline)
#   FIRMS_HTTP             (cliente HTTP seguro para controles de saldo;
#                          default mision_011_ejecucion_real/herramientas/
#                          firms_http.py — clave SOLO por entorno)
#   FIRMS_BASE             (base del servicio para los controles de saldo;
#                          default https://firms.modaps.eosdis.nasa.gov)
#   CONTROL_SALDO          (tras_fallo (default) | siempre | nunca — cuándo
#                          verificar el consumo real entre consultas;
#                          M011-C §2. Se asume que mapkey_status no consume
#                          transacciones de datos; si FIRMS documentara lo
#                          contrario, fijar CONTROL_SALDO=nunca)
#   SALDO_TIMEOUT          (default 15 s por control de saldo)
#   HOTSPOTS_COMANDO       (override del comando hotspots; pruebas offline)
#   VERIFICADOR_RUTA       (override del verificador del piloto)
#   DIR_EJECUCIONES        (default mision_007_datos_reales/ejecuciones)
#   AVAIL_RUTA             (ruta del CSV de disponibilidad documental;
#                          default mision_007_datos_reales/datos/data_availability_ALL.csv;
#                          lo escribe el PREFLIGHT antes de descargar)
#   ESPERA_ENTRE_CONSULTAS (default 5 s; cortesía de cuota entre consultas)
#   REINTENTOS_CONSULTA    (default 2; reintentos EXTRA de script por consulta)
#   ESPERA_BASE_REINTENTO  (default 10 s; espera progresiva base*intento)
#
# EVIDENCIA POR EJECUCIÓN:
#   $DIR_EJECUCIONES/<run_id>/preflight_result.json    (GO del preflight M011:
#       transporte, huella pública de la clave, saldo inicial y política de
#       transacciones, disponibilidad NRT por producto)
#   $DIR_EJECUCIONES/<run_id>/consultas.jsonl          (1 línea por intento:
#       consulta, producto, período, exit_code, estado_ingest, manifest_id,
#       raw_sha256, error truncado, ts UTC; summary completo de ingest)
#   $DIR_EJECUCIONES/<run_id>/saldo_checks.jsonl       (M011-C §2: controles
#       de saldo entre consultas; saldo disponible, pendientes, decisión)
#   $DIR_EJECUCIONES/<run_id>/detenida_saldo.json      (solo si se detiene
#       por cuota: consultas PENDIENTES, no fallidas — relanzar y no repetir)
#   $DIR_EJECUCIONES/<run_id>/intentos/*.stdout|stderr (texto redactado)
#   $DIR_EJECUCIONES/<run_id>/resumen_ejecucion.json   (estado final por consulta)
#   El manifiesto de cada ingesta conserva SHA256, rutas, período y notas v2.
#
# NOTAS CIENTÍFICAS:
#   - Ventana de 7 días UTC completos; split 5+2 porque el Area API admite
#     DAY_RANGE 1..5 (docs oficiales re-verificadas 2026-11-12; el parámetro
#     date es el INICIO del rango: [DATE] .. [DATE+DAY_RANGE-1]).
#   - Fuentes: MODIS_NRT (Terra+Aqua, C6.1), VIIRS_NOAA20_NRT, VIIRS_NOAA21_NRT.
#     S-NPP EXCLUIDO (cese de distribución 2026-11-02; data_availability del
#     2026-11-12 con clave vigente: max_date VIIRS_SNPP_NRT = 2026-11-02).
#   - Cada ingesta genera manifiesto con URL REDACTADA, request_key idempotente,
#     RAW content-addressed (SHA256) y cuarentena de filas inválidas.
#   - El bbox de CONSULTA (-62.7,-27.6,-54.2,-19.3) NO es el país: la
#     pertenencia territorial la decide el polígono ADM0 de la capa activa
#     (INE 2022, 263 distritos) en `hotspots geo assign`.
#   - Una consulta sin detecciones NO es ausencia de fuego: success_no_detections.
#   - Al final ejecuta el verificador del piloto: si los datos presentes no
#     están respaldados por los manifiestos del piloto, termina con código 3.
#
# CÓDIGOS DE SALIDA:
#   0  piloto ejecutado y verificado como real
#   3  ejecutado, pero la procedencia no se puede demostrar (ver advertencias)
#   1  error de infraestructura (credenciales, dependencias) o verificador en error
#   2  preflight: sin salida TCP directa a FIRMS (NADA se descargó)
#   3b preflight: MAP_KEY rechazada (inválida o EXPUESTA: regenerar) — ver
#      mision_011_ejecucion_real/herramientas/preflight_firms.sh
#   4  preflight: saldo insuficiente para las 6 consultas (NADA se descargó)
#      M011-C §2: TAMBIÉN 4 si la cuota se agota EN MEDIO de la ejecución
#      (consultas restantes PENDIENTES en detenida_saldo.json, no fallidas)
#   5  preflight: ventana no disponible en algún producto (NADA se descargó)
# ============================================================================
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"
HERRAMIENTAS="mision_007_datos_reales/herramientas"
FIRMS_HTTP_DEFAULT="mision_011_ejecucion_real/herramientas/firms_http.py"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    sed -n '2,70p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
fi

# --- dependencias ------------------------------------------------------------
comandos_requeridos=(python)
for cmd in "${comandos_requeridos[@]}"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: falta el comando '$cmd' en PATH." >&2
        exit 1
    fi
done
# M011-C §1: ya no se requiere curl (ninguna llamada HTTP lleva la clave en
# argv; el HTTP con clave va por firms_http.py / paquete hotspots).

# GNU date: probamos la operación que vamos a usar (BSD/macOS falla aquí).
if ! date -u -d "2026-11-04 +5 days" +%F >/dev/null 2>&1; then
    echo "ERROR: se requiere GNU date (coreutils). En macOS: brew install coreutils" >&2
    echo "       y usar 'gdate', o ejecutar en Linux/WSL." >&2
    exit 1
fi

# hotspots: override por entorno (pruebas), comando instalado o módulo python.
if [ -n "${HOTSPOTS_COMANDO:-}" ]; then
    read -r -a HOTSPOTS <<< "$HOTSPOTS_COMANDO"
elif command -v hotspots >/dev/null 2>&1; then
    HOTSPOTS=(hotspots)
elif [ -f "src/hotspots/cli/app.py" ]; then
    HOTSPOTS=(python -m hotspots.cli.app)
else
    echo "ERROR: paquete 'hotspots' no encontrado. Corré: pip install -e \".[dev,api]\"" >&2
    exit 1
fi

# --- credenciales: entorno tiene precedencia; .env solo como default ---------
# (si FIRMS_MAP_KEY ya está en el entorno, NO se carga .env — evita sorpresas
#  en entornos de prueba y respeta la precedencia estándar env > archivo)
if [ -f .env ] && [ -z "${FIRMS_MAP_KEY:-}" ]; then
    set -a; . ./.env; set +a
fi
if [ -z "${FIRMS_MAP_KEY:-}" ]; then
    echo "ERROR: FIRMS_MAP_KEY no está configurada. Copiala a .env (ver .env.example)." >&2
    exit 1
fi

# --- ventana ------------------------------------------------------------------
DESDE="${1:-${DESDE:-2026-11-04}}"
DESDE5="$(date -u -d "$DESDE +5 days" +%F)"   # segunda consulta: 2 días restantes
HASTA="$(date -u -d "$DESDE +6 days" +%F)"

ESPERA_ENTRE_CONSULTAS="${ESPERA_ENTRE_CONSULTAS:-5}"
REINTENTOS_CONSULTA="${REINTENTOS_CONSULTA:-2}"
ESPERA_BASE_REINTENTO="${ESPERA_BASE_REINTENTO:-10}"
DIR_EJECUCIONES="${DIR_EJECUCIONES:-mision_007_datos_reales/ejecuciones}"
AVAIL_RUTA="${AVAIL_RUTA:-mision_007_datos_reales/datos/data_availability_ALL.csv}"
VERIFICADOR_RUTA="${VERIFICADOR_RUTA:-$HERRAMIENTAS/verificar_piloto.py}"
FIRMS_HTTP="${FIRMS_HTTP:-$FIRMS_HTTP_DEFAULT}"
FIRMS_BASE="${FIRMS_BASE:-https://firms.modaps.eosdis.nasa.gov}"
CONTROL_SALDO="${CONTROL_SALDO:-tras_fallo}"   # tras_fallo | siempre | nunca
SALDO_TIMEOUT="${SALDO_TIMEOUT:-15}"

case "$CONTROL_SALDO" in
    tras_fallo|siempre|nunca) ;;
    *)
        echo "ERROR: CONTROL_SALDO inválido: '$CONTROL_SALDO' (usar tras_fallo|siempre|nunca)." >&2
        exit 1
        ;;
esac

RUN_ID="piloto-$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_DIR="$DIR_EJECUCIONES/$RUN_ID"
mkdir -p "$RUN_DIR/intentos"

# --- preflight M011: conectividad, saldo y disponibilidad ANTES de descargar --
# (PREFLIGHT_SCRIPT vacío = omitir; solo previsto para pruebas offline con
#  stubs. En producción SIEMPRE corre y su código se propaga si no da GO.)
PREFLIGHT_SCRIPT="${PREFLIGHT_SCRIPT:-mision_011_ejecucion_real/herramientas/preflight_firms.sh}"
if [ -n "$PREFLIGHT_SCRIPT" ]; then
    echo ""
    echo "== Preflight M011: conectividad, saldo de la MAP_KEY y disponibilidad =="
    PREFLIGHT_AVAIL_DEST="$AVAIL_RUTA" \
    PREFLIGHT_RESULTADO_JSON="$RUN_DIR/preflight_result.json" \
        bash "$PREFLIGHT_SCRIPT"
    codigo_preflight=$?
    if [ "$codigo_preflight" -ne 0 ]; then
        echo "ERROR: el preflight NO dio GO (código ${codigo_preflight})." >&2
        echo "       Ninguna consulta del piloto fue lanzada; nada se descargó." >&2
        exit "$codigo_preflight"
    fi
    if [ -f "$AVAIL_RUTA" ]; then
        cp "$AVAIL_RUTA" "$RUN_DIR/data_availability_ALL.csv" 2>/dev/null || true
    fi
fi

# Saldo inicial registrado (M011-C §2): del preflight (que acaba de correr).
SALDO_INICIAL=""
if [ -f "$RUN_DIR/preflight_result.json" ]; then
    SALDO_INICIAL="$(python3 -c "
import json
try:
    d = json.load(open('$RUN_DIR/preflight_result.json'))
    print(d['saldo_transacciones']['transactions_available'])
except Exception:
    print('')
" 2>/dev/null || true)"
fi

# Redacta la MAP_KEY de un archivo de texto antes de persistirlo (higiene
# M011-C §1). SIN subprocess: grep con la clave como PATRÓN también ponía la
# clave en argv del proceso grep; la comparación se hace dentro de bash.
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

# Control de saldo ENTRE consultas (M011-C §2). Devuelve 0 = continuar,
# 1 = detener el lanzamiento de nuevas peticiones. La clave viaja SOLO por
# el entorno hacia firms_http.py (nunca en argv). Si el control no se puede
# verificar (transporte), se registra y se continúa sin bloquear: las
# consultas son independientes y ya autorizadas por el preflight.
comprobar_saldo() {
    local pendientes="$1" code salida disp dec
    [ "$CONTROL_SALDO" = "nunca" ] && return 0
    code="$(FIRMS_MAP_KEY="$FIRMS_MAP_KEY" python3 "$FIRMS_HTTP" mapkey-status \
        --base "$FIRMS_BASE" --timeout "$SALDO_TIMEOUT" \
        --out "$RUN_DIR/saldo_ultimo_estado.json" \
        --err-out "$RUN_DIR/saldo_stderr.txt" 2>/dev/null || echo 000)"
    redactar_archivo "$RUN_DIR/saldo_ultimo_estado.json"
    redactar_archivo "$RUN_DIR/saldo_stderr.txt"
    if [ "$code" != "200" ]; then
        echo "-- control de saldo: sin verificación posible (HTTP ${code}); se continúa"
        python "$HERRAMIENTAS/registrar_ejecucion.py" saldo \
            --run-dir "$RUN_DIR" --momento "http_${code}" --disponible null \
            --pendientes "$pendientes" --decision "SIN_VERIFICACION" \
            >/dev/null 2>&1 || true
        return 0
    fi
    salida="$(python3 -c "
import sys, json
sys.path.insert(0, 'mision_011_ejecucion_real/herramientas')
from preflight_decision import parse_mapkey_status, decision_continuar
estado = parse_mapkey_status(open('$RUN_DIR/saldo_ultimo_estado.json').read())
print(json.dumps({'estado': estado, 'decision': decision_continuar(estado, $pendientes)}))
" 2>/dev/null || true)"
    if [ -z "$salida" ]; then
        echo "-- control de saldo: respuesta no interpretable; se continúa"
        python "$HERRAMIENTAS/registrar_ejecucion.py" saldo \
            --run-dir "$RUN_DIR" --momento "esquema_no_interpretable" \
            --disponible null --pendientes "$pendientes" \
            --decision "SIN_VERIFICACION" >/dev/null 2>&1 || true
        return 0
    fi
    disp="$(echo "$salida" | python3 -c "import json,sys; print(json.load(sys.stdin)['estado']['transactions_available'])")"
    dec="$(echo "$salida" | python3 -c "import json,sys; print(json.load(sys.stdin)['decision']['decision'])")"
    python "$HERRAMIENTAS/registrar_ejecucion.py" saldo \
        --run-dir "$RUN_DIR" --momento "entre_consultas" --disponible "$disp" \
        --pendientes "$pendientes" --decision "$dec" >/dev/null 2>&1 || true
    echo "-- control de saldo: disponible=${disp} pendientes=${pendientes} → ${dec}"
    if [ "$dec" = "DETENER_SALDO_INSUFICIENTE" ]; then
        python "$HERRAMIENTAS/registrar_ejecucion.py" saldo \
            --run-dir "$RUN_DIR" --momento "detencion" --disponible "$disp" \
            --pendientes "$pendientes" --decision "$dec" --detener \
            >/dev/null 2>&1 || true
        return 1
    fi
    return 0
}

echo "== Piloto FIRMS 7 días | ventana ${DESDE}..${HASTA} (UTC) =="
echo "== Fuentes: MODIS_NRT (Terra+Aqua), VIIRS_NOAA20_NRT, VIIRS_NOAA21_NRT =="
echo "== Split 5+2 (DAY_RANGE 1..5 documentado) | run_id: ${RUN_ID} =="
echo "== Capa geo activa: $(cat data/geo/active_version.txt 2>/dev/null || echo 'sin capa (correr geo build)') =="
echo "== Independencia por consulta: el fallo de una NO cancela las restantes =="

# --- 6 ingestas reales (idempotentes: request_key salta lo ya exitoso) --------
# M011-C §2: EXITOSAS cuenta las completadas (o ya ingestado por idempotencia)
# para calcular las PENDIENTES de cada control de saldo; DETENIDA_SALDO corta
# el lanzamiento de nuevas peticiones sin marcarlas como fallidas.
consulta_num=0
EXITOSAS=0
DETENIDA_SALDO=0
for PRODUCTO in MODIS_NRT VIIRS_NOAA20_NRT VIIRS_NOAA21_NRT; do
    for VENTANA in "$DESDE 5" "$DESDE5 2"; do
        set -- $VENTANA
        FECHA="$1"
        RANGO="$2"
        consulta_num=$((consulta_num + 1))
        CONSULTA_ID="$(printf '%02d-%s-%s-%sd' "$consulta_num" "$PRODUCTO" "$FECHA" "$RANGO")"
        HASTA_VENTANA="$(date -u -d "$FECHA +$((RANGO - 1)) days" +%F)"
        max_intentos=$((REINTENTOS_CONSULTA + 1))
        intento=0
        exit_code=1
        while [ "$intento" -lt "$max_intentos" ]; do
            intento=$((intento + 1))
            OUT="$RUN_DIR/intentos/${CONSULTA_ID}_intento${intento}.stdout.json"
            ERR="$RUN_DIR/intentos/${CONSULTA_ID}_intento${intento}.stderr.txt"
            echo "-- [${CONSULTA_ID}] intento ${intento}/${max_intentos}: ${FECHA} +${RANGO}d (${PRODUCTO})"
            "${HOTSPOTS[@]}" ingest --source firms-api --product "$PRODUCTO" \
                --date "$FECHA" --day-range "$RANGO" --allow-network \
                >"$OUT" 2>"$ERR"
            exit_code=$?
            redactar_archivo "$OUT"
            redactar_archivo "$ERR"
            ESTADO="$(python "$HERRAMIENTAS/registrar_ejecucion.py" registrar \
                --run-dir "$RUN_DIR" --consulta-id "$CONSULTA_ID" \
                --producto "$PRODUCTO" --fecha "$FECHA" --day-range "$RANGO" \
                --periodo-hasta "$HASTA_VENTANA" --intento-script "$intento" \
                --exit-code "$exit_code" --stdout "$OUT" --stderr "$ERR" \
                2>/dev/null || echo '{"estado": null, "exit_code": '"$exit_code"'}')"
            echo "-- [${CONSULTA_ID}] resultado: ${ESTADO}"
            if [ "$exit_code" -eq 0 ]; then
                break
            fi
            # M011-C §2: tras un fallo, verificar el consumo real ANTES de
            # quemar reintentos contra una cuota posiblemente agotada.
            if [ "$CONTROL_SALDO" = "tras_fallo" ]; then
                if ! comprobar_saldo "$((6 - EXITOSAS))"; then
                    DETENIDA_SALDO=1
                    break 3
                fi
            fi
            if [ "$intento" -lt "$max_intentos" ]; then
                espera=$((ESPERA_BASE_REINTENTO * intento))
                echo "-- [${CONSULTA_ID}] reintento en ${espera}s"
                sleep "$espera"
            fi
        done
        if [ "$exit_code" -eq 0 ]; then
            EXITOSAS=$((EXITOSAS + 1))
        fi
        # M011-C §2 (modo siempre): verificación de consumo tras CADA consulta.
        if [ "$CONTROL_SALDO" = "siempre" ]; then
            if ! comprobar_saldo "$((6 - EXITOSAS))"; then
                DETENIDA_SALDO=1
                break 2
            fi
        fi
        if [ "$ESPERA_ENTRE_CONSULTAS" -gt 0 ]; then
            sleep "$ESPERA_ENTRE_CONSULTAS"
        fi
    done
done

if [ "$DETENIDA_SALDO" -eq 1 ]; then
    echo "" >&2
    echo "ERROR: cuota de transacciones insuficiente para continuar con" >&2
    echo "seguridad (M011-C §2). Se detuvo el lanzamiento de nuevas peticiones:" >&2
    echo "las consultas no lanzadas quedan PENDIENTES (no fallidas, no son días" >&2
    echo "sin detecciones) en $RUN_DIR/detenida_saldo.json. Esperar el reinicio" >&2
    echo "de la ventana (10 minutos, gratuito) y relanzar: las ya exitosas NO se" >&2
    echo "repiten (idempotencia por request_key)." >&2
    python "$HERRAMIENTAS/registrar_ejecucion.py" resumen \
        --run-dir "$RUN_DIR" --desde "$DESDE" --hasta "$HASTA" \
        --verificador-exit 4 --saldo-inicial "${SALDO_INICIAL:-}" \
        >/dev/null 2>&1 || true
    exit 4
fi

# --- evidencia documental de disponibilidad -----------------------------------
# (M011: la disponibilidad ya se capturó en el PREFLIGHT, antes de descargar;
#  aquí solo se garantiza la copia dentro del directorio de la ejecución.)
echo ""
echo "== data_availability (capturada por el preflight) =="
if [ -f "$AVAIL_RUTA" ]; then
    cp "$AVAIL_RUTA" "$RUN_DIR/data_availability_ALL.csv" 2>/dev/null || true
    echo "copiada al run: $RUN_DIR/data_availability_ALL.csv"
else
    echo "AVISO: sin CSV de disponibilidad en ${AVAIL_RUTA} (el preflight debió capturarlo)"
fi

# --- territorio (capa activa) + eventos + verificación ------------------------
echo ""
echo "== Reasignación territorial (capa activa) =="
"${HOTSPOTS[@]}" geo assign || echo "AVISO: geo assign terminó con error (no aborta el piloto)"

echo ""
echo "== Eventos de co-detección =="
"${HOTSPOTS[@]}" events build || echo "AVISO: events build terminó con error (no aborta el piloto)"

echo ""
echo "== Verificación del piloto (clasifica la procedencia de los datos) =="
codigo=0
python "$VERIFICADOR_RUTA" "$DESDE" || codigo=$?

python "$HERRAMIENTAS/registrar_ejecucion.py" resumen \
    --run-dir "$RUN_DIR" --desde "$DESDE" --hasta "$HASTA" \
    --verificador-exit "$codigo" --saldo-inicial "${SALDO_INICIAL:-}" \
    || echo "AVISO: no se pudo escribir el resumen de la ejecución"

echo ""
echo "== Piloto completo (verificador: código ${codigo}). Resumen de la ejecución: ${RUN_DIR}/resumen_ejecucion.json =="
exit "${codigo}"
