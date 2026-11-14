"use client";

// Eventos y evolución (v3): expedientes de co-detección arriba, evolución
// temporal abajo — dos secciones con identidad propia.

import { DataGate } from "@/components/fireia/data-gate";
import { SectionHero } from "@/components/fireia/section-hero";
import { EventosTab } from "@/components/mvp/eventos-tab";
import { SeriesTab } from "@/components/mvp/series-tab";

export function EventosView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="01"
        categoria="Análisis · eventos"
        title="Cuándo el ruido se vuelve fenómeno."
        lede="Cuando MODIS y VIIRS detectan lo mismo en una ventana cercana de espacio y tiempo, el pipeline lo agrupa en un evento para estudiarlo en conjunto. Acá están los eventos del período y cómo evolucionó la actividad día a día."
      />
      <DataGate>
        {(datos) => (
          <div className="space-y-6">
            <section aria-labelledby="eventos-lista">
              <h2
                id="eventos-lista"
                className="mb-3 font-display text-xl font-semibold tracking-tight text-foreground"
              >
                Expedientes de co-detección
              </h2>
              <EventosTab eventos={datos.eventos} />
            </section>
            <section aria-labelledby="eventos-evolucion" className="scroll-mt-24">
              <h2
                id="eventos-evolucion"
                className="mb-3 font-display text-xl font-semibold tracking-tight text-foreground"
              >
                Evolución del período
              </h2>
              <SeriesTab stats={datos.stats} />
            </section>
          </div>
        )}
      </DataGate>
    </div>
  );
}
