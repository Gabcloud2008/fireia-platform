# Cartografía y límites administrativos de Paraguay

Actualizado en la **Misión 007** (2026-11-11): la capa activa pasó a ser la
cartografía **INE 2022 vía OCHA COD-AB** (263 distritos, pcodes oficiales,
padres explícitos verificados). La capa 2012 (geoBoundaries, 247) queda
versionada como **histórica** y ambas coexisten sin mezclarse; la matriz de
correspondencias 247↔263 vive en
`mision_007_datos_reales/datos/matriz_correspondencia_adm2.csv`. Este documento
es la referencia única de la capa geográfica del proyecto: qué geometría usamos,
de dónde salió, qué año representa, qué NO es y cómo se resolvió la
discrepancia territorial con el INE.

## 1. Resumen ejecutivo

| Pregunta | Respuesta corta |
|---|---|
| ¿Qué capa está activa? | **INE 2022 vía OCHA COD-AB** (`ine2022-codab-hdx`, ADM0+ADM1+ADM2) — Misión 007 |
| ¿Qué año representa? | **2022** (CNPV; vintage de límites declarado: 2022-01-01) |
| ¿Cuántas unidades trae? | 1 país, 18 departamentos (17 + Asunción), **263 distritos** (verificados al descargar) |
| ¿Y la capa anterior? | geoBoundaries gbOpen 2012 (247) queda como **capa histórica versionada**, sin sobrescribir |
| ¿Cómo se corresponden? | Matriz 247↔263: 195 exactas, 28 cambios de nombre, 18 parciales, 4 divisiones, 14 creaciones post-2012, 2 slivers degenerados de la fuente 2012 |
| ¿Es delimitación legal? | **No**: el propio INE la declara "meramente referencial" para operativos estadísticos |
| ¿Cómo se incorporó? | Procedimiento versionado de 12 pasos ejecutado al pie de la letra (§8) |

## 2. Las fuentes, verificadas

### 2.0 INE 2022 vía OCHA COD-AB (capa activa desde la Misión 007)

- **Productor declarado**: DGEEC / INE Paraguay. **Redistribución**: OCHA
  Field Information Services Section (FISS), dataset
  *Paraguay - Subnational Administrative Boundaries (COD-AB) v01* en HDX
  (`data.humdata.org/dataset/cod-ab-pry`).
- **Vintage de límites**: 2022-01-01. Revisión de exactitud: 2026-07-09;
  válida para uso humanitario: 2026-07-29; última modificación del recurso:
  2026-09-24.
- **Licencia**: CC BY-IGO (redistribución OCHA); el productor original publica
  bajo la Licencia de Uso de la Información Pública del Gobierno Paraguayo.
- **Descargado el 2026-11-11** (GeoJSON y SHP completos, hashes SHA256 en
  `configs/geo_sources.yaml` ficha `ine2022-codab-hdx`), validado (conteos
  1/18/263, pcodes únicos, jerarquía explícita 100 % consistente) y construido
  con `hotspots geo build --schema codab --expected-adm2 263`.
- La descarga del zip original del INE está bloqueada desde el entorno del
  proyecto (DNS de ine.gov.py inalcanzable; enlaces JS). El COD-AB es la
  redistribución oficial de la misma geometría y declara la procedencia.

### 2.1 geoBoundaries gbOpen PRY (capa histórica, activa hasta la Misión 006)

Metadatos verificados contra la API oficial el **2026-11-11**
(`geoboundaries.org/api/current/gbOpen/PRY/ADM2/`):

- `boundarySource`: "Direcion General de Estadica, Encuestas y Censos" (DGEEC)
- `boundarySourceURL`: `geo.stp.gov.py/user/dgeec/tables/paraguay_2012_barrios_y_localidades/public`
- `boundaryYearRepresented`: **2012**
- `boundaryLicense`: **CC BY 4.0**
- `admUnitCount` (ADM2): **247**
- `buildDate`: 2023-12-12 · `sourceDataUpdateDate`: 2023-10-26

Detalles relevantes:

- La geometría original es de la DGEEC (Paraguay), redistribuida por
  geoBoundaries (William & Mary geoLab).
- La URL de origen sugiere que la capa ADM2 deriva de una cartografía de
  **barrios y localidades de 2012** adaptada a nivel distrital.
