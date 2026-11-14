# FIREIA — Web (código fuente y guía de edición)

**FIREIA** es la plataforma web de inteligencia de incendios forestales de Paraguay,
construida sobre observaciones satelitales MODIS y VIIRS (NASA FIRMS). Este paquete
contiene **todo el código fuente de la web** más esta guía, preparada para que otro
equipo pueda instalarlo, entenderlo, editarlo y evolucionarlo sin depender del
equipo original.

- Proyecto madre: *Harmonization of MODIS and VIIRS Hot Spots* — NASA Space Apps Challenge 2026, Desafío 1.9, caso de estudio Paraguay.
- Repositorios oficiales (toda subida se replica en ambos): `p400-full/modis-viirs-hotspots-paraguay` (organización) y `p400/modis-viirs-hotspots-paraguay` (espejo personal).
- Este paquete vive en la carpeta `web/` de ambos repositorios; el archivo `fireia-web-codigo-<fecha>.zip` es el mismo contenido en un solo archivo.

---

## 1. Qué puede hacer la plataforma hoy

- **Resumen general** con el mapa como pieza central, métricas clave y ticker de actividad.
- **Mapa de Paraguay** (MapLibre) con focos activos, límites departamentales y distritales, controles discretos y capas MODIS/VIIRS diferenciadas por color.
- **Observaciones satelitales**: explorador de datos con rail de filtros (producto, sensor, día/noche, fechas, departamento) y detalle de cada observación en lenguaje sencillo.
- **Comparación MODIS × VIIRS**: composición de dos mitades enfrentadas (split-screen), sin resultados "reconciliados" inventados.
- **Eventos y evolución**: expedientes de co-detección (eventos donde ambos satélites observan el mismo foco) y evolución temporal.
- **Historial y calendario**: banda de cobertura diaria del almacén como pieza visual central.
- **Inteligencia ambiental**: mosaico de variables ambientales con unidad y fuente declaradas; ninguna fuente está conectada todavía y así se declara.
- **Anomalías**: narración del método (experimento 001, método rolling_median_mad_v1) y sus resultados, declarando que la serie es sintética.
- **Centro de inteligencia**: chat conversacional por reglas locales (sin IA conectada, declarado en la interfaz).
- **Laboratorio de simulaciones**: banco de pruebas con generadores sintéticos deterministas (semilla fija) y banner de reglas.
- **Riesgo y estimaciones futuras**: en desarrollo declarado; no inventa pronósticos.
- **Información y sistema**: informes, catálogo de fuentes, metodología, documentación, diagrama de pipeline de 7 pasos, calidad (con banda de cobertura), trazabilidad (bitácora de corridas), validación científica y tablero de estado.

## 2. Regla de oro: honestidad del dato

Esta regla domina todo el diseño y **debe sobrevivir a cualquier edición**:

1. Los datos del almacén son **fixtures sintéticos** de FIRMS (cero datos reales consumidos; la Fase 1B está bloqueada por compuerta). El origen viaja SIEMPRE en las respuestas de la API (`data_source` + `data_source_nota`) y se muestra en la interfaz.
2. Cuando un módulo no tiene datos reales o un modelo validado, la interfaz lo **declara** ("Sintético", "En desarrollo") con el componente `EmptyState` o badges; nunca simula contenido inexistente ni inventa puntuaciones.
3. Las simulaciones usan generadores deterministas con semilla fija, para que cualquier persona reproduzca los mismos números.
4. Nada en el frontend dispara ingestas ni llamadas a FIRMS: es **consumidor de solo lectura** de la API espejo.

## 3. Stack técnico

| Capa | Tecnología |
| --- | --- |
| Framework | Next.js 16 (App Router), React 19, TypeScript 5 (modo strict) |
| Estilos | Tailwind CSS 4 + tokens CSS propios (tema exclusivamente claro) |
| Componentes | shadcn/ui sobre Radix UI (`src/components/ui/`) |
| Iconos | lucide-react |
| Mapa | MapLibre GL JS 6 (`public/maplibre-gl-worker.mjs` es su worker) |
| Gráficos | Recharts 2 |
| Movimiento | framer-motion 12 (con respeto a `prefers-reduced-motion`) |
| Datos locales | JSON estáticos en `src/data/mvp/` leídos por `src/lib/mvp-store.ts` |

