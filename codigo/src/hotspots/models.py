"""Modelo de datos de observaciones normalizadas.

Principios (Fase 0, Entregables 2 y 6):

- Se conservan TODOS los atributos originales del CSV de FIRMS con sus nombres
  exactos; los campos derivados viven en columnas SEPARADAS y no sobrescriben
  nada.
- MODIS y VIIRS nunca se fusionan en una observación indistinguible: cada fila
  conserva ``sensor``, ``satellite`` (código original), ``satellite_name``
  (derivado) y ``product``.
- No se aplican factores de área de píxel ni ningún escalamiento de conteos.

Identidad y duplicados (Misión 002, corrección D):

- ``obs_id`` es determinista e incluye ``product``: mismo producto + satélite +
  instrumento + fecha/hora + coordenadas => mismo identificador. Es la base de
  la deduplicación idempotente de RE-ingestas del MISMO producto.
- Dos productos distintos que detectan el mismo fenómeno producen SIEMPRE
  ``obs_id`` distintos: la identidad de una observación pertenece a su producto
  y nunca se fusiona (decisión arquitectónica explícita).
- La coincidencia ENTRE productos (harmonización MODIS/VIIRS) es un problema
  científico de la Fase 2 y NO se resuelve colapsando identidades: la vista
  ``candidate_matches`` de DuckDB genera PAREJAS candidatas preservando ambas
  identidades (ver ``storage/duckdb_store.py``).

Coordenadas ausentes (Misión 002, corrección A):

- ``latitude``/``longitude`` admiten ``None``. Una coordenada ausente NUNCA se
  reemplaza por ``0.0``: (0, 0) es una ubicación geográfica real (golfo de
  Guinea), no un valor faltante. Las filas sin coordenadas van a cuarentena
  con los errores ``missing_latitude`` / ``missing_longitude``.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

# Tipos de columna del esquema de salida (Parquet + vistas DuckDB).
KIND_STR = "str"
KIND_FLOAT = "float"
KIND_LIST_STR = "list_str"
KIND_BINARY = "binary"

# Orden canónico de columnas del almacén normalizado.
SCHEMA: list[tuple[str, str]] = [
    # --- procedencia (primero, para trazabilidad inmediata) ---
    ("obs_id", KIND_STR),
    ("provider", KIND_STR),
    ("product", KIND_STR),
    ("source_kind", KIND_STR),
    ("run_id", KIND_STR),
    ("manifest_id", KIND_STR),
    ("ingested_at_utc", KIND_STR),
    # --- atributos originales FIRMS (nombres exactos del CSV) ---
    ("latitude", KIND_FLOAT),
    ("longitude", KIND_FLOAT),
    ("acq_date", KIND_STR),
    ("acq_time", KIND_STR),
    ("satellite", KIND_STR),
    ("instrument", KIND_STR),
    ("confidence", KIND_STR),
    ("frp", KIND_FLOAT),
    ("brightness", KIND_FLOAT),
    ("bright_t31", KIND_FLOAT),
    ("bright_ti4", KIND_FLOAT),
    ("bright_ti5", KIND_FLOAT),
    ("scan", KIND_FLOAT),
    ("track", KIND_FLOAT),
    ("daynight", KIND_STR),
    ("version", KIND_STR),
    # --- campos derivados (nunca pisan los originales) ---
    ("acq_datetime_utc", KIND_STR),
    ("sensor", KIND_STR),
    ("satellite_name", KIND_STR),
    ("confidence_band", KIND_STR),
    ("quality_flags", KIND_LIST_STR),
    # --- geometría (GeoParquet: punto WKB, CRS OGC:CRS84 = lon/lat) ---
    ("geometry", KIND_BINARY),
]


def wkb_point(lon: float, lat: float) -> bytes:
    """Codifica un punto como WKB little-endian (GeoParquet, OGC:CRS84).

    Formato: byte_order(1) + geometry_type(1=POINT) + x(lon) + y(lat).
    """
    return struct.pack("<BIdd", 1, 1, lon, lat)


def compute_obs_id(
    provider: str,
    product: str,
    satellite: str,
    instrument: str,
    acq_datetime_utc: str,
    lat: float,
    lon: float,
) -> str:
    """Identificador determinista de la observación (base de deduplicación).

    Incluye ``product`` A PROPÓSITO: una observación es hija de su producto
    (sensor + procesamiento NRT/SP). Re-ingerir el mismo producto produce el
    mismo id (deduplicación); productos distintos nunca colisionan (sin fusión
    prematura de sensores — la coincidencia entre productos vive en la vista
    ``candidate_matches``, no en el id).
    """
    key = "|".join(
        [provider, product, satellite, instrument, acq_datetime_utc, f"{lat:.6f}", f"{lon:.6f}"]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


@dataclass
class NormalizedObservation:
    """Una detección de foco de calor, normalizada y con procedencia completa."""

    # procedencia
    provider: str
    product: str
    source_kind: str
    run_id: str
    manifest_id: str
    ingested_at_utc: str
    # atributos originales (nombres FIRMS). None = ausente en el CSV original:
    # JAMÁS se sustituye por 0.0 (ver docstring del módulo).
    latitude: float | None
    longitude: float | None
    acq_date: str
    acq_time: str
    satellite: str
    instrument: str
    confidence: str
    frp: float | None = None
    brightness: float | None = None
    bright_t31: float | None = None
    bright_ti4: float | None = None
    bright_ti5: float | None = None
    scan: float | None = None
    track: float | None = None
    daynight: str = ""
    version: str | None = None
    # derivados
    acq_datetime_utc: str = ""
    sensor: str = ""
    satellite_name: str = ""
    confidence_band: str = ""
    quality_flags: list[str] = field(default_factory=list)
    obs_id: str = ""

    def to_row(self) -> dict:
        """Diccionario en el orden de SCHEMA (incluye geometry WKB).

        ``geometry`` es ``None`` si falta alguna coordenada: nunca se fabrica
        un punto (0, 0). En el pipeline, esas filas van a cuarentena antes de
        llegar aquí; el guard es defensa en profundidad.
        """
        has_coords = self.latitude is not None and self.longitude is not None
        return {
            "obs_id": self.obs_id,
            "provider": self.provider,
            "product": self.product,
            "source_kind": self.source_kind,
            "run_id": self.run_id,
            "manifest_id": self.manifest_id,
            "ingested_at_utc": self.ingested_at_utc,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "acq_date": self.acq_date,
            "acq_time": self.acq_time,
            "satellite": self.satellite,
            "instrument": self.instrument,
            "confidence": self.confidence,
            "frp": self.frp,
            "brightness": self.brightness,
            "bright_t31": self.bright_t31,
            "bright_ti4": self.bright_ti4,
            "bright_ti5": self.bright_ti5,
            "scan": self.scan,
            "track": self.track,
            "daynight": self.daynight,
            "version": self.version,
            "acq_datetime_utc": self.acq_datetime_utc,
            "sensor": self.sensor,
            "satellite_name": self.satellite_name,
            "confidence_band": self.confidence_band,
            "quality_flags": list(self.quality_flags),
            "geometry": wkb_point(self.longitude, self.latitude) if has_coords else None,
        }


@dataclass
class QuarantinedRow:
    """Fila rechazada por QC: se conserva íntegra (nunca se borra) con sus errores."""

    raw: dict  # columnas originales del CSV, tal como llegaron (strings)
    errors: list[str]  # motivos hard que invalidaron la fila
    flags: list[str]  # flags soft detectados antes del rechazo
    provider: str
    product: str
    run_id: str
    ingested_at_utc: str

    def to_row(self) -> dict:
        row = dict(self.raw)
        row.update(
            {
                "errors": list(self.errors),
                "soft_flags": list(self.flags),
                "provider": self.provider,
                "product": self.product,
                "run_id": self.run_id,
                "ingested_at_utc": self.ingested_at_utc,
            }
        )
        return row
