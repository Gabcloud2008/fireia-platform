"""Pruebas de seguridad y aceptación M011-C — prioridad máxima §1 y §5.

TODO offline (sin red externa, sin clave real), con un servidor HTTP LOCAL:

1. **Argv**: mientras el preflight real se ejecuta contra el servidor local,
   se escanea ``/proc/*/cmdline``: la MAP_KEY (de prueba) NO aparece en los
   argumentos de NINGÚN proceso. Esta es la demostración dinámica de que la
   clave jamás viaja en argv (el defecto de M011 era ``curl`` con la clave
   embebida en la URL).
2. **Logs/evidencia**: ningún archivo de evidencia del preflight ni su
   stdout/stderr contienen la clave.
3. **Escenarios del preflight (§5)**: clave ausente (1), clave expuesta (3),
   cuota insuficiente (4), ventana no disponible (5), conectividad fallida
   (2), página informativa en vez del API (1), 429 ≠ clave inválida (4).
4. **GO completo**: huella aceptada → transporte → esquema → saldo →
   disponibilidad → resultado JSON con política de transacciones.
5. **Orquestador (§2)**: control de saldo entre consultas que DETIENE el
   lanzamiento cuando la cuota no alcanza (código 4, consultas pendientes,
   no fallidas) e idempotencia (skip de las ya exitosas).
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERR_M011 = REPO / "mision_011_ejecucion_real" / "herramientas"
PREFLIGHT = HERR_M011 / "preflight_firms.sh"
FIRMS_HTTP = HERR_M011 / "firms_http.py"
ORQUESTADOR = REPO / "mision_007_datos_reales" / "herramientas" / "piloto_firms_7dias.sh"
sys.path.insert(0, str(HERR_M011))

CLAVE_PRUEBA = "STUBKEY-N0REAL-M011C"  # ficticia; jamás una clave real

CSV_DISPONIBILIDAD = (
    "data_id,min_date,max_date,day_range_nrt\n"
    "MODIS_NRT,2026-09-01,2026-11-11,1\n"
    "VIIRS_NOAA20_NRT,2026-08-01,2026-11-11,1\n"
    "VIIRS_NOAA21_NRT,2024-01-17,2026-11-11,1\n"
    "VIIRS_SNPP_NRT,2024-01-17,2026-11-02,1\n"
)
CSV_DISPONIBILIDAD_RECORTADO = CSV_DISPONIBILIDAD.replace(
    "VIIRS_NOAA21_NRT,2024-01-17,2026-11-11,1",
    "VIIRS_NOAA21_NRT,2024-01-17,2026-11-08,1",
)
JSON_ESTADO_OK = (
    '{"transaction_limit": 5000, "current_transactions": 46, '
    '"transaction_interval": "10 minutes"}'
)
JSON_ESTADO_CUOTA_BAJA = (
    '{"transaction_limit": 5000, "current_transactions": 4998, '
    '"transaction_interval": "10 minutes"}'
)  # disponible = 2 < 6 consultas
PAGINA_HTML = "<html><body>FIRMS portal</body></html>"


class ServidorFirmsFalso:
    """Servidor HTTP local que imita los endpoints de FIRMS usados por el
    preflight. http://127.0.0.1 es la única base http:// admitida por
    firms_http.py (excepción documentada para pruebas offline)."""

    def __init__(self, respuestas: dict[str, tuple[int, str]] | None = None):
        self.respuestas = respuestas or {
            "/api/area/": (200, PAGINA_HTML),  # sondeo de transporte
            "/mapserver/mapkey_status/": (200, JSON_ESTADO_OK),
            "/api/data_availability/csv/ALL": (200, CSV_DISPONIBILIDAD),
        }
        handler = self._construir_handler()
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.puerto = self.httpd.server_address[1]
        self.hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def _construir_handler(self):
        respuestas = self.respuestas

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):  # silencio en la salida de pruebas
                pass

            def do_GET(self):  # noqa: N802 (API de http.server)
                import urllib.parse

                # retardo deliberado: mantiene vivo al proceso cliente
                # (firms_http.py) el suficiente para que el escaneo de
                # /proc/*/cmdline lo muestre si filtrara la clave en argv
                time.sleep(0.12)
                ruta = urllib.parse.urlparse(self.path)
                # data_availability llega como /api/data_availability/csv/{KEY}/ALL
                if ruta.path.startswith("/api/data_availability/csv/"):
                    clave_resp = "/api/data_availability/csv/ALL"
                elif ruta.path.startswith("/mapserver/mapkey_status"):
                    clave_resp = "/mapserver/mapkey_status/"
                else:
                    clave_resp = ruta.path
                codigo, cuerpo = respuestas.get(clave_resp, (404, "not found"))
                data = cuerpo.encode()
                self.send_response(codigo)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return Handler

    def __enter__(self):
        self.hilo.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.puerto}"


def _huella(clave: str) -> str:
    return hashlib.sha256(clave.encode()).hexdigest()[:16]


def _escanear_cmdlines(clave: str) -> list[str]:
    """Lee /proc/*/cmdline y devuelve las líneas de comando que contienen la
    clave (demostración de fuga real por argv)."""
    fugas: list[str] = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            crudo = (proc / "cmdline").read_bytes()
        except OSError:
            continue
        if not crudo:
            continue
        argv = crudo.replace(b"\0", b" ").decode("utf-8", errors="replace")
        if clave in argv:
            fugas.append(f"pid {proc.name}: {argv}")
    return fugas


def _correr_preflight(
    tmp_path: Path,
    base: str,
    *,
    clave: str | None = CLAVE_PRUEBA,
    env_extra: dict[str, str] | None = None,
    dest_avail: str | None = None,
    con_escaneo_argv: bool = False,
) -> tuple[subprocess.CompletedProcess, list[str]]:
    """Ejecuta el preflight REAL contra una base local, sin tocar el .env del
    repo (FIREIA_ENV_FILE apunta a un archivo inexistente)."""
    env = os.environ.copy()
    env.pop("FIRMS_MAP_KEY", None)
    env.pop("FIREIA_CLAVES_EXPUESTAS_FP_EXTRA", None)
    if clave is not None:
        env["FIRMS_MAP_KEY"] = clave
    env["FIREIA_ENV_FILE"] = str(tmp_path / "no_existe.env")
    env["FIRMS_BASE"] = base
    env["DIR_EVIDENCIAS"] = str(tmp_path / "evidencias")
    env["PREFLIGHT_RESULTADO_JSON"] = str(tmp_path / "preflight_result.json")
    if dest_avail:
        env["PREFLIGHT_AVAIL_DEST"] = dest_avail
    if env_extra:
        env.update(env_extra)

    fugas: list[str] = []
    if con_escaneo_argv and clave:
        proceso = subprocess.Popen(
            ["bash", str(PREFLIGHT)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
        )
        # muestreo de /proc mientras el preflight vive (sus hijos incluidos:
        # python3 firms_http.py mapkey-status/data-availability con la clave
        # en el ENTORNO; si algún argv la contuviera, aparece aquí).
        while proceso.poll() is None:
            fugas.extend(_escanear_cmdlines(clave))
            time.sleep(0.02)
        stdout, stderr = proceso.communicate()
        resultado = subprocess.CompletedProcess(
            ["bash", str(PREFLIGHT)], proceso.returncode, stdout, stderr
        )
    else:
        resultado = subprocess.run(
            ["bash", str(PREFLIGHT)],
            capture_output=True, text=True, env=env, timeout=120,
        )
    return resultado, fugas


# ---------------------------------------------------------------------------
# §1 — la clave jamás en argv (demostración dinámica) ni en logs/evidencia
# ---------------------------------------------------------------------------

def test_preflight_go_completo_sin_clave_en_argv_ni_evidencia(tmp_path):
    """Escenario GO completo contra el servidor local + escaneo DINÁMICO de
    /proc/*/cmdline durante la ejecución: cero apariciones de la clave en
    argv de cualquier proceso; cero apariciones en stdout/stderr y en toda
    la evidencia persistida."""
    with ServidorFirmsFalso() as servidor:
        resultado, fugas = _correr_preflight(
            tmp_path, servidor.base, con_escaneo_argv=True
        )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    # §1: NINGÚN proceso llevó la clave en sus argumentos
    assert fugas == [], f"MAP_KEY filtrada en argv: {fugas}"
    # §1: la clave no aparece en la salida ni en la evidencia
    textos = [resultado.stdout, resultado.stderr]
    evidencias = tmp_path / "evidencias"
    for archivo in evidencias.rglob("*"):
        if archivo.is_file():
            textos.append(archivo.read_text(encoding="utf-8", errors="replace"))
    resumen = tmp_path / "preflight_result.json"
    if resumen.exists():
        textos.append(resumen.read_text(encoding="utf-8"))
    for texto in textos:
        assert CLAVE_PRUEBA not in texto, "MAP_KEY presente en salida/evidencia"
    # el resultado GO documenta la política conservadora (§2)
    reporte = json.loads(resumen.read_text(encoding="utf-8"))
    assert reporte["decision"] == "GO"
    assert reporte["map_key"] == {
        "huella_publica": _huella(CLAVE_PRUEBA),
        "valor": "NO REGISTRADO",
    }
    assert reporte["saldo_transacciones"]["transactions_available"] == 4954
    politica = reporte["politica_transacciones"]
    assert politica["saldo_inicial"] == 4954
    assert "no_fijado" in politica["coste_por_peticion"]
    assert reporte["disponibilidad_ventana"]["ventana_disponible"] is True
    assert reporte["mapkey_status"]["clasificacion"] == "esquema_valido"


def test_preflight_redacta_la_clave_de_errores_de_transporte(tmp_path):
    """Un error de urllib incluye la URL completa (con la clave si la lleva):
    firms_http.py la redacta ANTES de persistirla (defensa en profundidad).
    Base inalcanzable: el error de transporte se persiste redactado."""
    resultado, _ = _correr_preflight(
        tmp_path, "http://127.0.0.1:1",  # puerto cerrado: sin transporte
    )
    assert resultado.returncode == 2  # bloqueo de transporte
    assert CLAVE_PRUEBA not in resultado.stdout + resultado.stderr
    diag = list((tmp_path / "evidencias").rglob("conexion_diagnostico.txt"))
    assert diag, "sin diagnóstico de conexión"
    for d in diag:
        contenido = d.read_text(encoding="utf-8", errors="replace")
        assert CLAVE_PRUEBA not in contenido


def test_firms_http_redacta_la_clave_del_query_string(tmp_path):
    """La redacción defensiva de firms_http.py elimina la clave de cualquier
    texto de error que la contuviera (urllib puede incluir la URL completa,
    con la clave en el query string, en algunos errores como redirecciones
    o respuestas parciales). Verificación unitaria + e2e sin fuga."""
    sys.path.insert(0, str(HERR_M011))
    import firms_http

    con_clave = f"HTTPError: redirect loop en http://x/mapkey_status/?MAP_KEY={CLAVE_PRUEBA}"
    redactado = firms_http._redact(con_clave, CLAVE_PRUEBA)
    assert CLAVE_PRUEBA not in redactado
    assert "{MAP_KEY}" in redactado

    err = tmp_path / "err.txt"
    env = {**os.environ, "FIRMS_MAP_KEY": CLAVE_PRUEBA}
    resultado = subprocess.run(
        [sys.executable, str(FIRMS_HTTP), "mapkey-status",
         "--base", "http://127.0.0.1:1", "--timeout", "3",
         "--out", str(tmp_path / "out.json"), "--err-out", str(err)],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert resultado.returncode == 0
    assert resultado.stdout.strip() == "000"
    # el error persistido (sea cual sea su texto) jamás contiene la clave
    assert CLAVE_PRUEBA not in err.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# §5 — escenarios de fallo del preflight (códigos de salida correctos)
# ---------------------------------------------------------------------------

def test_preflight_clave_ausente_detiene_con_codigo_1(tmp_path):
    """Sin FIRMS_MAP_KEY y sin .env: código 1, y NADA se consulta."""
    with ServidorFirmsFalso() as servidor:
        resultado, _ = _correr_preflight(tmp_path, servidor.base, clave=None)
    assert resultado.returncode == 1
    assert "FIRMS_MAP_KEY no configurada" in resultado.stderr
    # sin evidencia de consultas: no llegó a pedir nada
    assert not (tmp_path / "preflight_result.json").exists()


def test_preflight_clave_expuesta_se_rechaza_con_codigo_3(tmp_path):
    """Una clave cuya huella pública está registrada como expuesta se
    rechaza ANTES de cualquier consulta (código 3)."""
    with ServidorFirmsFalso() as servidor:
        resultado, _ = _correr_preflight(
            tmp_path, servidor.base,
            env_extra={"FIREIA_CLAVES_EXPUESTAS_FP_EXTRA": _huella(CLAVE_PRUEBA)},
        )
    assert resultado.returncode == 3
    assert "EXPUESTA" in resultado.stderr
    assert _huella(CLAVE_PRUEBA) in resultado.stderr  # la HUELLA sí (pública)
    assert not (tmp_path / "preflight_result.json").exists()


def test_preflight_cuota_insuficiente_detiene_con_codigo_4(tmp_path):
    """Saldo real disponible (2) < consultas del piloto (6): código 4, no se
    descarga nada, y el mensaje NO culpa a la clave."""
    respuestas = {
        "/api/area/": (200, PAGINA_HTML),
        "/mapserver/mapkey_status/": (200, JSON_ESTADO_CUOTA_BAJA),
        "/api/data_availability/csv/ALL": (200, CSV_DISPONIBILIDAD),
    }
    with ServidorFirmsFalso(respuestas) as servidor:
        resultado, _ = _correr_preflight(tmp_path, servidor.base)
    assert resultado.returncode == 4
    assert "saldo insuficiente" in resultado.stderr
    assert "MAP_KEY" not in resultado.stderr  # la cuota no es culpa de la clave
    assert not (tmp_path / "preflight_result.json").exists()


def test_preflight_429_es_cuota_no_clave_invalida(tmp_path):
    """M011-C §4: HTTP 429 del endpoint de estado = cuota (código 4), JAMÁS
    clasificado como clave inválida (antes habría sido código 3)."""
    respuestas = {
        "/api/area/": (200, PAGINA_HTML),
        "/mapserver/mapkey_status/": (429, "too many transactions"),
    }
    with ServidorFirmsFalso(respuestas) as servidor:
        resultado, _ = _correr_preflight(tmp_path, servidor.base)
    assert resultado.returncode == 4
    assert "cuota" in resultado.stderr.lower()
    assert "clave inválida" not in resultado.stderr
    assert "regenerála" not in resultado.stderr


def test_preflight_403_si_es_clave_invalida_codigo_3(tmp_path):
    """Un rechazo REAL de credencial (403) sí es código 3."""
    respuestas = {
        "/api/area/": (200, PAGINA_HTML),
        "/mapserver/mapkey_status/": (403, "forbidden"),
    }
    with ServidorFirmsFalso(respuestas) as servidor:
        resultado, _ = _correr_preflight(tmp_path, servidor.base)
    assert resultado.returncode == 3
    assert "rechazó la MAP_KEY" in resultado.stderr


def test_preflight_pagina_informativa_no_es_api_ni_clave_invalida(tmp_path):
    """M011-C §4: 200 con HTML en mapkey_status = el host responde pero NO es
    una respuesta válida del API: código 1 (infraestructura/API), no 3."""
    respuestas = {
        "/api/area/": (200, PAGINA_HTML),
        "/mapserver/mapkey_status/": (200, PAGINA_HTML),  # portal, no API
    }
    with ServidorFirmsFalso(respuestas) as servidor:
        resultado, _ = _correr_preflight(tmp_path, servidor.base)
    assert resultado.returncode == 1
    assert "NO con el servicio esperado" in resultado.stderr
    assert "pagina_informativa" in resultado.stderr
    assert "rechazó la MAP_KEY" not in resultado.stderr


def test_preflight_conectividad_fallida_codigo_2(tmp_path):
    """Base inalcanzable (puerto cerrado): código 2 (transporte), con
    diagnóstico persistido; nada más se consulta."""
    resultado, _ = _correr_preflight(tmp_path, "http://127.0.0.1:1")
    assert resultado.returncode == 2
    assert "transporte" in resultado.stderr.lower()
    assert not (tmp_path / "preflight_result.json").exists()


def test_preflight_ventana_no_disponible_codigo_5_sin_sustitucion(tmp_path):
    """Un producto no cubre la ventana: código 5; se reportan las fechas
    reales por producto y NO se sustituye la ventana en silencio."""
    respuestas = {
        "/api/area/": (200, PAGINA_HTML),
        "/mapserver/mapkey_status/": (200, JSON_ESTADO_OK),
        "/api/data_availability/csv/ALL": (200, CSV_DISPONIBILIDAD_RECORTADO),
    }
    with ServidorFirmsFalso(respuestas) as servidor:
        resultado, _ = _correr_preflight(tmp_path, servidor.base)
    assert resultado.returncode == 5
    assert "no cubre 2026-11-04..2026-11-10" in resultado.stderr
    assert "APROBACIÓN EXPLÍCITA" in resultado.stderr
    # las fechas reales del producto recortado quedan visibles en stdout
    assert "2026-11-08" in resultado.stdout
    assert not (tmp_path / "preflight_result.json").exists()


def test_preflight_fallo_al_copiar_disponibilidad_no_se_oculta(tmp_path):
    """M011-C §4: si la copia del CSV al destino del orquestador falla, NO se
    oculta: código 1 y mensaje explícito (nada se descarga)."""
    destino_inexistente = tmp_path / "dir_sin_permiso" / "subdir" / "avail.csv"
    with ServidorFirmsFalso() as servidor:
        resultado, _ = _correr_preflight(
            tmp_path, servidor.base, dest_avail=str(destino_inexistente)
        )
    assert resultado.returncode == 1
    assert "no se pudo copiar el CSV de disponibilidad" in resultado.stderr


def test_preflight_go_copia_la_disponibilidad_al_orquestador(tmp_path):
    """Contrato: con GO, el CSV de disponibilidad queda en el destino."""
    destino = tmp_path / "avail_para_orquestador.csv"
    with ServidorFirmsFalso() as servidor:
        resultado, _ = _correr_preflight(
            tmp_path, servidor.base, dest_avail=str(destino)
        )
    assert resultado.returncode == 0
    assert destino.exists()
    assert "MODIS_NRT" in destino.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# §2 — orquestador: control de saldo que detiene; idempotencia
# ---------------------------------------------------------------------------

SUMMARY_OK = {
    "mode": "api",
    "product": "STUB",
    "state": "success_with_detections",
    "rows_raw": 10,
    "rows_valid": 10,
    "rows_quarantined": 0,
    "raw_path": "data/raw/firms/STUB/2026/x.csv",
    "raw_sha256": "a" * 64,
    "raw_already_existed": False,
    "manifest_id": "stub_manifest_0001",
    "manifest_path": "data/manifests/firms/manifest-stub_manifest_0001.json",
    "parquet_path": None,
    "quarantine_path": None,
    "planned_url": "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/STUB/...",
    "planned_requests": 1,
    "notes": [],
}


def _escribir_ejecutable(ruta: Path, contenido: str) -> Path:
    ruta.write_text(contenido, encoding="utf-8")
    ruta.chmod(ruta.stat().st_mode | 0o111)
    return ruta


def _stub_hotspots(ruta: Path, comportamiento: str) -> Path:
    codigo = f"""#!/usr/bin/env python3
