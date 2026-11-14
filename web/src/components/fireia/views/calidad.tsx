"use client";

// Calidad de información (v3): envoltorio con hero editorial.

import { ShieldCheck } from "lucide-react";

import { DataGate } from "@/components/fireia/data-gate";
import { SectionHero } from "@/components/fireia/section-hero";
import { CalidadTab } from "@/components/mvp/calidad-tab";

export function CalidadView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="02"
        categoria="Sistema · control de calidad"
        icon={ShieldCheck}
        title="Ningún número sin revisar."
        lede="Qué se revisó antes de que cada cifra llegue a la pantalla: cómo se clasificó cada día, qué registros quedaron en cuarentena y qué significa cada estado del control."
      />
      <DataGate>
        {(datos) => (
          <CalidadTab calidad={datos.calidad} cobertura={datos.cobertura} />
        )}
      </DataGate>
    </div>
  );
}
