# Diccionario de datos

Una observación = una detección de foco de calor (una fila del CSV de FIRMS), normalizada con procedencia completa. El esquema canónico está definido en `src/hotspots/models.py` (`SCHEMA`), se escribe en GeoParquet y se expone en las vistas DuckDB `observations` (deduplicada) y `observations_raw`.

## Procedencia (escritas por el pipeline)

| Columna | Tipo | Descripción |
|---|---|---|
| `obs_id` | VARCHAR | SHA256 determinista de (provider, product, satellite, instrument, acq_datetime_utc, lat, lon). Base de la deduplicación DENTRO de un mismo producto: dos productos que detectan el mismo fenómeno producen obs_id DISTINTOS (sin fusión de sensores; la coincidencia entre productos vive en `candidate_matches`). |
| `provider` | VARCHAR | Siempre `firms` en Fase 1. |
| `product` | VARCHAR | Producto FIRMS consultado (ej. `MODIS_NRT`, `VIIRS_NOAA20_NRT`). |
| `source_kind` | VARCHAR | `firms_api` o `fixture` (ingesta offline). |
| `run_id` | VARCHAR | Identificador de la corrida de ingesta (uuid4). |
| `manifest_id` | VARCHAR | Manifiesto que documenta la corrida. |
| `ingested_at_utc` | VARCHAR | ISO 8601 UTC del momento de ingesta. |

## Atributos originales (nombres EXACTOS del CSV de FIRMS — jamás modificados)

| Columna | Tipo | Dominio / notas |
|---|---|---|
| `latitude` | DOUBLE | -90..90 (hard). Ausente en el origen => cuarentena con `missing_latitude` (NUNCA 0.0). |
| `longitude` | DOUBLE | -180..180 (hard). Ausente en el origen => cuarentena con `missing_longitude`. |
| `acq_date` | VARCHAR | YYYY-MM-DD (original, sin transformar). |
| `acq_time` | VARCHAR | HHMM u HHMMSS (original, UTC según FIRMS). |
| `satellite` | VARCHAR | Código original del CSV (T, A, N, ...). |
| `instrument` | VARCHAR | `MODIS` o `VIIRS`. |
| `confidence` | VARCHAR | MODIS: entero 0–100. VIIRS: `l` / `n` / `h`. Dominio por familia (hard). |
| `frp` | DOUBLE | MW. ≥ 0 (hard); > `qc.frp.plausible_max` => flag soft. |
| `brightness` | DOUBLE | MODIS: temperatura de brillo banda ~4 µm (K). Opcional. |
| `bright_t31` | DOUBLE | MODIS: banda 31 ~11 µm (K). Opcional. |
| `bright_ti4` | DOUBLE | VIIRS: banda I4 ~3,74 µm (K). Opcional. |
| `bright_ti5` | DOUBLE | VIIRS: banda I5 ~11 µm (K). Opcional. |
| `scan` | DOUBLE | Tamaño del píxel a lo largo del escaneo. ≤ 0 => flag soft. |
| `track` | DOUBLE | Tamaño del píxel a lo largo de la traza. ≤ 0 => flag soft. |
| `daynight` | VARCHAR | `D` / `N` (hard). |
| `version` | VARCHAR | Versión del producto FIRMS (passthrough). |

## Campos derivados (columnas SEPARADAS; nunca pisan los originales)

| Columna | Tipo | Descripción |
|---|---|---|
| `acq_datetime_utc` | VARCHAR | `acq_date` + `acq_time` en ISO 8601 UTC (`...Z`). |
| `sensor` | VARCHAR | `MODIS` / `VIIRS` (del instrumento). |
| `satellite_name` | VARCHAR | Nombre canónico del mapeo provisional (`T`→Terra, `A`→Aqua, `N`→S-NPP); si no está mapeado, pasa el código original + flag. |
| `confidence_band` | VARCHAR | VIIRS: low/nominal/high. MODIS: banda según convención del proyecto (`low_max: 30`, `nominal_max: 80` en `configs/qc.yaml`) — no es una definición de FIRMS; el valor original se conserva siempre. |
| `quality_flags` | VARCHAR[] | Flags soft acumulados (ver docs/validation.md). |

