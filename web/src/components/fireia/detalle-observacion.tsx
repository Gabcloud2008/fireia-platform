"use client";

// Detalle de una observación en lenguaje sencillo (M012 §9): primero la
// interpretación simple, los valores técnicos originales al final.
// Reutilizado por el panel del mapa y el detalle de observaciones.

import { Flame, Moon, Sun } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Observacion } from "@/lib/mvp-types";

export function DetalleObservacion({ o }: { o: Observacion }) {
  const confidencial: Record<string, string> = {
    l: "baja — el algoritmo tiene poca seguridad de que sea fuego",
    nominal:
      "intermedia — señal razonable, puede haber falsos positivos ocasionales",
    high: "alta — señal clara y persistente en las bandas térmicas",
  };

  return (
    <div className="space-y-4">
      {/* --- interpretación sencilla --- */}
      <div className="space-y-3">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Cuándo y dónde
          </p>
          <p className="mt-0.5 text-sm font-medium text-foreground">
            {o.acq_date} ·{" "}
            {o.acq_time.slice(0, 2)}:{o.acq_time.slice(2)} UTC
          </p>
          <p className="text-xs text-muted-foreground">
            {o.departamento ?? "fuera del país"}
            {o.distrito ? ` · distrito ${o.distrito}` : ""} · coordenadas{" "}
            {o.latitude.toFixed(3)}, {o.longitude.toFixed(3)}
          </p>
        </div>

        <div className="rounded-xl bg-secondary/70 px-4 py-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Intensidad energética estimada
          </p>
          <p className="mt-0.5 text-2xl font-bold tabular-nums text-foreground">
            {o.frp !== null ? `${o.frp.toFixed(1)} MW` : "sin dato"}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Energía que el sensor estima que irradia el foco en ese instante.
            Los valores de MODIS y VIIRS no son comparables entre sí.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Badge className="border-transparent bg-tint text-[11px] font-medium text-flame">
            Sensor {o.sensor}
          </Badge>
          <Badge
            variant="outline"
            className="border-border bg-card text-[11px] font-normal text-muted-foreground"
          >
            {o.satellite_name}
          </Badge>
          <Badge
            variant="outline"
            className="border-border bg-card text-[11px] font-normal text-muted-foreground"
          >
            <Flame className="mr-1 size-3" aria-hidden />
            Confianza {o.confidence_band}
          </Badge>
          <Badge
            variant="outline"
            className="border-border bg-card text-[11px] font-normal text-muted-foreground"
          >
            {o.daynight === "D" ? (
              <>
                <Sun className="mr-1 size-3" aria-hidden />
                Pass diurno
              </>
            ) : (
              <>
                <Moon className="mr-1 size-3" aria-hidden />
                Pass nocturno
              </>
            )}
          </Badge>
        </div>

        <p className="text-xs leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">
            Nivel de confianza:
          </span>{" "}
          {confidencial[o.confidence_band] ?? o.confidence_band}.
        </p>
      </div>

      {/* --- valores técnicos originales --- */}
      <details className="group rounded-xl border border-border bg-background/60">
        <summary className="cursor-pointer select-none list-none px-4 py-2.5 text-xs font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
          Valores técnicos y procedencia
          <span className="float-right transition-transform duration-200 group-open:rotate-180">
            ▾
          </span>
        </summary>
        <dl className="space-y-1.5 border-t border-border px-4 py-3">
          {(
            [
              ["Identificador", o.obs_id],
              ["Producto", o.product],
              ["Instrumento", o.instrument],
              ["Confianza (valor original)", o.confidence],
              [
                "Temperatura de brillo",
                o.brightness !== null
                  ? `${o.brightness.toFixed(2)} K (banda 21)`
                  : "—",
              ],
              [
                "Bandas VIIRS I4 / I5",
                o.bright_ti4 !== null && o.bright_ti5 !== null
                  ? `${o.bright_ti4.toFixed(2)} K / ${o.bright_ti5.toFixed(2)} K`
                  : "—",
              ],
              [
                "Tamaño del píxel (scan × track)",
                o.scan !== null && o.track !== null
                  ? `${o.scan.toFixed(1)} × ${o.track.toFixed(1)}`
                  : "—",
              ],
              [
                "Asignación territorial",
                o.dentro_pais
                  ? "dentro del país (point-in-polygon, ADM1)"
                  : "fuera del polígono del país",
              ],
              ["Versión de límites", o.version_limites],
            ] as Array<[string, string]>
          ).map(([k, v]) => (
            <div key={k} className="flex items-start justify-between gap-4">
              <dt className="shrink-0 text-[11px] text-muted-foreground">{k}</dt>
              <dd className="break-all text-right text-[11px] font-medium text-foreground">
                {v}
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  );
}
