# Registro de cambios

## [0.3.0] — Misión 011: preflight obligatorio, saldo FIRMS y preparación de la ejecución real (2026-11-12)

### Agregado

- **Preflight del piloto (M011)**: nuevo
  `mision_011_ejecucion_real/herramientas/preflight_firms.sh` +
  `preflight_decision.py`. Antes de descargar NADA verifica, en orden:
  huella pública de la MAP_KEY vs registro de claves expuestas en
  conversaciones (rechazo por `sha256[:16]`, código 3) → conectividad HTTPS
  directa a FIRMS (código 2) → saldo de transacciones disponible vía
  `mapserver/mapkey_status/?MAP_KEY=...` (endpoint oficial de la Fire Data
  Academy; el saldo disponible = transaction_limit − current_transactions,
  NO confundido con el límite documentado de 5000/10 min; código 4 si el
  saldo < 6 consultas, con la vía documentada y gratuita para obtener
  cuota: reinicio automático de la ventana o aumento de límite vía FIRMS) →
  disponibilidad NRT de la ventana 2026-11-04..10 por producto
  (código 5 si algún producto no la cubre; la ventana NO se sustituye en
  silencio).
- **Orquestador integrado al preflight** (`piloto_firms_7dias.sh`): el
  preflight corre ANTES de las 6 consultas; sin GO no se lanza ninguna
  consulta y el código del bloqueo se propaga. La evidencia de
  disponibilidad se captura UNA sola vez antes de descargar (se eliminó el
  `data_availability` redundante post-ejecución).
- **17 pruebas offline nuevas** (242 total): 15 de lógica del preflight
  (formato documentado del endpoint, variantes, saldo suficiente/insuficiente,
  umbral exacto de 6, huellas expuestas, ventana por producto, CSV
  malformado, sintaxis bash, contrato orquestador↔preflight) + 2 del
  orquestador (sin GO ⇒ ninguna consulta lanzada; GO ⇒ evidencia en el run).
- **Documentación M011**: runbook del propietario WSL/Linux
  (`02_runbook_wsl_linux.md`), estado documentado de las 6 consultas
  (`03_estado_consultas_piloto.json`), texto de Asana preparado
  (`04_asana_texto.md`), README de la misión, informe final.

### Corregido

- `.env.example`: regla de seguridad actualizada — la MAP_KEY de M010 está
  expuesta y quemada (huella `92e0e8c1984aa80d`); la clave nueva vive solo
  en `.env` local (600), jamás en chat.
- Cosmético de evidencia: los códigos HTTP de las sondas del preflight ya
  no se duplican (000000 → 000).

### Estado de la adquisición real

- Sin cambios respecto a M010 en lo esencial: el entorno de trabajo sigue
  SIN salida TCP a `firms.modaps.eosdis.nasa.gov` (4ª misión consecutiva,
  evidencia timestamped del preflight) y la MAP_KEY disponible está
  expuesta (no reutilizable por regla M011). Las 6 consultas quedan
  PENDIENTES_EJECUCION_EXTERNA con estado documentado por consulta; el
  runbook las hace ejecutables con 2 comandos en WSL/Linux del propietario.
- Ningún dato simulado presentado como real; ningún RAW vacío creado;
  ningún falso éxito. La Misión 011 NO se declara completada.

## [0.2.0] — Misión 010: desbloqueo de la adquisición real y robustez del piloto (2026-11-12)

### Corregido

- **Independencia por consulta en el piloto (§9.4 del encargo)**: el
  orquestador (`mision_007_datos_reales/herramientas/piloto_firms_7dias.sh`)
  ya NO aborta en el primer fallo (`set -e` removido; manejo explícito de
  errores) — las 6 consultas se intentan SIEMPRE. Reintentos de script con
  espera progresiva (`REINTENTOS_CONSULTA`, `ESPERA_BASE_REINTENTO`) sobre
  los reintentos de transporte con backoff exponencial (M004).
