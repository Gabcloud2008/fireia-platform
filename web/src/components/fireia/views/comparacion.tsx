"use client";

// Comparación MODIS–VIIRS (v3 — split-screen): dos mitades enfrentadas con
// un divisor central, cada una con la identidad de su sensor. Debajo, el
// gráfico compartido y las coincidencias confirmadas. El FRP nunca se
// mezcla y ninguna coincidencia se presenta como observación idéntica.

import { useMemo } from "react";
import Link from "next/link";
import { ArrowRight, Clock } from "lucide-react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { DataGate } from "@/components/fireia/data-gate";
import type { DatosMVP } from "@/components/fireia/data-provider";
import { SectionHero } from "@/components/fireia/section-hero";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

const COLOR_MODIS = "#d97c45";
const COLOR_VIIRS = "#3e8e87";

const tooltipStyle = {
  backgroundColor: "#ffffff",
  border: "1px solid #ecdfd1",
  borderRadius: "10px",
  color: "#39332f",
  fontSize: "12px",
  boxShadow: "0 8px 20px rgb(57 51 47 / 0.08)",
};

export function ComparacionView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="03"
        categoria="Exploración · dos sensores"
        title="El mismo fuego, mirado dos veces."
        lede="MODIS y VIIRS ven el suelo con píxeles y sensibilidades distintas. Compará qué detectó cada uno, cuándo, y qué coincidencias quedaron confirmadas por el método de co-detección del pipeline."
      />
      <DataGate>{(datos) => <Comparacion datos={datos} />}</DataGate>
    </div>
  );
}