import json, os, sys

args = sys.argv[1:]

def _valor(bandera):
    if bandera in args:
        return args[args.index(bandera) + 1]
    return None

if not args or args[0] != "ingest":
    print(json.dumps({{"stub": True}}))
    raise SystemExit(0)

producto = _valor("--product") or "STUB"
fecha = _valor("--date") or ""

if "{comportamiento}" == "fail_first":
    if producto == "MODIS_NRT" and fecha == "2026-11-04":
        sys.stderr.write("ConnectionError: stub\\n")
        raise SystemExit(1)
elif "{comportamiento}" == "skip_all":
    s = json.loads({json.dumps(SUMMARY_OK)!r})
    s["product"] = producto
    s["state"] = "skipped_already_ingested"
    print(json.dumps(s))
    raise SystemExit(0)

s = json.loads({json.dumps(SUMMARY_OK)!r})
s["product"] = producto
print(json.dumps(s))
raise SystemExit(0)
"""
    return _escribir_ejecutable(ruta, codigo)


def _stub_preflight_go(ruta: Path, saldo_inicial: int) -> Path:
    cuerpo = (
        '{"decision": "GO", "saldo_transacciones": '
        '{"transactions_available": ' + str(saldo_inicial) + '}, "stub": true}'
    )
    codigo = f"""#!/usr/bin/env bash