- Archivos fuente intactos en `data/geo/geoboundaries-gbOpen-PRY-9469f09/source/`
  con SHA256 en `configs/geo_sources.yaml` y en el manifiesto geo.

### 2.2 INE — Revisión 2025 (referencia oficial vigente)

- **Estimaciones y proyecciones de la población distrital 2000-2035,
  Revisión 2025**: "los **263 distritos** del país incluyendo Asunción".
  URL: `ine.gov.py/resumen/284/...` (consultada 2026-11-11).
- La **cartografía digital del INE** (2022 en el portal, capas SHP/KML/GeoJSON
  por departamento) se describe a sí misma como trazada "meramente
  referencial" para operativos estadísticos, bajo la Licencia de Uso de la
  Información Pública del Gobierno Paraguayo.
- El Portal Geoestadístico del INE presentó cartografía actualizada en
  2025-2026 con miras al próximo censo.

### 2.3 SNC — Servicio Nacional de Catastro

- **"Estudio de límites distritales de la República del Paraguay" (V2023,
  publicado 2024)**: `catastro.gov.py/public/3c5e5b_Limites...V2023.pdf`.
  Documenta el marco jurídico de los límites distritales y menciona los 263
  distritos. No se pudo descargar el PDF completo en esta misión (el fetch
  falló); queda citado por su portada/metadata y lo reportado por el buscador.

### 2.4 Otras vías de creación territorial (contexto)

- Diputados (2025-09): proyecto con dictamen para redefinir límites de tres
  distritos en Caaguazú — los límites distritales siguen en movimiento legal.
- Rojas Potrero: media sanción (2025-2026) — distritos "en trámite" que aún
  no existen para fines estadísticos.

## 3. La discrepancia 247 → 263, documento por documento

La diferencia neta es **16 unidades** entre la capa 2012 y la Revisión 2025.
Cronología verificada:

- **2012**: la cartografía base (hoy en geoBoundaries) registra 247 distritos.
- **2019**: la prensa especializada reporta 255 municipios (ABC Color,
  2019-11-11: "En el Paraguay existen 255 municipios").
- **2019-2021**: creación de los últimos distritos documentados:
  - **Maracaná** (2016, según Última Hora 2025-11-27)
  - **Laurel** (Canindeyú, 2019 — La Nación 2020-12-20)
  - **Cerro Corá** (Amambay, 2020)
  - **Paso Horqueta** (Concepción, 2020)
  - **Campo Aceval** (Presidente Hayes, 2020)
  - **Puerto Yvapovo** (San Pedro, 2020)
  - **San José del Rosario** (San Pedro, 2020)
  - **Boquerón** (depto. Boquerón, promulgado enero 2021 — RCC Chaco)
  - **Nueva Asunción** (Presidente Hayes, **Ley 6731**, sancionada
    abril 2021 — ABC Color + silpy.congreso.gov.py)
- **2025**: el INE publica la Revisión 2025 con 263 distritos.

**Lo que NO está verificado**: la composición exacta de los 16. Los 9 listados
arriba están documentados con fecha y fuente; el resto requiere el listado
oficial completo de la cartografía INE 2025 (descarga pendiente de
autorización). La prensa (Última Hora, 2025-11-27, investigación de Lucas Boh
y Nastasja Görzen) publica una lista de **36 municipios creados en ~20 años**:
3 de Mayo, Arroyito, Azotey, Boquerón, Bahía Negra, Campo Aceval, Carmelo
Peralta, Cerro Corá, Doctor Raúl Peña, Filadelfia, General Bruguez, Itacuá,
Karapai, Laurel, Liberación, Loma Plata, Maracaná, María Antonia, Nueva
Asunción, Nueva Toledo, Paso Barreto, Paso Horqueta, Puerto Adela, San
Alfredo, San Carlos del Apa, San José del Rosario, San Vicente Pancholo,
Sargento José Félix López, Tavapy, Tebicuary, Tembiaporã, Teniente Esteban
Martínez, Teniente Irala Fernández, Yby Pytã, Ybyrarobana, Zanja Pytã — de la
cual varios preceden a 2012 (p. ej. Zanja Pytã, 2011) y no explican la
diferencia. **No inventamos la lista faltante.**

## 4. Carácter de los límites: qué son y qué no son

