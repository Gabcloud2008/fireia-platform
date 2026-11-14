# Fuentes de datos y contratos de API

Todos los contratos fueron verificados contra la documentación oficial el 2026-11-11 (consulta de páginas públicas de documentación; NO se consumió la API ni se usaron credenciales).

## NASA FIRMS — Area API (fuente principal)

- Documentación: https://firms.modaps.eosdis.nasa.gov/api/area/
- URL: `GET {base}/api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}[/{DATE}]`
- `SOURCE`: `MODIS_NRT`, `MODIS_SP`, `VIIRS_SNPP_NRT/SP`, `VIIRS_NOAA20_NRT/SP`, `VIIRS_NOAA21_NRT/SP`, `LANDSAT_NRT` (solo EEUU/Canadá).
- `AREA`: bbox `west,south,east,north` (o `world`). Máximo: -180,-90,180,90.
- `DAY_RANGE`: 1–5 (verificado).
- `DATE`: YYYY-MM-DD opcional (sin él, devuelve lo más reciente).
- Respuesta: CSV (columnas por familia: MODIS con `brightness`/`bright_t31`; VIIRS con `bright_ti4`/`bright_ti5`).
- Límite: 5000 transacciones / 10 min (los requests grandes cuentan como múltiples).
- Estado S-NPP: la distribución cesó el 2026-11-02 15:40 UTC (NESDIS OSPO Update #4); el índice de la API (v4.2.8) lo anuncia y remite a NOAA-20/21. `VIIRS_SNPP_NRT` está marcado `active: false` en `configs/sources.yaml`: verificar qué responde el endpoint en la primera consulta real (Fase 1B) antes de usarlo.

## NASA FIRMS — data_availability

- Documentación: https://firms.modaps.eosdis.nasa.gov/api/data_availability/
- URL: `GET {base}/api/data_availability/csv/{MAP_KEY}/{SENSOR|ALL}`
- Devuelve disponibilidad de fechas de datos SP/NRT por sensor.
- Uso en el proyecto: evidencia del proveedor para el registro de estados (distinguir `provider_missing_data` de fallos propios).
- Implementado en `FirmsClient.fetch_data_availability()` (requiere red: Fase 1B).

## NASA FIRMS — missing_data

- Página: https://firms.modaps.eosdis.nasa.gov/api/missing_data/
- Es una tabla HTML (días con datos faltantes por satélite/tipo de dato); NO tiene contrato CSV documentado. La página aclara que NRT solo se muestra a partir de la última fecha disponible del estándar por satélite.
- Implementado como descarga de página (`FirmsClient.fetch_missing_data_page()`), con parseo diferido: no se inventa un endpoint que no está documentado.

## NASA Earthdata Login (Fase 1B)

- https://urs.earthdata.nasa.gov/
- Token Bearer (`Authorization: Bearer <token>`) aceptado por varios endpoints de CMR/LAADS, pero no por todos los servicios: la autenticación debe verificarse POR ENDPOINT (así lo exige la misión).
- Mecanismo clásico alternativo: `~/.netrc` (credenciales básicas).
- Implementado en `hotspots/earthdata/session.py` con estrategia explícita (`bearer` | `netrc`) y errores claros para 401/403. El token jamás aparece en logs, `repr` ni mensajes de error.

## Productos configurados (`configs/sources.yaml`)

| Producto | Sensor | Familia | Estado |
|---|---|---|---|
| `MODIS_NRT` / `MODIS_SP` | MODIS (Terra+Aqua) | modis | activo (hasta el apagado de Terra/Aqua, "fines 2026 / principios 2027" según alerta Earthdata del 02-may-2025) |
| `VIIRS_NOAA20_NRT` / `_SP` | VIIRS | viirs | activo |
| `VIIRS_NOAA21_NRT` / `_SP` | VIIRS | viirs | activo (primario de la constelación) |
| `VIIRS_SNPP_NRT` / `_SP` | VIIRS | viirs | inactivo (cese de distribución 2026-11-02; backfill por portal de archivo) |

## Bounding box de estudio

Paraguay: `-62.7, -27.6, -54.2, -19.3` (W, S, E, N) — Fase 0, Entregable 3. Margen para el chequeo soft de área: 0.5°.

## Pendiente de verificación en vivo (Fase 1B)

1. Respuesta exacta de la API ante MAP_KEY inválida (heurística actual: texto plano que menciona "map_key" + "invalid"/"not valid").
2. Cuerpo exacto de una respuesta sin detecciones (se asume encabezado solamente o vacío).
3. Códigos `satellite` reales de NOAA-20/NOAA-21 en el CSV.
4. Qué devuelve `VIIRS_SNPP_NRT` tras el cese del 2026-11-02.