- **Registro de ejecución por intento**: nuevo
  `herramientas/registrar_ejecucion.py` + `ejecuciones/<run_id>/` con
  `consultas.jsonl` (1 línea por intento: producto, período, exit_code,
  estado_ingest, manifest_id, raw_sha256, error truncado, ts UTC) y
  `resumen_ejecucion.json` (estado final por consulta + totales). 4 pruebas
  offline nuevas (225 total).
- **Higiene de evidencia**: `data_availability` solo persiste CSV válido
  (encabezado `data_id`); stdout/stderr de cada intento se persisten con la
  MAP_KEY redactada a `{MAP_KEY}`; precedencia de credenciales
  `entorno > .env`.
- **Recuperación del entorno**: el sandbox se recicló y el git local quedó
  en M005 (`6b35d43`); el estado canónico M009 (`765264f`) se restauró desde
  el espejo HF (árboles byte a byte idénticos en ambos repos) preservando el
  estado antiguo en `backup/m005-estado-local`. El layout de trabajo volvió
  a raíz (codigo/ es solo el espejo).
- **Reportes sustituidos eliminados del árbol de trabajo**:
  `mision_007_datos_reales/datos/reporte_piloto.json` (engañoso, M007 —
  la fidelización M009 solo lo había quitado del espejo `codigo/`, seguía en
  la RAÍZ de ambos repos HF; se elimina también de la raíz en la sync M010)
  y `reporte_piloto_LOGICA_VERIFICADA_con_fixtures.json` (honesto pero
  sustituido; permanece en el historial). Ambos siguen accesibles en el
  historial git/HF.

### Nuevo

- **Credencial**: MAP_KEY regenerada por el propietario instalada en `.env`
  (600, gitignored) y **validada contra el endpoint oficial de
  disponibilidad** (devolvió el CSV real de productos). Huella pública:
  `sha256[:16] = 92e0e8c1984aa80d`. El valor nunca se imprime ni persiste.
- **Disponibilidad NRT con evidencia real** (canal auxiliar documental):
  MODIS_NRT, VIIRS_NOAA20_NRT y VIIRS_NOAA21_NRT cubren la ventana
  2026-11-04..10; VIIRS_SNPP_NRT terminó 2026-11-02 (exclusión confirmada).
  Documentación oficial del Area API re-verificada: `DAY_RANGE 1..5`
  (split 5+2 obligatorio), `date` = inicio del rango, cuota documentada
  5000 trans./10 min.
- **`mision_010_desbloqueo_piloto/`**: informe final (formato A–I),
  diagnóstico de conectividad reproducible, evidencia de disponibilidad,
  runbook de ejecución externa (un comando en entorno autorizado) y estado
  HF/Asana con texto preparado.

### Verificación

- 225 passed (venv nuevo, instalación limpia `.[api,dev]`), ruff limpio.
- **Punteros LFS detectados y corregidos**: el clon git sin `git-lfs` dejó
  28 artefactos >10 MB (duckdb, parquet, geojson) como punteros — se
  descargó el contenido real del espejo canónico vía `resolve` verificando
  SHA256 contra el `oid sha256` de cada puntero (28/28 OK). Tras la
  reparación: `hotspots verify` = 15 manifiestos / 37 artefactos, **todos
  los SHA256 OK** (3 SUPERSEDED históricos documentados, no inconsistencia).
  El `duckdb` inválido que frenó el primer intento era el puntero, no datos.
- Intento real del piloto desde el entorno bloqueado: **6/6 consultas
  intentadas de forma independiente** (24 intentos TCP con backoff del
  transporte), todas `download_failed` con manifiesto v2 por consulta
  (URL redactada, `error=ConnectionError`, `intentos=x4`, período completo,
  sin RAW vacío). Verificador: 6/6 manifiestos del piloto no exitosos →
  exit 3, clasificación `vacio`. Escaneo de fuga de MAP_KEY en evidencias:
  0 coincidencias.

