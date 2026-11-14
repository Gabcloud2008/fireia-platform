#!/usr/bin/env python3
"""Misión 016 — FIREIA LIVE · Reporte de corridas de ingesta a Supabase.

Pegamento operativo (NO modifica el pipeline científico): traduce los
resultados del pipeline (manifiestos + Parquet) al esquema operativo de
Supabase vía REST (service_role, solo desde GitHub Actions).

Subcomandos:
  estado  — actualiza el estado de una corrida (pendiente→ejecutando→…)
  run     — reporta el resultado completo: corrida, cobertura, assets,
            ventana de detecciones, alertas por reglas y salud del sistema.

Reglas de alertas implementadas (reproducibles, con evidencia; Fase H):
  R-001 adquisicion_fallida      — resultado de corrida en error
  R-002 cobertura_sin_datos      — corrida exitosa sin filas descargadas
  R-003 cuarentena_masiva        — >50 % de filas en cuarentena (n>=20)
  R-004 aumento_inusual          — detecciones del día >> media móvil 7 días

Nunca imprime valores de secretos. Falla con exit != 0 si Supabase no
puede actualizarse (la corrida queda visible como fallida en Actions).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ALERTA_VERSION = "016.1"
MAX_DETECCIONES_INSERT = 5000  # tope de protección del plan free


def _env(nombre: str) -> str:
    import os
    v = os.environ.get(nombre, "")
    if not v:
        print(f"ERROR: falta variable {nombre}", file=sys.stderr)
        sys.exit(2)
    return v


class Supabase:
    def __init__(self) -> None:
        self.base = _env("SUPABASE_URL").rstrip("/")
        self.key = _env("SUPABASE_SERVICE_ROLE_KEY")
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _url(self, ruta: str) -> str:
        return f"{self.base}/rest/v1/{ruta}"

    def parchar_run(self, run_id: str, campos: dict) -> dict:
        r = requests.patch(
            self._url(f"fireia_ingestion_runs?run_id=eq.{run_id}"),
            headers=self.headers,
            json={**campos, "updated_at": datetime.now(timezone.utc).isoformat()},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()[0] if r.text.strip().startswith("[") else {}

    def insertar(self, tabla: str, filas: list[dict]) -> None:
        if not filas:
            return
        r = requests.post(self._url(tabla), headers=self.headers, json=filas, timeout=60)
        r.raise_for_status()

    def upsert_salud(self, servicio: str, status: str, **extra: object) -> None:
        fila = {
            "service": servicio,
            "status": status,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **extra,
        }
        r = requests.post(
            self._url("fireia_system_health"),
            headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
            json=fila,
            timeout=30,
        )
        r.raise_for_status()

    def media_movil_detecciones(self, product: str, dias: int = 7) -> tuple[float, float]:
        """(media, desvío) de detecciones por día de los últimos `dias` días (excluye hoy)."""
        r = requests.get(
            self._url("rpc/fireia_media_detecciones_dia"),
            headers=self.headers,
            params={"p_product": product, "p_dias": dias},
            timeout=30,
        )
        if r.ok:
            cuerpo = r.json()
            if isinstance(cuerpo, list) and cuerpo:
                return float(cuerpo[0]["media"] or 0), float(cuerpo[0]["desvio"] or 0)
            if isinstance(cuerpo, dict):
                return float(cuerpo.get("media") or 0), float(cuerpo.get("desvio") or 0)
        return (0.0, 0.0)


def _ultimo_manifiesto(data_dir: Path) -> Path | None:
    carpeta = data_dir / "manifests" / "firms"
    if not carpeta.exists():
        return None
    candidatos = sorted(carpeta.glob("manifest-*.json"), key=lambda p: p.stat().st_mtime)
    return candidatos[-1] if candidatos else None


def cmd_estado(args: argparse.Namespace) -> int:
    sb = Supabase()
    sb.parchar_run(args.run_id, {"status": args.estado, "pipeline_version": args.pipeline_version})
    print(f"run {args.run_id} → {args.estado}")
    return 0


def _evaluar_alertas(sb: Supabase, run_id: str, product: str, counts: dict, resultado: str, hoy: date) -> list[dict]:
    alertas: list[dict] = []
    ahora = datetime.now(timezone.utc).isoformat()

    if resultado != "exito":
        alertas.append({
            "created_at_utc": ahora,
            "area": {"tipo": "pais", "id": "PY"},
            "rule": "R-001-adquisicion-fallida",
            "rule_version": ALERTA_VERSION,
            "severity": "advertencia",
            "evidence": {"product": product, "resultado": resultado, "counts": counts},
            "run_id": run_id,
            "review_state": "nueva",
        })

    if resultado == "exito" and counts.get("rows_raw", 0) == 0:
        # honestidad: 0 filas puede ser respuesta sin detecciones O problema;
        # se alerta como 'sin datos' con evidencia para revisión humana
        alertas.append({
            "created_at_utc": ahora,
            "area": {"tipo": "pais", "id": "PY"},
            "rule": "R-002-cobertura-sin-datos",
            "rule_version": ALERTA_VERSION,
            "severity": "info",
            "evidence": {"product": product, "nota": "corrida exitosa sin filas descargadas; verificar ventana y disponibilidad FIRMS"},
            "run_id": run_id,
            "review_state": "nueva",
        })

    total = counts.get("rows_raw", 0) or 0
    cuar = counts.get("rows_quarantined", 0) or 0
    if total >= 20 and cuar / total > 0.5:
        alertas.append({
            "created_at_utc": ahora,
            "area": {"tipo": "pais", "id": "PY"},
            "rule": "R-003-cuarentena-masiva",
            "rule_version": ALERTA_VERSION,
            "severity": "aviso",
            "evidence": {"product": product, "rows_raw": total, "rows_quarantined": cuar,
                         "proporcion": round(cuar / total, 3)},
            "run_id": run_id,
            "review_state": "nueva",
        })

    # R-004: aumento inusual (solo modo real, n>=30, media 7d)
    validos = counts.get("rows_valid", 0) or 0
    if args_modo_global == "real" and validos >= 30:
        try:
            media, desvio = sb.media_movil_detecciones(product)
            if media > 0 and validos > media + 3 * max(desvio, 1.0):
                alertas.append({
                    "created_at_utc": ahora,
                    "area": {"tipo": "pais", "id": "PY"},
                    "rule": "R-004-aumento-inusual-detecciones",
                    "rule_version": ALERTA_VERSION,
                    "severity": "advertencia",
                    "evidence": {"product": product, "validas_hoy": validos,
                                 "media_7d": round(media, 1), "desvio_7d": round(desvio, 1),
                                 "criterio": "validas > media + 3*max(desvio,1)"},
                    "run_id": run_id,
                    "review_state": "nueva",
                })
        except Exception as e:  # noqa: BLE001 — la alerta no debe romper el reporte
            print(f"aviso: R-004 no evaluada ({type(e).__name__})")
    return alertas


args_modo_global = "real"


def cmd_run(args: argparse.Namespace) -> int:
    global args_modo_global
    args_modo_global = args.modo
    sb = Supabase()
    data_dir = Path(args.data_dir)

    man_path = _ultimo_manifiesto(data_dir)
    if man_path is None:
        sb.parchar_run(args.run_id, {
            "status": "error",
            "errors": [{"codigo": "sin_manifiesto", "mensaje": "no se encontró manifiesto de ingesta"}],
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        print("ERROR: sin manifiesto; corrida marcada error", file=sys.stderr)
        return 1
    man = json.loads(man_path.read_text(encoding="utf-8"))
    counts = man.get("counts", {})

    resultado = "exito" if args.resultado in ("success", "exito") and man.get("processing_state") == "completed" else (
        "parcial" if args.resultado in ("success", "exito") else "error"
    )

    # 1) corrida
    fila = sb.parchar_run(args.run_id, {
        "status": resultado,
        "downloaded": counts.get("rows_raw"),
        "valid": counts.get("rows_valid"),
        "quarantined": counts.get("rows_quarantined"),
        "manifest": {"manifest_id": man.get("manifest_id"), "result_state": man.get("result_state"),
                     "artifacts": [{k: a.get(k) for k in ("path", "role", "sha256", "size")}
                                   for a in man.get("artifacts", [])]},
        "pipeline_version": man.get("schema_version"),
        "workflow_run_url": args.workflow_run_url or None,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    })
    t0 = fila.get("started_at")
    if t0:
        try:
            dur = (datetime.now(timezone.utc) - datetime.fromisoformat(t0.replace("Z", "+00:00"))).total_seconds()
            sb.parchar_run(args.run_id, {"duration_s": round(dur, 1)})
        except Exception:  # noqa: BLE001
            pass

    # 2) cobertura
    estado_cov = "sin_datos" if counts.get("rows_raw", 0) == 0 else (
        "huecos" if counts.get("rows_quarantined", 0) > 0 else "ok"
    )
    sb.insertar("fireia_coverage", [{
        "run_id": args.run_id,
        "product": args.product,
        "interval_lo": man.get("acquisition_period", {}).get("from") or args.fecha or str(date.today()),
        "interval_hi": man.get("acquisition_period", {}).get("to") or args.fecha or str(date.today()),
        "gaps": man.get("gaps", []),
        "failures": man.get("failures", []),
        "state": estado_cov,
        "obs_count": counts.get("rows_valid"),
    }])

    # 3) assets
    import re
    m_url = re.search(r"actions/runs/(\d+)", args.workflow_run_url or "")
    run_gh = m_url.group(1) if m_url else "local"
    prefijo_artifacto = f"fireia-ingesta-{args.modo}-{args.product}-{run_gh}"
    assets = []
    for a in man.get("artifacts", []):
        role = a.get("role", "")
        tipo = "raw" if "raw" in role else ("parquet" if "parquet" in role else "manifest")
        p = Path(a.get("path", ""))
        try:
            rel = p.relative_to(data_dir)
        except ValueError:
            rel = Path(p.name)
        assets.append({
            "run_id": args.run_id,
            "asset_type": tipo,
            "storage": "gha-artifact",
            "path": f"{prefijo_artifacto}/{rel}",
            "sha256": a.get("sha256"),
            "bytes": a.get("size"),
            "product": args.product,
        })
    assets.append({
        "run_id": args.run_id,
        "asset_type": "manifest",
        "storage": "gha-artifact",
        "path": f"{prefijo_artifacto}/{man_path.name}",
        "sha256": None,
        "bytes": man_path.stat().st_size,
        "product": args.product,
    })
    sb.insertar("fireia_data_assets", assets)

    # 4) ventana móvil de detecciones (desde Parquet, tope MAX)
    insertadas = 0
    pq_path = next((Path(a["path"]) for a in man.get("artifacts", []) if a.get("role") == "observations_parquet"), None)
    if pq_path and pq_path.exists():
        import pyarrow.parquet as pq
        t = pq.read_table(pq_path, columns=["product", "satellite", "latitude", "longitude",
                                            "acq_date", "acq_time", "confidence", "bright_t31"])
        df = t.to_pylist()
        df.sort(key=lambda r: r["acq_date"])
        filas = []
        for r in df[:MAX_DETECCIONES_INSERT]:
            filas.append({
                "run_id": args.run_id,
                "product": r["product"],
                "satellite": r["satellite"] or "N/D",
                "latitude": float(r["latitude"]),
                "longitude": float(r["longitude"]),
                "acq_date": str(r["acq_date"]),
                "acq_time": r["acq_time"],
                "confidence": r.get("confidence"),
                "bright_ti31": float(r["bright_t31"]) if r.get("bright_t31") is not None else None,
            })
        sb.insertar("fireia_latest_detections", filas)
        insertadas = len(filas)

    # 5) alertas
    alertas = _evaluar_alertas(sb, args.run_id, args.product, counts, resultado, date.today())
    sb.insertar("fireia_alerts", alertas)

    # 6) salud
    sb.upsert_salud("pipeline", "ok" if resultado == "exito" else "degradado",
                    problem=None if resultado == "exito" else f"última corrida {resultado}",
                    last_ok_at=datetime.now(timezone.utc).isoformat() if resultado == "exito" else None,
                    details={"detections_insertadas": insertadas, "modo": args.modo})

    print(json.dumps({
        "run_id": args.run_id, "resultado": resultado,
        "counts": counts, "estado_cobertura": estado_cov,
        "assets": len(assets), "detecciones_insertadas": insertadas,
        "alertas": len(alertas),
    }, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a1 = sub.add_parser("estado")
    a1.add_argument("--run-id", required=True)
    a1.add_argument("--estado", required=True, choices=["ejecutando", "exito", "error", "parcial"])
    a1.add_argument("--pipeline-version", default="")
    a1.set_defaults(fn=cmd_estado)

    a2 = sub.add_parser("run")
    a2.add_argument("--run-id", required=True)
    a2.add_argument("--data-dir", required=True)
    a2.add_argument("--product", required=True)
    a2.add_argument("--modo", default="real", choices=["real", "fixture"])
    a2.add_argument("--resultado", default="success")
    a2.add_argument("--fecha", default="")
    a2.add_argument("--workflow-run-url", default="")
    a2.set_defaults(fn=cmd_run)

    args = ap.parse_args()
    for intento in range(3):
        try:
            return args.fn(args)
        except Exception as e:  # noqa: BLE001 — reintento con backoff
            print(f"intento {intento + 1} falló: {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(5 * (intento + 1))
    print("ERROR: reporte a Supabase falló tras reintentos", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
