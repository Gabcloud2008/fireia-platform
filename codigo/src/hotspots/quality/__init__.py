"""Controles de calidad: taxonomía de estados y validación por registro."""

from hotspots.quality.checks import CheckResult, check_record
from hotspots.quality.states import ALL_STATES, IngestState, IngestStatusRecord

__all__ = ["ALL_STATES", "CheckResult", "IngestState", "IngestStatusRecord", "check_record"]