| Tipo de límite | Existe en Paraguay así | Fuente | ¿Lo usamos? |
|---|---|---|---|
| Estadístico | Construido para operativos censales/encuestas | INE, DGEEC | Sí (la capa activa ES esto) |
| Administrativo de referencia | Referencia de la DPA sin efecto legal pleno | SNC (estudio V2023) | Documentado, no integrado |
| Catastral | Parcelario | SNC | No — no es límite distrital |
| Legal pleno | Con respaldo documental suficiente | — | Ninguna capa disponible lo acredita |

**Nuestra postura**: la capa activa es **estadística, referencia de 2012**.
El propio INE califica su cartografía de "meramente referencial". El estudio
del SNC desarrolla la imprecisión normativa de los límites distritales
paraguayos. Por eso **ninguna geometría de este proyecto debe citarse como
frontera legal definitiva**, y las estadísticas por distrito declaran la
versión de límites con la que fueron calculadas (`version_limites`).

## 5. Auditoría geométrica de la capa activa (ejecutada)

`hotspots geo audit` (Misión 005) sobre la capa real `9469f09`:

- Conteos: ADM0=1, ADM1=18, ADM2=247 (validados contra el inventario de la fuente).
- **0 hallazgos** en: geometrías vacías/inválidas, duplicados por
  admin_id/shape_id/nombre, unidades fuera del país, superposiciones ≥ 1 km²
  (tolerancia documentada), distritos sin departamento.
- La fuente llegó **sin geometrías inválidas** (0 reparaciones `make_valid`).
  Nota: antes de la Misión 005, el contador de reparaciones era
  estructuralmente incapaz de reportar otra cosa que 0 (contaba DESPUÉS de
  reparar); hoy el registro es antes/después con detalle por unidad y se
  persiste en el parquet.
- El enlace distrito→departamento se deriva espacialmente (la fuente no trae
  el campo padre) y queda marcado `padre_derivado=true`.

Limitaciones del chequeo: la superposición < 1 km² se considera ruido de
digitalización (sliver); la consistencia ADM1 vs ADM0 se evalúa por
diferencia simétrica de área.

## 6. Registro cartográfico versionado

`configs/geo_sources.yaml` ficha cada versión con: institución, fuente, URLs,
año representado, fechas de descarga/incorporación, licencia, SHA256 por
nivel, estado, **carácter** (estadístico/catastral/…) y limitaciones. Hoy:

- `geoboundaries-gbOpen-PRY-9469f09` — **activa**, estadística, 2012.
- `ine-revision-2025` — **no incorporada** (263 distritos; geometría sin
  descargar, autorización pendiente).
- `snc-limite-distrital-referencial` — **documentada** (estudio, no geometría).

La regla de la plataforma: **cambiar de cartografía = escribir una versión
NUEVA de `obs_geo`**, jamás sobrescribir. Las estadísticas históricas siguen
siendo reproducibles contra la versión con la que fueron calculadas.

## 7. Incorporación de la capa INE 2022 — EJECUTADA en la Misión 007

La autorización existió (el propietario ordenó obtener la cartografía INE 2022
en la Misión 007) y el procedimiento versionado de 12 pasos preparado en la
Misión 006 (`mision_006_consolidacion_cientifica/03_auditoria_cartografica.md`
§5) se ejecutó completo, adaptando un paso:

1. **Descarga**: el zip original del INE está inaccesible desde el entorno
   (DNS de `ine.gov.py` bloqueado + enlaces JS), así que se descargó la
   **redistribución oficial OCHA COD-AB** (HDX), que declara productor
   DGEEC/INE y vintage 2022-01-01: `pry_admin_boundaries.geojson.zip` (77,098,564
   bytes) y `pry_admin_boundaries.shp.zip` (72,999,245 bytes), ambos con SHA256
   en `configs/geo_sources.yaml`.
2. **Originales preservados**: `data/geo/ine2022-codab-hdx/source/`
   (pry_admin{0,1,2}.geojson, bytes exactos del zip).
3. **Ficha**: `configs/geo_sources.yaml` → `ine2022-codab-hdx` (procedencia,
   licencia CC BY-IGO, hashes, conteos, limitaciones) + la ficha
   `ine-cartografia-digital-2022` actualizada a `documentada`.
4. **Identificadores**: pcodes OCHA/INE (`adm2_pcode`, p. ej. PY0000) como
   `shape_id`; nombres oficiales con acentos; **padre explícito `adm1_name`**
   (nuevo soporte `--schema codab`: el padre ya no se deriva, se verifica).
