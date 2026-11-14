# Inteligencia ambiental: fuentes complementarias (investigadas, no integradas)

Fecha: 11-nov-2026. Este documento investiga qué fuentes ambientales y de validación
independiente aportan al problema, con su ficha completa. **Todavía no hay una sola
línea de código que las consuma** — la integración requiere datos reales del piloto y
decisión de alcance; meterlas antes sería decorar.

Por qué cada fuente y no otra: el criterio es que aporte algo **medible y relacionable**
con detecciones de focos de calor en Paraguay (variables de peligro, condiciones del
combustible, o validación independiente del evento de fuego).

## 1. Fichas de fuentes

### ERA5-Land — reanalysis meteorológico

| Campo | Valor verificado |
|---|---|
| Organismo | Copernicus Climate Change Service (C3S) / ECMWF |
| Producto | ERA5-Land (reanalysis de la componente de superficie) |
| Resolución | 0.1° × 0.1° (~9 km nativo), grilla regular lat/lon |
| Cobertura | Global |
| Frecuencia | Horaria (1950 a ~5 días antes de hoy) |
| Unidades | SI por variable (K para temperatura 2 m, m para precipitación acumulada, m s⁻¹ viento a 10 m, kg m⁻² humedad del suelo) |
| Formato | GRIB (NetCDF vía API) |
| Licencia | CC-BY (con citación del DOI) |
| Acceso | Climate Data Store: https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land (requiere cuenta gratuita) |
| Limitaciones | Es simulación (reanalysis), no observación directa; incertidumbre crece hacia el pasado; 9 km no resuelve valles ni tormentas convectivas locales |
| Qué aporta | Temperatura, precipitación, humedad de suelo y viento en la fecha/hora y lugar de cada detección: las variables de peligro clásicas |

### CHIRPS — precipitación satelitorial con estaciones

| Campo | Valor verificado |
|---|---|
| Organismo | UCSB Climate Hazards Center (+ USGS) |
| Producto | CHIRPS v2.0 (InfraRed Precipitation with Stations) |
| Resolución | 0.05° (~5 km) |
| Cobertura | Cuasi-global 50°S–50°N (Paraguay incluido) |
| Frecuencia | Diaria/pentadal/mensual, 1981–presente |
| Unidades | mm |
| Licencia | Uso libre con atribución (términos del CHC) |
| Acceso | https://www.chc.ucsb.edu/data/chirps |
| Limitaciones | Estaciones de suelo escasas en el Chaco (la parte que más nos interesa): la señal es más satelital que pluviométrica ahí; no detecta lluvia bajo nubes densas tan bien como radar |
| Qué aporta | Serie de sequía/acumulado que explica por qué hay temporadas de fuego peores que otras; complementa (no reemplaza) ERA5-Land |

### ESA WorldCover 10 m v200 (2021) — cobertura del suelo

| Campo | Valor verificado |
|---|---|
| Organismo | ESA (producción: Zanaga et al. 2022) |
| Producto | WorldCover 10 m 2021 v200 |
| Resolución | 10 m |
| Clases | 11 clases (bosque, pastizal, cultivo, urbano, agua…) |
| Licencia | **CC BY 4.0** (redistribuible con atribución) |
| Acceso | https://esa-worldcover.org (y Zenodo DOI 10.5281/zenodo.7254221) |
| Limitaciones | Episodio único (2021): no detecta cambios posteriores; clases genéricas (no distingue pastura cultivada de pastura natural) |
| Qué aporta | El "qué está ardiendo": un foco sobre pastizal del Chaco y uno sobre bosque atlántico remanente son fenómenos distintos; con 10 m podemos atribuir cobertura a la detección VIIRS de 375 m |

### MCD64A1 v6.1 — área quemada mensual MODIS

| Campo | Valor verificado |
|---|---|
| Organismo | NASA LP DAAC (producción: Giglio et al.) |
| Producto | MCD64A1 v6.1 Burned Area |
| Resolución | 500 m |
| Frecuencia | Mensual, global |
| Licencia | NASA open data: sin restricciones de uso o redistribución |
| Acceso | LP DAAC / Earthdata (requiere cuenta Earthdata) |
| Limitaciones | Mensual (no sirve para tiempo casi-real); 500 m subestima fuegos pequeños; comparte sensor MODIS con nuestros focos (¡no es independiente del sensor!, solo del algoritmo) |
| Qué aporta | **Validación independiente del evento**: un evento reconstruido con detecciones debería caer dentro de un píxel quemado del mes correspondiente. Es el producto contra el que contrastar perímetros (que nosotros NO calculamos) |

### GOES-16/GOES-18 ABI — fuego geostacionario

| Campo | Valor |
|---|---|
| Organismo | NOAA / GOES-R series |
| Producto | Fire Detection and Characterization (FDC) L2 |
| Resolución | 2 km en el subpunto (más grueso hacia el borde del disco) |
| Frecuencia | Cada 10–15 min (full disk) — continuidad temporal que ningún polar da |
| Licencia | Datos públicos de NOAA |
| Acceso | NOAA CLASS / GOES-R series en Earthdata; FIRMS también lo distribuye |
| Limitaciones | 2 km detecta solo fuegos grandes; para Paraguay (borde del disco de GOES-16) el píxel efectivo es mayor |
| Qué aporta | La dimensión temporal que a MODIS/VIIRS les falta: cómo EVOLUCIONA un fuego entre pasadas polares. Es el candidato natural para la etapa de reconstrucción fina |

## 2. Cómo se integrarían (diseño, sin implementar)

Regla general: la integración es una RELACIÓN versionada entre la observación/evento
y el píxel ambiental correspondiente — igual que `obs_geo`: nunca se toca la
observación original.

| Fuente | Clave de unión | Granularidad | Semántica |
|---|---|---|---|
| ERA5-Land | (lon, lat, hora UTC) → celda 0.1° | hora de la detección | condiciones en el momento y lugar de la detección |
| CHIRPS | (lon, lat) → celda 0.05° + ventana [−30, −7] días | día | acumulado previo (combustible seco) |
| WorldCover | (lon, lat) → píxel 10 m | estático (2021) | clase de cobertura bajo la detección |
| MCD64A1 | (lon, lat, mes) → píxel 500 m | mes | si el punto cayó en área quemada ese mes |
| GOES FDC | (lon, lat, ±10 min) | 10–15 min | detecciones del mismo fuego entre pasadas |

Advertencia de escalas (documentada a propósito): cruzar una detección VIIRS de
375 m con humedad de suelo de 9 km o precipitación de 5 km NO produce "la humedad
del fuego": produce "la humedad del área de 9 km alrededor del fuego". Toda
estadística que salga de ahí tiene que decirlo con esas palabras.

## 3. Qué haría falta para integrarlas

1. Datos reales del piloto (7 días de NRT) sobre los que las variables tengan sentido.
2. Decisión de alcance: ¿las cinco fuentes o empezar con ERA5-Land + WorldCover
   (las dos más directamente interpretables)?
3. Cuentas/credenciales para CDS (ERA5-Land) y Earthdata (MCD64A1) — jamás por
   chat; mismas reglas de higiene que FIRMS_MAP_KEY.
4. Extensión del esquema de manifiestos para archivos ambientales (rol
   `environmental_raster`) y de la tabla de relaciones (`obs_environment`).
