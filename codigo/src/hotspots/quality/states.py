"""Taxonomía de estados de ingesta (QC de nivel 0).

Diez estados operativos. Cada registro de estado lleva fuente, producto, motivo
y contexto — un estado sin contexto no sirve para auditar nada.

Correspondencia con la taxonomía de 6 estados de la Fase 0 (Entregable 6):

  Fase 0                       | Aquí
  -----------------------------|------------------------------------------
  download_error               | download_failed / parse_failed
  response_ok_rows             | success_with_detections
  response_ok_empty_verified   | success_no_detections
  no_coverage                  | no_coverage
  cloud_obscured               | cloud_obscured
  provider_not_available       | provider_missing_data

Décimo estado (Misión 002, corrección C — antes confluido en ``parse_failed``):

  ``success_all_quarantined``: el archivo se interpretó CORRECTAMENTE como CSV
  de FIRMS y tenía filas, pero NINGUNA superó el QC de registro. No es un error
  de parseo (el archivo es válido) ni una ausencia de detecciones (las había,
  pero se rechazaron y están íntegras en cuarentena). Separar este caso evita
  contaminar ``parse_failed`` (síntoma de contrato roto) con rechazos de QC
  (síntoma de calidad del dato), y evita reportar "sin detecciones" cuando el
  proveedor sí envió filas.

Aclaración científica permanente: "success_no_detections" significa que la
consulta funcionó y el proveedor devolvió un CSV válido con cabecera y cero
filas de detección. NO significa que no haya incendios: puede haber nubes
(cloud_obscured se determina con máscaras de nube, no con la ausencia de
focos), no cobertura, o fuegos por debajo del umbral del sensor. Un cuerpo
HTTP 200 VACÍO no es "sin detecciones": es una respuesta anómala e
indeterminada y se registra como ``unknown`` (Misión 002, corrección B).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum


class IngestState(str, Enum):
    SUCCESS_WITH_DETECTIONS = "success_with_detections"
    SUCCESS_NO_DETECTIONS = "success_no_detections"
    SUCCESS_ALL_QUARANTINED = "success_all_quarantined"
    NO_COVERAGE = "no_coverage"
    PROVIDER_MISSING_DATA = "provider_missing_data"
    CLOUD_OBSCURED = "cloud_obscured"
    DOWNLOAD_FAILED = "download_failed"
    PARSE_FAILED = "parse_failed"
    AUTHENTICATION_FAILED = "authentication_failed"
    UNKNOWN = "unknown"


ALL_STATES = tuple(s.value for s in IngestState)

#: Estados que representan una corrida COMPLETADA de punta a punta. Base del
#: salto idempotente por ``request_key``: si una petición exacta ya terminó en
#: uno de estos estados, re-ejecutarla no aporta nada (los mismos bytes =>
#: el mismo resultado).
SUCCESS_STATES: tuple[str, ...] = (
    IngestState.SUCCESS_WITH_DETECTIONS.value,
    IngestState.SUCCESS_NO_DETECTIONS.value,
    IngestState.SUCCESS_ALL_QUARANTINED.value,
)


def processing_state_of(state: IngestState) -> str:
    """Estado de procesamiento del manifiesto (completed | raw_only | failed).

    - ``completed``: la consulta se procesó de punta a punta (incluye estados
      del proveedor como no_coverage/provider_missing_data/cloud_obscured).
    - ``raw_only``: se obtuvieron bytes y quedaron preservados en RAW como
      evidencia, pero no pudieron interpretarse como CSV de FIRMS
      (parse_failed, unknown con cuerpo anómalo).
    - ``failed``: la transacción HTTP falló (download/authentication); la
      evidencia del error también se conserva en RAW.
    """
    completed = SUCCESS_STATES + (
        IngestState.NO_COVERAGE.value,
        IngestState.PROVIDER_MISSING_DATA.value,
        IngestState.CLOUD_OBSCURED.value,
    )
    if state.value in completed:
        return "completed"
    if state in (IngestState.PARSE_FAILED, IngestState.UNKNOWN):
        return "raw_only"
    return "failed"


@dataclass
class IngestStatusRecord:
    """Un evento de ingesta con su estado, motivo y contexto verificable."""

    provider: str
    source: str  # firms_api | fixture | firms_data_availability | ...
    product: str
    state: str  # IngestState.value
    reason: str
    occurred_at_utc: str
    run_id: str
    manifest_id: str = ""
    context: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "provider": self.provider,
            "source": self.source,
            "product": self.product,
            "state": self.state,
            "reason": self.reason,
            "occurred_at_utc": self.occurred_at_utc,
            "run_id": self.run_id,
            "manifest_id": self.manifest_id,
            "context_json": json.dumps(self.context, ensure_ascii=False, sort_keys=True),
        }
