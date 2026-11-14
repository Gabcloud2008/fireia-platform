"use client";

// Misión 016 — FIREIA LIVE · Insignia de estado en vivo para el header.
// Honestidad por diseño: muestra la antigüedad REAL de los datos (FIRMS NRT
// tiene latencia de horas; no es transmisión instantánea). Sin Supabase
// configurado no renderiza nada (la web sigue funcionando igual).
import { Activity } from "lucide-react";

import { useFireiaLive } from "@/hooks/use-fireia-live";
import { cn } from "@/lib/utils";

export function LiveStatus() {
  const live = useFireiaLive();

  if (!live.enVivo) return null;

  const { edadHoras, ultimaCorrida, alertasNuevas } = live;
  const color =
    edadHoras === null
      ? "text-muted-foreground"
      : edadHoras <= 3
        ? "text-emerald-600"
        : edadHoras <= 24
          ? "text-amber-600"
          : "text-red-600";

  const textoEdad =
    edadHoras === null
      ? "sin adquisiciones aún"
      : edadHoras < 1
        ? "datos de hace menos de 1 h"
        : `datos de hace ${edadHoras.toFixed(0)} h`;

  return (
    <span
      className="hidden items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[11px] font-medium sm:inline-flex"
      title={`Última corrida: ${ultimaCorrida?.product ?? "—"} (${ultimaCorrida?.status ?? "—"})${
        alertasNuevas > 0 ? ` · ${alertasNuevas} alerta(s) nuevas` : ""
      }`}
    >
      <Activity className={cn("size-3 animate-pulse", color)} aria-hidden />
      <span className={color}>EN VIVO</span>
      <span className="text-muted-foreground">· {textoEdad}</span>
    </span>
  );
}
