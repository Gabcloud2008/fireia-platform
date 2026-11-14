"use client";

// Laboratorio de simulaciones (v3 — banco de pruebas): banner-reglas
// integrado al hero y selector de módulos como segmented control. Todo lo
// que se muestra aquí es sintético y está permanentemente etiquetado.

import { useState } from "react";
import { FlaskConical } from "lucide-react";

import { SectionHero } from "@/components/fireia/section-hero";
import {
  SimActividad,
  SimAgrupacion,
  SimAmbiental,
  SimAnomalias,
  SimCoincidencia,
  SimEscenarios,
  SimTemporal,
} from "@/components/fireia/sim/modulos";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const MODULOS = [
  { id: "actividad", label: "Actividad satelital", componente: SimActividad },
  { id: "coincidencia", label: "Coincidencias", componente: SimCoincidencia },
  { id: "agrupacion", label: "Agrupación", componente: SimAgrupacion },
  { id: "temporal", label: "Temporal", componente: SimTemporal },
  { id: "ambiental", label: "Ambiental", componente: SimAmbiental },
  { id: "anomalias", label: "Anomalías", componente: SimAnomalias },
  { id: "escenarios", label: "Escenarios futuros", componente: SimEscenarios },
] as const;

export function SimulacionesView() {
  const [modulo, setModulo] = useState<string>("actividad");
  const Activo = MODULOS.find((m) => m.id === modulo)?.componente ?? SimActividad;

  return (
    <div className="space-y-5">
      <SectionHero
        indice="02"
        categoria="Inteligencia · laboratorio"
        icon={FlaskConical}
        title="Banco de pruebas, no realidad."
        lede="Explorá de forma interactiva cómo funcionan (o funcionarán) las capacidades de FIREIA con escenarios controlados. Nada de lo que ves aquí ocurrió: son demostraciones con datos sintéticos y semilla fija, separadas por completo del almacén real."
      />

      <Tabs value={modulo} onValueChange={setModulo} className="gap-4">
        <TabsList className="h-auto w-full justify-start overflow-x-auto rounded-full border border-border bg-card p-1">
          {MODULOS.map((m, i) => (
            <TabsTrigger
              key={m.id}
              value={m.id}
              className="gap-1.5 rounded-full px-3.5 text-xs data-[state=active]:bg-tint data-[state=active]:text-foreground"
            >
              <span className="hidden font-mono sm:inline">{i + 1} ·</span>
              {m.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {MODULOS.map((m) => (
          <TabsContent
            key={m.id}
            value={m.id}
            className="rounded-3xl border border-border bg-card p-5 sm:p-6"
          >
            {modulo === m.id && <Activo />}
          </TabsContent>
        ))}
      </Tabs>

      <p className="text-[11px] leading-relaxed text-muted-foreground/85">
        Cada módulo se puede restablecer y muestra los parámetros que
        controlás. Ningún resultado afirma precisión o capacidad predictiva de
        un modelo.
      </p>
    </div>
  );
}