Notas del andamiaje (presentes pero **no usados por FIREIA**): Prisma/`src/lib/db.ts`
(solo un modelo User/Post de ejemplo), `zustand`, el endpoint raíz `GET /api`
("Hello, world!"). Puedes ignorarlos o retirarlos si algún día dejas de necesitarlos.

## 4. Inicio rápido

Requisitos: Node.js 20+ (o Bun 1.1+). El proyecto incluye `bun.lock`; con npm también funciona.

```bash
cd web
cp .env.example .env      # opcional: solo define DATABASE_URL (Prisma, no usado por FIREIA)
npm install               # o: bun install
npm run dev               # o: bun run dev  →  http://localhost:3000
```

Scripts disponibles (`package.json`):

| Script | Qué hace |
| --- | --- |
| `dev` | Servidor de desarrollo en el puerto 3000 (log en `dev.log`) |
| `build` | Build de producción standalone (`output: "standalone"`) |
| `start` | Sirve el build standalone con Bun |
| `lint` | ESLint sobre todo el proyecto |
| `db:push` / `db:generate` / `db:migrate` | Utilidades Prisma (no usadas por FIREIA) |

## 5. Estructura del proyecto

```
web/
├── README.md                     ← esta guía
├── fireia-web-codigo-<fecha>.zip ← todo el paquete en un archivo
├── package.json / tsconfig.json / next.config.ts / tailwind.config.ts
├── postcss.config.mjs / eslint.config.mjs / components.json / bun.lock
├── .env.example                  ← configuración documentada (el .env real NUNCA se sube)
├── public/
│   ├── fireia.svg                ← favicon / marca
│   ├── logo.svg
│   ├── maplibre-gl-worker.mjs    ← worker del mapa (no editar a mano)
│   └── robots.txt
├── prisma/schema.prisma          ← andamiaje, no usado por FIREIA
├── scripts/
│   └── exportar_mvp.py           ← puente pipeline → JSON de la web (ver §8)
└── src/
    ├── app/
    │   ├── layout.tsx            ← metadata, fuentes (Fraunces + Geist), Toaster
    │   ├── page.tsx              ← ÚNICA ruta de la SPA: monta el shell y las vistas
    │   ├── globals.css           ← tokens de diseño FIREIA (§7) y estilos base
    │   └── api/                  ← 9 rutas API espejo del pipeline (§9)
    ├── components/
    │   ├── fireia/               ← TODO el producto FIREIA (§6, §7)
    │   │   ├── app-shell.tsx     ← barra superior + menú hamburguesa + pie
    │   │   ├── nav-config.ts     ← menú, grupos, alias de vistas (§6)
    │   │   ├── hash-router.tsx / hash-link.tsx  ← navegación por hash sin recarga
    │   │   ├── data-provider.tsx / data-gate.tsx ← carga compartida + esqueleto/error
    │   │   ├── motion.tsx        ← primitivas de movimiento (respetan reduced-motion)
    │   │   ├── section-hero.tsx  ← cabeceras editoriales (2 modos con personalidad)
    │   │   ├── cobertura-band.tsx / ticker-actividad.tsx / detalle-observacion.tsx
    │   │   ├── empty-state.tsx   ← estado vacío/no disponible elegante
    │   │   ├── sim/modulos.tsx   ← módulos interactivos del laboratorio
    │   │   └── views/            ← las 20 vistas, una por sección (§6)
    │   ├── mvp/                  ← componentes del MVP original (mapa, tabs) reutilizados
    │   └── ui/                   ← shadcn/ui (primitivas Radix ya estilizadas)
    ├── data/mvp/                 ← DATOS: almacen.json, anomalias_exp001.json, departamentos.geojson
    ├── hooks/                    ← use-mobile, use-toast
    └── lib/
        ├── mvp-store.ts          ← lector con caché de los JSON de src/data/mvp
        ├── mvp-types.ts          ← tipos del almacén
        └── fireia/
            ├── disponibilidad.ts ← estados de disponibilidad por módulo
            └── services/         ← adaptadores: almacen, ambiental, conversacion, simulaciones
```

## 6. SPA, navegación y las 20 vistas