## Misión 005 — Integridad territorial, validación científica y fortalecimiento (2026-11-11)

### Correcciones

- **`geo/boundaries.py`** — El conteo de geometrías reparadas por `make_valid`
  se registraba DESPUÉS de repararlas (siempre 0, bug estructural). Ahora se
  cuenta ANTES, con detalle por unidad (nivel, nombre, motivo de invalidez
  original), se expone `geometrias_invalidas_originales` y se PERSISTE en el
  parquet (`hotspots_geo_audit`) — antes el meta se perdía en el roundtrip.
- **`api/app.py` `/api/statistics`** — `by=product|satellite` contaba TODAS
  las observaciones del almacén (incluidas detecciones de Argentina, Brasil y
  Bolivia dentro del rectángulo de consulta) mientras `by=departamento`
  filtraba `dentro_pais`: criterios incompatibles en una misma pantalla. Ahora
  el scope es parámetro explícito (`nacional|area_consulta`, default nacional)
  y viaja en cada respuesta con su criterio por escrito.
- **`analysis/anomaly.py`** — Con MAD=0 y valor distinto de la mediana, el
  detector emitía `z=±Infinity` (JSON inválido con `allow_nan=false`),
  contradiciendo su propia documentación. Ahora: anomalía con `z=null` +
  `motivo="dispersion_cero"` + serialización estricta probada.
- **`config.py` + `configs/sources.yaml`** — `area.paraguay_bbox` confundía
  el rectángulo de CONSULTA con el territorio. Ahora: `firms_query.bbox`
  (consulta) + alias deprecado con warning + documentación de que la
  pertenencia nacional la decide solo el polígono ADM0. El manifiesto de
  ingesta registra el bbox con su rol explícito.

### Nuevas capacidades

- **`analysis/calendar.py`** — Calendario de cobertura: distingue
  `con_detecciones` / `cero_detecciones_asumido` (cero real dentro del
  intervalo cubierto) / `solo_rechazadas_qc` / `sin_datos`. Un día sin
  observaciones ya NO se interpreta automáticamente como día sin fuego.
  Integrado a `/api/anomalies` (serie comparable: ceros adentro, huecos
  afuera, supuestos en la respuesta) y al endpoint nuevo `/api/coverage`.
- **`events/engine.py` v2** — Diagnósticos de encadenamiento transitivo por
  evento: `diametro_metros` (máxima distancia entre miembros),
  `alerta_encadenamiento` (diámetro > 2×distancia o duración > 2×ventana) y
  `frp_por_producto` (desglose que no miente: `frp_total` NO es potencia
  física del fuego). El agrupamiento NO cambió; los umbrales siguen siendo
  convención del proyecto.
- **`geo/boundaries.py` `audit()`** — Auditoría geométrica completa (vacías,
  inválidas residuales, duplicados por admin_id/shape_id/nombre, unidades
  fuera del país, superposiciones con tolerancia, consistencia ADM1 vs ADM0,
  distritos sin padre). Expuesta como `hotspots geo audit`. Sobre la capa
  real: 0 hallazgos.
- **`geo/registry.py` + `configs/geo_sources.yaml`** — Registro cartográfico
  versionado con procedencia completa y CARÁCTER de los límites
  (estadístico/referencial/catastral). Fichadas: capa activa 2012 (247),
  INE Revisión 2025 (263, no incorporada), estudio SNC (documentada).
- **`cli verify`** — Manifiestos SUPERSEDED: un artefacto regenerado y
  re-registrado por un manifiesto más nuevo se reporta como evidencia
  histórica, no como inconsistencia (con normalización de rutas
  relativas/absolutas entre manifiestos viejos y nuevos).
- **`/api/health`** — Reporta `observaciones` (área de consulta) y
  `observaciones_nacionales` (dentro_pais) con etiquetas de scope.

