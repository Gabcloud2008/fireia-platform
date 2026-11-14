"""Almacén analítico en Parquet (convención GeoParquet para puntos).

Decisiones técnicas (justificación en docs/architecture.md):

- Sin GeoPandas: los puntos se codifican como WKB puro (21 bytes) y el archivo
  lleva los metadatos ``geo`` de la especificación GeoParquet 1.0. DuckDB y
  cualquier lector GeoParquet los entienden. Evita una dependencia pesada
  (GDAL/PROJ) que el pipeline todavía no necesita.
- Particionado por producto y año: ``observations/product=<P>/year=<YYYY>/``.
  Las filas NUNCA se mezclan entre productos (cada producto es un sensor
  concreto; MODIS_NRT contiene Terra+Aqua, que siguen distinguibles por la
  columna ``satellite``).
- Append-only: cada corrida escribe un ``part-<run_id>.parquet`` nuevo. La
  deduplicación se resuelve en la vista de DuckDB por ``obs_id`` (determinista),
  así re-ingestar jamás produce conteos duplicados ni destruye datos.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hotspots.models import (
    KIND_BINARY,
    KIND_FLOAT,
    KIND_LIST_STR,
    KIND_STR,
    SCHEMA,
    QuarantinedRow,
)

_ARROW_TYPES = {
    KIND_STR: pa.string(),
    KIND_FLOAT: pa.float64(),
    KIND_LIST_STR: pa.list_(pa.string()),
    KIND_BINARY: pa.binary(),
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_table(rows: list[dict]) -> pa.Table:
    data = {name: [row.get(name) for row in rows] for name, _ in SCHEMA}
    arrays = {name: pa.array(data[name], type=_ARROW_TYPES[kind]) for name, kind in SCHEMA}
    schema = pa.schema([pa.field(name, _ARROW_TYPES[kind]) for name, kind in SCHEMA])
    return pa.Table.from_pydict(arrays, schema=schema)


def _write_table_atomic(table: pa.Table, path: Path) -> None:
    """Escribe Parquet de forma atómica: tmp + rename (corrección F1).

    Una interrupción a mitad de escritura deja a lo sumo un ``.tmp`` huérfano
    (que los listados ignoran), nunca un ``part-*.parquet`` corrupto que
    rompería el refresh de las vistas DuckDB.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp)
    os.replace(tmp, path)


def _geo_metadata(rows: list[dict]) -> bytes:
    """Metadatos `geo` según la spec GeoParquet 1.0.

    El CRS se omite a propósito: la spec define que sin `crs` el sistema de
    referencia es OGC:CRS84 (lon/lat), que es exactamente nuestra semántica, y
    es la única forma que DuckDB 2.0 lee sin error (verificado: con
    crs="OGC:CRS84" o su URN completo, DuckDB rechaza el archivo).
    """
    # Solo filas con coordenadas completas definen el bbox (las válidas siempre
    # las tienen; guard defensivo contra geometrías nulas — corrección A).
    lons = [r["longitude"] for r in rows if r.get("longitude") is not None]
    lats = [r["latitude"] for r in rows if r.get("latitude") is not None]
    bbox = [min(lons), min(lats), max(lons), max(lats)] if lons and lats else [0.0, 0.0, 0.0, 0.0]
    geo = {
        "version": "1.0.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                # geometry_types es OBLIGATORIO en la spec GeoParquet 1.0
                "geometry_types": ["Point"],
                "bbox": bbox,
            }
        },
        "creator": "hotspots-paraguay/0.1.0",
    }
    return json.dumps(geo).encode("utf-8")


class ParquetStore:
    """Escritura append-only de observaciones, cuarentena y estados."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    # ------------------------------------------------------------- observaciones
    def append_observations(
        self, records: list, *, product: str, year: str | int, run_id: str
    ) -> Path | None:
        """Escribe un part-file de observaciones normalizadas (GeoParquet)."""
        if not records:
            return None
        rows = [r.to_row() for r in records]
        folder = self.root / "observations" / f"product={product}" / f"year={year}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"part-{run_id}.parquet"
        table = _build_table(rows).replace_schema_metadata({b"geo": _geo_metadata(rows)})
        _write_table_atomic(table, path)
        return path

    # ---------------------------------------------------------------- cuarentena
    def append_quarantine(self, rows: list[QuarantinedRow], *, run_id: str) -> Path | None:
        """Escribe las filas rechazadas (íntegras, con sus errores). Nunca se borran."""
        if not rows:
            return None
        dicts = [q.to_row() for q in rows]
        folder = self.root / "quarantine"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"part-{run_id}.parquet"
        keys: list[str] = []
        for d in dicts:
            for k in d:
                if k not in keys:
                    keys.append(k)
        arrays = {}
        fields = []
        for k in keys:
            sample = next((d[k] for d in dicts if d.get(k) is not None), None)
            if isinstance(sample, list):
                arrays[k] = pa.array([d.get(k) for d in dicts], type=pa.list_(pa.string()))
                fields.append(pa.field(k, pa.list_(pa.string())))
            else:
                arrays[k] = pa.array(
                    [str(d.get(k, "")) if d.get(k) is not None else None for d in dicts],
                    type=pa.string(),
                )
                fields.append(pa.field(k, pa.string()))
        table = pa.Table.from_pydict(arrays, schema=pa.schema(fields))
        _write_table_atomic(table, path)
        return path

    # ------------------------------------------------------------ estados de ingesta
    def append_status(self, status_rows: list[dict], *, run_id: str) -> Path | None:
        if not status_rows:
            return None
        folder = self.root / "ingest_status"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"part-{run_id}.parquet"
        keys = list(status_rows[0].keys())
        arrays = {k: pa.array([r.get(k) for r in status_rows], type=pa.string()) for k in keys}
        schema = pa.schema([pa.field(k, pa.string()) for k in keys])
        _write_table_atomic(pa.Table.from_pydict(arrays, schema=schema), path)
        return path

    # -------------------------------------------------------------------- listados
    def observation_files(self) -> list[Path]:
        base = self.root / "observations"
        if not base.exists():
            return []
        return sorted(p for p in base.rglob("part-*.parquet") if p.is_file())

    def quarantine_files(self) -> list[Path]:
        base = self.root / "quarantine"
        if not base.exists():
            return []
        return sorted(p for p in base.rglob("part-*.parquet") if p.is_file())

    def status_files(self) -> list[Path]:
        base = self.root / "ingest_status"
        if not base.exists():
            return []
        return sorted(p for p in base.rglob("part-*.parquet") if p.is_file())
