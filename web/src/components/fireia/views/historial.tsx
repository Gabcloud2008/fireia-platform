"use client";

// Historial y calendario (v3): la banda de cobertura como pieza visual
// central (retícula de días clasificados), la línea temporal debajo y la
// recurrencia territorial como barras horizontales legibles.

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Map as MapIcon } from "lucide-react";

import { DataGate } from "@/components/fireia/data-gate";
import type { DatosMVP } from "@/components/fireia/data-provider";
import { SectionHero } from "@/components/fireia/section-hero";
import { CoberturaBand } from "@/components/fireia/cobertura-band";
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

const DIAS_SEMANA = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"];

export function HistorialView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="02"
        categoria="Análisis · tiempo"
        title="El período, día por día."
        lede="Qué días hubo datos, cuántas detecciones dejó cada uno y qué territorios aparecen una y otra vez. Cada día está clasificado antes de entrar a cualquier estadística: un día sin datos nunca se cuenta como día sin fuego."
      />
      <DataGate>{(datos) => <ContenidoHistorial datos={datos} />}</DataGate>
    </div>
  );
}

function ContenidoHistorial({ datos }: { datos: DatosMVP }) {
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

  const porDiaSemana = useMemo(() => {
    const acc = DIAS_SEMANA.slice(1)
      .concat(DIAS_SEMANA[0])
      .map((d) => ({ dia: d, detecciones: 0 }));
    const idx = new Map(acc.map((a, i) => [a.dia, i]));
    for (const o of datos.observaciones) {
      const dow = new Date(`${o.acq_date}T00:00:00Z`).getUTCDay();
      const nombre = DIAS_SEMANA[dow];
      const i = idx.get(nombre);
      if (i !== undefined) acc[i].detecciones += 1;
    }
    return acc;
  }, [datos.observaciones]);

  const recurrencia = useMemo(() => {
    const mapa = new Map<
      string,
      { departamento: string; MODIS: number; VIIRS: number; dias: Set<string> }
    >();
    for (const o of datos.observaciones) {
      if (!o.departamento) continue;
      const actual =
        mapa.get(o.departamento) ??
        { departamento: o.departamento, MODIS: 0, VIIRS: 0, dias: new Set<string>() };
      if (o.sensor === "MODIS") actual.MODIS += 1;
      else actual.VIIRS += 1;
      actual.dias.add(o.acq_date);
      mapa.set(o.departamento, actual);
    }
    return Array.from(mapa.values())
      .map((d) => ({
        departamento: d.departamento,
        MODIS: d.MODIS,
        VIIRS: d.VIIRS,
        total: d.MODIS + d.VIIRS,
        diasDistintos: d.dias.size,
      }))
      .sort((a, b) => b.total - a.total);
  }, [datos.observaciones]);

  const maxTotal = Math.max(...recurrencia.map((r) => r.total), 1);
  const diasCobertura = datos.cobertura?.dias ?? [];
  const resumen = datos.cobertura?.resumen ?? {};

  return (
    <div className="space-y-5">
      {/* --- banda de cobertura: la pieza visual central --- */}
      <Card className="border-border bg-card shadow-none">
        <CardContent className="p-5 sm:p-6">
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-display text-lg font-semibold tracking-tight text-foreground">
              Calendario de cobertura
            </p>
            <p className="text-[11px] text-muted-foreground">
              {datos.health.cobertura.desde} → {datos.health.cobertura.hasta}
            </p>
          </div>
          <CoberturaBand
            dias={diasCobertura}
            resumen={resumen}
            supuestos={datos.cobertura?.supuestos}
          />
        </CardContent>
      </Card>

      {/* --- línea temporal por día --- */}
      <Card className="border-border bg-card shadow-none">
        <CardContent className="p-5 sm:p-6">
          <p className="font-display text-lg font-semibold tracking-tight text-foreground">
            Detecciones por día
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Los días sin barras no tuvieron detecciones (o no tuvieron datos:
            la banda de arriba lo aclara).
          </p>
          <div className="mt-4 h-64 sm:h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={porDia} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
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
                <Bar dataKey="MODIS" name="MODIS" stackId="a" fill={COLOR_MODIS} />
                <Bar
                  dataKey="VIIRS"
                  name="VIIRS"
                  stackId="a"
                  fill={COLOR_VIIRS}
                  radius={[3, 3, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* --- semanal + recurrencia --- */}
      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="min-w-0 border-border bg-card shadow-none lg:col-span-2">
          <CardContent className="p-5 sm:p-6">
            <p className="font-display text-lg font-semibold tracking-tight text-foreground">
              Por día de semana
            </p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Con pocos días de ventana esto es descriptivo, no un patrón
              estacional.
            </p>
            <div className="mt-4 h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={porDiaSemana} margin={{ top: 8, right: 8, bottom: 0, left: -22 }}>
                  <CartesianGrid stroke="#f0e6da" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="dia" tick={{ fill: "#82766d", fontSize: 11 }} stroke="#e4d5c6" />
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
                  <Bar
                    dataKey="detecciones"
                    name="Detecciones"
                    fill="#e9a477"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card className="min-w-0 border-border bg-card shadow-none lg:col-span-3">
          <CardContent className="p-5 sm:p-6">
            <p className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight text-foreground">
              <MapIcon className="size-4 text-flame" aria-hidden />
              Recurrencia por departamento
            </p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Detecciones totales y en cuántos días distintos apareció cada
              departamento. Que aparezca muchos días sugiere actividad
              persistente, no necesariamente el mismo fuego.
            </p>
            <div className="mt-4 max-h-72 space-y-3 overflow-y-auto pr-1">
              {recurrencia.map((d) => (
                <div key={d.departamento}>
                  <div className="flex items-baseline justify-between gap-2 text-xs">
                    <span className="font-medium text-foreground">{d.departamento}</span>
                    <span className="tabular-nums text-muted-foreground">
                      <strong className="font-display text-sm text-foreground">{d.total}</strong>{" "}
                      · {d.diasDistintos} días
                    </span>
                  </div>
                  <div className="mt-1.5 flex h-2 overflow-hidden rounded-full bg-secondary">
                    <span
                      className="h-full bg-modis"
                      style={{ width: `${(d.MODIS / maxTotal) * 100}%` }}
                      title={`MODIS: ${d.MODIS}`}
                    />
                    <span
                      className="h-full bg-viirs"
                      style={{ width: `${(d.VIIRS / maxTotal) * 100}%` }}
                      title={`VIIRS: ${d.VIIRS}`}
                    />
                  </div>
                </div>
              ))}
              {recurrencia.length === 0 && (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  Sin detecciones dentro del país en este período.
                </p>
              )}
            </div>
            <p className="mt-3 flex flex-wrap gap-x-4 text-[10px] text-muted-foreground/80">
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-modis" aria-hidden /> MODIS
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-viirs" aria-hidden /> VIIRS
              </span>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