### Rendimiento (medido, bench_001)

- `build_events`: timestamps pre-parseados una vez por observación (antes:
  `strptime` dentro del bucle interno, O(n·k) parses). Caso 8 000 obs/1 día:
  **24,24 s → 1,23 s (~20×)**, mismos pares exactos (verificado por suite y
  por el propio benchmark).

### Documentación

- `docs/cartografia.md` (nuevo): auditoría territorial completa —
  discrepancia 247 vs 263 con fuentes verificadas, 9 distritos nuevos
  documentados con fecha/ley, carácter de los límites, procedimiento de
  incorporación INE 2025 pendiente de autorización.
- `docs/sensores.md` (nuevo): estado operativo verificado nov-2026 (S-NPP
  cesado 2026-11-02 15:40 UTC; Terra/Aqua con cierre proyectado feb/sep
  2027), semántica de confianza MODIS (0-100) vs VIIRS (l/n/h) y regla de no
  conversión.
- `LICENSE` (nuevo, MIT) — pyproject lo declaraba pero el archivo no existía.
- Actualizados: README, architecture (módulos nuevos), harmonization,
  data_dictionary (columnas nuevas de eventos/obs_geo).

### Pruebas

- Suite: **158 → 183** (+25: territoriales, MAD=0, serialización estricta,
  cadena transitiva, FRP por producto, calendario de cobertura, registro
  cartográfico, verify superseded, bbox deprecado). Ruff limpio.

## Misión 004 (2026-11-11)

Ver `mision_004_plataforma/`. Geografía nacional real, eventos v1, IA honesta,
API+dashboard, 158 pruebas.

## Misión 003 (2026-11-11)

Ver `mision_003_preparacion_nacional/`. Preparación geográfica y auditoría de
Fase 1B.

## Misión 002 (2026-11-10)

Auditoría correctiva y endurecimiento de Fase 1A.

## Fase 1A (2026-11-10)

Pipeline de ingesta MODIS/VIIRS offline: RAW inmutable, QC, GeoParquet+DuckDB,
manifiestos SHA256, CLI, 78 pruebas.

## [0.1.9] — Misión 009: primera base real (preparación verificada) (2026-11-12)

### Corregido

- **Contrato de manifiestos fallidos** (`ingestion/pipeline.py`): la evidencia
  del fallo vive AHORA en el manifiesto — `error=<tipo>` (antes solo quedaba
  en el log de sesión; el informe M008 citaba `ConnectionError` que el JSON
  histórico no conservaba), `intentos=<resumen>` y `raw=no_hubo_cuerpo…`.
  Un fallo de transporte (sin respuesta) ya NO fabrica un artefacto RAW de
  tamaño cero: el manifiesto lo declara explícito. El manifiesto histórico
  `26184c5d80235689` NO se alteró (procedencia histórica preservada).
- **Período de adquisición solicitado**: `acquisition_period` registra
  `from=date` → `to=date+day_range-1` (antes solo el día inicial) y una nota
  de ventana relativa cuando no hay fecha explícita. 3 pruebas nuevas (221
  total).
- **Cachés publicadas**: 12 ficheros de `.pytest_cache/.ruff_cache` que la
  sincronización M008 subió a AMBOS repos HF fueron eliminados (commits
  HF `0b90a7d2` y `c4e64ba9`, verificación 0 restantes).
- **Permisos de secretos**: `.env` y ficheros de token del workspace a 600.

### Nuevo

- **MVP con procedencia explícita (§11)**: `exportar_mvp.py` deriva
  `modo_datos` (sintetico/real/mixto) del `source_kind` de cada fila — nunca
  de una constante; banner de la UI con 5 presentaciones por modo + período
  mostrado + clasificación + limitaciones; `/api/health` (Next.js y FastAPI)
  reporta modo, clasificación, cobertura temporal, ventana del piloto
  objetivo y estado de validación.
