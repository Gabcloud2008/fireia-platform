# Armonización MODIS–VIIRS: decisiones y su fundamento

Este documento explica por qué los pares candidatos y los eventos se construyen como se construyen, de dónde salen los umbrales y qué NO están afirmando. Lo revisamos cada vez que tocamos un parámetro.

## 1. Qué instrumentos estamos comparando (y su estado real, nov-2026)

| Instrumento | Plataformas | Resolución del píxel de fuego | Hora local de paso (día/noche) | Estado verificado |
|---|---|---|---|---|
| MODIS | Terra, Aqua | ~1 km en nadir (crece con el ángulo de escaneo hasta ~2×5 km) | Terra ~10:30/22:30 (deriva a horas más tempranas desde 2022); Aqua ~13:30/01:30 (deriva: superó 13:45 en feb-2023 y sigue corriendo) | Operativos, pero NASA anunció el comienzo del cese de operaciones de ambas plataformas para fines de 2026 / principios de 2027 |
| VIIRS 375 m | S-NPP | 375 m | ~13:30 / 01:30 | **Cese del flujo activo de fuego el 2026-11-02** (anuncio oficial FIRMS/Earthdata). Histórico disponible |
| VIIRS 375 m | NOAA-20, NOAA-21 | 375 m | ~13:30 / 01:30 (mismo plano orbital que S-NPP, ~50 min de desfase entre satélites) | Operativos; NOAA-21 (antes JPSS-2) con productos V2 de fuego desde mar-2026 |

