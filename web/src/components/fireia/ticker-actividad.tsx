"use client";

// Ticker de actividad (sala de redacciones): los últimos focos detectados
// desfilan en una cinta continua. Pausa al pasar el mouse y se congela
// completamente con prefers-reduced-motion (globals.css).

import type { Observacion } from "@/lib/mvp-types";

export function TickerActividad({ items }: { items: Observacion[] }) {
  if (items.length === 0) return null;

  const fragmento = (ariaOculto: boolean) => (
    <div
      className="flex shrink-0 items-center gap-7 pr-7"
      aria-hidden={ariaOculto || undefined}
    >
      {items.map((o) => (
        <span
          key={o.obs_id}
          className="flex items-center gap-2 whitespace-nowrap text-xs text-muted-foreground"
        >
          <span
            className={`size-2 shrink-0 rounded-full ${
              o.sensor === "MODIS" ? "bg-modis" : "bg-viirs"
            }`}
            aria-hidden
          />
          <span className="font-semibold text-foreground">{o.sensor}</span>
          foco {o.departamento ? `en ${o.departamento.toLowerCase()}` : "vecino al país"}
          <span className="font-mono text-[10px] text-muted-foreground/70">
            {o.acq_datetime_utc.slice(5, 16).replace("T", " ")} UTC
          </span>
        </span>
      ))}
    </div>
  );

  return (
    <div
      className="fireia-marquee-mask overflow-hidden border-y border-border bg-card/70 py-2.5"
      role="marquee"
      aria-label="Últimas detecciones registradas"
    >
      <div className="fireia-marquee">
        {fragmento(false)}
        {fragmento(true)}
      </div>
    </div>
  );
}
