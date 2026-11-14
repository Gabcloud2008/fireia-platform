"use client";

// Riesgo y estimaciones futuras (v4): IA predictiva REAL (Misión E) con
// evaluación honesta. La etiqueta es "≥1 detección VIIRS en la celda el
// mes siguiente" — una agrupación inferida, NO un incendio confirmado.

import { useEffect, useState } from "react";
import { Loader2, ShieldCheck, TrendingUp } from "lucide-react";

import { SectionHero } from "@/components/fireia/section-hero";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface MetricasParte {
  roc_auc: number;
  pr_auc: number;
  brier: number;
  ece: number;
  precision: number;
  recall: number;
  f1: number;
  matriz_confusion: number[][];
  n: number;
  positivos: number;
}

interface RespuestaIA {
  data_source: string;
  nota: string;
  version: string;
  semilla: number;
  dataset: { filas: number; celdas: number; positivos: number; tasa_positivos: number };
  particiones: { temporal: { entrenamiento: string[]; validacion: string[]; evaluacion: string[]; filas: number[] } };
  modelos: Record<string, { info: { tipo: string; parametros?: string; features?: string[] }; validacion: MetricasParte; evaluacion: MetricasParte }>;
  mejor_modelo: string;
  importancia: Array<{ feature: string; importancia: number }>;
  validacion_geografica: { roc_auc_medio: number | null; roc_auc_por_banda: number[] };
  curvas: { prevalencia?: number; curvas: Record<string, { roc_auc: number; pr_auc: number; roc: number[][]; pr: number[][] }> };
}

const NOMBRE_MODELO: Record<string, string> = {
  baseline_climatologia: "Baseline · climatología",
  baseline_persistencia: "Baseline · persistencia",
  regresion_logistica: "Regresión logística",
  random_forest: "Random Forest",
  gradient_boosting: "Gradient Boosting",
};

const LIMITACIONES = [
  "La etiqueta es una detección satelital en celda-mes: no es un incendio confirmado ni superficie quemada.",
  "Horizonte único de 1 mes; no se validaron horizontes mayores.",
  "La ventaja sobre el baseline de climatología es modesta (+10,5% PR-AUC relativo) y así se comunica.",
  "El experimento exp_001 de anomalías es SINTÉTICO y no forma parte de esta validación.",
  "Los meses sin cobertura FWI (2026-05..09) se excluyen sin imputación.",
];