Fuentes: NASA Earthdata, "Transitioning from Suomi NPP VIIRS & OMPS: What FIRMS Users Need to Know" (https://www.earthdata.nasa.gov/news/blog/transitioning-from-suomi-npp-viirs-omps-what-firms-users-need-know); alerta "Transition from MODIS to VIIRS" (https://www.earthdata.nasa.gov/data/alerts-outages/transition-from-modis-viirs); MODIS Land Team, notas de deriva orbital de Terra/Aqua (https://modis-land.gsfc.nasa.gov/news.html); alerta de productos V2 de NOAA-21 (https://www.earthdata.nasa.gov/data/alerts-outages/additional-viirs-version-2-thermal-anomaly-active-fire-data-products-released).

**Consecuencia para el proyecto**: la ventana MODIS se está cerrando. El piloto usa MODIS_NRT (Terra+Aqua) + VIIRS_NOAA20_NRT + VIIRS_NOAA21_NRT porque es la última oportunidad de armonizar en vivo ambos sensores; después de 2027 la armonización MODIS–VIIRS pasa a ser un ejercicio histórico (que sigue siendo válido para 24+ años de registro).

**Consecuencia para los umbrales**: la deriva orbital de Aqua (~13:45+ hora local y avanzando) separa sus pasos de los de la constelación 13:30. Un par Aqua-MODIS ↔ VIIRS de la misma tarde puede quedar a más de 600 s por este motivo, no porque sea otro fuego. Por eso el análisis de sensibilidad (§4) importa: el umbral por defecto no es dogma.

## 2. Por qué "candidato" y no "duplicado"

Dos detecciones cercanas de dos productos distintos **no son la misma detección**: son dos mediciones independientes de algo que quizás sea el mismo fenómeno. La arquitectura lo respeta:

- `obs_id` incluye el producto: MODIS y VIIRS nunca colisionan en identidad.
- La vista `candidate_matches` produce PAREJAS (relación), preservando ambos `obs_id`.
- Los eventos agrupan pares en componentes conexas y conservan la membresía N:M.
- Ninguna observación se borra, fusiona ni reescribe en el proceso.

Un par candidato dice: "estas dos detecciones están a Δt ≤ umbral y Δd ≤ umbral". No dice: "es el mismo fuego". Para eso haría falta geometría de píxel por ángulo de escaneo, máscaras de nube por escena y validación con área quemada — todo trabajo futuro documentado, no asumido.

## 3. De dónde salen los umbrales por defecto (600 s / 2000 m)

No los heredamos de ninguna spec de NASA: son **convención del proyecto**, elegidas con esta lógica:

- **600 s (10 min)**: los pasos satelitales de la constelación de la tarde (Aqua, S-NPP, NOAA-20, NOAA-21) ocurren en la misma franja horaria local (~13:30), desfasados por minutos a decenas de minutos. Una co-detección genuina del mismo frente de fuego en la misma pasada tiene Δt de segundos a pocos minutos. 600 s captura eso con margen, sin abrir la ventana a fuegos distintos que arden simultáneamente a cientos de metros (que un umbral de horas sí conflationaría).
- **2000 m**: MODIS resuelve ~1 km en nadir y su píxel crece con el ángulo de escaneo (en Paraguay, con pasadas no siempre en nadir, 1.5–2 km de huella es normal). VIIRS resuelve 375 m. La co-registración de un mismo frente de fuego entre un sensor de 1 km y uno de 375 m puede fácilmente diferir en 1–2 píxeles MODIS. 2000 m ≈ 2 píxeles MODIS.

Ambos números son **hipótesis de trabajo verificables**, y el chequeo es parte de la herramienta:

```bash
hotspots match-sensitivity            # tabla dt × distancia sobre el almacén actual
hotspots events build --dt-seconds 900 --distance-m 3000   # reconstruir con otros valores
```

Si el conteo de pares o eventos se multiplica al mover un umbral al valor vecino del grid, los resultados de ese análisis son sensibles al parámetro y hay que decirlo en cualquier conclusión que lo use.

## 4. Análisis de sensibilidad: cómo se hace y cómo se lee

`hotspots match-sensitivity` recalcula los pares entre productos en cada celda del grid `dt ∈ {300, 600, 900, 1800} s × distancia ∈ {500, 1000, 2000, 3750} m` sobre las observaciones YA almacenadas (offline, sin red). 3750 m está a propósito: ~1 píxel MODIS al borde de escaneo + margen.

Lectura honesta de la tabla:

- Estabilidad entre celdas vecinas → el agrupamiento es robusto en esa zona del espacio de parámetros.
- Salto brusco (×2 o más) → hay pares cuya pertenencia a un evento depende del umbral: cualquier estadística construida sobre ellos debe reportar el rango, no un número único.
- Con datos reales del piloto, la tabla se guarda en el informe de la corrida (Misión 004: `mision_004_plataforma/`).

## 5. Qué NO afirma un evento

- No es un incendio confirmado: es un grupo de detecciones satelitales coherentes entre sí.
- No tiene perímetro ni área quemada: `dispersion_metros` es la distancia máxima del centroide a una detección miembro — dispersión de puntos, no tamaño de fuego.
- No reemplaza productos de área quemada (MCD64A1, Fire_cci): son fuentes independientes y la comparación con ellos es un experimento futuro, no una afirmación.
- `frp_total` es la suma de las FRP de las detecciones miembro, NO el FRP "real" del fuego (la misma llama medida por dos sensores no se suma).

## 6. Diferencias instrumentales que conservamos a propósito

| Aspecto | MODIS | VIIRS 375 m | Qué conservamos |
|---|---|---|---|
| Resolución | 1 km (nadir) | 375 m | La resolución no se "corrige": un MODIS píxel puede contener varios focos VIIRS |
| Confianza | 0–100 (entero, `confidence`) | l/n/h (categórica) | Valor original siempre; `confidence_band` es derivada y documentada como convención |
| Bandas de brillo | `brightness` (21 µm), `bright_t31` (3.9/11 µm MOD) | `bright_ti4` (3.74 µm I4), `bright_ti5` (11 µm I5) | Columnas separadas por familia; nunca se mezclan |
| FRP | MW (MOD14) | MW (VNP14IMG) | Escala físicamente comparable pero con sesgos de sensibilidad distintos; no se ajusta |
| Satélite | T (Terra), A (Aqua) | N (S-NPP), 1 (NOAA-20), 2 (NOAA-21) | Código original + nombre mapeado; códigos desconocidos pasan con flag |

La comparación MODIS–VIIRS es interesante **por** estas diferencias: VIIRS 375 m detecta fuegos más pequeños y débiles que MODIS 1 km; MODIS aporta continuidad histórica de dos décadas. Armonizar no es borrar la diferencia: es poder decir "esto lo vieron los dos" y "esto solo lo vio el que más resuelve" con evidencia.
