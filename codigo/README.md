
# Paraguay Fire Intelligence — Harmonization of MODIS and VIIRS Hot Spots

Dataset del proyecto **Harmonization of MODIS and VIIRS Hot Spots**
(NASA Space Apps Challenge 2026, Desafío 1.9). Caso de estudio: **República del
Paraguay, territorio nacional completo** (los 17 departamentos más Asunción;
capa activa: **cartografía INE 2022 vía OCHA COD-AB con 263 distritos**
incorporada y verificada en la Misión 007; la capa 2012 gbOpen con 247 queda
como histórica versionada y la matriz de correspondencias 247↔263 está
documentada en `mision_007_datos_reales/datos/`) — no solo el Gran Chaco, que
es región de interés pero no el límite del estudio.

## Qué contiene este repositorio

- **`codigo/`** — la plataforma completa (Python 3.10+): pipeline de ingesta de
  focos de calor MODIS/VIIRS vía NASA FIRMS con RAW inmutable content-addressed,
  QC de 10 estados, GeoParquet + DuckDB, capa geográfica nacional oficial
  (polígono ADM0 + departamentos + distritos, versionados con manifiesto),
  eventos de co-detección entre sensores, análisis de anomalías con split
  temporal, API REST y dashboard. **242 pruebas automatizadas offline**
  (183 heredadas + 14 de contexto ambiental + 7 del esquema COD-AB/INE 2022 +
  14 de la Misión 008 + 3 de la Misión 009: contrato de manifiestos fallidos
  con error explícito en el manifiesto, sin artefacto RAW vacío fabricado y
  período de adquisición solicitado completo; + 4 de la Misión 010:
  orquestador del piloto con consultas independientes y registro por intento;
  + 15 y 2 de la Misión 011: lógica del preflight — saldo ≠ límite, rechazo de
  claves expuestas por huella, ventana por producto — y bloqueo del piloto
  sin GO del preflight).
- **`codigo/mvp_frontend/`** — MVP web del dashboard como **proyecto Next.js
  completo y ejecutable** (package.json + configs + src/ autocontenido;
  verificado install→build→serve desde cero): consume el almacén vía export
  JSON, con banner de datos sintéticos y origen declarado en cada respuesta;
  incluye su exportador portátil desde el DuckDB. Cartografía real INE 2022
  (CC BY-IGO) y filtros por fecha/sensor/satélite/departamento verificados.
- **`codigo/data/geo/`** — límites administrativos versionados: **INE 2022 vía
  OCHA COD-AB (capa activa, 263 distritos, CC BY-IGO, productor DGEEC/INE)**
  y geoBoundaries gbOpen PRY 2012 (capa histórica, CC BY 4.0), ambos con
  SHA256 y manifiesto de procedencia.
- **`mision_001_fase0/`** — investigación y diseño de la Fase 0 (12 documentos).
- **`mision_002_fase1a/`** — entrega de la Fase 1A.
- **`mision_002_fase1a_correctiva/`** — auditoría correctiva y endurecimiento.
- **`mision_003_preparacion_nacional/`** — preparación geoespacial nacional
  (auditoría, fuentes de límites, diseño, piloto planificado).
- **`mision_004_plataforma/`** — plataforma nacional: auditoría, implementación
  geográfica real, eventos, IA honesta, API/dashboard, seguridad, MVP frontend
  y sincronización verificada.
- **`mision_005_integridad/`** — integridad territorial y validación
  científica: cuatro defectos corregidos (conteo de geometrías inválidas,
  bbox de consulta vs pertenencia nacional, scope de estadísticas,
  encadenamiento cuantificado), motor de eventos ~20× más rápido medido,
  registro cartográfico versionado y auditoría con fuentes oficiales.
- **`mision_006_consolidacion_cientifica/`** — consolidación científica:
  auditoría reproducida (197 pruebas), escenario satelital post-S-NPP
  verificado (S-NPP terminó 2-nov-2026; Terra/Aqua 2027), cartografía INE
  2022 fichada con procedimiento de incorporación, arquitectura de contexto
  ambiental implementada (módulo + registro + pruebas), alternativas del
  motor de eventos evaluadas con números (exp_003) y MVP convertido en
  proyecto ejecutable verificado de punta a punta.
- **`mision_008_corrective/`** — corrección estructural (Etapa 1): causa
  raíz de la clasificación de procedencia corregida (fixtures jamás se
  etiquetan como API real), registro cartográfico con UNA capa activa,
  verificador del piloto reescrito con alcance estricto al universo del
  piloto (clasificación real/fixture en cada reporte) y 10 pruebas de
  exclusión de datos ajenos, lock verificado en instalación limpia
  (218 pruebas), piloto portable (Linux/WSL), matriz técnica de productos
  MODIS/VIIRS y diseños científicos (armonización v2, memoria histórica,
  ambiental, protocolo experimental FIREIA, evolución del MVP).
- **`mision_009_primera_base_real/`** — Misión 009: auditoría independiente
  de la Misión 008 (218→221 pruebas reproducidas, instalación limpia
  verificada, espejo HF dual confirmado por blobs), intento real del piloto
  registrado con el contrato de manifiestos fallidos v2 (error de transporte
  DENTRO del manifiesto, sin artefacto RAW vacío, período solicitado
  completo), bloqueo FIRMS reconfirmado (dominio modaps entero inalcanzable
  desde el entorno), eliminación de cachés de ambos repos HF, MVP con modo
  de procedencia explícito derivado de source_kind (banner + /api/health +
  API FastAPI) y actualización de Asana preparada (sin credenciales).