La plataforma es una **SPA de una sola ruta** (`/`). Cada sección se representa con
un hash (`#/mapa`, `#/eventos`, …) para que atrás/adelante del navegador funcione y
la app nunca se recargue. El micro-router está en `hash-router.tsx`; los enlaces
internos usan `HashLink` (ancla nativa, porque `pushState` no dispara `hashchange`).

El menú completo vive en **`src/components/fireia/nav-config.ts`**. Para añadir,
quitar, reordenar o renombrar secciones basta con editar ese archivo: el shell,
el router y los alias se actualizan solos. Las vistas antiguas de la iteración
M011 mantienen alias (`panel → inicio`, `pronosticos → riesgo`, …) para no romper
enlaces compartidos.

| Vista (hash) | Archivo en `views/` | Composición propia (v3) |
| --- | --- | --- |
| `inicio` | `inicio.tsx` | Editorial: el mapa manda, la tipografía tiene voz |
| `mapa` | `mapa.tsx` | Exploración con hero compacto y mapa protagonista |
| `observaciones` | `observaciones.tsx` | Explorador de datos: rail de filtros + tabla |
| `comparacion` | `comparacion.tsx` | Split-screen MODIS × VIIRS |
| `eventos` | `eventos.tsx` | Expedientes de co-detección + evolución |
| `historial` | `historial.tsx` | Banda de cobertura como pieza visual central |
| `ambiental` | `ambiental.tsx` | Mosaico de variables con unidad y fuente |
| `anomalias` | `anomalias.tsx` | Método narrado como cadena → resultado |
| `inteligencia` | `inteligencia.tsx` | Conversación primero (chat por reglas) |
| `simulaciones` | `simulaciones.tsx` | Banco de pruebas + banner-reglas (badge "Sintético") |
| `riesgo` | `riesgo.tsx` | En desarrollo declarado (badge "En desarrollo") |
| `informes` | `informes.tsx` | Mesa de redacción: configuración + vista previa |
| `fuentes` | `fuentes.tsx` | Catálogo tipo registro (filas) |
| `metodologia` | `metodologia.tsx` | Editorial numerada (números display gigantes) |
| `documentacion` | `documentacion.tsx` | Centro de referencia en cuatro movimientos |
| `procesamiento` | `procesamiento.tsx` | Diagrama de pipeline de 7 pasos |
| `calidad` | `calidad.tsx` | Hero editorial + banda de cobertura |
| `trazabilidad` | `trazabilidad.tsx` | Bitácora de auditoría (línea de corridas) |
| `validacion` | `validacion.tsx` | Marcador de métricas del experimento |
| `estado` | `estado.tsx` | Tablero de estado: franja de salud + verificaciones |

Patrón común de una vista: `SectionHero` (cabecera editorial) → `DataGate`
(esqueleto mientras carga, error con reintento, o contenido) → contenido. Los
datos llegan por `useFireia()` del `data-provider`; no abras tu propia conexión
HTTP para el almacén.

## 7. Sistema de diseño

Definido en `src/app/globals.css` como tokens CSS + utilidades `@theme inline`.
**Tema exclusivamente claro**: no introduzcas fondos oscuros ni degradados pesados.

### Paleta base

| Token | Valor | Uso |
| --- | --- | --- |
| `--background` | `#FFF9F3` | Fondo general (crema) |
| `--card` / `--popover` | `#FFFFFF` | Superficies elevadas |
| `--foreground` | `#39332F` | Texto principal (marrón muy oscuro) |
| `--muted-foreground` | `#82766D` | Texto secundario (gris cálido) |
| `--primary` | `#E9A477` | Naranja pastel de marca |
| `--accent` | `#F4C5A5` | Naranja claro (fondos suaves) |
| `--secondary` / `--muted` | `#F4EAE0` | Beige (bandas, filas, chips) |
| `--destructive` | `#B5543B` | Errores |
| `--border` / `--input` | `#ECDFD1` | Bordes discretos |
| `--radius` | `0.75rem` | Radio base (sm/md/lg/xl derivan de él) |

### Colores de identidad (MODIS × VIIRS y acciones)