## Geometría

| Columna | Tipo | Descripción |
|---|---|---|
| `geometry` | BLOB | Punto WKB little-endian (GeoParquet 1.0, CRS84 implícito = lon/lat). `wkb_point(lon, lat)` en models.py. |

## Tablas auxiliares

- `quarantine` (vista): filas rechazadas por QC con TODAS sus columnas originales + `errors` (VARCHAR[]), `soft_flags`, `provider`, `product`, `run_id`, `ingested_at_utc`. Nunca se borran.
- `ingest_status` (vista): un registro por evento de ingesta: `provider`, `source`, `product`, `state` (taxonomía de 10 estados), `reason`, `occurred_at_utc`, `run_id`, `manifest_id`, `context_json`.

## Vista `candidate_matches` (corrección D — Fase 2)

Pares de observaciones de PRODUCTOS DISTINTOS que caen dentro de una ventana temporal (<= 600 s) y una proximidad espacial (<= 2000 m, distancia equirectangular aproximada). Columnas: `obs_id_a`, `obs_id_b`, `product_a/b`, `sensor_a/b`, `satellite_a/b`, `acq_datetime_utc_a/b`, `dt_seconds`, `distance_m`. Es GENERACIÓN DE CANDIDATOS (convención del proyecto), no matching científico: la Fase 2 aplicará los criterios de armonización realmente validados. Ninguna observación se fusiona ni se borra.

## Manifiestos (`data/manifests/firms/manifest-<id>.json`)

| Campo | Descripción |
|---|---|
| `manifest_id` | SHA256 corto del contenido canónico. |
| `request_key` | Hash canónico de (provider, source, product, params) — clave de idempotencia. |
| `result_state` / `processing_state` | Estado final (`success_*`, `parse_failed`, ...) y si completó. |
| `sensor`, `satellite_scope` | Identidad del producto. |
| `acquisition_period` | Fechas consultadas. |
| `counts` | `rows_raw` / `rows_valid` / `rows_quarantined`. |
| `artifacts[]` | `path`, `sha256`, `size`, `role` (raw_csv, observations_parquet, quarantine_parquet). |
| `run_id`, `created_at_utc`, `schema_version` | Trazabilidad de la corrida. |

---

## Capa geográfica (Misión 004)

### Tabla `unidades_admin` (GeoParquet, `data/geo/<versión>/unidades_admin.parquet`)

Una fila por unidad administrativa. Inmutable por versión: la próxima fuente vive
en `data/geo/<otra-versión>/`.

| Columna | Tipo | Qué es |
|---|---|---|
| `admin_id` | str | ID estable y versionado: `<versión>:ADM1:ALTO-PARANÁ` (slug sin acentos) |
| `shape_id` | str | ID de la fuente (geoBoundaries `shapeID`) |
| `nombre` | str | Nombre tal como viene de la fuente |
| `nivel` | int8 | 0 = país, 1 = departamento, 2 = distrito |
| `padre_admin_id` | str | null | Unidad padre (ADM2→ADM1→ADM0); el padre de los distritos se DERIVA espacialmente (`padre_derivado = true`) porque la fuente no lo trae |
| `bbox_w/s/e/n` | float | Extensión de la geometría (prefiltro point-in-polygon) |
| `geometry` | binary | Polígono/multipolígono WKB, OGC:CRS84 |

### Tabla `obs_geo` (Parquet append-only, `data/processed/obs_geo/part-*.parquet`)

La relación observación ↔ unidad administrativa. Una fila por (observación,
versión de límites). Cambiar de versión NO actualiza filas: escribe una tanda
nueva.

