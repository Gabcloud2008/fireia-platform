"""Normalización de CSV de FIRMS (formato Area API / descargas del portal).

Columnas exactas según la familia de producto (guías de usuario FIRMS, Fase 0):

- MODIS (MOD14/MYD14):  latitude, longitude, brightness, scan, track, acq_date,
  acq_time, satellite, instrument, confidence, version, bright_t31, frp, daynight
- VIIRS 375 m (VNP14IMG/VJ114IMG): idem pero con bright_ti4 y bright_ti5.

Decisiones documentadas:

- ``acq_time`` acepta HHMM y HHMMSS (el CSV de FIRMS usa ambos formatos según
  el producto/versón).
- El código de la columna ``satellite`` se mapea con la tabla PROVISIONAL de
  ``configs/sources.yaml`` (T/A/N confirmados; códigos de NOAA-20/21 por
  confirmar contra datos reales en Fase 1B). Los códigos sin mapeo pasan tal
  cual con flag ``satellite_code_unmapped`` — no se descarta la fila.
- Ninguna fila se descarta: las inválidas van a cuarentena con sus errores.
- Coordenada ausente (columna vacía) => error ``missing_latitude`` /
  ``missing_longitude`` y cuarentena. NUNCA se sustituye por 0.0: (0, 0) es
  una ubicación real (golfo de Guinea), no un valor faltante (Misión 002,
  corrección A).
- Se tolera un BOM UTF-8 inicial en el archivo (algunas descargas del portal
  de FIRMS lo traen); no forma parte del encabezado.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone

from hotspots.models import (
    NormalizedObservation,
    QuarantinedRow,
    compute_obs_id,
)
from hotspots.quality.checks import check_record

MODIS_COLUMNS = [
    "latitude",
    "longitude",
    "brightness",
    "scan",
    "track",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
    "confidence",
    "version",
    "bright_t31",
    "frp",
    "daynight",
]
VIIRS_COLUMNS = [
    "latitude",
    "longitude",
    "bright_ti4",
    "scan",
    "track",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
    "confidence",
    "version",
    "bright_ti5",
    "frp",
    "daynight",
]


class FirmsParseError(Exception):
    """Error a nivel de archivo (columnas faltantes, familia indetectable)."""


@dataclass
class ParseOutcome:
    records: list[NormalizedObservation] = field(default_factory=list)
    quarantined: list[QuarantinedRow] = field(default_factory=list)
    family: str | None = None
    n_rows: int = 0
    notes: list[str] = field(default_factory=list)


def detect_family(header: list[str]) -> str | None:
    """Detecta la familia de producto por el encabezado (modis | viirs | None)."""
    cols = {h.strip().lower() for h in header}
    if {"brightness", "bright_t31"} <= cols:
        return "modis"
    if {"bright_ti4", "bright_ti5"} <= cols:
        return "viirs"
    return None


def parse_firms_csv(
    text: str,
    *,
    product: str,
    settings,
    run_id: str,
    manifest_id: str,
    ingested_at_utc: str,
    expected_family: str | None = "auto",
    source_kind: str | None = None,
) -> ParseOutcome:
    """Parsea un CSV de FIRMS completo y devuelve registros + cuarentena.

    Lanza :class:`FirmsParseError` solo ante errores de archivo (encabezado
    irreconocible, columnas faltantes, familia incompatible con el producto).

    ``expected_family``: "auto" (default) deduce la familia esperada del
    producto configurado; ``None`` desactiva el chequeo (modo 'validate'
    sobre archivos arbitrarios).

    ``source_kind``: procedencia de ESTA corrida (Misión 008 — integridad de
    procedencia). ``"fixture"`` para ingesta offline de archivos locales,
    ``"firms_api"`` para la API real. Si viene ``None`` se conserva el
    fallback histórico (config del producto → ``firms_api``), pero los dos
    modos del pipeline SIEMPRE lo pasan explícito: una observación ingesteda
    como fixture jamás debe quedar etiquetada como si viniera de la API real.
    """
    if text is None or not text.strip():
        return ParseOutcome(notes=["empty_body"])

    text = text.lstrip("\ufeff")  # BOM de descargas del portal: no es encabezado

    if expected_family == "auto":
        try:
            expected_family = settings.product_cfg(product).get("family")
        except ValueError:
            expected_family = None

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise FirmsParseError("CSV sin encabezado")

    header = [h.strip() for h in reader.fieldnames]
    family = detect_family(header)
    if family is None:
        raise FirmsParseError(
            f"Encabezado irreconocible como CSV de FIRMS: {header[:6]}… "
            "(falta brightness/bright_t31 o bright_ti4/bright_ti5)"
        )

    expected_columns = MODIS_COLUMNS if family == "modis" else VIIRS_COLUMNS
    missing = [c for c in expected_columns if c not in header]
    if missing:
        raise FirmsParseError(f"Columnas faltantes para familia {family}: {missing}")

    if expected_family is not None and family != expected_family:
        raise FirmsParseError(
            f"El archivo es familia {family!r} pero el producto {product!r} "
            f"espera familia {expected_family!r}"
        )

    outcome = ParseOutcome(family=family)
    product_cfg = settings.product_cfg(product)
    qc = settings.qc

    for raw_row in reader:
        raw = {(k or "").strip(): (v or "").strip() for k, v in raw_row.items()}
        outcome.n_rows += 1
        rec, parse_errors = _normalize_row(
            raw,
            product=product,
            product_cfg=product_cfg,
            settings=settings,
            run_id=run_id,
            manifest_id=manifest_id,
            ingested_at_utc=ingested_at_utc,
            source_kind=source_kind,
        )
        result = check_record(rec, settings) if not parse_errors else None
        if parse_errors or (result is not None and not result.ok):
            errors = list(parse_errors) + (list(result.errors) if result else [])
            flags = list(result.flags) if result else []
            outcome.quarantined.append(
                QuarantinedRow(
                    raw=raw,
                    errors=errors,
                    flags=flags,
                    provider="firms",
                    product=product,
                    run_id=run_id,
                    ingested_at_utc=ingested_at_utc,
                )
            )
            continue
        rec.quality_flags = result.flags if result else []
        _append_confidence_band(rec, qc, family)
        outcome.records.append(rec)

    return outcome


def _normalize_row(
    raw: dict,
    *,
    product: str,
    product_cfg: dict,
    settings,
    run_id: str,
    manifest_id: str,
    ingested_at_utc: str,
    source_kind: str | None = None,
) -> tuple[NormalizedObservation, list[str]]:
    """Convierte una fila cruda en registro normalizado (best-effort).

    Los fallos de conversión devuelven errores de parseo (hard) — la fila
    completa va a cuarentena, nunca se inventa un valor. En particular, una
    coordenada ausente produce ``missing_latitude``/``missing_longitude``
    (corrección A): NO se rellena con 0.0.
    """
    errors: list[str] = []

    def _float(name: str) -> float | None:
        val = raw.get(name, "")
        if val == "":
            return None
        try:
            return float(val)
        except ValueError:
            errors.append(f"invalid_{name}")
            return None

    lat = _float("latitude")
    lon = _float("longitude")
    # Coordenada ausente vs. no numérica: errores distintos, ambos hard.
    # (0, 0) es una ubicación geográfica real: jamás representa "faltante".
    if lat is None and raw.get("latitude", "") == "":
        errors.append("missing_latitude")
    if lon is None and raw.get("longitude", "") == "":
        errors.append("missing_longitude")

    acq_date = raw.get("acq_date", "")
    acq_time = raw.get("acq_time", "")
    acq_dt = _parse_datetime(acq_date, acq_time)
    if not acq_dt:  # _parse_datetime devuelve "" ante fecha u hora inválidas
        if not _valid_date(acq_date):
            errors.append("invalid_acq_date")
        if not _valid_time(acq_time):
            errors.append("invalid_acq_time")

    satellite = raw.get("satellite", "")
    instrument = raw.get("instrument", "").upper()

    rec = NormalizedObservation(
        provider="firms",
        product=product,
        source_kind=source_kind or product_cfg.get("source_kind", "firms_api"),
        run_id=run_id,
        manifest_id=manifest_id,
        ingested_at_utc=ingested_at_utc,
        latitude=lat,
        longitude=lon,
        acq_date=acq_date,
        acq_time=acq_time,
        satellite=satellite,
        instrument=instrument,
        confidence=raw.get("confidence", ""),
        frp=_float("frp"),
        brightness=_float("brightness"),
        bright_t31=_float("bright_t31"),
        bright_ti4=_float("bright_ti4"),
        bright_ti5=_float("bright_ti5"),
        scan=_float("scan"),
        track=_float("track"),
        daynight=raw.get("daynight", ""),
        version=raw.get("version", "") or None,
        acq_datetime_utc=acq_dt,
        sensor=instrument,
        satellite_name=settings.satellite_codes.get(satellite, satellite),
    )
    if acq_dt and lat is not None and lon is not None and not errors:
        rec.obs_id = compute_obs_id(
            rec.provider,
            rec.product,
            rec.satellite,
            rec.instrument,
            acq_dt,
            lat,
            lon,
        )
    # Sin obs_id una fila JAMÁS llega al almacén válido: sin coordenadas o sin
    # fecha hay error de parseo y la fila va a cuarentena (corrección A2:
    # obs_id vacío colapsaba filas distintas en la vista deduplicada).
    return rec, errors


def _append_confidence_band(rec: NormalizedObservation, qc: dict, family: str) -> None:
    """Banda de confianza derivada (convención del proyecto, valor original intacto)."""
    if family == "viirs":
        bands = qc["confidence"]["viirs_lnh"].get("bands_map", {})
        rec.confidence_band = bands.get(rec.confidence, "")
    else:
        try:
            cval = int(rec.confidence)
        except (TypeError, ValueError):
            rec.confidence_band = ""
            return
        bands = qc["confidence"]["modis_0_100"]["bands"]
        if cval < bands["low_max"]:
            rec.confidence_band = "low"
        elif cval <= bands["nominal_max"]:
            rec.confidence_band = "nominal"
        else:
            rec.confidence_band = "high"


def _valid_date(s: str) -> bool:
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _valid_time(s: str) -> bool:
    fmt = "%H%M" if len(s) == 4 else ("%H%M%S" if len(s) == 6 else None)
    if fmt is None:
        return False
    try:
        datetime.strptime(s, fmt)
        return True
    except ValueError:
        return False


def _parse_datetime(date_s: str, time_s: str) -> str:
    """acq_date + acq_time (UTC en FIRMS) -> ISO 8601 con Z. '' si es inválido."""
    if not date_s:
        return ""
    try:
        d = datetime.strptime(date_s, "%Y-%m-%d")
    except ValueError:
        return ""
    fmt = "%H%M" if len(time_s or "") == 4 else ("%H%M%S" if len(time_s or "") == 6 else None)
    if fmt is None:
        return ""
    try:
        t = datetime.strptime(time_s, fmt)
    except ValueError:
        return ""
    dt = datetime(d.year, d.month, d.day, t.hour, t.minute, t.second, tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
