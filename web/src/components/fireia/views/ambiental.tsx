"use client";

// Inteligencia ambiental (v4 — mosaico de variables REALES): las 7 fuentes
// de M014 están integradas y trazables (Misión D). Cada variable muestra su
// estado real y los datos fluyen por /api/ambiental.

import {
  CloudRain,
  CloudSun,
  Droplets,
  Gauge,
  Sprout,
  Thermometer,
  Wind,
} from "lucide-react";

import { SectionHero } from "@/components/fireia/section-hero";
import { Badge } from "@/components/ui/badge";
import { ambientalService, ETIQUETA_ESTADO_FUENTE } from "@/lib/fireia/services/ambiental";
import { MODULOS, ETIQUETA_DISPONIBILIDAD } from "@/lib/fireia/disponibilidad";

const ICONOS_VARIABLE: Record<string, React.ComponentType<{ className?: string }>> = {
  temperatura: Thermometer,
  precipitacion: CloudRain,
  humedad: Droplets,
  viento: Wind,
  vegetacion: Sprout,
  sequia: Gauge,
};

export function AmbientalView() {
  const variables = ambientalService.listarVariables();
  const modulo = MODULOS.find((m) => m.clave === "ambiental")!;
  const disp = ETIQUETA_DISPONIBILIDAD[modulo.disponibilidad];

  return (
    <div className="space-y-5">
      <SectionHero
        indice="03"
        categoria="Análisis · contexto ambiental"
        icon={CloudSun}
        title="El fuego no ocurre en el vacío."
        lede="Siete fuentes ambientales REALES están integradas y trazables: clima, humedad, FWI, cobertura y área quemada asociadas a cada celda y mes de la grilla nacional 0,1°. Se estudian asociaciones, no causas."
        meta={
          <Badge
            variant="outline"
            className={`rounded-full px-3 py-1.5 text-[11px] font-medium ${disp.clase}`}
          >
            {disp.etiqueta}
          </Badge>
        }
      />

      {/* --- mosaico de variables --- */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {variables.map((v, i) => {
          const est = ETIQUETA_ESTADO_FUENTE[v.estado];
          const Icono = ICONOS_VARIABLE[v.id] ?? CloudSun;
          const destacado = i === 0;
          return (
            <div
              key={v.id}
              className={`flex flex-col justify-between gap-4 rounded-2xl border p-5 transition-transform duration-200 hover:-translate-y-0.5 ${
                destacado
                  ? "border-[#eeddc9] bg-gradient-to-b from-[#fff4e8] to-[#fdeedd]"
                  : "border-border bg-card"
              }`}
            >
              <div>
                <div className="flex items-start justify-between gap-3">
                  <span
                    className={`flex size-11 items-center justify-center rounded-2xl ${
                      destacado ? "bg-card text-flame" : "bg-secondary text-brown"
                    }`}
                    aria-hidden
                  >
                    <Icono className="size-5.5" />
                  </span>
                  <Badge
                    variant="outline"
                    className={`shrink-0 text-[10px] font-medium ${est.clase}`}
                  >
                    {est.etiqueta}
                  </Badge>
                </div>
                <p className="mt-3.5 font-display text-lg font-semibold tracking-tight text-foreground">
                  {v.nombre}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {v.descripcion}
                </p>
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-2 border-t border-border/60 pt-3 text-[11px]">
                <div>
                  <dt className="text-muted-foreground">Unidad</dt>
                  <dd className="font-medium text-foreground">{v.unidad}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Resolución</dt>
                  <dd className="font-medium text-foreground">{v.resolucion}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-muted-foreground">Fuente (integrada)</dt>
                  <dd className="font-medium text-foreground">
                    {v.fuente} · {v.licencia}
                  </dd>
                </div>
              </dl>
            </div>
          );
        })}
      </div>

      <div className="rounded-2xl border border-dashed border-[#e4d5c6] bg-[#fffdfb] px-5 py-4">
        <p className="text-xs leading-relaxed text-muted-foreground">
          <strong className="text-foreground">Nota metodológica:</strong>{" "}
          las variables integradas (Misión D) permiten estudiar asociaciones —
          por ejemplo, humedad de suelo baja con más detecciones (ρ = −0,39),
          VPD alto con más detecciones (ρ = +0,26) — medidas con Spearman sobre
          la serie mensual y sin usar información futura. Son asociaciones, no
          relaciones causales: FIREIA no afirma causas sin evidencia ni
          métodos validados.
        </p>
      </div>
    </div>
  );
}