function Comparacion({ datos }: { datos: DatosMVP }) {
  const porDia = useMemo(() => {
    const fechas = Array.from(
      new Set(datos.stats.nacional_dia.map((s) => s.acq_date)),
    ).sort();
    return fechas.map((f) => {
      const modis = datos.stats.nacional_dia.find(
        (s) => s.acq_date === f && s.product === "MODIS_NRT",
      );
      const viirs = datos.stats.nacional_dia.find(
        (s) => s.acq_date === f && s.product === "VIIRS_NOAA20_NRT",
      );
      return {
        fecha: f.slice(5),
        MODIS: modis?.detecciones ?? 0,
        VIIRS: viirs?.detecciones ?? 0,
      };
    });
  }, [datos.stats.nacional_dia]);

  const satelitesPorSensor = useMemo(() => {
    const modis = new Set<string>();
    const viirs = new Set<string>();
    for (const o of datos.observaciones) {
      (o.sensor === "MODIS" ? modis : viirs).add(o.satellite_name);
    }
    return {
      modis: Array.from(modis).sort().join(", ") || "—",
      viirs: Array.from(viirs).sort().join(", ") || "—",
    };
  }, [datos.observaciones]);

  const frpPorSensor = useMemo(() => {
    const acc = { MODIS: 0, VIIRS: 0 };
    for (const s of datos.stats.nacional_dia) {
      if (s.product === "MODIS_NRT") acc.MODIS += s.frp_total;
      else acc.VIIRS += s.frp_total;
    }
    return acc;
  }, [datos.stats.nacional_dia]);

  const ventanas = datos.cobertura?.cobertura_por_producto ?? {};

  const mitades = [
    {
      nombre: "MODIS",
      producto: "MODIS_NRT",
      color: COLOR_MODIS,
      resolucion: "1 km por píxel",
      satelites: satelitesPorSensor.modis,
      detecciones: datos.health.resumen.modis,
      frp: frpPorSensor.MODIS,
      ventana: ventanas["MODIS_NRT"],
      descripcion:
        "Vuela en Terra y Aqua. Su píxel grande es excelente para fuegos extensos, pero puede quedarse corto con fuegos pequeños.",
      fondo: "bg-gradient-to-b from-[#fff1e2] to-[#fbe7d2] border-[#eeddc9]",
      texto: "text-modis-deep",
      dot: "bg-modis",
    },
    {
      nombre: "VIIRS",
      producto: "VIIRS_NOAA20_NRT",
      color: COLOR_VIIRS,
      resolucion: "375 m por píxel",
      satelites: satelitesPorSensor.viirs,
      detecciones: datos.health.resumen.viirs,
      frp: frpPorSensor.VIIRS,
      ventana: ventanas["VIIRS_NOAA20_NRT"],
      descripcion:
        "Vuela en NOAA-20. Su píxel casi tres veces más chico detecta fuegos pequeños y fríos que MODIS pasa por alto.",
      fondo: "bg-gradient-to-b from-[#eaf3f1] to-[#ddeae7] border-[#cfe0dc]",
      texto: "text-viirs-deep",
      dot: "bg-viirs",
    },
  ];

  return (
    <div className="space-y-5">
      {/* ---------- split-screen ---------- */}
      <div className="relative grid md:grid-cols-2 md:gap-px md:overflow-hidden md:rounded-3xl md:border md:border-border">
        {/* divisor VS (solo escritorio) */}
        <div
          className="pointer-events-none absolute left-1/2 top-1/2 z-10 hidden -translate-x-1/2 -translate-y-1/2 md:block"
          aria-hidden
        >
          <span className="flex size-14 items-center justify-center rounded-full border border-border bg-card font-display text-sm font-bold tracking-wide text-foreground shadow-[0_10px_26px_-12px_rgb(57_51_47/0.4)]">
            VS
          </span>
        </div>

        {mitades.map((t) => (
          <div
            key={t.nombre}
            className={`relative flex min-w-0 flex-col gap-5 border p-6 sm:p-8 ${t.fondo} md:border-0`}
          >
            <div>
              <p
                className={`flex items-center gap-2.5 font-display text-3xl font-bold tracking-tight ${t.texto}`}
              >
                <span className={`size-3 rounded-full ${t.dot}`} aria-hidden />
                {t.nombre}
              </p>
              <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                {t.producto}
              </p>
            </div>

            <p className="max-w-md text-sm leading-relaxed text-foreground/85">
              {t.descripcion}
            </p>

            <div className="flex items-end gap-3">
              <p className="fireia-index text-6xl text-foreground">
                {t.detecciones}
              </p>
              <p className="pb-2 text-xs text-muted-foreground">
                detecciones
                <br />
                en el período
              </p>
            </div>

            <dl className="grid grid-cols-2 gap-x-5 gap-y-3.5 border-t border-[#00000012] pt-4 text-sm">
              {(
                [
                  ["Resolución", t.resolucion],
                  ["Satélites", t.satelites],
                  ["Intensidad total (FRP)", `${t.frp.toFixed(1)} MW`],
                ] as Array<[string, string]>
              ).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    {k}
                  </dt>
                  <dd className="mt-0.5 text-[13px] font-semibold text-foreground">
                    {v}
                  </dd>
                </div>
              ))}
              <div className="col-span-2">
                <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Ventana de cobertura
                  {t.ventana?.inferida ? " (inferida)" : ""}
                </dt>
                <dd className="mt-0.5 text-[13px] font-semibold tabular-nums text-foreground">
                  {t.ventana ? `${t.ventana.desde} → ${t.ventana.hasta}` : "—"}
                </dd>
              </div>
            </dl>
          </div>
        ))}
      </div>

      {/* ---------- gráfico compartido ---------- */}
      <Card className="border-border bg-card shadow-none">
        <CardContent className="p-5 sm:p-6">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-display text-lg font-semibold tracking-tight text-foreground">
              Detecciones por día, cara a cara
            </p>
            <p className="text-[11px] text-muted-foreground">
              ventana completa del almacén
            </p>
          </div>
          <p className="mb-4 max-w-3xl text-xs leading-relaxed text-muted-foreground">
            Que un sensor tenga más detecciones no significa «más fuego»: cada
            instrumento tiene otra resolución y otra sensibilidad.
          </p>
          <div className="h-64 sm:h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={porDia} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                <CartesianGrid stroke="#f0e6da" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="fecha" tick={{ fill: "#82766d", fontSize: 11 }} stroke="#e4d5c6" />
                <YAxis
                  allowDecimals={false}
                  tick={{ fill: "#82766d", fontSize: 11 }}
                  stroke="#e4d5c6"
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={{ color: "#82766d" }}
                  cursor={{ fill: "#f4eae066" }}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: "#82766d" }} />
                <Bar dataKey="MODIS" name="MODIS" fill={COLOR_MODIS} radius={[3, 3, 0, 0]} />
                <Bar dataKey="VIIRS" name="VIIRS" fill={COLOR_VIIRS} radius={[3, 3, 0, 0]} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* ---------- coincidencias ---------- */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl border border-border bg-card p-5 sm:p-6">
          <p className="fireia-kicker text-muted-foreground">Coincidencias entre satélites</p>
          <div className="mt-4 flex items-end gap-6">
            <div>
              <p className="fireia-index text-5xl text-flame">
                {datos.calidad.pares_candidatos}
              </p>
              <p className="mt-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                pares candidatos
              </p>
            </div>
            <div>
              <p className="fireia-index text-5xl text-viirs">
                {datos.health.resumen.eventos}
              </p>
              <p className="mt-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                coincidencias confirmadas
                <Link
                  href="#/eventos"
                  className="inline-flex items-center gap-0.5 normal-case tracking-normal text-flame underline-offset-4 hover:underline"
                >
                  ver eventos
                  <ArrowRight className="size-3" aria-hidden />
                </Link>
              </p>
            </div>
          </div>
          <p className="mt-4 border-t border-border/60 pt-3.5 text-xs leading-relaxed text-muted-foreground">
            Una <strong className="text-foreground">coincidencia</strong>{" "}
            significa que dos sensores registraron observaciones en una zona y
            un período cercanos. Eso permite estudiar si podrían estar
            relacionadas — no las convierte en observaciones idénticas ni en
            incendios confirmados. Los pares candidatos los junta la ventana
            espaciotemporal; los eventos confirmados, el método versionado del
            pipeline.
          </p>
        </div>

        {/* ---------- par por par ---------- */}
        {datos.eventos.length > 0 && (
          <div className="rounded-2xl border border-border bg-card p-5 sm:p-6">
            <p className="fireia-kicker flex items-center gap-2 text-muted-foreground">
              <Clock className="size-3.5" aria-hidden />
              Cómo coincidieron, par por par
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              Miembros del evento confirmado con su sensor y hora. Cuanto más
              cerca en el tiempo estén dos miembros de sensores distintos, más
              plausible es que hayan visto el mismo fenómeno.
            </p>
            <ol className="mt-4 space-y-0">
              {[...datos.eventos[0].miembros]
                .sort((a, b) =>
                  a.acq_datetime_utc.localeCompare(b.acq_datetime_utc),
                )
                .map((m, i, arr) => (
                  <li key={m.obs_id}>
                    <div className="flex items-center gap-3">
                      <span
                        className={`size-2.5 shrink-0 rounded-full ${
                          m.sensor === "MODIS" ? "bg-modis" : "bg-viirs"
                        }`}
                        aria-hidden
                      />
                      <Badge
                        className={`shrink-0 border-transparent text-[10px] font-semibold ${
                          m.sensor === "MODIS"
                            ? "bg-tint text-modis-deep"
                            : "bg-[#e0edec] text-viirs-deep"
                        }`}
                      >
                        {m.sensor}
                      </Badge>
                      <p className="min-w-0 flex-1 truncate text-xs text-foreground">
                        {m.departamento ?? "fuera del país"}
                        {m.distrito ? ` · ${m.distrito}` : ""}
                      </p>
                      <p className="shrink-0 font-mono text-[11px] text-muted-foreground">
                        {m.acq_datetime_utc.slice(11, 19)} UTC
                      </p>
                    </div>
                    {i < arr.length - 1 && (
                      <p
                        className="border-l border-border py-1 pl-[18px] text-[10px] tabular-nums text-muted-foreground/70"
                        aria-hidden
                      >
                        {Math.round(
                          (new Date(arr[i + 1].acq_datetime_utc).getTime() -
                            new Date(m.acq_datetime_utc).getTime()) /
                            60000,
                        )}{" "}
                        min después
                      </p>
                    )}
                  </li>
                ))}
            </ol>
          </div>
        )}
      </div>

      {/* ---------- nota de armonización ---------- */}
      <div className="rounded-2xl border border-border bg-secondary/60 px-5 py-4 text-xs leading-relaxed text-muted-foreground">
        <strong className="text-foreground">Sobre la armonización:</strong> el
        FRP de MODIS y el de VIIRS se miden con bandas espectrales y píxeles
        distintos, así que <em>no</em> se suman ni se convierten entre sí. Esta
        pantalla los muestra siempre por separado. Para explorar cómo cambian
        las coincidencias al variar la ventana espacial y temporal, visitá el{" "}
        <Link
          href="#/simulaciones"
          className="font-medium text-flame underline-offset-4 hover:underline"
        >
          laboratorio de simulaciones
        </Link>
        .
      </div>
    </div>
  );
}
