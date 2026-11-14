# Validación y control de calidad

## Taxonomía de estados de ingesta (10 estados)

Definida en `hotspots/quality/states.py`; cada evento queda registrado en la vista `ingest_status` con fuente, producto, motivo y contexto. El décimo estado (`success_all_quarantined`) se añadió en la Misión 002 (corrección C) para separar el rechazo de QC del error de parseo.

| Estado | Significado | Ejemplo típico |
|---|---|---|
| `success_with_detections` | Consulta exitosa con filas válidas | Día con actividad en el Chaco |
| `success_no_detections` | CSV válido con encabezado y CERO filas (válido, no error) | Día tranquilo — el contrato FIRMS devuelve solo el encabezado |
| `success_all_quarantined` | CSV válido con filas, pero NINGUNA superó QC | Lote completo con FRP negativo: el archivo está bien, los registros no |
| `no_coverage` | No existe cobertura aplicable | Fuera de la huella del sensor |
| `provider_missing_data` | El proveedor declara ausencia de datos | Fechas listadas por `missing_data` |
| `cloud_obscured` | Observación afectada por nubes (se determina con máscaras de nube, NO con ausencia de focos) | Estación húmeda (Fase 2) |
| `download_failed` | Fallo de descarga (red, 5xx, 429, 4xx) | Timeout, servidor caído |
| `parse_failed` | La respuesta no se pudo interpretar como CSV de FIRMS | Columnas faltantes, HTML/JSON inesperado, cuerpo corrupto |
| `authentication_failed` | Credencial ausente/inválida/sin permisos | 401/403, MAP_KEY inválida |
| `unknown` | No se pudo determinar (p. ej. HTTP 200 con cuerpo VACÍO: anómalo, no es "sin detecciones") | Respuesta indeterminada del proveedor |

Correspondencia con la taxonomía de 6 estados de la Fase 0 (Entregable 6): `download_error` → `download_failed`/`parse_failed`; `response_ok_rows` → `success_with_detections`; `response_ok_empty_verified` → `success_no_detections`; el resto es 1:1.

La regla científica central del proyecto: "success_no_detections" NO significa que no haya incendios. Puede haber nubes, falta de cobertura o fuegos bajo el umbral del sensor. La ausencia de focos jamás se usa como proxy de nubes. Y un cuerpo HTTP 200 VACÍO tampoco es "sin detecciones": FIRMS documenta la ausencia de detecciones como un CSV con encabezado y cero filas; el cuerpo vacío se registra como `unknown` (anómalo e indeterminado) para permitir reintento (Misión 002, corrección B).

## Clasificación del cuerpo de una respuesta 2xx (corrección B)

`sniff_body()` (en `hotspots/ingestion/firms.py`) clasifica el cuerpo antes de parsearlo. No se asume nada por el código HTTP:

| Cuerpo | Estado | Razón registrada |
|---|---|---|
| CSV con encabezado y cero filas | `success_no_detections` | `header_only_csv` |
| CSV con filas (parseable) | según QC de registros | — |
| Vacío / solo espacios | `unknown` | `empty_body` (permite reintento) |
| HTML (mantenimiento, portal) | `parse_failed` | `html_body` |
| JSON inesperado | `parse_failed` | `json_body` |
| Texto no-CSV (mensaje del proveedor) | `parse_failed` (o `authentication_failed` si coincide con patrones de auth) | `non_csv_body` |
| CSV malformado (columnas faltantes, familia incompatible) | `parse_failed` | mensaje exacto del error |

La evidencia de TODOS los casos (incluidos los anómalos) queda preservada en RAW con su SHA256, lista para reprocesar cuando se entienda la causa.

## Controles por registro (nivel 1)

Umbrales en `configs/qc.yaml`. Hard => la fila va a cuarentena (se conserva íntegra con sus errores). Soft => la fila pasa marcada con flag en `quality_flags`.

| Chequeo | Nivel | Regla |
|---|---|---|
| Latitud/longitud PRESENTES (columna vacía => cuarentena) | hard | `missing_latitude` / `missing_longitude` — JAMÁS se rellena con 0.0 |
| Coordenada fuera del área de estudio (+0.5°) | soft | flag `outside_query_bbox` (ámbito de estudio, no validez del dato) |
| Latitud/longitud numéricas y en rango global | hard | [-90,90] / [-180,180] => `invalid_*` / `*_out_of_range` |
| `acq_date` / `acq_time` parseables (YYYY-MM-DD; HHMM/HHMMSS) | hard | `invalid_acq_date` / `invalid_acq_time` |
| `instrument` ∈ {MODIS, VIIRS} | hard | sin identidad de sensor no hay fila |
| `daynight` ∈ {D, N} | hard | |
| `frp` presente y ≥ 0 | hard | `missing_frp` / `frp_below_min` |
| `frp` > 5000 MW | soft | flag `implausible_high_frp` (convención del proyecto, configurable) |
| Bandas de brillo numéricas y ≥ 0 K (si vienen) | hard | opcionales por familia |
| Confianza en el dominio de su familia | hard | MODIS: 0–100 entero; VIIRS: l/n/h |
| `scan`/`track` ≤ 0 | soft | flag `nonpositive_scan`/`nonpositive_track` |
| Código de satélite sin mapear | soft | flag `satellite_code_unmapped` (se conserva el código original) |

## Cuarentena

- Las filas rechazadas se escriben en `data/processed/quarantine/` con TODAS sus columnas originales + `errors` + `soft_flags` + procedencia.
- Nunca se eliminan ni "corrigen": el dato original es intocable.
- `hotspots status` reporta el total en cuarentena.

## Integridad y trazabilidad

- RAW content-addressed: el nombre del archivo es su SHA256; write-once y chmod 0444.
- Cada corrida produce un manifiesto JSON con: petición (sin secretos), estado, conteos y artefactos con SHA256 y tamaño.
- `request_key` canónico => idempotencia auditable.
- `obs_id` determinista => deduplicación en la vista `observations` sin reescrituras.
- `ingest_status` conserva el historial completo de eventos por fuente.
- `hotspots verify` recomputa el SHA256 de cada artefacto referenciado por cada manifiesto y comprueba existencia, tamaño y convención content-addressed de RAW (Misión 002).

## Qué verificar tras cada ingesta (operación)

```bash
hotspots status            # conteos por producto/satélite, cuarentena, estados
hotspots manifest list     # corridas y sus estados
hotspots manifest show ID  # detalle con hashes de artefactos
hotspots verify            # coherencia manifiestos <-> artefactos <-> SHA256
hotspots validate CSV      # revalidar cualquier archivo suelto
```
