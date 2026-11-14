"use client";

// Experimento 001 (v3): métricas como cifras display, gráfico de la serie
// sintética y el descargo honesto de lo que NO demuestra. Mostramos las
// métricas porque son reproducibles (semilla fija) y el experimento cazó
// dos defectos reales del método — no porque "la IA acierte".

import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { FlaskConical, ShieldAlert, Target } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { AnomaliasExp001 } from "@/lib/mvp-types";

const tooltipStyle = {
  backgroundColor: "#ffffff",
  border: "1px solid #ecdfd1",
  borderRadius: "10px",
  color: "#39332f",
  fontSize: "12px",
  boxShadow: "0 8px 20px rgb(57 51 47 / 0.08)",
};

export function AnomaliasTab({ anomalias }: { anomalias: AnomaliasExp001 }) {
  const datos = useMemo(
    () =>
      anomalias.serie_completa.map((p) => ({
        fecha: p.fecha.slice(5),
        valor: p.valor,
        inyectada: anomalias.anomalias_inyectadas.includes(p.fecha),
        detectada: anomalias.anomalias_detectadas.includes(p.fecha),
        yInyectada: anomalias.anomalias_inyectadas.includes(p.fecha)
          ? p.valor
          : null,
        yDetectada: anomalias.anomalias_detectadas.includes(p.fecha)
          ? p.valor
          : null,
      })),
    [anomalias],
  );

  const desde = anomalias.detalle[0]?.fecha.slice(5) ?? "03-01";

  const metricas: Array<[string, string, string?]> = [
    ["Plantadas", `${anomalias.anomalias_inyectadas.length}`, "anomalías sintéticas"],
    ["Detectadas", `${anomalias.verdaderos_positivos}`, "verdaderos positivos"],
    ["Falsos +", `${anomalias.falsos_positivos}`, "falsas alarmas"],
    [
      "Recall",
      `${anomalias.recall.toFixed(1)}%`,
      anomalias.precision !== null ? `precisión ${anomalias.precision.toFixed(1)}%` : "precisión —",
    ],
    [
      "MAE base",
      `${anomalias.mae_persistencia_baseline.toFixed(1)}`,
      "persistencia: baseline a vencer",
    ],
  ];

  return (
    <div className="space-y-4">
      {/* --- cifras del experimento --- */}
      <div className="grid grid-cols-2 gap-y-5 rounded-2xl border border-border bg-card px-5 py-5 sm:grid-cols-5 sm:divide-x sm:divide-border/70">
        {metricas.map(([k, v, sub]) => (
          <div key={k} className="px-1 sm:px-4 sm:first:pl-0 sm:last:pr-0">
            <p className="fireia-index text-4xl text-foreground">{v}</p>
            <p className="mt-1.5 text-[10px] font-semibold uppercase tracking-wider text-flame">
              {k}
            </p>
            {sub ? (
              <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">
                {sub}
              </p>
            ) : null}
          </div>
        ))}
      </div>

      {/* --- serie del experimento --- */}
      <Card className="border-border bg-card shadow-none">
        <CardContent className="p-5 sm:p-6">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <p className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight text-foreground">
              <FlaskConical className="size-4 text-flame" aria-hidden />
              Serie sintética del experimento 001
            </p>
            <span className="rounded-full bg-tint px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-flame">
              Demostración — datos sintéticos
            </span>
          </div>
          <p className="mb-4 max-w-3xl text-xs leading-relaxed text-muted-foreground">
            151 días: 120 de baseline + 31 evaluados ({anomalias.metodo}, umbral
            z = {anomalias.umbral_z}). Franja sombreada = ventana de evaluación;
            el baseline de cada día usa exclusivamente su pasado.
          </p>
          <div className="h-72 sm:h-80">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={datos} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                <CartesianGrid stroke="#f0e6da" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="fecha"
                  tick={{ fill: "#82766d", fontSize: 10 }}
                  stroke="#e4d5c6"
                  interval={14}
                />
                <YAxis tick={{ fill: "#82766d", fontSize: 11 }} stroke="#e4d5c6" />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelStyle={{ color: "#82766d" }}
                  cursor={{ strokeDasharray: "3 3", stroke: "#b7a89c" }}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: "#82766d" }} />
                <ReferenceArea x1={desde} x2="03-31" fill="#e9a477" fillOpacity={0.08} />
                <Line
                  type="monotone"
                  dataKey="valor"
                  name="Conteo diario (sintético)"
                  stroke="#82766d"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Scatter
                  dataKey="yInyectada"
                  name="Inyectada"
                  fill="#c05f2c"
                  shape="triangle"
                  fillOpacity={0.95}
                />
                <Scatter
                  dataKey="yDetectada"
                  name="Detectada"
                  fill="#3e8e87"
                  shape="circle"
                  fillOpacity={0.9}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="min-w-0 border-border bg-card shadow-none">
          <CardContent className="p-5 sm:p-6">
            <p className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight text-foreground">
              <Target className="size-4 text-viirs" aria-hidden />
              Las 4 anomalías, al detalle
            </p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Valor observado vs. esperado (mediana del día de semana, 8
              semanas) y su z.
            </p>
            <div className="mt-4 overflow-x-auto rounded-xl border border-border">
              <Table>
                <TableHeader>
                  <TableRow className="border-border/70 hover:bg-transparent">
                    <TableHead className="text-muted-foreground">Fecha</TableHead>
                    <TableHead className="text-right text-muted-foreground">Valor</TableHead>
                    <TableHead className="text-right text-muted-foreground">Esperado</TableHead>
                    <TableHead className="text-right text-muted-foreground">z</TableHead>
                    <TableHead className="text-muted-foreground">Dirección</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {anomalias.detalle.map((d) => (
                    <TableRow key={d.fecha} className="border-border/60">
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {d.fecha}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-foreground">
                        {d.valor}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">
                        {d.esperado.toFixed(1)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs font-semibold text-flame">
                        {d.z > 0 ? "+" : ""}
                        {d.z.toFixed(1)}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {d.direccion === "alto" ? "pico alto" : "caída"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>

        <div className="rounded-2xl border border-[#ecc7b3] bg-[#fdf3ec] p-5 sm:p-6">
          <p className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight text-[#8a4516]">
            <ShieldAlert className="size-4 text-flame" aria-hidden />
            Lo que esto NO demuestra
          </p>
          <div className="mt-3 space-y-3 text-xs leading-relaxed text-[#a3765a]">
            <p>
              <strong className="text-[#8a4516]">{anomalias.datos}.</strong> La
              serie es un generador con semilla fija (nivel base + ciclo
              semanal + ruido 8% + 4 anomalías inyectadas). No representa la
              actividad real de fuegos en Paraguay.
            </p>
            <p>
              <strong className="text-[#8a4516]">No hay modelos predictivos
              validados</strong> y no los presentamos: sin datos reales del
              piloto no hay validación posible, y presentar un modelo entrenado
              con sintéticos como predicción es exactamente lo que esta misión
              prohíbe. La persistencia queda como baseline a vencer; su MAE
              también es sintético.
            </p>
            <p>
              Lo valioso del experimento: cazó dos defectos reales del método
              (MAD subestimado por weekday → z inflado; anomalías viejas
              contaminando la mediana). Ambas lecciones quedaron documentadas en
              el código fuente del detector.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
