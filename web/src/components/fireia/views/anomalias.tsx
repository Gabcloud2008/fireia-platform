"use client";

// Anomalías (v3 — método → resultado): el método se narra como una cadena
// de cuatro pasos, después el resultado con cifras display y el gráfico.
// El único contenido actual es el experimento 001 sobre serie sintética,
// identificado de forma visible. Una anomalía no es predicción ni incendio
// confirmado.

import { ArrowRight, Activity } from "lucide-react";

import { DataGate } from "@/components/fireia/data-gate";
import { SectionHero } from "@/components/fireia/section-hero";
import { AnomaliasTab } from "@/components/mvp/anomalias-tab";

const CADENA_METODO = [
  { paso: "Región", detalle: "todo el país (serie nacional)" },
  { paso: "Período", detalle: "151 días sintéticos (01-11 → 03-31)" },
  { paso: "Referencia", detalle: "mediana móvil, 8 semanas, por día de semana" },
  { paso: "Diferencia", detalle: "desvíos (z) respecto de esa referencia" },
];

export function AnomaliasView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="04"
        categoria="Análisis · señales inusuales"
        icon={Activity}
        title="Días que se apartan de lo esperable."
        lede="Una anomalía es un día cuya actividad detectada se aleja de su propio histórico. Llama la atención; no predice nada ni confirma un incendio. El único experimento actual corre sobre una serie sintética con semilla fija."
      />

      <DataGate>
        {(datos) => (
          <div className="space-y-5">
            {/* --- cadena del método --- */}
            <div className="grid gap-2 rounded-2xl border border-border bg-card p-4 sm:grid-cols-4 sm:gap-0">
              {CADENA_METODO.map((c, i) => (
                <div key={c.paso} className="relative px-1 sm:px-4 sm:first:pl-0">
                  <p className="fireia-kicker flex items-center gap-1.5 text-flame">
                    <span
                      className="flex size-4.5 items-center justify-center rounded-full bg-tint font-mono text-[9px] text-flame"
                      aria-hidden
                    >
                      {i + 1}
                    </span>
                    {c.paso}
                  </p>
                  <p className="mt-1.5 text-xs leading-snug text-muted-foreground">
                    {c.detalle}
                  </p>
                  {i < CADENA_METODO.length - 1 && (
                    <ArrowRight
                      className="absolute -right-[7px] top-1 hidden size-3.5 text-[#c4ae97] sm:block"
                      aria-hidden
                    />
                  )}
                </div>
              ))}
            </div>

            <AnomaliasTab anomalias={datos.anomalias} />
          </div>
        )}
      </DataGate>
    </div>
  );
}