- **`mision_009_primera_base_real/`**: informe final A-L, estado del piloto
  con bloqueo documentado (intento real `45a6a571c314c99f`, exit 1), análisis
  científico preparado (no ejecutable sin datos), estado HF/Asana y
  evidencias versionadas (manifiestos, log sanitizado, reporte del piloto,
  auditoría HF).

### Verificación

- 221 passed (local + venv limpio), ruff limpio, `hotspots verify`
  14 manifiestos / 37 artefactos SHA256 OK, build producción MVP + smoke
  9/9 rutas, instalación limpia 14/14 = lock exacto, escaneo de fuga de
  MAP_KEY: 0 coincidencias en árbol/historial (22 commits)/logs.

## [0.1.8] — Misión 008: corrección estructural y consolidación (2026-11-11)

### Corregido (bloque crítico de la Misión 007)

- **Procedencia de observaciones (causa raíz de 4.4)**: el pipeline
  `--fixture` etiquetaba las observaciones como `source_kind='firms_api'`
  (default del config). Ahora `parse_firms_csv` recibe el source_kind del
  MODO de corrida: fixture→'fixture', firms_api→'firms_api'. Almacén demo
  regenerado con etiquetas honestas. Pruebas: propagación + clasificación.
- **Registro cartográfico (4.1)**: geoBoundaries 2012 pasa a `estado:
  historica` (coherente con active_version.txt → ine2022-codab-hdx);
  `estado_nota` en ambas capas; test actualizado al contrato de UNA capa
  activa + verificación de coherencia con el runtime.
- **requirements.lock (4.2)**: comentario de cabecera desactualizado
  (197→218); instalación limpia verificada en venv nuevo (pip check OK;
  13/13 versiones del lock = instalación de pyproject; suite 218 passed).
- **Verificador del piloto (4.3)**: reescrito con alcance estricto al
  universo del piloto — ventanas acotadas (BETWEEN), emparejamiento de
  manifiestos por request_key EXACTO (split 5+2), manifiestos
  faltantes/incompletos/incompatibles, correspondencia RAW↔procesado
  (SHA256+tamaño+conteos), duplicados con la fórmula corregida
  (sum(rows_valid)−obs distintas; antes conflareaba rows_raw con cuarentena),
  territorial/eventos/cuarentena restringidos al piloto, clasificación de
  procedencia (real/fixture/synthetic/unknown/vacio) en el JSON y en el
  nombre del archivo, código de salida 3 cuando la procedencia no es
  demostrable. 10 pruebas nuevas incluidas registros ajenos al período y
  consultas incompatibles.
- **Reportes engañosos (4.4)**: eliminado reporte_piloto.json (fechas de
  fixture + procedencia mal declarada); los reportes ahora llevan la
  clasificación en el nombre y en el contenido (reporte_piloto_
  2026-11-04_vacio.json = estado real del piloto, con el manifiesto
  download_failed del intento genuino de esta sesión).
- **Portabilidad del piloto (4.5)**: script con chequeo de dependencias
  (bash/GNU date/curl/hotspots), --help, DESDE por argumento o env,
  invocación python -m fallback, códigos de salida documentados;
  probado en el entorno (falla rápido y claro sin red; evidencia
  preservada).

### Añadido

- Pruebas de casos límite de infraestructura: .tmp residual de escritura
  interrumpida (ignorado por el almacén RAW), no-rescritura write-once,
  fila truncada a mitad (respuesta parcial) → cuarentena sin crash,
  propagación de source_kind.
- Matriz técnica de productos MODIS/VIIRS con fuentes y fechas de consulta
  (mision_008_corrective/02): MOD14/MYD14 C6.1, VJ114IMG/VJ214IMG V002,
  latencias NRT (≤3 h) y SP (2-3 meses, hasta 5), disponibilidad histórica.
