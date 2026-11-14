"""Capa de almacenamiento: RAW inmutable, Parquet analítico y DuckDB."""

from hotspots.storage.duckdb_store import DuckDBStore
from hotspots.storage.parquet_store import ParquetStore
from hotspots.storage.raw import RawStore, StoredRaw, sha256_bytes

__all__ = ["DuckDBStore", "ParquetStore", "RawStore", "StoredRaw", "sha256_bytes"]