| Token | Valor | Uso |
| --- | --- | --- |
| `--color-modis` | `#D97C45` (deep `#8A4516`) | Todo lo MODIS |
| `--color-viirs` | `#3E8E87` (deep `#1F5450`) | Todo lo VIIRS |
| `--color-flame` | `#C05F2C` | Acento "fuego" en visualizaciones |
| `--color-action` | `#C05F2C` | Acciones importantes: naranja intenso SOLO aquí |
| `--color-tint` | `#F7E3D2` | Tintes suaves |
| `--color-brown` | `#6B5D52` | Marrón medio para jerarquías |

### Tipografía y movimiento

- **Display**: Fraunces (títulos, números editoriales) — variable `--font-fraunces`.
- **Texto**: Geist; **código**: Geist Mono — cargadas en `layout.tsx` con `next/font`.
- Movimiento: primitivas de `motion.tsx` (variantes como constantes); `MotionRoot`
  desactiva animaciones si el usuario prefiere movimiento reducido. Duraciones cortas,
  sin rebotes exagerados.

Reglas duras: naranja intenso `#C05F2C` solo para acciones importantes; bordes finos
y sombras suaves (nada de sombras pesadas); una vista = una composición propia, no
una grilla de tarjetas idénticas; iconografía lucide discreta y consistente.

## 8. Capa de datos y regeneración

```
pipeline (repo madre, DuckDB data/processed/hotspots.duckdb)
        │  scripts/exportar_mvp.py   (solo lectura del DuckDB + capas GeoJSON)
        ▼
src/data/mvp/almacen.json · anomalias_exp001.json · departamentos.geojson
        │  src/lib/mvp-store.ts      (lector con caché, solo servidor)
        ▼
rutas API de Next (§9)  →  servicios frontend (src/lib/fireia/services/)
        ▼
data-provider (contexto compartido)  →  vistas
```

- Los JSON son **fixtures sintéticos** exportados el 2026-11-11, cobertura
  2026-09-15 → 2026-09-21. La fuente (`data_source: "fixture"`) viaja en cada respuesta.
- Para regenerarlos tras una nueva ingesta del pipeline: ejecuta `exportar_mvp.py`
  ajustando las rutas `REPO`/`DB`/`OUT` de su cabecera (apuntan al layout del
  equipo original; adáptalas a donde vivan el repo del pipeline y este proyecto).
- `departamentos.geojson` es geoBoundaries gbOpen PRY (geometría DGEEC), CC BY 4.0,
  versión hash `9469f09` — no lo edites a mano.
- Con datos reales en el futuro: exporta igual y la web no necesita cambios de
  contrato; solo actualiza notas y periodos en `data_source_nota`.

## 9. API interna (rutas de Next, espejo del contrato FastAPI del pipeline)

| Endpoint | Qué devuelve |
| --- | --- |
| `GET /api/health` | Estado del servicio + `data_source` + nota de origen + resumen |
| `GET /api/stats` | Estadísticas nacional por día/semana/mes y por departamento |
| `GET /api/observations` | Detecciones con filtros: `product`, sensor, día/noche, fechas, departamento, `dentro_pais` |
| `GET /api/events` | Eventos de co-detección MODIS–VIIRS con sus miembros |
| `GET /api/quality` | Estados de ingesta, corridas, cuarentena y pares candidatos |
| `GET /api/anomalias` | Resultado del experimento 001 (declara que la serie es SINTÉTICA) |
| `GET /api/coverage` | Calendario de cobertura: distingue "cero detecciones" de "sin datos" |
| `GET /api/geo/departamentos` | GeoJSON ADM1 (18 departamentos) con fuente y versión |
| `GET /api` | "Hello, world!" — residuo del andamiaje, sin uso |

Contrato: las respuestas SIEMPRE incluyen el origen del dato. Al añadir un
endpoint nuevo, replica este patrón (ver `src/app/api/events/route.ts` como
referencia más simple) y su servicio correspondiente en `src/lib/fireia/services/`.

## 10. Recetas de edición

**Cambiar un color o tipografía** → `src/app/globals.css` (tokens §7). No metas
hexágonos sueltos en los componentes: usa los tokens (`bg-primary`, `text-muted-foreground`,
`text-modis`, …) para que el tema siga siendo coherente.