- Diseños científicos versionados: armonización v2 (oportunidad de
  observación), eventos + memoria histórica (protocolo de estabilidad),
  fuentes ambientales (matriz con latencia/incertidumbre), protocolo
  experimental FIREIA (etiquetas, validación temporal/geográfica,
  baselines, umbrales mínimos de datos), auditoría del MVP con plan de
  evolución, flujo del piloto mapeado a los 15 pasos.

### Verificado

- 218 pruebas passed · ruff limpio · 13 manifiestos/37 artefactos SHA256 OK
  (incluye el manifiesto download_failed del intento real) · build de
  producción del MVP · 8/8 rutas 200 · filtros por satélite/código y nombre.

## [0.1.7] — Misión 007: datos reales y cartografía INE 2022 (2026-11-11)

### Corregido (Etapa A)

- `pyproject.toml`: `pytest>=8,<9` era incompatible con `requirements.lock`
  (`pytest==9.2.0`); ahora `pytest>=8,<10` y el lock regenerado desde el
  entorno verificado (suite completa 204 passed con pytest 9.2.0).
- `httpx` añadido a dev (lo requiere `starlette.testclient`; antes faltaba y
  dos módulos de pruebas no recolectaban en un entorno limpio).
- `README.md`: cifras de pruebas desactualizadas (183/158 → 204) y referencia
  al ciclo de vida de S-NPP aclarada (cese 2026-11-02; histórico por archivo).
- `configs/geo_sources.yaml`: ficha INE 2022 completada con datos reales.
- Etiqueta `region:us` del dataset HF: verificada como tag de SISTEMA del Hub
  (presente en todos los datasets públicos probados; no está en el YAML de la
  tarjeta) — documentada como no removible por metadatos, con evidencia.

### Añadido (Etapa D — cartografía INE 2022 real)

- Soporte de esquema `codab` en `geo build` (OCHA COD-AB / INE 2022):
  campos `adm{N}_name`/`adm{N}_pcode` y **padre explícito `adm1_name`**
  verificado espacialmente (263/263 coinciden, 0 inconsistencias).
- Capa versionada `ine2022-codab-hdx` (1 país, 18 departamentos, 263
  distritos): descarga real vía HDX (GeoJSON+SHP, hashes en geo_sources.yaml),
  auditoría geométrica limpia (0 inválidas, 0 solapamientos ≥1 km², 0
  huérfanos) y activada siguiendo el procedimiento de 12 pasos.
- `admin_id` desambiguado por padre ante nombres repetidos dentro de un nivel
  (hallazgo real: dos distritos "Bella Vista", Amambay e Itapúa).
- Matriz de correspondencias 247↔263
  (`mision_007_datos_reales/datos/matriz_correspondencia_adm2.csv`): 195 exactas,
  28 cambios de nombre, 18 parciales, 4 divisiones, 14 creaciones post-2012,
  2 slivers degenerados de la fuente 2012.
- `geo audit` persiste ahora la verificación de padres en el parquet.
- `satellite_codes` extendido con nombres completos (observados en respuesta
  REAL del Area API: `satellite="Terra"` textual).

### Preparado (Etapas B/C — piloto FIRMS 7 días)

- `mision_007_datos_reales/herramientas/piloto_firms_7dias.sh` ejecuta el
  piloto completo (MODIS_NRT + VIIRS_NOAA20_NRT + VIIRS_NOAA21_NRT × split
  5+2, ventana 2026-11-04..2026-11-10 UTC) con el pipeline existente;
  `herramientas/verificar_piloto.py` verifica cobertura de días, duplicados
  técnicos y estadísticas (lógica probada contra fixtures).
- MAP_KEY validada contra la API real (540 detecciones MODIS el 2026-11-10,
  versión 6.1NRT, header exacto coincide con el fixture del contrato). La
  descarga masiva quedó BLOQUEADA por la política de salida de red del
  entorno (documentada con evidencia en 01_informe_tecnico.md §C).
