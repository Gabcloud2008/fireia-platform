"use client";

// Ingestión y procesamiento (v3 — diagrama de pipeline): los 7 pasos como
// nodos conectados sobre una línea, y los estados reales como barra
// proporcional + filas traducidas.

import { ArrowRight } from "lucide-react";

import { DataGate } from "@/components/fireia/data-gate";
import type { DatosMVP } from "@/components/fireia/data-provider";
import { SectionHero } from "@/components/fireia/section-hero";
import { Badge } from "@/components/ui/badge";

const ETAPAS = [
  { nombre: "Descarga", detalle: "Respuesta de NASA FIRMS (o fixture en esta demo)" },
  { nombre: "Clasificación", detalle: "Cada respuesta se clasifica según su contenido" },
  { nombre: "Lectura", detalle: "Los campos se normalizan; lo imposible se descarta" },
  { nombre: "Control de calidad", detalle: "Cada registro recibe uno de diez estados" },
  { nombre: "Respaldo crudo", detalle: "La respuesta original queda congelada, sin editar" },
  { nombre: "Almacén", detalle: "Los datos válidos entran a la base analítica" },
  { nombre: "Vistas y API", detalle: "Se calculan las estadísticas que ves aquí" },
];

/** Traducción de estados técnicos a lenguaje sencillo. */
const TRADUCCION_ESTADO: Record<
  string,
  { titulo: string; simple: string; clase: string; barra: string }
> = {
  ingested: {
    titulo: "Recibida y procesada",
    simple: "pasó todos los controles y ya está en el almacén",
    clase: "bg-[#e3efe3] text-[#3d6b4f]",
    barra: "bg-[#7fae94]",
  },
  skipped: {
    titulo: "Omitida a propósito",
    simple: "se decidió no procesarla (por ejemplo, día ya cubierto)",
    clase: "bg-secondary text-muted-foreground",
    barra: "bg-[#b7a89c]",
  },
  quarantined: {
    titulo: "En cuarentena",
    simple: "algo no cuadra: se conserva íntegra con sus errores",
    clase: "bg-[#f7dfd2] text-[#b5543b]",
    barra: "bg-[#d98d6e]",
  },
  rejected: {
    titulo: "Descartada",
    simple: "no pasó la validación y quedó registrada como descartada",
    clase: "bg-[#f7dfd2] text-[#b5543b]",
    barra: "bg-[#b5543b]",
  },
};

function traducir(state: string) {
  return (
    TRADUCCION_ESTADO[state] ?? {
      titulo: state,
      simple: "estado técnico del pipeline",
      clase: "bg-[#fdf3e3] text-[#8a6116]",
      barra: "bg-[#d9bfa8]",
    }
  );
}

export function ProcesamientoView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="01"
        categoria="Sistema · el camino del dato"
        title="De la órbita a esta pantalla."
        lede="Siete pasos separan una respuesta satelital de los números que estás viendo. En cada flecha queda evidencia verificable; los estados técnicos están traducidos y los detalles a un clic."
      />
      <DataGate>{(datos) => <Contenido datos={datos} />}</DataGate>
    </div>
  );
}

function Contenido({ datos }: { datos: DatosMVP }) {
  const totalEstados = datos.calidad.estados.reduce((a, e) => a + e.registros, 0);

  return (
    <div className="space-y-5">
      {/* --- pipeline: nodos conectados --- */}
      <div className="rounded-3xl border border-border bg-card px-5 py-6 sm:px-7">
        <p className="fireia-kicker text-muted-foreground">El camino del dato</p>
        <ol className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-7 xl:gap-2">
          {ETAPAS.map((etapa, i) => (
            <li key={etapa.nombre} className="relative">
              <div className="h-full rounded-2xl border border-border bg-[#fffdfb] p-3.5 transition-colors hover:border-[#ecc7b3]">
                <p className="flex items-center gap-2 text-xs font-semibold text-foreground">
                  <span className="fireia-index flex size-6 items-center justify-center rounded-full bg-tint text-sm text-flame">
                    {i + 1}
                  </span>
                  {etapa.nombre}
                </p>
                <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
                  {etapa.detalle}
                </p>
              </div>
              {i < ETAPAS.length - 1 && (
                <ArrowRight
                  className="absolute -right-[11px] top-1/2 z-10 hidden size-3.5 -translate-y-1/2 text-[#c4ae97] xl:block"
                  aria-hidden
                />
              )}
            </li>
          ))}
        </ol>
      </div>

      {/* --- estados reales: barra proporcional + filas --- */}
      <div className="rounded-3xl border border-border bg-card px-5 py-6 sm:px-7">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="font-display text-lg font-semibold tracking-tight text-foreground">
            Estado de los registros de esta ventana
          </p>
          <p className="text-[11px] tabular-nums text-muted-foreground">
            {totalEstados} registros de ingesta
          </p>
        </div>

        {/* barra apilada */}
        <div
          className="mt-4 flex h-3.5 overflow-hidden rounded-full bg-secondary"
          role="img"
          aria-label={`Distribución de ${totalEstados} registros por estado`}
        >
          {datos.calidad.estados.map((e) => {
            const t = traducir(e.state);
            return (
              <span
                key={e.state}
                className={`h-full ${t.barra}`}
                style={{
                  width: `${
                    totalEstados > 0 ? (e.registros / totalEstados) * 100 : 0
                  }%`,
                }}
                title={`${t.titulo}: ${e.registros}`}
              />
            );
          })}
        </div>

        <div className="mt-4 space-y-2.5">
          {datos.calidad.estados.map((e) => {
            const t = traducir(e.state);
            return (
              <div
                key={e.state}
                className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border border-border/70 bg-[#fffdfb] px-4 py-3"
              >
                <Badge
                  className={`shrink-0 border-transparent text-[11px] font-medium ${t.clase}`}
                >
                  {t.titulo}
                </Badge>
                <span className="min-w-0 flex-1 text-xs text-muted-foreground">
                  {t.simple}
                </span>
                <span className="shrink-0 font-mono text-sm font-semibold tabular-nums text-foreground">
                  {e.registros}
                </span>
                <span className="w-full text-[10px] text-muted-foreground/70 sm:w-auto">
                  código original: <span className="font-mono">{e.state}</span>
                </span>
              </div>
            );
          })}
        </div>
        <p className="mt-3.5 text-[11px] leading-relaxed text-muted-foreground">
          Lo dudoso se conserva, nunca se borra en silencio.
        </p>
      </div>

      <div className="rounded-2xl border border-border bg-secondary/60 px-5 py-4 text-xs leading-relaxed text-muted-foreground">
        <strong className="text-foreground">Actualización:</strong> la ingesta
        real desde FIRMS está bloqueada a propósito (compuerta de red +
        credenciales + autorización del propietario). Esta plataforma es
        consumidora de solo lectura: navegarla no dispara descargas ni consume
        cuota de la API. Cuando se habilite la ingesta real, esta sección
        mostrará las corridas en vivo.
      </div>
    </div>
  );
}