if [ -n "${{PREFLIGHT_RESULTADO_JSON:-}}" ]; then
    printf '%s' {cuerpo!r} > "$PREFLIGHT_RESULTADO_JSON"
fi
if [ -n "${{PREFLIGHT_AVAIL_DEST:-}}" ]; then
    printf 'data_id,min_date,max_date\\nMODIS_NRT,2026-09-01,2026-11-11\\n' \\
        > "$PREFLIGHT_AVAIL_DEST"
fi
exit 0
"""
    return _escribir_ejecutable(ruta, codigo)


def _stub_verificador(ruta: Path) -> Path:
    return _escribir_ejecutable(
        ruta, "#!/usr/bin/env python3\nprint('stub')\nraise SystemExit(0)\n"
    )


def _correr_orquestador(
    tmp_path: Path,
    comportamiento: str,
    saldo_disponible: int,
    control_saldo: str = "tras_fallo",
) -> subprocess.CompletedProcess:
    """Orquestador REAL con hotspots/preflight/verificador de stub y
    firms_http.py REAL apuntando al servidor local de saldo."""
    respuestas = {
        "/api/area/": (200, PAGINA_HTML),
        "/mapserver/mapkey_status/": (
            200,
            json.dumps(
                {
                    "transaction_limit": 5000,
                    "current_transactions": 5000 - saldo_disponible,
                    "transaction_interval": "10 minutes",
                }
            ),
        ),
    }
    env = os.environ.copy()
    env.update(
        {
            "FIRMS_MAP_KEY": CLAVE_PRUEBA,
            "FIREIA_ENV_FILE": str(tmp_path / "no_existe.env"),
            "PREFLIGHT_SCRIPT": str(
                _stub_preflight_go(tmp_path / "preflight_stub.sh", 4954)
            ),
            "HOTSPOTS_COMANDO": str(
                _stub_hotspots(tmp_path / "hotspots_stub.py", comportamiento)
            ),
            "VERIFICADOR_RUTA": str(_stub_verificador(tmp_path / "verificador_stub.py")),
            "FIRMS_HTTP": str(FIRMS_HTTP),
            "CONTROL_SALDO": control_saldo,
            "SALDO_TIMEOUT": "5",
            "DIR_EJECUCIONES": str(tmp_path / "ejecuciones"),
            "AVAIL_RUTA": str(tmp_path / "avail.csv"),
            "ESPERA_ENTRE_CONSULTAS": "0",
            "REINTENTOS_CONSULTA": "0",
            "ESPERA_BASE_REINTENTO": "0",
        }
    )
    with ServidorFirmsFalso(respuestas) as servidor:
        env["FIRMS_BASE"] = servidor.base
        return subprocess.run(
            ["bash", str(ORQUESTADOR)],
            capture_output=True, text=True, env=env, timeout=180,
        )


def _run_dir_de(tmp_path: Path) -> Path:
    ejecuciones = tmp_path / "ejecuciones"
    dirs = [d for d in ejecuciones.iterdir() if d.is_dir()]
    assert len(dirs) == 1
    return dirs[0]


def test_orquestador_detiene_por_saldo_y_deja_pendientes(tmp_path):
    """M011-C §2: la primera consulta falla; el control de saldo observa
    disponible=0 < pendientes=6 y DETIENE el lanzamiento: código 4, con
    detenida_saldo.json (pendientes, no fallidas) y sin más consultas."""
    resultado = _correr_orquestador(
        tmp_path, comportamiento="fail_first", saldo_disponible=0
    )
    assert resultado.returncode == 4, resultado.stdout + resultado.stderr
    assert "cuota de transacciones insuficiente" in resultado.stderr
    assert "PENDIENTES" in resultado.stderr

    run_dir = _run_dir_de(tmp_path)
    detenida = json.loads((run_dir / "detenida_saldo.json").read_text("utf-8"))
    assert detenida["razon"] == "saldo_insuficiente"
    assert detenida["transactions_available"] == 0
    nota = detenida["nota"].lower()
    assert "no son descargas fallidas" in nota  # pendientes, no fallidas
    assert "días sin detecciones" in nota
    # el control de saldo quedó registrado (saldo_checks.jsonl)
    saldos = [
        json.loads(linea)
        for linea in (run_dir / "saldo_checks.jsonl").read_text("utf-8").splitlines()
        if linea.strip()
    ]
    assert any(s["decision"] == "DETENER_SALDO_INSUFICIENTE" for s in saldos)
    # SOLO la primera consulta se intentó (la 1 falló; las 5 restantes no
    # se lanzaron: quedan pendientes, no fallidas)
    consultas = [
        json.loads(linea)
        for linea in (run_dir / "consultas.jsonl").read_text("utf-8").splitlines()
        if linea.strip()
    ]
    assert len(consultas) == 1
    resumen = json.loads((run_dir / "resumen_ejecucion.json").read_text("utf-8"))
    assert resumen["detenida_saldo"]["razon"] == "saldo_insuficiente"
    assert resumen["saldo_inicial"] == 4954
    assert resumen["total_consultas"] == 1 and resumen["fallidas"] == 1
    # la clave de prueba no quedó en ninguna evidencia del run
    for archivo in run_dir.rglob("*"):
        if archivo.is_file():
            assert CLAVE_PRUEBA not in archivo.read_text("utf-8", errors="replace"), (
                f"clave filtrada en {archivo}"
            )


def test_orquestador_continua_si_el_saldo_alcanza_tras_fallo(tmp_path):
    """Con saldo suficiente tras el fallo, las 6 consultas se intentan
    (independencia §9.4) y el control queda registrado como CONTINUAR."""
    resultado = _correr_orquestador(
        tmp_path, comportamiento="fail_first", saldo_disponible=100
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    run_dir = _run_dir_de(tmp_path)
    consultas = [
        json.loads(linea)
        for linea in (run_dir / "consultas.jsonl").read_text("utf-8").splitlines()
        if linea.strip()
    ]
    assert len(consultas) == 6  # la 1 falló; las 5 restantes se lanzaron igual
    saldos = [
        json.loads(linea)
        for linea in (run_dir / "saldo_checks.jsonl").read_text("utf-8").splitlines()
        if linea.strip()
    ]
    assert saldos and saldos[-1]["decision"] == "CONTINUAR"
    assert not (run_dir / "detenida_saldo.json").exists()
    resumen = json.loads((run_dir / "resumen_ejecucion.json").read_text("utf-8"))
    assert resumen["exitosas"] == 5 and resumen["fallidas"] == 1


def test_orquestador_idempotente_con_consultas_ya_exitosas(tmp_path):
    """§5 idempotencia: si las 6 consultas ya terminaron bien (skip por
    request_key), el orquestador las registra como exitosas sin fallar."""
    resultado = _correr_orquestador(
        tmp_path, comportamiento="skip_all", saldo_disponible=100,
        control_saldo="nunca",
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    run_dir = _run_dir_de(tmp_path)
    resumen = json.loads((run_dir / "resumen_ejecucion.json").read_text("utf-8"))
    assert resumen["exitosas"] == 6 and resumen["fallidas"] == 0
    estados = {
        json.loads(linea)["consulta_id"]: json.loads(linea)["estado_ingest"]
        for linea in (run_dir / "consultas.jsonl").read_text("utf-8").splitlines()
        if linea.strip()
    }
    assert len(estados) == 6
    assert all(e == "skipped_already_ingested" for e in estados.values())


def test_orquestador_control_saldo_siempre_verifica_entre_consultas(tmp_path):
    """CONTROL_SALDO=siempre: verifica el consumo tras CADA consulta; con
    saldo 0 se detiene antes de la segunda."""
    resultado = _correr_orquestador(
        tmp_path, comportamiento="ok", saldo_disponible=0, control_saldo="siempre"
    )
    assert resultado.returncode == 4, resultado.stdout + resultado.stderr
    run_dir = _run_dir_de(tmp_path)
    saldos = [
        json.loads(linea)
        for linea in (run_dir / "saldo_checks.jsonl").read_text("utf-8").splitlines()
        if linea.strip()
    ]
    # 1 control tras la consulta 1 (éxito) + 1 de detención
    assert len(saldos) == 2
    assert saldos[-1]["decision"] == "DETENER_SALDO_INSUFICIENTE"
    consultas = [
        json.loads(linea)
        for linea in (run_dir / "consultas.jsonl").read_text("utf-8").splitlines()
        if linea.strip()
    ]
    assert len(consultas) == 1  # la 2ª no se lanzó: quedó pendiente


# ---------------------------------------------------------------------------
# verificación estática adicional: el servidor local es la única http://
# ---------------------------------------------------------------------------

def test_firms_http_permite_http_solo_en_localhost():
    """La excepción http:// está restringida a localhost (pruebas); un host
    externo con http:// se rechaza y https:// siempre se acepta."""
    env = {**os.environ, "FIRMS_MAP_KEY": CLAVE_PRUEBA}
    for base, esperado in (
        ("https://firms.modaps.eosdis.nasa.gov", "ok"),
        ("http://127.0.0.1:9", "ok"),          # localhost: permitido (pruebas)
        ("http://localhost:9", "ok"),
        ("http://evil.example.com", "rechazado"),
        ("ftp://firms.modaps.eosdis.nasa.gov", "rechazado"),
    ):
        resultado = subprocess.run(
            [sys.executable, str(FIRMS_HTTP), "probe", "--base", base,
             "--timeout", "2"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        if esperado == "ok":
            assert resultado.returncode == 0, f"base {base} debía aceptarse"
        else:
            assert resultado.returncode == 2, f"base {base} debía rechazarse"


def test_patron_de_redaccion_presente_en_scripts():
    """Los scripts siguen redactando con el marcador público {MAP_KEY} (en el
    código bash aparece escapado como \\{MAP_KEY\\})."""
    for script in (PREFLIGHT, ORQUESTADOR):
        texto = script.read_text(encoding="utf-8")
        assert "{MAP_KEY" in texto  # marcador de redacción presente
        # y nunca imprimen la clave
        assert 'echo "$FIRMS_MAP_KEY"' not in texto
