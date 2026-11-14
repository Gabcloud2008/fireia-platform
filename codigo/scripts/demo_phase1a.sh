#!/usr/bin/env bash
# ============================================================================
# DEMO FASE 1A (endurecida, Misión 002) — hito 100% offline
#   1. Validar muestras sintéticas (incluye filas inválidas y coords ausentes)
#   2. Ingesta offline (fixtures) -> RAW + manifiesto + GeoParquet + DuckDB
#      - caso normal (MODIS + VIIRS)
#      - caso corrección C: todas las filas en cuarentena
#   3. Idempotencia: la misma ingesta otra vez -> skip
#   4. Dry-run de la ingesta real (plan sin red ni escrituras)
#   5. Verificación de integridad: manifiestos <-> artefactos <-> SHA256
#   6. Estado del almacén local
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==================================================================="
echo "1) VALIDACIÓN (muestras sintéticas)"
echo "==================================================================="
hotspots validate tests/fixtures/synthetic_modis_nrt.csv || true
hotspots validate tests/fixtures/synthetic_invalid_rows.csv || true
hotspots validate tests/fixtures/synthetic_missing_coords.csv || true

echo "==================================================================="
echo "2) INGESTA OFFLINE (fixture -> RAW + manifiesto + Parquet + DuckDB)"
echo "==================================================================="
hotspots ingest --fixture tests/fixtures/synthetic_modis_nrt.csv      --product MODIS_NRT
hotspots ingest --fixture tests/fixtures/synthetic_viirs_noaa20_nrt.csv --product VIIRS_NOAA20_NRT
hotspots ingest --fixture tests/fixtures/synthetic_invalid_rows.csv   --product MODIS_NRT
hotspots ingest --fixture tests/fixtures/synthetic_missing_coords.csv --product MODIS_NRT

echo "-------------------------------------------------------------------"
echo "2b) Corrección C: CSV válido con TODAS las filas rechazadas por QC"
echo "    (estado success_all_quarantined, NO parse_failed)"
echo "-------------------------------------------------------------------"
hotspots ingest --fixture tests/fixtures/synthetic_all_quarantined.csv --product MODIS_NRT

echo "==================================================================="
echo "3) IDEMPOTENCIA (misma ingesta -> skip, sin duplicar nada)"
echo "==================================================================="
hotspots ingest --fixture tests/fixtures/synthetic_modis_nrt.csv --product MODIS_NRT

echo "==================================================================="
echo "4) DRY-RUN de la ingesta real (sin red, sin escrituras)"
echo "==================================================================="
hotspots ingest --source firms-api --product VIIRS_NOAA21_NRT \
    --date 2026-09-15 --day-range 2 --dry-run

echo "==================================================================="
echo "5) VERIFICACIÓN de integridad (manifiestos <-> artefactos <-> SHA256)"
echo "==================================================================="
hotspots verify

echo "==================================================================="
echo "6) ESTADO del almacén"
echo "==================================================================="
hotspots status

echo "==================================================================="
echo "Manifiestos registrados:"
echo "==================================================================="
hotspots manifest list
echo ""
echo "DEMO COMPLETA (todo offline, sin credenciales, sin red)."
