"use client";

// Documentación (v3 — centro de referencia): guía en cuatro movimientos,
// API como filas mono y glosario con términos display. Referencia seca,
// pero legible y sin tarjetas clónicas.

import { BookOpen } from "lucide-react";

import { SectionHero } from "@/components/fireia/section-hero";
import { Badge } from "@/components/ui/badge";

const ENDPOINTS = [
  {
    metodo: "GET",
    ruta: "/api/health",
    descripcion: "Estado del almacén y origen de los datos (siempre declarado).",
  },
  {
    metodo: "GET",
    ruta: "/api/observations",
    descripcion:
      "Detecciones con filtros: sensor, producto, día/noche, fechas, departamento, dentro del país.",
  },
  {
    metodo: "GET",
    ruta: "/api/stats",
    descripcion: "Estadísticas nacionales por día y por departamento.",
  },
  {
    metodo: "GET",
    ruta: "/api/events",
    descripcion: "Eventos de co-detección con sus observaciones miembro.",
  },
  {
    metodo: "GET",
    ruta: "/api/quality",
    descripcion: "Estados de ingesta, cuarentena y corridas registradas.",
  },
  {
    metodo: "GET",
    ruta: "/api/coverage",
    descripcion: "Calendario de cobertura: clasificación de cada día.",
  },
  {
    metodo: "GET",
    ruta: "/api/anomalias",
    descripcion: "Resultado del experimento 001 (serie sintética con semilla).",
  },
  {
    metodo: "GET",
    ruta: "/api/geo/departamentos",
    descripcion: "GeoJSON de departamentos (geoBoundaries gbOpen).",
  },
];

const GLOSARIO = [
  {
    termino: "Detección (hotspot)",
    simple:
      "Un píxel que el satélite vio más caliente de lo normal. Puede ser fuego, un reflejo o un defecto; por eso trae nivel de confianza.",
  },
  {
    termino: "FRP",
    simple:
      "Potencia radiativa de fuego: la energía que el foco irradia, en megavatios. Es la «intensidad» de la detección. Los valores de MODIS y VIIRS no se comparan entre sí.",
  },
  {
    termino: "NRT",
    simple:
      "Near Real Time: datos procesados casi en tiempo real (horas después del pase del satélite), con menor revisión que los productos finales.",
  },
  {
    termino: "Confianza (confidence)",
    simple:
      "Qué tan seguro está el algoritmo de que la detección es fuego real: baja (l), media (nominal) o alta (high).",
  },
  {
    termino: "Co-detección",
    simple:
      "Dos sensores distintos que registraron observaciones en una zona y un período cercanos. Permite estudiar si podrían estar relacionadas.",
  },
  {
    termino: "Evento",
    simple:
      "Agrupación analítica de detecciones en la misma ventana de espacio y tiempo. No es necesariamente un incendio individual confirmado.",
  },
  {
    termino: "Point-in-polygon",
    simple:
      "Prueba matemática de si un punto cae dentro de un polígono; con ella se asigna cada detección a su departamento.",
  },
  {
    termino: "Fixture",
    simple:
      "Archivo de prueba con datos sintéticos. Esta demo carga fixtures: ningún dato real fue consumido.",
  },
  {
    termino: "Manifiesto",
    simple:
      "Registro de cada corrida del pipeline con el hash SHA256 de cada artefacto, para verificar que nada se alteró.",
  },
  {
    termino: "SHA256",
    simple:
      "Huella digital de un archivo: si un byte cambia, la huella cambia. Permite demostrar que la evidencia no fue modificada.",
  },
  {
    termino: "Compuerta (gate)",
    simple:
      "Bloqueo deliberado: la ingesta real solo corre con autorización explícita, credenciales válidas y la opción --allow-network.",
  },
  {
    termino: "Anomalía",
    simple:
      "Día en que la actividad se aparta de lo esperable según su propio histórico. Es una señal para mirar, no una predicción ni un incendio confirmado.",
  },
];

