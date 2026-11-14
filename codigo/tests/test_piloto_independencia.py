"""Pruebas offline del orquestador del piloto FIRMS (Misión 010/011, §9.4).

Verifican, con un `hotspots`, un `curl` y un preflight de stub (sin red, sin
datos reales):

1. Independencia por consulta: el fallo de la consulta 1 NO cancela las
   restantes; todas las 6 consultas se intentan y quedan registradas.
2. Reintento de script con espera progresiva: intentos fallidos se reintentan
   y el estado final refleja el último intento.
3. Higiene: la MAP_KEY nunca queda persistida en los textos de la ejecución
   (los archivos quedan redactados con {MAP_KEY}).
4. M011: si el preflight no da GO (bloqueo de transporte, saldo
   insuficiente), el orquestador NO lanza ninguna consulta y propaga el
   código del preflight.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

CLAVE_FICTICIA = "STUBKEYNOREAL1234"

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
    ruta.chmod(ruta.stat().st_mode | stat.S_IEXEC)
    return ruta


def _stub_hotspots(ruta: Path) -> Path:
    codigo = f"""#!/usr/bin/env python3
import json, os, sys

COMPORTAMIENTO = os.environ.get("STUB_BEHAVIOR", "ok")
args = sys.argv[1:]

def _valor(bandera):
    if bandera in args:
        return args[args.index(bandera) + 1]
    return None

if not args or args[0] != "ingest":
    print(json.dumps({{"stub": True, "cmd": args}}))
    raise SystemExit(0)

producto = _valor("--product") or "STUB"
fecha = _valor("--date") or ""

def fallir():
    sys.stderr.write("ConnectionError: Connection aborted (stub, "
                     f"clave {CLAVE_FICTICIA} en texto)\\n")
    raise SystemExit(1)

def exito(leak=False):
    s = json.loads({json.dumps(SUMMARY_OK)!r})
    s["product"] = producto
    if leak:
        s["planned_url"] = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{CLAVE_FICTICIA}/STUB/..."
    print(json.dumps(s))
    raise SystemExit(0)

if COMPORTAMIENTO == "fail_first":
    if producto == "MODIS_NRT" and fecha == "2026-11-04":
        fallir()
    exito()
elif COMPORTAMIENTO == "fail_then_succeed":
    marcador_file = os.environ["STUB_CONTADOR"]
    try:
        with open(marcador_file, "r", encoding="utf-8") as fh:
            marcador = int(fh.read().strip() or "0")
    except (OSError, ValueError):
        marcador = 0
    with open(marcador_file, "w", encoding="utf-8") as fh:
        fh.write(str(marcador + 1))
    if marcador % 2 == 0:
        fallir()
    exito()
elif COMPORTAMIENTO == "leak_key":
    exito(leak=True)
else:
    exito()
"""
    return _escribir_ejecutable(ruta, codigo)


def _stub_curl(ruta: Path) -> Path:
    codigo = """#!/usr/bin/env python3
import sys
args = sys.argv[1:]
if "-o" in args:
    destino = args[args.index("-o") + 1]
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write("data_id,min_date,max_date\\nMODIS_NRT,2026-09-01,2026-11-11\\n")
raise SystemExit(0)
"""
    return _escribir_ejecutable(ruta, codigo)


def _verificador_stub(ruta: Path) -> Path:
    codigo = """#!/usr/bin/env python3
import os
print('{"stub_verificador": true}')
raise SystemExit(int(os.environ.get("STUB_VERIFICADOR_EXIT", "0")))
"""
    ruta.write_text(codigo, encoding="utf-8")
    return ruta


def _stub_preflight(ruta: Path, exit_code: int) -> Path:
    """Preflight de stub: contrato con el orquestador (M011).

    Con exit 0 escribe el CSV de disponibilidad (destino del contrato) y el
    resumen; con cualquier otro código NO escribe nada (como el preflight
    real, que se detiene antes de capturar disponibilidad).
    """
    codigo = f"""#!/usr/bin/env bash
