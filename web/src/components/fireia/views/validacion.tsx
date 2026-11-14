"use client";

// Validación científica (v3 — marcador): las métricas del experimento como
// marcador con barras hacia 100%, el baseline a vencer y los pendientes
// como checklist honesto.

import Link from "next/link";
import { BadgeCheck, CircleDashed, FlaskConical, Radar } from "lucide-react";

import { DataGate } from "@/components/fireia/data-gate";
import { SectionHero } from "@/components/fireia/section-hero";
import { Badge } from "@/components/ui/badge";

export function ValidacionView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="04"
        categoria="Sistema · evidencia"
        icon={Radar}
        title="Qué se probó, qué falta."
        lede="Un panel honesto distingue evidencia de promesa: el experimento 001 corrió sobre una serie sintética reproducible, y los pendientes están declarados en voz alta."
      />
      <DataGate>{(datos) => <ContenidoValidacion datos={datos} />}</DataGate>
    </div>
  );
}

function ContenidoValidacion({
  datos,
}: {
  datos: {
    anomalias: {
      metodo: string;
      umbral_z: number;
      dias_evaluados: number;
      verdaderos_positivos: number;
      falsos_positivos: number;
      recall: number;
      precision: number | null;
      mae_persistencia_baseline: number;
      anomalias_inyectadas: string[];
    };
  };
}) {
  const a = datos.anomalias;

  const barras: Array<{ etiqueta: string; valor: number; texto: string }> = [
    {
      etiqueta: "Recall del detector",
      valor: a.recall,
      texto: `${a.verdaderos_positivos} de ${a.anomalias_inyectadas.length} anomalías plantadas`,
    },
    {
      etiqueta: "Precisión",
      valor: a.precision ?? 0,
      texto: a.precision !== null ? `${a.precision.toFixed(1)}% de aciertos` : "no calculable en esta serie",
    },
  ];

  return (
    <div className="space-y-5">
      {/* --- marcador del experimento --- */}
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="rounded-3xl border border-border bg-card p-5 sm:p-6 lg:col-span-3">
          <div className="flex flex-wrap items-center gap-2">
            <p className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight text-foreground">
              <FlaskConical className="size-4 text-flame" aria-hidden />
              Experimento 001 · detector de anomalías
            </p>
            <Badge className="border-transparent bg-tint text-[10px] font-bold text-flame">
              Serie sintética · semilla fija
            </Badge>
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
            Método {a.metodo}, umbral z = {a.umbral_z}, {a.dias_evaluados} días
            evaluados. Reproducible: misma semilla, mismo resultado.
          </p>

          <div className="mt-5 space-y-4">
            {barras.map((b) => (
              <div key={b.etiqueta}>
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-xs font-medium text-foreground">{b.etiqueta}</p>
                  <p className="font-display text-xl font-semibold text-foreground">
                    {b.valor.toFixed(1)}%
                  </p>
                </div>
                <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-[#f4c5a5] to-[#e9a477]"
                    style={{ width: `${Math.min(b.valor, 100)}%` }}
                  />
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground">{b.texto}</p>
              </div>
            ))}
            <div className="flex items-baseline justify-between border-t border-border/60 pt-3.5">
              <p className="text-xs font-medium text-foreground">Falsos positivos</p>
              <p className="font-display text-xl font-semibold text-flame">
                {a.falsos_positivos}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-3xl border border-border bg-secondary/60 p-5 sm:p-6 lg:col-span-2">
          <p className="fireia-kicker text-muted-foreground">Baseline a vencer</p>
          <p className="mt-3 font-display text-5xl font-semibold text-foreground">
            {a.mae_persistencia_baseline.toFixed(1)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            MAE de la «persistencia» (mañana igual a hoy): el pronóstico mínimo
            que cualquier modelo futuro debe superar.
          </p>
          <p className="mt-4 border-t border-border/60 pt-3.5 text-xs leading-relaxed text-muted-foreground">
            Lo valioso del experimento: cazó dos defectos reales del método (MAD
            subestimado por día de semana → z inflado; anomalías viejas
            contaminando la mediana), ambos documentados en el código del
            detector. Su MAE también es sintético: útil solo como referencia de
            método.
          </p>
        </div>
      </div>

      {/* --- pendientes: checklist --- */}
      <div className="rounded-3xl border border-dashed border-[#e4d5c6] bg-[#fffdfb] px-5 py-6 sm:px-7">
        <p className="fireia-kicker text-muted-foreground">Pendientes de validación</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {[
            {
              titulo: "Validación con datos reales",
              detalle:
                "Repetir las métricas sobre la ingesta real del piloto (Fase 1B). Sin datos reales no hay validación posible — esta es la compuerta principal.",
            },
            {
              titulo: "Comparación con fuentes independientes",
              detalle:
                "Contrastar los eventos de co-detección con otras fuentes de área quemada (por ejemplo, MODIS burned area) cuando se integren.",
            },
            {
              titulo: "Reproducibilidad completa",
              detalle:
                "Publicar el procedimiento para que un tercero recomponga el almacén y obtenga los mismos números (ya existe para ingesta; falta para análisis).",
            },
            {
              titulo: "Modelos predictivos",
              detalle:
                "Entrenar y evaluar frente al baseline de persistencia, con datos reales, antes de mostrar cualquier pronóstico.",
            },
          ].map((p) => (
            <div key={p.titulo} className="flex items-start gap-3">
              <CircleDashed
                className="mt-0.5 size-5 shrink-0 text-[#c4ae97]"
                aria-hidden
              />
              <div>
                <p className="text-sm font-semibold text-foreground">{p.titulo}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                  {p.detalle}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2.5 rounded-2xl border border-border bg-card px-5 py-4">
        <BadgeCheck className="size-4 shrink-0 text-viirs" aria-hidden />
        <p className="min-w-0 flex-1 text-xs leading-relaxed text-muted-foreground">
          Regla del proyecto: ninguna etapa se marca como completada porque
          exista su pantalla. Para explorar los métodos con escenarios
          controlados, usá el{" "}
          <Link
            href="#/simulaciones"
            className="font-medium text-flame underline-offset-4 hover:underline"
          >
            laboratorio de simulaciones
          </Link>
          .
        </p>
      </div>
    </div>
  );
}