export function RiesgoView() {
  const [ia, setIa] = useState<RespuestaIA | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    fetch("/api/ia", { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`/api/ia → ${r.status}`);
        return r.json() as Promise<RespuestaIA>;
      })
      .then((d) => {
        if (!cancelado) setIa(d);
      })
      .catch((e: unknown) => {
        if (!cancelado) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelado = true;
    };
  }, []);

  const mejor = ia ? ia.modelos[ia.mejor_modelo] : null;
  const evalMejor = mejor?.evaluacion;
  const orden = ["baseline_climatologia", "baseline_persistencia", "regresion_logistica", "random_forest", "gradient_boosting"];

  return (
    <div className="space-y-5">
      <SectionHero
        indice="03"
        categoria="Inteligencia · futuro"
        icon={TrendingUp}
        title="Riesgo del mes siguiente, con la evidencia a la vista."
        lede="Modelo entrenado sobre la base real nacional (2.691.999 detecciones, 2000–2026) con partición temporal estricta. Publicamos sus métricas, sus errores y sus límites: una probabilidad de detección nunca es un incendio confirmado."
      />

      {error && (
        <Card className="border-[#ecc7b3] bg-[#fdf1ea] shadow-none">
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No pudimos cargar la evaluación de la IA ({error}).
          </CardContent>
        </Card>
      )}

      {!ia && !error && (
        <div className="grid gap-3 sm:grid-cols-3" aria-busy="true">
          <Skeleton className="h-28 rounded-2xl" />
          <Skeleton className="h-28 rounded-2xl" />
          <Skeleton className="h-28 rounded-2xl" />
          <Skeleton className="h-64 rounded-2xl sm:col-span-3" />
        </div>
      )}

      {ia && evalMejor && (
        <>
          {/* métrica principal */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { k: "ROC-AUC", v: evalMejor.roc_auc.toFixed(3), d: `${NOMBRE_MODELO[ia.mejor_modelo]} · evaluación temporal 2025–26` },
              { k: "PR-AUC", v: evalMejor.pr_auc.toFixed(3), d: `prevalencia ${(ia.curvas?.prevalencia ?? evalMejor.positivos / evalMejor.n).toFixed(2)}` },
              { k: "Brier", v: evalMejor.brier.toFixed(3), d: "menor es mejor (calibración)" },
              { k: "Recall", v: `${(evalMejor.recall * 100).toFixed(1)}%`, d: "celda-meses con fuego recuperados" },
            ].map((m) => (
              <Card key={m.k} className="border-border bg-card shadow-none">
                <CardContent className="p-5">
                  <p className="fireia-kicker text-muted-foreground">{m.k}</p>
                  <p className="mt-1 font-display text-3xl font-semibold tracking-tight text-foreground">
                    {m.v}
                  </p>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{m.d}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* comparación de modelos */}
          <Card className="border-border bg-card shadow-none">
            <CardContent className="p-5 sm:p-6">
              <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-display text-lg font-semibold tracking-tight text-foreground">
                  Cinco modelos comparados
                </p>
                <Badge variant="outline" className="border-transparent bg-[#e3efe3] text-[10px] font-medium text-[#3d6b4f]">
                  datos reales · partición temporal
                </Badge>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted-foreground">
                      <th className="py-2 pr-3 font-medium">Modelo</th>
                      <th className="py-2 pr-3 font-medium">ROC-AUC</th>
                      <th className="py-2 pr-3 font-medium">PR-AUC</th>
                      <th className="py-2 pr-3 font-medium">Brier</th>
                      <th className="py-2 pr-3 font-medium">Precision</th>
                      <th className="py-2 pr-3 font-medium">Recall</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orden.map((m) => {
                      const e = ia.modelos[m]?.evaluacion;
                      if (!e) return null;
                      const destacado = m === ia.mejor_modelo;
                      return (
                        <tr
                          key={m}
                          className={`border-b border-border/50 ${destacado ? "bg-[#fff4ea] font-medium" : ""}`}
                        >
                          <td className="py-2.5 pr-3">
                            {NOMBRE_MODELO[m]}
                            {destacado && (
                              <Badge variant="outline" className="ml-2 border-[#eeddc9] bg-transparent text-[9px] font-normal text-flame">
                                mejor
                              </Badge>
                            )}
                          </td>
                          <td className="py-2.5 pr-3 tabular-nums">{e.roc_auc.toFixed(3)}</td>
                          <td className="py-2.5 pr-3 tabular-nums">{e.pr_auc.toFixed(3)}</td>
                          <td className="py-2.5 pr-3 tabular-nums">{e.brier.toFixed(3)}</td>
                          <td className="py-2.5 pr-3 tabular-nums">{(e.precision * 100).toFixed(1)}%</td>
                          <td className="py-2.5 pr-3 tabular-nums">{(e.recall * 100).toFixed(1)}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
                Entrenamiento {ia.particiones.temporal.entrenamiento[0]}–{ia.particiones.temporal.entrenamiento[1]} ·
                validación {ia.particiones.temporal.validacion[0]} ·
                evaluación {ia.particiones.temporal.evaluacion[0]}–{ia.particiones.temporal.evaluacion[1]}
                (efectivo 2026-04 por cobertura FWI). Semilla {ia.semilla}.
                La regresión logística no emite positivos al umbral 0,5 (limitación documentada, no corregida en silencio).
              </p>
            </CardContent>
          </Card>

          {/* importancia + geografía */}
          <div className="grid gap-3 lg:grid-cols-2">
            <Card className="border-border bg-card shadow-none">
              <CardContent className="p-5 sm:p-6">
                <p className="font-display text-lg font-semibold tracking-tight text-foreground">
                  Qué mira el modelo
                </p>
                <p className="mb-4 mt-1 text-[11px] text-muted-foreground">
                  Importancia de las 16 variables (Random Forest). Nunca usa información futura.
                </p>
                <ul className="space-y-2.5">
                  {ia.importancia.slice(0, 8).map((v) => (
                    <li key={v.feature}>
                      <div className="flex items-baseline justify-between text-xs">
                        <span className="font-medium text-foreground">{v.feature}</span>
                        <span className="tabular-nums text-muted-foreground">{v.importancia.toFixed(3)}</span>
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-secondary">
                        <div
                          className="h-full rounded-full bg-flame/70"
                          style={{ width: `${(v.importancia / ia.importancia[0].importancia) * 100}%` }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
            <Card className="border-border bg-card shadow-none">
              <CardContent className="p-5 sm:p-6">
                <p className="font-display text-lg font-semibold tracking-tight text-foreground">
                  Generalización espacial
                </p>
                <p className="mb-4 mt-1 text-[11px] text-muted-foreground">
                  Entrenar en 4 bandas de latitud y evaluar en la restante (Gradient Boosting).
                </p>
                <div className="flex items-end justify-between gap-2">
                  {ia.validacion_geografica.roc_auc_por_banda.map((a, i) => (
                    <div key={i} className="flex flex-1 flex-col items-center gap-1.5">
                      <span className="text-[10px] tabular-nums text-muted-foreground">{a.toFixed(2)}</span>
                      <div
                        className="w-full rounded-t-lg bg-[#81b29a]/80"
                        style={{ height: `${((a - 0.5) / 0.4) * 120 + 8}px` }}
                        aria-hidden
                      />
                      <span className="text-[10px] text-muted-foreground">Banda {i}</span>
                    </div>
                  ))}
                </div>
                <p className="mt-4 text-[11px] leading-relaxed text-muted-foreground">
                  Media {ia.validacion_geografica.roc_auc_medio}: el desempeño no depende de una sola
                  región; no hay colapso fuera del Chaco.
                </p>
                <div className="mt-4 flex items-start gap-2 rounded-xl bg-[#eef4ee] px-3 py-2.5">
                  <ShieldCheck className="mt-0.5 size-4 shrink-0 text-[#3d6b4f]" aria-hidden />
                  <p className="text-[11px] leading-relaxed text-[#3d6b4f]">
                    Cómo leer esto: la probabilidad estima <em>actividad detectable</em> por VIIRS
                    en la celda el mes próximo. Útil para priorizar monitoreo; no es un dictamen
                    de fuego ni de superficie quemada.
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* limitaciones */}
          <Card className="border-[#eeddc9] bg-[#fffdf9] shadow-none">
            <CardContent className="p-5 sm:p-6">
              <p className="font-display text-lg font-semibold tracking-tight text-foreground">
                Limitaciones declaradas
              </p>
              <ul className="mt-3 space-y-2">
                {LIMITACIONES.map((l) => (
                  <li key={l} className="flex items-start gap-2.5 text-xs leading-relaxed text-muted-foreground">
                    <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-[#d9c4ad]" aria-hidden />
                    {l}
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-[11px] leading-relaxed text-muted-foreground">{ia.nota}</p>
            </CardContent>
          </Card>
        </>
      )}

      {!ia && error && (
        <div className="flex items-center gap-2 rounded-2xl border border-border bg-secondary/60 px-5 py-4 text-xs text-muted-foreground">
          <Loader2 className="size-4" aria-hidden />
          La vista se reconstruirá al reintentar.
        </div>
      )}
    </div>
  );
}