if [ "{exit_code}" -eq 0 ]; then
    if [ -n "${{PREFLIGHT_AVAIL_DEST:-}}" ]; then
        {{
            printf 'data_id,min_date,max_date\\n'
            printf 'MODIS_NRT,2026-09-01,2026-11-11\\n'
            printf 'VIIRS_NOAA20_NRT,2026-08-01,2026-11-11\\n'
            printf 'VIIRS_NOAA21_NRT,2024-01-17,2026-11-11\\n'
            printf 'VIIRS_SNPP_NRT,2024-01-01,2026-11-02\\n'
        }} > "$PREFLIGHT_AVAIL_DEST"
    fi
    if [ -n "${{PREFLIGHT_RESULTADO_JSON:-}}" ]; then
        printf '{{"stub": true, "decision": "GO"}}' > "$PREFLIGHT_RESULTADO_JSON"
    fi
fi
exit {exit_code}
"""
    return _escribir_ejecutable(ruta, codigo)


def _correr_piloto(tmp_path: Path, comportamiento: str, reintentos: int,
                   exit_verificador: int, preflight_exit: int = 0) -> subprocess.CompletedProcess:
    shim = tmp_path / "shim"
    shim.mkdir(exist_ok=True)
    _stub_curl(shim / "curl")

    env = os.environ.copy()
    env.update({
        "STUB_BEHAVIOR": comportamiento,
        "STUB_CONTADOR": str(tmp_path / "stub_contador.txt"),
        "STUB_VERIFICADOR_EXIT": str(exit_verificador),
        "FIRMS_MAP_KEY": CLAVE_FICTICIA,
        "PREFLIGHT_SCRIPT": str(_stub_preflight(
            tmp_path / "preflight_stub.sh", preflight_exit)),
        "HOTSPOTS_COMANDO": str(_stub_hotspots(tmp_path / "hotspots_stub.py")),
        "VERIFICADOR_RUTA": str(_verificador_stub(tmp_path / "verificador_stub.py")),
        "DIR_EJECUCIONES": str(tmp_path / "ejecuciones"),
        "AVAIL_RUTA": str(tmp_path / "avail.csv"),
        "ESPERA_ENTRE_CONSULTAS": "0",
        "REINTENTOS_CONSULTA": str(reintentos),
        "ESPERA_BASE_REINTENTO": "0",
        # M011-C: estas pruebas ejercen la INDEPENDENCIA, no el control de
        # saldo (que se prueba con servidor local en test_seguridad_m011c).
        # nunca = cero llamadas HTTP desde la prueba: determinista offline y
        # sin tocar FIRMS real con claves ficticias.
        "CONTROL_SALDO": "nunca",
        "PATH": f"{shim}{os.pathsep}{env['PATH']}",
    })
    script = Path(__file__).resolve().parent.parent / (
        "mision_007_datos_reales/herramientas/piloto_firms_7dias.sh"
    )
    return subprocess.run(
        ["bash", str(script)],
        capture_output=True, text=True, env=env, timeout=180,
    )


def _estado_final(run_dir: Path) -> dict[str, dict]:
    finales: dict[str, dict] = {}
    for linea in (run_dir / "consultas.jsonl").read_text(encoding="utf-8").splitlines():
        if linea.strip():
            registro = json.loads(linea)
            finales[registro["consulta_id"]] = registro
    return finales


def _dir_ejecucion(tmp_path: Path) -> Path:
    raiz = tmp_path / "ejecuciones"
    ejecuciones = [d for d in raiz.iterdir() if d.is_dir()]
    assert len(ejecuciones) == 1
    return ejecuciones[0]


EXITOSOS = {"success_with_detections", "success_no_detections",
            "skipped_already_ingested", "dry_run"}


def test_un_fallo_no_cancela_las_demas_consultas(tmp_path):
    resultado = _correr_piloto(tmp_path, "fail_first", reintentos=0,
                               exit_verificador=3)
    # el verificador stub devuelve 3 y el script lo propaga
    assert resultado.returncode == 3, resultado.stdout + resultado.stderr

    run_dir = _dir_ejecucion(tmp_path)
    finales = _estado_final(run_dir)
    # las 6 consultas se INTENTARON a pesar del fallo de la primera
    assert len(finales) == 6
    caidas = [c for c in finales.values() if c["estado_ingest"] not in EXITOSOS]
    ok = [c for c in finales.values() if c["estado_ingest"] in EXITOSOS]
    assert len(caidas) == 1 and len(ok) == 5
    assert caidas[0]["producto"] == "MODIS_NRT"
    assert caidas[0]["fecha_consulta"] == "2026-11-04"
    assert caidas[0]["exit_code"] == 1
    assert "ConnectionError" in (caidas[0]["error"] or "")

    resumen = json.loads((run_dir / "resumen_ejecucion.json").read_text(encoding="utf-8"))
    assert resumen["total_consultas"] == 6
    assert resumen["exitosas"] == 5
    assert resumen["fallidas"] == 1
    assert resumen["verificador_exit"] == 3
    # la evidencia documental de disponibilidad se generó y se copió al run
    assert (tmp_path / "avail.csv").exists()
    assert (run_dir / "data_availability_ALL.csv").exists()


def test_reintento_por_consulta_con_exito_tardio(tmp_path):
    resultado = _correr_piloto(tmp_path, "fail_then_succeed", reintentos=1,
                               exit_verificador=0)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    run_dir = _dir_ejecucion(tmp_path)
    finales = _estado_final(run_dir)
    assert len(finales) == 6
    assert all(c["estado_ingest"] in EXITOSOS for c in finales.values())
    resumen = json.loads((run_dir / "resumen_ejecucion.json").read_text(encoding="utf-8"))
    # 6 consultas x 2 intentos (1 fallido + 1 exitoso) = 12 intentos registrados
    assert resumen["total_intentos"] == 12
    assert resumen["exitosas"] == 6 and resumen["fallidas"] == 0


def test_map_key_nunca_queda_persistida(tmp_path):
    resultado = _correr_piloto(tmp_path, "leak_key", reintentos=0,
                               exit_verificador=0)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    run_dir = _dir_ejecucion(tmp_path)
    filtrados = [
        p for p in run_dir.rglob("*")
        if p.is_file() and CLAVE_FICTICIA in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert filtrados == [], f"clave filtrada en: {filtrados}"
    # la redacción reemplaza por el marcador visible
    textos = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in run_dir.rglob("*") if p.is_file()
    )
    assert "{MAP_KEY}" in textos


def test_registrador_rechaza_stdout_no_json(tmp_path):
    """El registrador no debe inventar estados: stdout corrupto => estado None."""
    import sys
    herramientas = (Path(__file__).resolve().parent.parent
                    / "mision_007_datos_reales/herramientas")
    sys.path.insert(0, str(herramientas))
    import registrar_ejecucion as reg

    out = tmp_path / "roto.txt"
    out.write_text("Traceback (most recent call last): ...", encoding="utf-8")
    assert reg._cargar_stdout(str(out)) is None
    assert reg._cargar_stdout(None) is None


def test_preflight_sin_go_no_lanza_ninguna_consulta(tmp_path):
    """M011: transporte bloqueado (2) o saldo insuficiente (4) ⇒ el orquestador
    propaga el código del preflight y NO lanza ninguna de las 6 consultas."""
    for codigo in (2, 4):
        resultado = _correr_piloto(tmp_path, "ok", reintentos=0,
                                   exit_verificador=0, preflight_exit=codigo)
        assert resultado.returncode == codigo, (
            f"preflight {codigo}: " + resultado.stdout + resultado.stderr)
        assert "Ninguna consulta del piloto fue lanzada" in resultado.stderr
        # nada se ejecutó: ni consultas ni resumen
        ejecuciones = tmp_path / "ejecuciones"
        if ejecuciones.exists():
            for run_dir in ejecuciones.iterdir():
                assert not (run_dir / "consultas.jsonl").exists()
                assert not (run_dir / "resumen_ejecucion.json").exists()


def test_preflight_exitoso_queda_evidenciado_en_el_run(tmp_path):
    """M011: el GO del preflight queda como preflight_result.json en el run y
    la disponibilidad capturada se copia al directorio de la ejecución."""
    resultado = _correr_piloto(tmp_path, "ok", reintentos=0, exit_verificador=0)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    run_dir = _dir_ejecucion(tmp_path)
    pre = json.loads((run_dir / "preflight_result.json").read_text(encoding="utf-8"))
    assert pre["stub"] is True and pre["decision"] == "GO"
    assert (run_dir / "data_availability_ALL.csv").exists()
    csv_texto = (run_dir / "data_availability_ALL.csv").read_text(encoding="utf-8")
    assert "VIIRS_SNPP_NRT" in csv_texto  # exclusión documentada