const GUIA = [
  {
    n: "01",
    titulo: "Explorar",
    texto:
      "Abrí el mapa y tocá cualquier punto para ver su detalle. Filtrá por sensor, fecha o departamento; tocá un departamento del mapa para acotar la vista.",
  },
  {
    n: "02",
    titulo: "Entender",
    texto:
      "La comparación MODIS–VIIRS muestra qué vio cada satélite; «Historial y calendario» muestra cuándo; la recurrencia territorial muestra dónde se concentró.",
  },
  {
    n: "03",
    titulo: "Preguntar",
    texto:
      "El centro de inteligencia responde consultas simples sobre los datos cargados (modo demostración local, sin IA conectada).",
  },
  {
    n: "04",
    titulo: "Confiar",
    texto:
      "«Calidad», «Trazabilidad» y «Validación» muestran de dónde salió cada número y qué controles atravesó antes de llegar a la pantalla.",
  },
];

export function DocumentacionView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="04"
        categoria="Información · referencia"
        icon={BookOpen}
        title="Cómo usar FIREIA y qué significa cada cosa."
        lede="La referencia de la plataforma: qué ofrece la API, qué significa cada término y cómo sacarle provecho a cada sección."
      />

      {/* --- guía rápida en cuatro movimientos --- */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {GUIA.map((g, i) => (
          <div
            key={g.titulo}
            className={`flex flex-col gap-3 rounded-2xl border p-5 ${
              i === 0
                ? "border-[#eeddc9] bg-gradient-to-b from-[#fff4e8] to-[#fdeedd]"
                : "border-border bg-card"
            }`}
          >
            <p className="fireia-index text-3xl text-[#e5c9ae]" aria-hidden>
              {g.n}
            </p>
            <div>
              <p className="font-display text-[16px] font-semibold tracking-tight text-foreground">
                {g.titulo}
              </p>
              <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                {g.texto}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* --- API --- */}
      <section aria-labelledby="doc-api" className="rounded-3xl border border-border bg-card">
        <div className="border-b border-border/70 px-5 py-4 sm:px-7">
          <p className="font-display text-lg font-semibold tracking-tight text-foreground">
            API disponible <span className="text-muted-foreground">(espejo de solo lectura)</span>
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Estos endpoints existen y funcionan; el frontend los consume tal
            cual. No se crean endpoints ficticios.
          </p>
        </div>
        <ul className="divide-y divide-border/60">
          {ENDPOINTS.map((e) => (
            <li
              key={e.ruta}
              className="flex flex-col gap-1 px-5 py-3.5 sm:flex-row sm:items-center sm:gap-4 sm:px-7"
            >
              <Badge className="w-fit shrink-0 rounded-md border-transparent bg-[#e3efe3] px-2 py-0.5 font-mono text-[10px] font-bold text-[#3d6b4f]">
                {e.metodo}
              </Badge>
              <code className="w-56 shrink-0 font-mono text-xs font-semibold text-foreground">
                {e.ruta}
              </code>
              <span className="text-xs text-muted-foreground">{e.descripcion}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* --- glosario --- */}
      <section aria-labelledby="doc-glosario">
        <h2
          id="doc-glosario"
          className="mb-3 font-display text-xl font-semibold tracking-tight text-foreground"
        >
          Glosario en lenguaje sencillo
        </h2>
        <dl className="grid gap-x-8 gap-y-5 rounded-3xl border border-border bg-card px-5 py-6 sm:grid-cols-2 sm:px-7">
          {GLOSARIO.map((g) => (
            <div key={g.termino} className="border-b border-border/50 pb-4 last:border-0 sm:[&:nth-last-child(2)]:border-0">
              <dt className="font-display text-[16px] font-semibold tracking-tight text-foreground">
                {g.termino}
              </dt>
              <dd className="mt-1 text-xs leading-relaxed text-muted-foreground">
                {g.simple}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <p className="text-xs leading-relaxed text-muted-foreground">
        FIREIA (Paraguay Fire Intelligence) es el frontend del proyecto{" "}
        <span className="font-medium text-foreground">
          p400/modis-viirs-hotspots-paraguay
        </span>{" "}
        — NASA Space Apps Challenge 2026, reto 1.9. Licencias de las fuentes:
        detecciones NASA FIRMS; límites geoBoundaries gbOpen (CC BY 4.0);
        cartografía base colaboradores de OpenStreetMap.
      </p>
    </div>
  );
}