**Añadir una vista/sección** →
1. Crea `src/components/fireia/views/mi-vista.tsx` mirando una vista simple (`fuentes.tsx`).
2. Agrega la vista al tipo `Vista` y al array `NAV` en `nav-config.ts` (elige grupo e icono lucide).
3. Impórtala y conéctala en el switch de `src/app/page.tsx`.
4. Si su dato no existe todavía: usa `EmptyState` y decláralo en `disponibilidad.ts`.

**Renombrar una sección** → solo `label` en `nav-config.ts`; añade el nombre viejo a
`ALIAS_VISTAS` si hay enlaces compartidos con el hash anterior.

**Actualizar textos/copy** → están en español dentro de cada vista; los textos de
marca/SEO están en `layout.tsx` (`metadata`).

**Actualizar el mapa** → el componente vive en `src/components/mvp/mapa-map.tsx`
(MapLibre); los colores de capas usan `--color-modis`/`--color-viirs`.

**Regenerar datos** → §8. Nunca edites los JSON a mano.

**Añadir un endpoint** → crea `src/app/api/<nombre>/route.ts` con el patrón de
`events/route.ts`, lee del `mvp-store`, incluye `data_source` en la respuesta.

## 11. Convenciones del código

- **Idioma**: todo el copy de la interfaz, los comentarios y los nombres de
  dominio van en español; los identificadores técnicos (React/Next) en inglés estándar.
- **Comentarios con intención**: cada archivo abre con un comentario que explica
  qué es y por qué existe. Mantén esa tradición al editar.
- Componentes cliente con `"use client"` al inicio (SPA interactiva); los lectores
  de datos (`mvp-store.ts`) son solo servidor.
- Nombres en español para el dominio (`vista`, `almacen`, `cobertura`), sin tildes
  en identificadores (`codigo`, `anomalias`).
- UI shadcn/ui primero; un componente nuevo solo si ninguno encaja.
- Accesibilidad: foco visible, `aria-*` en estados de carga, cierre de menús con
  Esc y clic fuera, contraste AA sobre fondo crema.

## 12. Control de calidad antes de entregar

```bash
npm run lint     # 0 errores (los warnings del worker de maplibre en public/ son esperados)
npm run build    # debe terminar con la tabla de rutas sin fallos
```

Checklist manual (5–10 min): recorrer las 20 vistas del menú; verificar el estado
de carga (esqueleto) y el error con reintento (detén `dev` y recarga); probar el
hamburguesa en móvil (devtools: 375 px) con overlay y cierre por Esc/clic fuera;
verificar que el mapa y la tabla de observaciones son usables en pantalla chica;
confirmar que cada pantalla declara su origen de dato (fixture/sintético/en desarrollo).

Nota honesta sobre la config heredada: `next.config.ts` tiene
`typescript.ignoreBuildErrors: true`. El proyecto compila limpio con `tsc --noEmit`
fuera de las carpetas del sandbox; si editas, considera ponerlo en `false` para
que el build te proteja.

## 13. Reglas del proyecto (acuerdos del equipo)

1. **No inventar datos**: nada de puntuaciones, pronósticos o "resultados" que el
   backend no entregue; el origen viaja siempre en la respuesta y en la pantalla.
2. **Solo frontend**: esta web consume la API espejo; no añadas ingestas, llaves
   FIRMS ni llamadas de red hacia FIRMS desde la web.
3. **Tema claro exclusivamente**, con la paleta §7.
4. Toda subida al repositorio se **replica en ambos repos** (organización y espejo).
5. Cambios de contrato de datos: primero el pipeline (repo madre), luego la API
   espejo, luego la web.

## 14. Contexto y enlaces

- Proyecto: *Harmonization of MODIS and VIIRS Hot Spots*, NASA Space Apps Challenge 2026 (Desafío 1.9), caso Paraguay.
- Pipeline y ciencia (Python, DuckDB, FastAPI): carpeta `codigo/` del mismo repositorio, con su documentación en `codigo/docs/`.
- Historial de misiones (informes por etapa): carpetas `mision_001_fase0/` … `mision_011_ejecucion_real/`.
- Datos: NASA FIRMS (MODIS C6.1 / VIIRS 375 m NRT), geoBoundaries (CC BY 4.0); ver `fuentes.tsx` y el catálogo de la web.
- Licencias de la web: mismas del proyecto (ver `LICENSE` en la raíz del repositorio).
