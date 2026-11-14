"""Controles de calidad por registro (QC de nivel 1).

Dos niveles, siempre explícitos:

- ``hard`` (errores): la fila no es válida y va a CUARENTENA. Nunca se borra:
  la cuarentena conserva la fila original y los motivos exactos.
- ``soft`` (flags): la fila es válida pero queda marcada (p. ej. coordenada
  fuera del área de estudio, FRP implausiblemente alto, código de satélite sin
  mapear). Los flags viajan con el dato.

Umbrales configurables en ``configs/qc.yaml``. Los umbrales "plausibles" son
convención del proyecto, no especificaciones de NASA/FIRMS (documentado).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from hotspots.models import NormalizedObservation


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)  # hard
    flags: list[str] = field(default_factory=list)  # soft

    @property
    def ok(self) -> bool:
        return not self.errors


def _is_num(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def check_record(rec: NormalizedObservation, settings) -> CheckResult:
    """Valida un registro normalizado contra la configuración de QC."""
    errors: list[str] = []
    flags: list[str] = []
    qc = settings.qc

    # --- coordenadas (hard: ausencia o rango global; soft: área de consulta) ---
    # None = ausente en el origen => missing_* (NUNCA 0.0); no numérica => invalid_*;
    # fuera de rango global => *_out_of_range. Estar fuera del rectángulo de
    # consulta es SOFT (outside_query_bbox): es una anomalía de contrato del
    # proveedor, NO un dato inválido ni un hecho geográfico. La pertenencia al
    # territorio nacional la resuelve la capa geográfica (dentro_pais, obs_geo),
    # no el QC de ingesta.
    coord = qc["coordinate"]
    if rec.latitude is None:
        errors.append("missing_latitude")
    elif not _is_num(rec.latitude):
        errors.append("invalid_latitude")
    elif not (coord["lat_min"] <= rec.latitude <= coord["lat_max"]):
        errors.append("latitude_out_of_range")

    if rec.longitude is None:
        errors.append("missing_longitude")
    elif not _is_num(rec.longitude):
        errors.append("invalid_longitude")
    elif not (coord["lon_min"] <= rec.longitude <= coord["lon_max"]):
        errors.append("longitude_out_of_range")

    if not errors or all("latitude" not in e and "longitude" not in e for e in errors):
        w, s, e, n = settings.firms_query_bbox
        m = settings.query_bbox_margin_deg
        if not ((s - m) <= rec.latitude <= (n + m) and (w - m) <= rec.longitude <= (e + m)):
            flags.append("outside_query_bbox")

    # --- fecha/hora (hard) ---
    if not rec.acq_datetime_utc:
        if not rec.acq_date:
            errors.append("invalid_acq_date")
        if not rec.acq_time:
            errors.append("invalid_acq_time")

    # --- instrumento (hard: sin identidad de sensor no hay fila válida) ---
    if rec.instrument not in settings.instruments:
        errors.append(f"unknown_instrument:{rec.instrument or 'missing'}")

    # --- día/noche (hard) ---
    dn_domain = [str(x) for x in qc.get("daynight_domain", ["D", "N"])]
    if rec.daynight not in dn_domain:
        errors.append(f"invalid_daynight:{rec.daynight or 'missing'}")

    # --- FRP (hard: negativo; soft: implausible) ---
    frp_cfg = qc["frp"]
    if rec.frp is None:
        errors.append("missing_frp")
    elif not _is_num(rec.frp):
        errors.append("invalid_frp")
    else:
        if rec.frp < frp_cfg["min"]:
            errors.append("frp_below_min")
        elif rec.frp > frp_cfg["plausible_max"]:
            flags.append("implausible_high_frp")

    # --- bandas de temperatura de brillo (hard si vienen mal) ---
    b_cfg = qc.get("brightness", {})
    for band in ("brightness", "bright_t31", "bright_ti4", "bright_ti5"):
        val = getattr(rec, band)
        if val is None:
            continue  # opcional según familia de producto
        if not _is_num(val):
            errors.append(f"invalid_{band}")
        elif val < b_cfg.get("min", 0.0):
            errors.append(f"{band}_below_min")

    # --- dominios de confianza (hard) ---
    fam = _family_of(rec.instrument)
    if fam:
        domain_name = "modis_0_100" if fam == "modis" else "viirs_lnh"
        dom = qc["confidence"][domain_name]
        if dom["type"] == "integer":
            try:
                cval = int(rec.confidence)
                if not (dom["min"] <= cval <= dom["max"]):
                    errors.append(f"confidence_out_of_range:{rec.confidence}")
            except (TypeError, ValueError):
                errors.append(f"invalid_confidence:{rec.confidence or 'missing'}")
        else:  # enum
            if rec.confidence not in [str(v) for v in dom["values"]]:
                errors.append(f"invalid_confidence:{rec.confidence or 'missing'}")
    else:
        errors.append(f"unknown_instrument:{rec.instrument or 'missing'}")

    # --- geometría de escaneo (soft) ---
    for name in ("scan", "track"):
        val = getattr(rec, name)
        if val is not None and _is_num(val) and val <= 0:
            flags.append(f"nonpositive_{name}")

    # --- satélite sin mapear (soft: se conserva el código original) ---
    if rec.satellite_name == rec.satellite:
        flags.append("satellite_code_unmapped")

    return CheckResult(errors=errors, flags=flags)


def _family_of(instrument: str) -> str | None:
    """Familia de columnas según instrumento (modis | viirs | None)."""
    if instrument == "MODIS":
        return "modis"
    if instrument == "VIIRS":
        return "viirs"
    return None