| Columna | Tipo | Qué es |
|---|---|---|
| `obs_id` | str | Referencia a la observación (jamás se modifica) |
| `version_limites` | str | Con qué versión de límites se asignó |
| `dentro_pais` | bool | Resultado del punto contra el polígono ADM0 |
| `admin1_id` | str | null | Departamento (null si está fuera del país) |
| `admin2_id` | str | null | Distrito |
| `metodo` | str | Versión del algoritmo de asignación (`pip_shapely_strtree_v1`) |
| `asignado_en_utc` | str | Cuándo se asignó |

### Vistas geográficas (DuckDB)

- `observations_geo`: observaciones + `dentro_pais`, `admin1_id`, `admin2_id`,
  `departamento` (nombre), `distrito` (nombre), `version_limites` — LEFT JOIN:
  una observación sin asignar queda con nulls, no desaparece.
- `stats_departamento_dia` / `stats_nacional_dia` / `stats_nacional_semana` /
  `stats_nacional_mes`: conteos y FRP total filtrando `dentro_pais` (las
  observaciones fuera del país NO cuentan para estadísticas nacionales).
- `cobertura_area`: cuántas observaciones caen dentro/fuera del país — la medición
  diaria de "fracción del rectángulo que es país vecino".

## Eventos (Misión 004)

### Tabla `events` (snapshot por corrida, `data/processed/events/part-<ts>-<run>.parquet`)

| Columna | Tipo | Qué es |
|---|---|---|
| `event_id` | str | Hash determinista de (método, parámetros, obs miembro ordenadas) |
| `metodo` | str | `co_detection_component_v1` |
| `parametros` | str | JSON `{"dt_seconds":..,"distance_m":..}` |
| `n_observaciones` | int32 | Tamaño de la componente conexa |
| `productos` / `sensores` / `satelites` | list[str] | Participantes (≥2 productos por construcción) |
| `primera_obs_utc` / `ultima_obs_utc` / `duracion_segundos` | — | Ventana temporal del evento |
| `lat_centroide` / `lon_centroide` | float | Centroide de las detecciones (NO una ubicación "real" del fuego) |
| `dispersion_metros` | float | Distancia máxima detección→centroide. **NO es perímetro ni tamaño de incendio** |
| `frp_total` / `frp_max` | float | Suma/máximo de las FRP de detecciones miembro (la suma NO es el FRP del fuego) |
| `confianzas` | list[str] | Valores de confianza de los miembros |

### Tabla `event_observations` (membresía N:M)

`event_id`, `obs_id`, `creado_en_utc`, `run_id` — la relación evento↔observación.
Una observación puede pertenecer a un solo evento por snapshot, pero la relación
histórica entre snapshots se conserva completa.

### Vistas

- `events` / `event_observations`: leen el ÚLTIMO snapshot; los anteriores quedan
  como archivos de evidencia.

---

## Columnas nuevas (Misión 005)

### events (snapshot v2, `co_detection_component_v2`)

| Columna | Tipo | Significado |
|---|---|---|
| `diametro_metros` | float | Máxima distancia entre dos miembros cualesquiera del evento (cota de extensión espacial) |
| `alerta_encadenamiento` | bool | True si diámetro > 2×distance_m o duración > 2×dt_seconds: el evento creció por encadenamiento transitivo (convención de diagnóstico, no umbral científico) |
| `frp_por_producto` | string (JSON) | FRP sumado POR producto (p. ej. `{"MODIS_NRT": 75.5, "VIIRS_NOAA20_NRT": 44.5}`); `frp_total` suma sensores distintos y NO es potencia física del fuego |

### unidades_admin.parquet — metadatos

| Clave | Contenido |
|---|---|
| `hotspots_geo_audit` | JSON con `geometrias_invalidas_originales`, `geometrias_reparadas` y `detalle_reparaciones` (por unidad, con el motivo original de invalidez) — contadas ANTES de reparar |

### Calendario de cobertura (`analysis/calendar.py`)

Estados por día: `con_detecciones` · `cero_detecciones_asumido` ·
`solo_rechazadas_qc` · `sin_datos`. Las fechas de cuarentena cuentan como
evidencia de adquisición (extienden el intervalo cubierto) pero no son
ceros comparables.
