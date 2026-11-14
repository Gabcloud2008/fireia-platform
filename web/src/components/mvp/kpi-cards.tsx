"use client";

// Indicadores del período (M012, tema claro): tarjetas blancas, etiquetas en
// gris cálido y valores con tabular-nums. Los colores de sensor son los
// oficiales de FIREIA: naranja para MODIS y verde azulado para VIIRS.

import { Flame, Layers, MapPin, Radar, Satellite } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { Almacen } from "@/lib/mvp-types";

function Kpi({
  icon: Icon,
  label,
  value,
  hint,
  color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  hint: string;
  color: string;
}) {
  return (
    <Card className="border-border bg-card shadow-none transition-colors hover:bg-[#fffdfb]">
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
          <Icon className={`size-4 ${color}`} aria-hidden />
        </div>
        <p className="mt-2 text-2xl font-bold tabular-nums text-foreground">{value}</p>
        <p className="mt-1 text-[11px] leading-snug text-muted-foreground/90">{hint}</p>
      </CardContent>
    </Card>
  );
}

export function KpiCards({ resumen }: { resumen: Almacen["resumen"] }) {
  return (
    <section
      aria-label="Indicadores del período"
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
    >
      <Kpi
        icon={Flame}
        label="Detecciones (país)"
        value={resumen.dentro_pais}
        hint={`dentro del polígono del país · ${resumen.total - resumen.dentro_pais} vecinas en el área de consulta`}
        color="text-flame"
      />
      <Kpi
        icon={Satellite}
        label="MODIS"
        value={resumen.modis}
        hint="MODIS_NRT (Terra/Aqua)"
        color="text-modis"
      />
      <Kpi
        icon={Satellite}
        label="VIIRS"
        value={resumen.viirs}
        hint="VIIRS_NOAA20_NRT"
        color="text-viirs"
      />
      <Kpi
        icon={Layers}
        label="Eventos"
        value={resumen.eventos}
        hint="co-detección entre sensores"
        color="text-brown"
      />
      <Kpi
        icon={MapPin}
        label="Departamentos"
        value={resumen.departamentos_afectados.length}
        hint="con al menos una detección"
        color="text-brown"
      />
      <Kpi
        icon={Radar}
        label="Pares candidatos"
        value={resumen.pares_candidatos}
        hint="MODIS↔VIIRS en ventana espaciotemporal"
        color="text-muted-foreground"
      />
    </section>
  );
}
