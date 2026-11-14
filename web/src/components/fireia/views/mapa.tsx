"use client";

// Mapa de Paraguay (v3): pantalla de exploración con hero compacto —
// el protagonista es el mapa a pantalla casi completa.

import { DataGate } from "@/components/fireia/data-gate";
import { HeroCompacto } from "@/components/fireia/section-hero";
import { MapaTab } from "@/components/mvp/mapa-tab";

export function MapaView() {
  return (
    <div className="space-y-4">
      <HeroCompacto
        indice="01"
        categoria="Exploración · mapa"
        title="El país, foco por foco"
        lede="Todas las detecciones de MODIS y VIIRS sobre el territorio. Tocá un punto para ver su detalle, un evento agrupado para entenderlo, o un departamento para filtrarlo."
      />
      <DataGate>
        {(datos) => (
          <MapaTab
            observaciones={datos.observaciones}
            eventos={datos.eventos}
            departamentos={datos.departamentos}
          />
        )}
      </DataGate>
    </div>
  );
}