- **`mision_010_desbloqueo_piloto/`** — Misión 010: entorno de trabajo
  recuperado íntegro desde el espejo HF (estado canónico M009, árboles byte
  a byte idénticos); MAP_KEY regenerada por el propietario y **validada
  contra el endpoint oficial de disponibilidad**; ventana 2026-11-04..10
  **confirmada disponible en NRT** para MODIS_NRT, VIIRS_NOAA20_NRT y
  VIIRS_NOAA21_NRT (S-NPP cesó 2026-11-02); documentación oficial del Area
  API re-verificada (DAY_RANGE 1..5, date = inicio del rango, cuota
  5000 trans./10 min); **orquestador del piloto robustecido** — consultas
  independientes (un fallo ya no cancela las restantes), reintentos acotados
  con espera progresiva, registro JSONL por intento y resumen por ejecución
  con run_id; intento real desde el entorno bloqueado registrado 6/6 con
  manifiesto por consulta; reporte engañoso de M007 eliminado de la raíz de
  ambos repos; **runbook de ejecución externa de un solo comando**.
- **`mision_007_datos_reales/`** — datos reales e integración cartográfica:
  MAP_KEY de FIRMS **validada con consulta real** (540 detecciones MODIS el
  2026-11-10, versión 6.1NRT); token Earthdata probado (inválido según CMR,
  no requerido para FIRMS); **cartografía INE 2022 real descargada, validada
  (263 distritos verificados) e incorporada como capa activa** con auditoría
  geométrica limpia; **matriz de correspondencias 247↔263** completa (195
  exactas, 28 renombres, 18 parciales, 4 divisiones, 14 creaciones post-2012,
  2 slivers de la fuente 2012); piloto FIRMS de 7 días **listo para ejecutar**
  (script + verificador probado; descarga bloqueada SOLO por la salida de red
  del entorno de desarrollo, documentada con evidencia); dependencias
  coherentizadas (pytest 9.2.0 + httpx) y 218 pruebas.

## Qué NO contiene (importante)

**No contiene observaciones satelitales reales todavía.** El almacén demo se
carga con fixtures sintéticos claramente identificados como tales (la API y el
dashboard muestran el origen de los datos en cada respuesta y en pantalla). La
MAP_KEY de FIRMS fue validada con una consulta real (Misión 007) y
re-validada contra el endpoint oficial de disponibilidad tras su rotación
(Misión 010); el pipeline de ingesta está completo y la ventana del piloto
está confirmada disponible en NRT para los 3 productos, pero la descarga
masiva del piloto de 7 días quedó bloqueada
por la política de salida de red del entorno de desarrollo (diagnóstico
reproducible en `mision_010_desbloqueo_piloto/02_diagnostico_conectividad.md`);
el runbook `mision_010_desbloqueo_piloto/04_procedimiento_ejecucion_externa.md`
ejecuta el piloto real con un comando en cualquier entorno con acceso a FIRMS.
Declarar otra cosa sería mentir sobre el estado del proyecto.

Un punto caliente satelital no equivale a un incendio confirmado; un evento
reconstruido agrupa detecciones, no certifica fuego. El sistema preserva esa
distinción en cada capa.

## Uso rápido

```bash
pip install -e "codigo[dev,api]"
cd codigo
hotspots test                                  # 225 pruebas offline
hotspots ingest --fixture tests/fixtures/synthetic_modis_nrt.csv --product MODIS_NRT
hotspots geo build --version ine2022-codab-hdx --schema codab --expected-adm2 263 \
    --adm0 data/geo/ine2022-codab-hdx/source/pry_admin0.geojson \
    --adm1 data/geo/ine2022-codab-hdx/source/pry_admin1.geojson \
    --adm2 data/geo/ine2022-codab-hdx/source/pry_admin2.geojson
hotspots geo assign && hotspots events build
hotspots serve                                 # API + dashboard
```

## Licencias por componente

| Componente | Licencia | Fuente |
|---|---|---|
| Código de la plataforma | MIT | este repo |
| Límites INE 2022 (capa activa, 263 distritos) | CC BY-IGO | OCHA COD-AB v01 (productor: DGEEC/INE Paraguay) — citar: INE Paraguay y OCHA FISS, HDX |
| Límites 2012 (capa histórica, 247 distritos) | CC BY 4.0 | geoBoundaries gbOpen (geometría DGEEC, Paraguay) — citar: geoBoundaries, William & Mary geoLab |
| Documentos de misión | CC BY 4.0 | este repo |
| Datos FIRMS (cuando se ingieran) | NASA open data | NASA FIRMS / LANCE |

## Cita

Proyecto Paraguay Fire Intelligence — NASA Space Apps Challenge 2026, Desafío
1.9. Límites administrativos: INE Paraguay / DGEEC vía OCHA COD-AB (CC BY-IGO,
capa activa 2022, 263 distritos) y geoBoundaries (William & Mary geoLab),
gbOpen PRY 2012 (CC BY 4.0, capa histórica).
