# Arquitectura (Fase 1A)

## Diagrama de flujo

```
                      ┌─────────────────────────────────────────────┐
                      │ FUENTES (solo Fase 1B, con autorización)    │
                      │  FIRMS Area API · data_availability ·       │
                      │  missing_data · Earthdata (CMR/LAADS)       │
                      └───────────────────┬─────────────────────────┘
                                          │ Transport (interfaz inyectable;
                                          │  RequestsTransport solo con red)
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ INGESTIÓN  src/hotspots/ingestion/                                      │
│  firms.py (cliente + clasificación de respuesta)                        │
│  pipeline.py (orquesta: dry-run / fixture / api con compuerta 1B)       │
└───────────────────┬─────────────────────────────────────────────────────┘
                    │ bytes crudos + estado
                    ▼
┌──────────────────────────────┐   ┌──────────────────────────────────────┐
│ RAW INMUTABLE  storage/raw   │   │ MANIFIESTOS  provenance/manifests    │
│ content-addressed (SHA256)   │◄──┤ request_key (idempotencia) + índice  │
│ write-once, chmod 0444       │   │ JSONL + JSON por corrida             │
└──────────────────┬───────────┘   └──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ NORMALIZACIÓN + QC  normalization/firms_csv.py + quality/               │
│  esquema común, atributos originales intactos, campos derivados         │
│  separados; filas inválidas -> CUARENTENA (nunca se borran)             │
└───────────────────┬─────────────────────────────────────────────────────┘
                    │ registros válidos
                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ALMACÉN ANALÍTICO  storage/parquet_store.py                             │
│  GeoParquet 1.0 (puntos WKB, CRS84 implícito) particionado por          │
│  product=/year=  ·  quarantine/  ·  ingest_status/   (append-only)      │
└───────────────────┬─────────────────────────────────────────────────────┘
                    │ vistas
                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ DUCKDB  storage/duckdb_store.py                                         │
│  observations (deduplicada por obs_id) · observations_raw · quarantine · │
│  ingest_status                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Decisiones (y por qué)

1. Transport inyectable, sin `requests` en la lógica. Toda la ingesta depende de la interfaz `Transport`. Las pruebas inyectan `FakeTransport` con respuestas programadas, así la suite completa corre offline. El transporte real solo se instancia en modo api con `--allow-network`.

2. RAW content-addressed. El nombre del archivo ES su SHA256. Mismo contenido => mismo archivo (write-once + chmod 0444). La idempotencia a nivel archivo sale gratis y la integridad la puede verificar cualquiera.

3. Tres niveles de idempotencia.
   a) RAW content-addressed (mismo bytes => no se duplica);
   b) `request_key` en manifiestos (misma petición exitosa => la corrida se salta);
   c) `obs_id` determinista + vista deduplicada en DuckDB (re-ingestas nunca inflan conteos, sin reescribir nada).

4. GeoParquet sin GeoPandas. Los puntos se codifican como WKB puro (21 bytes: `struct.pack("<BIdd", 1, 1, lon, lat)`) con los metadatos `geo` de la spec 1.0. Con eso se evita la cadena GDAL/PROJ (pesada) que el pipeline no necesita. Detalle verificado: DuckDB 2.0 exige `geometry_types` y rechaza `crs: "OGC:CRS84"` como URI; sin `crs`, la spec define CRS84 (lon/lat) y DuckDB lo lee correctamente (`GEOMETRY('OGC:CRS84')`).

5. DuckDB como motor de vistas, no como almacén de copia. Los datos viven en Parquet append-only; DuckDB los consulta con vistas. La deduplicación por `obs_id` (determinista) se resuelve en la vista: nunca hay que reescribir ni compactar para no duplicar.

6. Una observación = una fila con identidad completa. MODIS y VIIRS nunca se fusionan: `sensor`, `satellite` (código original), `satellite_name` (derivado), `instrument` y `product` viajan en cada fila. Las bandas de brillo específicas de cada familia (`brightness`/`bright_t31` vs `bright_ti4`/`bright_ti5`) coexisten como columnas anulables con sus nombres originales.

7. Sin pandas en el pipeline. El CSV se parsea con `csv` de la stdlib y se escribe con PyArrow directo. Menos dependencias, menos superficie.

8. Compuerta de red explícita. `run_ingest(mode="api")` sin `allow_network=True` lanza `PipelineBlocked`. La primera solicitud real de FIRMS requiere, además, `FIRMS_MAP_KEY` configurada. Esto codifica la regla de la misión: nada de red sin autorización.

9. Logging con redacción automática. `RedactingFilter` reemplaza cualquier ocurrencia de los secretos configurados por `***REDACTED***` en todos los registros de log.

## Módulos

| Módulo | Responsabilidad |
|---|---|
| `hotspots.config` | Config centralizada (env + YAML), secretos sin repr |
| `hotspots.models` | Esquema común, obs_id determinista, WKB de puntos |
| `hotspots.ingestion.base` | Interfaz Transport + RequestsTransport |
| `hotspots.ingestion.firms` | Cliente FIRMS (area/availability/missing_data) + clasificación |
| `hotspots.ingestion.pipeline` | Orquestación dry-run/fixture/api + compuerta 1B |
| `hotspots.normalization.firms_csv` | CSV FIRMS -> registros normalizados + cuarentena |
| `hotspots.quality.states` | Taxonomía de 10 estados de ingesta + mapping processing_state |
| `hotspots.quality.checks` | Validación hard/soft por registro |
| `hotspots.storage.raw` | RAW inmutable content-addressed |
| `hotspots.storage.parquet_store` | GeoParquet append-only + cuarentena + estados |
| `hotspots.storage.duckdb_store` | Vistas y consultas (dedup por obs_id; vista candidate_matches entre productos) |
| `hotspots.provenance.manifests` | Manifiestos, request_key, índice JSONL |
| `hotspots.earthdata.session` | Sesión Earthdata (bearer/netrc) para Fase 1B |
| `hotspots.cli.app` | CLI validate/manifest/ingest/status/verify/test |

## Límites conocidos del diseño actual

- `missing_data` de FIRMS es una página HTML sin contrato CSV documentado: el cliente la descarga y el parseo queda diferido (documentado en `docs/sources.md`).
- Los textos de error de FIRMS (p. ej. MAP_KEY inválida) no están documentados exhaustivamente: la clasificación usa heurísticas conservadoras a verificar en la primera consulta real (Fase 1B).
- El mapeo de códigos `satellite` para NOAA-20/21 es provisional; los códigos no mapeados pasan con flag `satellite_code_unmapped`.

---

## Extensiones de la Misión 004 (nov-2026)

### Capa geográfica (`src/hotspots/geo/`)

Separación estricta de conceptos: `firms_query_bbox` (rectángulo de consulta,
con margen, incluye vecinos) ≠ polígono nacional ≠ pertenencia territorial. Los
límites (geoBoundaries gbOpen, CC BY 4.0) entran como datos versionados con
manifiesto propio (rol `geo_boundaries`), se materializan en `unidades_admin.parquet`
(WKB + GeoParquet) y la asignación es una relación append-only (`obs_geo`) —
jamás un atributo de la observación. Point-in-polygon con Shapely (STRtree +
geometrías preparadas; convención documentada: el borde cuenta como dentro).

### Eventos (`src/hotspots/events/`)

Los eventos de co-detección son componentes conexas del grafo de pares
candidatos entre productos. Semántica de snapshots: cada corrida escribe el
conjunto completo; las vistas leen el último; los anteriores quedan como
evidencia. El motor replica en Python la misma fórmula de la vista SQL y una
prueba de consistencia verifica que ambos caminos producen los mismos pares.

### Análisis (`src/hotspots/analysis/`)

Anomalías por mediana móvil + MAD de residuos (ciclo semanal removido),
split temporal estricto (el baseline nunca mira el futuro del día evaluado),
guardas de suficiencia y explicabilidad por día. Baselines de persistencia y
climatología como listón obligatorio. Los experimentos llevan la marca
`datos_sinteticos` en su propio resultado.

### API + dashboard (`src/hotspots/api/`)

FastAPI de solo lectura sobre el almacén DuckDB. Cada endpoint sirve datos que
existen: si la vista no existe, 404 con mensaje útil en vez de arrays vacíos que
aparenten contenido. El origen de los datos (`fixture` / `firms_api` / `mixto`)
se calcula de los manifiestos y se propaga a health/quality/anomalías y al
banner del dashboard. Dashboard: MapLibre (departamentos oficiales + puntos por
sensor) + ECharts (producto, calendario), servido por el mismo proceso
(`hotspots serve`).

---

## Extensiones de la Misión 005

```
src/hotspots/
  analysis/calendar.py   NUEVO — calendario de cobertura: distingue
                         "cero detecciones" (cero comparable dentro del
                         intervalo cubierto) de "sin datos" (hueco) y de
                         "solo rechazadas por QC". Alimenta /api/coverage
                         y la serie de /api/anomalies.
  geo/registry.py        NUEVO — registro cartográfico versionado
                         (configs/geo_sources.yaml): procedencia completa
                         por versión de límites, con CARÁTER declarado
                         (estadístico/referencial/catastral).
```

Cambios de contrato relevantes:

- `/api/statistics` y `/api/calendar` responden con `scope` explícito
  (`nacional` filtra `dentro_pais`; `area_consulta` es todo el almacén).
- Eventos v2: `diametro_metros`, `alerta_encadenamiento` (diagnóstico del
  encadenamiento transitivo, factor 2 como convención) y `frp_por_producto`
  (el desglose honesto del FRP; `frp_total` no es potencia física).
- El flujo RAW → … → API incorpora el paso de cobertura entre análisis y
  API: las series estadísticas solo usan días comparables del calendario.
