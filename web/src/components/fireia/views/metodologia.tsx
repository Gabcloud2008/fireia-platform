"use client";

// Metodología (v3 — editorial numerada): números display gigantes a la
// izquierda, la versión sencilla a la vista y los detalles técnicos
// plegables debajo de cada punto.

import { BadgeCheck } from "lucide-react";

import { SectionHero } from "@/components/fireia/section-hero";
import { Card, CardContent } from "@/components/ui/card";

const PASOS = [
  {
    titulo: "De dónde vienen los datos",
    simple:
      "La NASA publica las detecciones de focos de calor de sus satélites a través de FIRMS. FIREIA toma dos productos: MODIS (Terra/Aqua, píxeles de 1 km) y VIIRS (NOAA-20, píxeles de 375 m). En esta demo se usan fixtures sintéticos; la ingesta real está detrás de una compuerta de red.",
    tecnico:
      "Productos MODIS_NRT (C6.1) y VIIRS_NOAA20_NRT. Descarga vía Area API con MAP_KEY, clasificación por código HTTP + inspección de cuerpo, RAW content-addressed por SHA256 e inmutable, ingesta idempota (reprocesar no duplica).",
  },
  {
    titulo: "Cómo se ubica cada detección",
    simple:
      "Para decir en qué departamento cayó cada punto, se comprueba si sus coordenadas caen dentro del polígono oficial del departamento. Las detecciones fuera del país se conservan y se marcan como tales.",
    tecnico:
      "Point-in-polygon contra ADM1 de geoBoundaries gbOpen (geometría DGEEC, CC BY 4.0, versión 9469f09). Coordenadas 0.0/0.0 nunca pasan el control de calidad.",
  },
  {
    titulo: "Cómo se agrupan los eventos",
    simple:
      "Cuando varias detecciones de MODIS y VIIRS caen en la misma zona y ventana de tiempo, se agrupan en un «evento» para estudiarlas juntas. Es una agrupación analítica: no necesariamente un incendio individual confirmado, y la dispersión del grupo no es un perímetro.",
    tecnico:
      "Componentes conexas de pares entre productos en ventana espaciotemporal (método versionado). Membresía N:M conservada por snapshot; alerta de encadenamiento cuando el evento crece por reachability. Los snapshots se reconstruyen por corrida y los anteriores quedan como evidencia.",
  },
  {
    titulo: "Cómo se clasifica cada día",
    simple:
      "Antes de calcular cualquier serie, cada día del período recibe una etiqueta: con detecciones, sin detecciones (asumido cero), solo detecciones descartadas por calidad, o sin datos. Así, un día sin datos jamás se cuenta como día sin fuego.",
    tecnico:
      "Clasificación de cobertura diaria por producto (ventana inferida cuando corresponde) + supuestos declarados. Las series estadísticas solo incluyen días clasificados.",
  },
  {
    titulo: "Cómo se controla la calidad",
    simple:
      "Cada registro pasa por un control de ingesta con diez estados posibles. Lo dudoso va a cuarentena y se conserva íntegro con sus errores: nunca se descarta en silencio. Todo queda registrado con su motivo.",
    tecnico:
      "Taxonomía de 10 estados (ingested, skipped, quarantined, rejected…). Manifiestos por corrida con SHA256 por artefacto; hotspots verify recomputa todos los hashes. Compuerta --allow-network + credenciales + autorización para la ingesta real.",
  },
  {
    titulo: "El experimento de anomalías",
    simple:
      "Para probar el detector de días inusuales se usó una serie sintética con semilla fija: 151 días con ciclo semanal, ruido y cuatro picos plantados. El experimento sirvió para encontrar dos defectos reales del método, que quedaron documentados. No representa la actividad real de Paraguay.",
    tecnico:
      "rolling_median_mad_v1, umbral z = 3.0, baseline por día de semana (8 semanas). Defectos cazados: MAD subestimado por weekday (z inflado) y anomalías viejas contaminando la mediana. Recall/precisión solo sobre la serie sintética; MAE de persistencia como baseline a vencer.",
  },
];

export function MetodologiaView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="03"
        categoria="Información · cómo trabajamos"
        icon={BadgeCheck}
        title="Seis pasos, cero magia."
        lede="Cómo trabaja FIREIA, explicado paso a paso. Cada punto tiene la versión sencilla a la vista y los detalles técnicos plegables debajo."
      />

      <div className="space-y-3">
        {PASOS.map((p, i) => (
          <Card
            key={p.titulo}
            className="border-border bg-card shadow-none transition-colors hover:border-[#ecc7b3]"
          >
            <CardContent className="flex gap-5 p-5 sm:gap-7 sm:p-6">
              <p className="fireia-index w-12 shrink-0 text-5xl text-[#e5c9ae] sm:w-16 sm:text-6xl" aria-hidden>
                {String(i + 1).padStart(2, "0")}
              </p>
              <div className="min-w-0 flex-1">
                <p className="font-display text-lg font-semibold tracking-tight text-foreground">
                  {p.titulo}
                </p>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                  {p.simple}
                </p>
                <details className="group mt-3 rounded-xl border border-border bg-[#fffdfb]">
                  <summary className="cursor-pointer select-none list-none px-4 py-2.5 text-xs font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
                    Detalles técnicos
                    <span className="float-right transition-transform duration-200 group-open:rotate-180">
                      ▾
                    </span>
                  </summary>
                  <p className="border-t border-border px-4 py-3 text-xs leading-relaxed text-foreground/90">
                    {p.tecnico}
                  </p>
                </details>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Principio rector del proyecto: no se presenta ningún resultado sin
        declarar su origen y sus límites. Si un método no existe o no fue
        validado, la plataforma lo dice en lugar de simularlo.
      </p>
    </div>
  );
}
