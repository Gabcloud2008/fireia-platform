"""Ingesta modular: transports, conectores por fuente y pipeline."""

from hotspots.ingestion.base import FetchResult, RequestsTransport, Transport, TransportError
from hotspots.ingestion.firms import (
    CredentialsError,
    FirmsClient,
    classify_response,
    header_only_csv,
)
from hotspots.ingestion.pipeline import IngestSummary, PipelineBlocked, run_ingest

__all__ = [
    "CredentialsError",
    "FetchResult",
    "FirmsClient",
    "IngestSummary",
    "PipelineBlocked",
    "RequestsTransport",
    "Transport",
    "TransportError",
    "classify_response",
    "header_only_csv",
    "run_ingest",
]
