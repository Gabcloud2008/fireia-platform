# Sensores MODIS y VIIRS: estado operativo y semántica (noviembre 2026)

Verificado contra fuentes oficiales el **2026-11-11** para la Misión 005.
Este documento es la base del bloqueo/activación de productos en
`configs/sources.yaml`: nada de lo que está acá se dedujo, todo se citó.

## 1. Estado operativo por satélite (2026-11-11)

| Satélite | Instrumento | Estado nov-2026 | Fin de operaciones | Confianza |
|---|---|---|---|---|
| **Terra** | MODIS | Operativo (drift de órbita documentado desde 2020-2021) | Actividades de fin de ciencia proyectadas para **febrero 2027** | Alta (NASA) |
| **Aqua** | MODIS | Operativo nominal (STM mar-2026) | Cierre proyectado **~septiembre 2027** (enero de 2026 se estimaba agosto 2026; extendido por energía) | Alta (NASA/Copernicus) |
| **Suomi NPP** | VIIRS | **Distribución de datos CERRADA** el **2026-11-02 15:40 UTC**; desorbitado desde 2026-12-01 (planificado) | Ya ocurrió | Alta (NESDIS) |
| **NOAA-20** | VIIRS | Operativo | — | Alta (NASA/NOAA) |
| **NOAA-21** | VIIRS | Operativo (primera imagen dic-2022) | — | Alta (NESDIS) |
| NOAA-22 (ex JPSS-4) | VIIRS | No verificado para FIRMS en esta misión | — | No verificado |

Fuentes (consultadas 2026-11-11):

- NESDIS, "Cessation of S-NPP data to users on/after November 2, 2026"
  (2026-08-03) y "Update #4" (2026-11-02): la distribución cesó a las
  **15:40 UTC** del 2-nov-2026; "VIIRS data will no longer be available
  after November 2, 2026".
- NESDIS (2026-10-19): desorbitación de Suomi NPP desde el 1-dic-2026.
- NASA Earthdata, "Transition from MODIS to VIIRS": "In late 2026/early
  2027, NASA's Terra and Aqua platforms that carry the MODIS instrument
  will begin shutting down operations"; "Suomi NPP is no longer delivering
  new data".
- NASA Science, "Terra: The End of An Era" (2025-12-29): fines de ciencia
  proyectados por combustible/energía: Terra en febrero (2027).
- Copernicus ATMOS (2026): Terra ~enero 2027, Aqua ~septiembre 2027.
- MODIS Instrument Operations Status (STM 2026-03): Aqua MODIS "continues to
  operate nominally. Current expected decommissioning: August 2026" —
  estimación que fue extendida (el estado de agosto-2026 proyecta el
  apagado por pasivización de la nave).
- NIFC/Esri Live Feeds: "As of November 1, 2026, data from the Suomi NPP
  satellite will cease to be available from NASA. Data updates from
  NOAA-20 and NOAA-21 will continue."

**Implicancia para el proyecto**: VIIRS S-NPP NO debe reactivarse como
producto NRT (la distribución cesó; el archivo histórico se sirve por el
portal, no por la API de área). MODIS Terra/Aqua siguen siendo fuentes NRT
vigentes durante la ventana del piloto, con fecha de cierre dentro del
horizonte de planificación — la plataforma debe estar preparada para el
cierre de MODIS sin romper la historia.

## 2. Productos FIRMS que manejamos

| Producto FIRMS | Sensor | Satélites | Resolución | Estado en sources.yaml |
|---|---|---|---|---|
| MODIS_NRT / MODIS_SP | MODIS | Terra (T), Aqua (A) | ~1 km | activos |
| VIIRS_SNPP_NRT / SP | VIIRS | S-NPP (N) | 375 m | **inactivos** — distribución cesada 2026-11-02 15:40 UTC (NESDIS OSPO); backfill por portal de archivo |
| VIIRS_NOAA20_NRT / SP | VIIRS | NOAA-20 ("1") | 375 m | activos |
| VIIRS_NOAA21_NRT / SP | VIIRS | NOAA-21 ("2") | 375 m | activos |

Los códigos de la columna `satellite` (T/A/N/1/2) están documentados en
`sources.yaml` con su fuente; los no mapeados pasan tal cual con flag
`satellite_code_unmapped` (no se descarta la fila).

## 3. Semántica de campos por familia (reglas de armonización)

### 3.1 MODIS (Terra/Aqua, C6.1)

- `confidence`: **entero 0-100**; bandas derivadas del propio usuario FIRMS:
  l < 25 ≤ n < 75 ≤ h (convención difundida por FIRMS/LANCE).
- `brightness` / `bright_t31`: bandas 21/22 y 31 (K).
- `frp`: potencia radiativa de fuego, MW (~1 km de píxel).
- Resolución efectiva ~1 km en el nadir, degradada hacia el borde del barrido.

### 3.2 VIIRS 375 m (S-NPP/NOAA-20/NOAA-21, VNP14IMG)

- `confidence`: **enum l/n/h directamente** (no hay escala 0-100 en el
  producto de 375 m — el de 750 m sí usa 0-100).
- `bright_ti4` / `bright_ti5`: bandas I4/I5 (K).
- `frp`: MW, píxel de 375 m.
- Resolución 375 m: mejor respuesta sobre fuegos pequeños y mejor trazado de
  frentes que MODIS 1 km (documentado por LANCE/Esri).

### 3.3 Regla del proyecto (no de NASA)

**No convertimos la confianza de MODIS a la escala de VIIRS ni al revés.**
Conservamos `confidence` original + `confidence_band` (armonización de
BANDA, no de escala), documentada en `docs/harmonization.md` con su análisis
de sensibilidad. Cualquier cruce futuro que exija una escala común tendrá
que justificarse con literatura y versionarse aparte.

## 4. Qué significa cada campo en la plataforma

- `frp_total` de un evento: **suma de FRP de detecciones de múltiples
  sensores sobre (probablemente) el mismo fuego** — NO es la potencia física
  del incendio (doble conteo esperable). Desde la Misión 005 cada evento
  lleva `frp_por_producto` (desglose) y la documentación lo aclara.
- `dispersion_metros`: dispersión de detecciones alrededor del centroide —
  no es un perímetro ni un área quemada.
- Una detección (punto caliente) no es un incendio confirmado: es una
  anomalía térmica detectada por sensor.

## 5. Cambios respecto de la Misión 004

- Verificación independiente del cese de S-NPP: el YAML de la Misión 004 ya
  lo declaraba ("Distribución cesada 2026-11-02 15:40 UTC, NESDIS OSPO");
  esta misión lo re-verificó contra NESDIS Update #4 y el aviso de
  Earthdata — coincide.
- Se agrega la cronología de cierre MODIS (Terra feb-2027, Aqua ~sep-2027)
  como contexto de planificación del piloto.
- Este archivo pasa a ser la fuente canónica del estado satelital del
  proyecto (antes vivía en notas dispersas del YAML y de README).
