"use client";

// Evolución temporal (v3): detecciones por día y potencia radiativa (FRP)
// por día. Regla de honestidad: el FRP de MODIS y VIIRS nunca se suma ni
// se apila — cada sensor se muestra por separado.

import { useMemo } from "react";
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

import { Card, CardContent } from "@/components/ui/card";
import type { Almacen } from "@/lib/mvp-types";

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

export function SeriesTab({ stats }: { stats: Almacen["stats"] }) {
  const porDia = useMemo(() => {
    // eje continuo de fechas (con ceros) para que los huecos se vean como huecos
    const fechas = Array.from(
      new Set(stats.nacional_dia.map((s) => s.acq_date)),
    ).sort();
    return fechas.map((f) => {
      const modis = stats.nacional_dia.find(
        (s) => s.acq_date === f && s.product === "MODIS_NRT",
      );
      const viirs = stats.nacional_dia.find(
        (s) => s.acq_date === f && s.product === "VIIRS_NOAA20_NRT",
      );
      return {
        fecha: f.slice(5),
        MODIS: modis?.detecciones ?? 0,
        VIIRS: viirs?.detecciones ?? 0,
        frpModis: modis?.frp_total ?? 0,
        frpViirs: viirs?.frp_total ?? 0,
      };
    });
  }, [stats]);

  const totalModis = porDia.reduce((acc, d) => acc + d.MODIS, 0);
  const totalViirs = porDia.reduce((acc, d) => acc + d.VIIRS, 0);
  const frpModis = porDia.reduce((acc, d) => acc + d.frpModis, 0);
  const frpViirs = porDia.reduce((acc, d) => acc + d.frpViirs, 0);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="border-border bg-card shadow-none lg:col-span-2">
        <CardContent className="p-5 sm:p-6">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-display text-lg font-semibold tracking-tight text-foreground">
              Detecciones por día y sensor
            </p>
            <p className="text-[11px] tabular-nums text-muted-foreground">
              MODIS {totalModis} · VIIRS {totalViirs}
            </p>
          </div>
          <p className="mb-4 text-xs leading-relaxed text-muted-foreground">
            Eje de fechas continuo: los días sin barras no tuvieron
            detecciones.
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

      <Card className="border-border bg-card shadow-none lg:col-span-2">
        <CardContent className="p-5 sm:p-6">
          <p className="font-display text-lg font-semibold tracking-tight text-foreground">
            Potencia radiativa (FRP) por día y sensor
          </p>
          <p className="mb-4 mt-1 text-xs leading-relaxed text-muted-foreground">
            FRP total en MW: MODIS {frpModis.toFixed(1)} · VIIRS{" "}
            {frpViirs.toFixed(1)}. Las barras van lado a lado porque el FRP de
            cada sensor se mide de forma distinta: no se suma entre sensores.
          </p>
          <div className="h-64 sm:h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={porDia} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                <CartesianGrid stroke="#f0e6da" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="fecha" tick={{ fill: "#82766d", fontSize: 11 }} stroke="#e4d5c6" />
                <YAxis tick={{ fill: "#82766d", fontSize: 11 }} stroke="#e4d5c6" />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={{ color: "#82766d" }}
                  cursor={{ fill: "#f4eae066" }}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: "#82766d" }} />
                <Bar
                  dataKey="frpModis"
                  name="FRP MODIS"
                  fill={COLOR_MODIS}
                  radius={[3, 3, 0, 0]}
                />
                <Bar
                  dataKey="frpViirs"
                  name="FRP VIIRS"
                  fill={COLOR_VIIRS}
                  radius={[3, 3, 0, 0]}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
