# Procedimiento de ingesta

## Modos

| Modo | Comando | Red | Escribe |
|---|---|---|---|
| Fixture (offline) | `hotspots ingest --fixture CSV --product P [--date D]` | No | RAW + manifiesto + GeoParquet + DuckDB |
| Dry-run | `hotspots ingest --source firms-api --product P ... --dry-run` | No | Nada (solo imprime el plan) |
| Real (api) | `hotspots ingest --source firms-api --product P ... --allow-network` | Sí | Todo, si hay credencial y autorización |

## Flujo (idéntico para fixture y api; solo cambia de dónde salen los bytes)

1. Compuertas: el modo api exige `--allow-network` (compuerta de la Fase 1B) y `FIRMS_MAP_KEY` configurada. Sin eso, error claro y no se hace nada.
2. Idempotencia nivel petición: se calcula el `request_key` canónico (proveedor + fuente + producto + parámetros). Si existe un manifiesto previo con ese request_key y estado `success_*`, la corrida se salta (`skipped_already_ingested`).
3. Obtención: fixture lee el archivo local; api hace 1 request GET al Area API con el contrato documentado (DAY_RANGE 1–5).
4. Clasificación: HTTP 401/403 => `authentication_failed`; 429/5xx/4xx => `download_failed`; texto de error de FIRMS => `authentication_failed`. En 2xx se clasifica el CUERPO antes de parsear (Misión 002, corrección B): vacío => `unknown` (`empty_body`, reintento permitido); HTML/JSON/texto => `parse_failed` con razón explícita; encabezado sin filas => `success_no_detections`; CSV con filas => parseo + QC (corrección C: si ninguna fila supera QC => `success_all_quarantined`, NO `parse_failed`).
5. RAW: los bytes crudos se guardan content-addressed (`data/raw/firms/<producto>/<año>/<sha256>.csv`, write-once, chmod 0444). Las respuestas de error TAMBIÉN se guardan como evidencia.
6. Normalización + QC: columnas originales intactas + derivados; filas inválidas a cuarentena con sus errores exactos (nunca se borran).
7. Manifiesto: JSON con request_key, estado, conteos y artefactos con SHA256; se indexa en `index.jsonl`.
8. GeoParquet append-only: `data/processed/observations/product=P/year=A/` + cuarentena + `ingest_status`.
9. DuckDB: se refrescan las vistas (`observations` deduplicada por `obs_id`, `observations_raw`, `quarantine`, `ingest_status`, `candidate_matches`).

## Idempotencia (los tres niveles)

1. RAW: mismo contenido => mismo archivo (el nombre ES el SHA256).
2. request_key: misma petición exitosa => skip de corrida completa.
3. obs_id: la vista `observations` deduplica por observación; re-ingestar jamás infla conteos ni exige reescrituras.

Una aclaración que conviene tener escrita: el salto por `request_key` aplica a corridas con estado `success_with_detections` / `success_no_detections` / `success_all_quarantined`. Los estados fallidos o indeterminados (`parse_failed`, `unknown`, `download_failed`, ...) NO saltan la idempotencia: se reintentan. Limitación documentada: el `request_key` no incluye la versión de la configuración de QC — si cambian los umbrales de `configs/qc.yaml`, las corridas previas exitosas no se reprocesan solas.

Verificado por pruebas: `test_idempotencia_doble_ingesta`, `test_success_all_quarantined_es_idempotente`, `test_api_cuerpo_vacio_permite_reintento`, `test_api_con_transport_falso_flujo_completo`, `test_deduplicacion_por_obs_id`, `test_ingest_idempotente_por_cli`.

## Backfill histórico (futuro, Fase 1B+)

El backfill 2000–2026 se hará contra el portal de archivo de FIRMS (entrega asíncrona + FTP), no contra la API (ver Fase 0, Entregable 3). El pipeline de la Fase 1A ya acepta cualquier CSV FIRMS local vía `--fixture`, que es exactamente el formato que entrega el portal: el backfill reutiliza este camino con verificación de hash incluida. Requiere autorización específica antes de ejecutarse (volumen).

## Identidad de observaciones y coincidencias (corrección D)

- `obs_id` incluye `product` A PROPÓSITO: la identidad pertenece al producto (sensor + procesamiento). Re-ingerir el mismo producto deduplica; dos productos que ven el mismo fuego producen DOS observaciones con DOS `obs_id` distintos. No hay fusión prematura de sensores.
- La vista `candidate_matches` (DuckDB) genera PAREJAS candidatas entre productos distintos dentro de una ventana de 600 s y 2000 m (umbrales de generación de candidatos, convención del proyecto, configurables en `DuckDBStore`). Es materia prima para la armonización científica de la Fase 2: conserva `obs_id_a`/`obs_id_b`, `dt_seconds` y `distance_m` (aproximación equirectangular). NO es matching científico.

## Lo que la ingesta NUNCA hace

- No modifica ni borra RAW existente (write-once + solo lectura).
- No inventa registros para completar series vacías.
- No confunde "sin detecciones" con "sin incendios" (ver docs/validation.md).
- No fusiona streams de sensores ni escala conteos por área de píxel.
- No usa la red sin `--allow-network` + credencial + autorización.