5. **Validación de geometrías**: 0 inválidas originales (ninguna reparación);
   conteos verificados 1/18/263 contra los archivos descargados.
6. **Jerarquía**: los 263 distritos caen en un departamento (verificación
   espacial + explícita: 263/263 coinciden, 0 inconsistencias).
7. **Duplicados**: 1 par de nombres legítimos ("Bella Vista" en Amambay e
   Itapúa) → `admin_id` desambiguado por padre
   (`ADM2:BELLA-VISTA--AMAMBAY` / `ADM2:BELLA-VISTA--ITAPUA`); hallazgo de
   nombre duplicado reportado por la auditoría.
8. **Huecos/solapamientos**: auditoría limpia (0 superposiciones ≥1 km² en
   ADM1 y ADM2; diferencia simétrica ADM1 vs ADM0 bajo tolerancia).
9. **Comparación con la capa 2012**: matriz de correspondencias completa
   (`mision_007_datos_reales/datos/matriz_correspondencia_adm2.csv`): 195
   coincidencias exactas, 28 cambios de nombre, 18 correspondencias parciales
   (geometría divergente), 4 divisiones territoriales (Curuguaty, Gral. Resquín,
   Mcal. Estigarribia, Tte. Irala Fernández), 14 creaciones post-2012 (incl.
   Nueva Asunción, Ley 6731/2021) y 2 slivers degenerados de la fuente 2012
   (duplicados de San Juan del Paraná, 0.2-0.3 km²).
10. **Diff documentado**: este documento + `mision_007_datos_reales/`.
11. **Capa versionada**: `data/geo/ine2022-codab-hdx/unidades_admin.parquet`
    (manifiesto geo propio, fuente `ine_codab_hdx`); la 9469f09 NO se tocó.
12. **Reasignación + comparación**: `hotspots geo assign` con la nueva capa;
    sobre las 28 observaciones sintéticas: 0 cambios de pertenencia nacional,
    0 cambios de distrito (normalizado), 22 diferencias de grafía en nombres
    (la capa 2012 usa MAYÚSCULAS sin acentos; la INE 2022 usa grafía oficial),
    1 caso real de división visible (obs. de Mariscal Estigarribia 2012
    repartidas entre Boquerón y Mcal. José Félix Estigarribia 2022).

La capa 2012 sigue disponible para reproducibilidad (activable con
`hotspots geo activate --version geoboundaries-gbOpen-PRY-9469f09`); las
estadísticas por distrito de distintas capas NUNCA se mezclan en una misma
serie (el `admin_id` lleva la versión).

## 8. Convenciones que gobiernan la asignación territorial

- Pertenencia nacional: **polígono ADM0**, nunca el bbox de consulta.
- Borde: un punto SOBRE el límite cuenta como dentro (`covers`) — convención
  propia documentada; la fuente no define semántica de borde.
- Fuera de Paraguay no es inválido: es una observación válida de otro país
  (el rectángulo de consulta incluye vecinos por diseño).
- Puntos sin coordenadas: nunca se asignan; quedan reportados.
- La asignación es reproducible: mismo BoundarySet → mismo resultado
  (`ASSIGN_METHOD` versionado).

## 9. Fuentes consultadas (con fecha)

1. geoBoundaries API PRY ADM2 — geoboundaries.org (2026-11-11).
2. INE, "Estimaciones y proyecciones de la población distrital 2000-2035,
   Revisión 2025" — ine.gov.py/resumen/284 (2026-11-11).
3. INE, "Cartografía digital 2022" — ine.gov.py/microdatos/cartografia-digital-2022.php (2026-11-11).
4. SNC, "Estudio de límites distritales V2023" — catastro.gov.py (cita; PDF no descargable en esta misión).
5. ABC Color, "La creación de municipios en el Paraguay (I)" (2019-11-11).
6. La Nación, "Siete nuevos municipios elegirán por primera vez a sus autoridades" (2020-12-20).
7. Última Hora, "Se crearon dos nuevos municipios" (2020-06-22).
8. RCC Chaco, "Es ley: creación del municipio Boquerón" (2021-01-15).
9. ABC Color, "'Nueva Asunción', otro distrito creado a mansalva" (2021-04-22);
   Ley 6731 en silpy.congreso.gov.py.
10. Última Hora, "Creación de nuevos municipios benefició al crimen organizado"
    (2025-11-27) — lista de 36 municipios, fuente secundaria.
