# Guía de resolución de errores

| Síntoma / mensaje | Causa | Solución |
|---|---|---|
| `FIRMS_MAP_KEY no está configurada` | Falta la credencial para una operación real | Crear `.env` desde `.env.example` y completar (con valores regenerados). No es necesaria para validate/fixture/dry-run/tests. |
| `BLOQUEADO: ... --allow-network` (PipelineBlocked) | Compuerta de la Fase 1B | Es el comportamiento correcto. Usar `--dry-run` para ver el plan; la primera solicitud real requiere flag + credencial + autorización del propietario. |
| `authentication_failed` (401/403) | MAP_KEY inválida o token Earthdata expirado/sin permisos | Regenerar la credencial en el sitio oficial. OJO: no todos los servicios NASA aceptan Bearer — verificar por endpoint (docs/sources.md). |
| `download_failed` con `error=ConnectionError/Timeout` | Red, DNS o proveedor caído | Reintentar más tarde; el sistema es idempotente (re-ejecutar no duplica nada). |
| `download_failed` por 429 | Límite de 5000 transacciones / 10 min de FIRMS | Esperar la ventana; para backfill usar el portal de archivo, no la API. |
| `parse_failed: Columnas faltantes` | El CSV no es de la familia esperada o viene malformado | Verificar el archivo con `hotspots validate`. Si el producto y la familia no coinciden, corregir `--product`. |
| `parse_failed` en fixture con encabezado irreconocible | El archivo no es un CSV de FIRMS | El header debe incluir `brightness`+`bright_t31` (MODIS) o `bright_ti4`+`bright_ti5` (VIIRS). |
| Filas en CUARENTENA tras una ingesta | Registros que no pasaron QC hard | `hotspots status` muestra el total; revisar `data/processed/quarantine/part-*.parquet` (columna `errors`). No es un fallo del pipeline: es el sistema funcionando. |
| `state: unknown` con `reason: empty_body` | HTTP 200 con cuerpo vacío: anómalo e indeterminado (NO es "sin detecciones") | La evidencia quedó en RAW. Reintentar la misma corrida (unknown no salta la idempotencia); si persiste, investigar con data_availability en Fase 1B. |
| `state: success_all_quarantined` | CSV válido cuyas filas TODAS fallaron QC | No es un error del pipeline ni del archivo: revisar `data/processed/quarantine/part-*.parquet` (columna `errors`) para ver los motivos exactos. |
| `state: parse_failed` con `reason: html_body/json_body` | El proveedor devolvió HTML/JSON en un endpoint CSV (mantenimiento, proxy) | La evidencia quedó en RAW. Reintentar más tarde; si persiste, revisar la URL/base_url. |
| `state: success_no_detections` en un día con fuegos esperados | Puede ser correcto (nubes, umbral del sensor) o un problema del proveedor | NO asumir fallo. Contrastar con `data_availability`/`missing_data` (Fase 1B) y con las máscaras de nube (Fase 2). |
| `DAY_RANGE debe estar entre 1 y 5` | Parámetro fuera del contrato del Area API | Usar 1–5 y partir las consultas mayores en varias corridas. |
| `Producto desconocido: ...` | `--product` no está en `configs/sources.yaml` | Ver el listado del error o revisar `configs/sources.yaml`. |
| DuckDB: `database is locked` | Otro proceso tiene abierto `hotspots.duckdb` | Cerrar la otra sesión (p. ej. un `duckdb.connect()` en un notebook) y reintentar. |
| Tests fallan con `geoparquet ... invalid CRS` | Se generó un Parquet con `crs` explícito (versión vieja del código) | Regenerar los datos (`data/processed`): el generador actual omite `crs` (CRS84 implícito, compatible con DuckDB 2.0). |
| `.env` no se carga | Archivo fuera de la raíz del repo o mal nombrado | `Settings` busca `<repo>/.env`; verificar nombre exacto y ubicación. |

## Cuándo NO es un error

- `skipped_already_ingested`: idempotencia trabajando (misma petición ya exitosa).
- `success_no_detections`: CSV válido con encabezado y cero filas. No confundir con ausencia de incendios (docs/validation.md).
- `success_all_quarantined`: el archivo es válido; los registros no pasaron QC y están íntegros en cuarentena con sus motivos exactos.
- Flags soft (`outside_query_bbox`, `implausible_high_frp`, `satellite_code_unmapped`): registros válidos con observaciones de calidad.
