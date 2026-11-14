#!/usr/bin/env python3
"""Registro de ejecución del piloto FIRMS (Misión 010 §9.4; M011-C §2).

Registra un intento de consulta (una línea JSONL), los controles de saldo
de transacciones entre consultas (``saldo_checks.jsonl``) o genera el
resumen final de la ejecución. Sin secretos: lo que se persiste proviene del
summary de ``hotspots ingest`` (URL ya redactada por el transporte) o del
primer renglón de stderr truncado; el shell redacta además la MAP_KEY de
ambos archivos antes de llamar aquí.

Uso:
  registrar_ejecucion.py registrar --run-dir DIR --consulta-id ID \
      --producto P --fecha YYYY-MM-DD --day-range N --periodo-hasta H \
      --intento-script N --exit-code C [--stdout F] [--stderr F]
      # imprime {"estado": ..., "exit_code": ...} del intento

  registrar_ejecucion.py saldo --run-dir DIR --momento M --disponible N|null \
      --pendientes P --decision D [--detener]
      # registra un control de saldo (M011-C §2); con --detener escribe
      # además detenida_saldo.json (quedan consultas pendientes, no fallidas)

  registrar_ejecucion.py resumen --run-dir DIR --desde D --hasta H \
      [--verificador-exit C] [--saldo-inicial N]
      # escribe resumen_ejecucion.json (incluye saldo y detenidas si las hay)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

# Estados que el CLI de hotspots considera exitosos (exit 0).
ESTADOS_EXITO = {
    "success_with_detections",
    "success_no_detections",
    "skipped_already_ingested",
    "dry_run",
}

# M011-C §2: el estado "detenida_saldo" NO es una descarga fallida: son
# consultas pendientes que no se lanzaron porque la cuota restante no
# permitía continuar con seguridad. Se reintentan relanzando el piloto
# (las ya exitosas no se repiten).

CAMPOS_FINALES = (
    "consulta_id",
    "producto",
    "periodo",
    "estado_ingest",
    "exit_code",
    "manifest_id",
    "raw_sha256",
    "intento_script",
    "error",
)


def _cargar_stdout(ruta: str | None) -> dict | None:
    """Parsea el stdout de ``hotspots ingest`` si es el JSON del summary."""
    if not ruta:
        return None
    try:
        texto = Path(ruta).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not texto.startswith("{"):
        return None
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return None
    return datos if isinstance(datos, dict) else None


def cmd_registrar(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    summary = _cargar_stdout(args.stdout)
    estado = summary.get("state") if summary else None

    primer_error: str | None = None
    if args.stderr:
        try:
            stderr = Path(args.stderr).read_text(encoding="utf-8", errors="replace")
        except OSError:
            stderr = ""
        lineas = stderr.strip().splitlines()
        if lineas:
            primer_error = lineas[0][:300]

    registro = {
        "run_id": run_dir.name,
        "consulta_id": args.consulta_id,
        "producto": args.producto,
        "fecha_consulta": args.fecha,
        "day_range": args.day_range,
        "periodo": {"desde": args.fecha, "hasta": args.periodo_hasta},
        "intento_script": args.intento_script,
        "exit_code": args.exit_code,
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "estado_ingest": estado,
        "manifest_id": (summary or {}).get("manifest_id"),
        "raw_sha256": (summary or {}).get("raw_sha256"),
        "raw_path": (summary or {}).get("raw_path"),
        "error": primer_error,
        "summary_ingest": summary,
    }
    with (run_dir / "consultas.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n")

    print(json.dumps({"estado": estado, "exit_code": args.exit_code}, ensure_ascii=False))
    return 0


def _int_o_none(valor: str) -> int | None:
    if valor is None or valor.strip().lower() in ("", "null", "none"):
        return None
    try:
        return int(valor)
    except ValueError:
        return None


def cmd_saldo(args: argparse.Namespace) -> int:
    """Registra un control de saldo entre consultas (M011-C §2)."""
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    disponible = _int_o_none(args.disponible)
    pendientes = _int_o_none(args.pendientes)
    registro = {
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "momento": args.momento,
        "transactions_available": disponible,
        "pendientes": pendientes,
        "decision": args.decision,
    }
    with (run_dir / "saldo_checks.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False, sort_keys=True) + "\n")
    if args.detener:
        (run_dir / "detenida_saldo.json").write_text(
            json.dumps(
                {
                    "razon": "saldo_insuficiente",
                    "transactions_available": disponible,
                    "pendientes_estimadas": pendientes,
                    "ts_utc": registro["ts_utc"],
                    "nota": (
                        "consultas NO lanzadas por cuota insuficiente: NO son "
                        "descargas fallidas ni días sin detecciones. Esperar el "
                        "reinicio de la ventana (10 minutos, gratuito) y "
                        "relanzar el piloto: las ya exitosas no se repiten "
                        "(idempotencia por request_key)."
                    ),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"decision": args.decision}, ensure_ascii=False))
    return 0


def cmd_resumen(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    finales: dict[str, dict] = {}
    total_intentos = 0
    for linea in (run_dir / "consultas.jsonl").read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        registro = json.loads(linea)
        total_intentos += 1
        # el último intento registrado gana como estado final de la consulta
        finales[registro["consulta_id"]] = registro

    consultas = [finales[clave] for clave in sorted(finales)]
    exitosas = [
        c for c in consultas
        if c.get("estado_ingest") in ESTADOS_EXITO and c.get("exit_code") == 0
    ]

    # M011-C §2: controles de saldo y consultas detenidas por cuota.
    saldo_checks: list[dict] = []
    ruta_saldos = run_dir / "saldo_checks.jsonl"
    if ruta_saldos.exists():
        for linea in ruta_saldos.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                saldo_checks.append(json.loads(linea))
    detenida = None
    ruta_detenida = run_dir / "detenida_saldo.json"
    if ruta_detenida.exists():
        try:
            detenida = json.loads(ruta_detenida.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            detenida = {"razon": "detenida_saldo_ilegible"}

    resumen = {
        "run_id": run_dir.name,
        "ventana": {"desde": args.desde, "hasta": args.hasta},
        "generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_consultas": len(consultas),
        "exitosas": len(exitosas),
        "fallidas": len(consultas) - len(exitosas),
        "total_intentos": total_intentos,
        "verificador_exit": args.verificador_exit,
        "saldo_inicial": _int_o_none(args.saldo_inicial),
        "controles_de_saldo": len(saldo_checks),
        "ultimo_saldo": saldo_checks[-1] if saldo_checks else None,
        "detenida_saldo": detenida,
        "consultas": [
            {campo: c.get(campo) for campo in CAMPOS_FINALES}
            for c in consultas
        ],
    }
    if detenida is not None:
        resumen["nota_detenida_saldo"] = (
            "la ejecución se detuvo ANTES de lanzar consultas porque la cuota "
            "restante no permitía continuar con seguridad; las consultas no "
            "lanzadas quedan PENDIENTES (no son fallidas ni días sin "
            "detecciones). Relanzar tras el reinicio de la ventana (10 min)."
        )
    (run_dir / "resumen_ejecucion.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "total_consultas": resumen["total_consultas"],
        "exitosas": resumen["exitosas"],
        "fallidas": resumen["fallidas"],
        "total_intentos": resumen["total_intentos"],
        "detenida_saldo": bool(detenida),
    }, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    reg = sub.add_parser("registrar", help="registra un intento de consulta")
    for nombre in ("run_dir", "consulta_id", "producto", "fecha", "periodo_hasta"):
        reg.add_argument(f"--{nombre.replace('_', '-')}", required=True)
    reg.add_argument("--day-range", type=int, required=True)
    reg.add_argument("--intento-script", type=int, required=True)
    reg.add_argument("--exit-code", type=int, required=True)
    reg.add_argument("--stdout")
    reg.add_argument("--stderr")
    reg.set_defaults(func=cmd_registrar)

    res = sub.add_parser("resumen", help="genera resumen_ejecucion.json")
    res.add_argument("--run-dir", required=True)
    res.add_argument("--desde", required=True)
    res.add_argument("--hasta", required=True)
    res.add_argument("--verificador-exit", type=int, default=None)
    res.add_argument(
        "--saldo-inicial",
        default=None,
        help="saldo de transacciones al inicio (del preflight; M011-C §2)",
    )
    res.set_defaults(func=cmd_resumen)

    sal = sub.add_parser("saldo", help="registra un control de saldo (M011-C)")
    sal.add_argument("--run-dir", required=True)
    sal.add_argument(
        "--momento", required=True,
        help="etiqueta del momento (p. ej. entre_consultas, http_429)",
    )
    sal.add_argument(
        "--disponible", required=True,
        help="transacciones disponibles (número o null si no se pudo verificar)",
    )
    sal.add_argument("--pendientes", required=True, help="consultas pendientes")
    sal.add_argument("--decision", required=True, help="CONTINUAR | DETENER_... | SIN_VERIFICACION")
    sal.add_argument(
        "--detener",
        action="store_true",
        help="marca la detención por saldo (escribe detenida_saldo.json)",
    )
    sal.set_defaults(func=cmd_saldo)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
