"use client";

// Informes (v4 — mesa de redacción): la configuración a la izquierda y la
// vista previa compuesta como una hoja de informe real (papel blanco,
// titular display, cifras y distribución). La exportación JSON/CSV se
// genera en el navegador con los datos cargados (sin backend).

import { useMemo, useState } from "react";
import { Download } from "lucide-react";

import { DataGate } from "@/components/fireia/data-gate";
import type { DatosMVP } from "@/components/fireia/data-provider";
import { SectionHero } from "@/components/fireia/section-hero";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function InformesView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="01"
        categoria="Información · informes"
        title="Armá el resumen del período."
        lede="Elegí período y región; la vista previa se recalcula al instante con los datos del almacén cargado, en tu navegador. Exportá el informe en JSON o la serie diaria en CSV."
      />
      <DataGate>{(datos) => <GeneradorInformes datos={datos} />}</DataGate>
    </div>
  );
}

function GeneradorInformes({ datos }: { datos: DatosMVP }) {
  const fechas = useMemo(
    () => Array.from(new Set(datos.observaciones.map((o) => o.acq_date))).sort(),
    [datos.observaciones],
  );
  const departamentos = useMemo(
    () =>
      Array.from(
        new Set(
          datos.observaciones
            .filter((o) => o.departamento)
            .map((o) => o.departamento as string),
        ),
      ).sort(),
    [datos.observaciones],
  );

  const [desde, setDesde] = useState(fechas[0] ?? "todas");
  const [hasta, setHasta] = useState(fechas[fechas.length - 1] ?? "todas");
  const [region, setRegion] = useState("todo");

  const resumen = useMemo(() => {
    const obs = datos.observaciones.filter((o) => {
      if (o.acq_date < desde) return false;
      if (o.acq_date > hasta) return false;
      if (region !== "todo" && o.departamento !== region) return false;
      return true;
    });
    const modis = obs.filter((o) => o.sensor === "MODIS").length;
    const viirs = obs.length - modis;
    const porDep = new Map<string, number>();
    for (const o of obs) {
      const d = o.departamento ?? "fuera del país";
      porDep.set(d, (porDep.get(d) ?? 0) + 1);
    }
    const topDias = new Map<string, number>();
    for (const o of obs) topDias.set(o.acq_date, (topDias.get(o.acq_date) ?? 0) + 1);
    const eventosRelacionados = region === "todo"
      ? datos.eventos.length
      : datos.eventos.filter((e) =>
          e.miembros.some((m) => m.departamento === region),
        ).length;

    return {
      total: obs.length,
      modis,
      viirs,
      diasDistintos: topDias.size,
      departamentos: Array.from(porDep.entries()).sort((a, b) => b[1] - a[1]),
      diaMasActivo:
        Array.from(topDias.entries()).sort((a, b) => b[1] - a[1])[0] ?? null,
      eventos: eventosRelacionados,
    };
  }, [datos, desde, hasta, region]);

  function _descargar(nombre: string, contenido: string, tipo: string) {
    const blob = new Blob([contenido], { type: tipo });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nombre;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportarJson() {
    const informe = {
      fireia_informe: true,
      origen: datos.health.data_source,
      generado_en: new Date().toISOString(),
      periodo: { desde, hasta },
      region,
      resumen,
    };
    _descargar(
      `fireia_informe_${desde}_${hasta}.json`,
      JSON.stringify(informe, null, 2),
      "application/json",
    );
  }

  function exportarCsv() {
    const serie = datos.stats.nacional_dia
      .filter((s) => s.acq_date >= desde && s.acq_date <= hasta)
      .sort((a, b) => a.acq_date.localeCompare(b.acq_date));
    const lineas = ["fecha,producto,detecciones,frp_total"];
    for (const s of serie) {
      lineas.push(
        `${s.acq_date},${s.product},${s.detecciones},${Number(s.frp_total ?? 0).toFixed(2)}`,
      );
    }
    _descargar(
      `fireia_serie_${desde}_${hasta}.csv`,
      lineas.join("\n"),
      "text/csv",
    );
  }


  const maxDep = Math.max(...resumen.departamentos.map(([, n]) => n), 1);

  return (
    <div className="grid gap-5 lg:grid-cols-12">
      {/* --- configuración --- */}
      <aside className="min-w-0 lg:col-span-4">
        <div className="space-y-4 rounded-2xl border border-border bg-card p-5 lg:sticky lg:top-24">
          <p className="fireia-kicker text-muted-foreground">Definí el informe</p>
          <div>
            <label htmlFor="inf-desde" className="mb-1 block text-[11px] font-medium text-muted-foreground">
              Desde
            </label>
            <Select value={desde} onValueChange={setDesde}>
              <SelectTrigger id="inf-desde" className="h-10 w-full rounded-xl border-border bg-card text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {fechas.map((f) => (
                  <SelectItem key={f} value={f}>
                    {f}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label htmlFor="inf-hasta" className="mb-1 block text-[11px] font-medium text-muted-foreground">
              Hasta
            </label>
            <Select value={hasta} onValueChange={setHasta}>
              <SelectTrigger id="inf-hasta" className="h-10 w-full rounded-xl border-border bg-card text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {fechas.map((f) => (
                  <SelectItem key={f} value={f}>
                    {f}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label htmlFor="inf-region" className="mb-1 block text-[11px] font-medium text-muted-foreground">
              Región
            </label>
            <Select value={region} onValueChange={setRegion}>
              <SelectTrigger id="inf-region" className="h-10 w-full rounded-xl border-border bg-card text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="max-h-72">
                <SelectItem value="todo">Todo el país</SelectItem>
                {departamentos.map((d) => (
                  <SelectItem key={d} value={d}>
                    {d}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            size="sm"
            onClick={exportarJson}
            className="w-full rounded-full bg-action text-white hover:bg-action/90"
          >
            <Download className="size-3.5" aria-hidden />
            Exportar informe (JSON)
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={exportarCsv}
            className="w-full rounded-full"
          >
            <Download className="size-3.5" aria-hidden />
            Exportar serie diaria (CSV)
          </Button>
          <p id="inf-export-nota" className="text-[11px] leading-relaxed text-muted-foreground">
            La exportación se genera en tu navegador con los datos del almacén
            cargado (origen: {datos.health.data_source}); incluye membrete,
            cifras y serie del período seleccionado.
          </p>
        </div>
      </aside>

      {/* --- hoja del informe --- */}
      <div className="min-w-0 lg:col-span-8">
        <article className="fireia-paper rounded-3xl border border-border bg-white px-6 py-8 sm:px-10 sm:py-10">
          {/* membrete */}
          <div className="flex flex-wrap items-start justify-between gap-3 border-b-2 border-foreground/85 pb-4">
            <div>
              <p className="fireia-kicker text-flame">FIREIA · Informe de actividad</p>
              <h2 className="mt-1.5 font-display text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                {region === "todo" ? "Paraguay, todo el territorio" : region}
              </h2>
              <p className="mt-1 font-mono text-xs text-muted-foreground">
                {desde} → {hasta}
              </p>
            </div>
            <Badge
              variant="outline"
              className="rounded-full border-transparent bg-tint px-2.5 py-1 text-[10px] font-medium text-flame"
            >
              origen: {datos.health.data_source}
            </Badge>
          </div>

          {/* cifras principales */}
          <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
            {(
              [
                ["Detecciones", resumen.total],
                ["Días activos", resumen.diasDistintos],
                ["Eventos", resumen.eventos],
              ] as Array<[string, number]>
            ).map(([k, v]) => (
              <div key={k}>
                <p className="fireia-index text-4xl text-foreground">{v}</p>
                <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {k}
                </p>
              </div>
            ))}
            <div>
              <p className="font-display text-xl font-semibold text-foreground sm:text-2xl">
                {resumen.diaMasActivo
                  ? resumen.diaMasActivo[0].slice(5)
                  : "—"}
              </p>
              <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Día más activo
                {resumen.diaMasActivo
                  ? ` · ${resumen.diaMasActivo[1]} detecciones`
                  : ""}
              </p>
            </div>
          </div>

          {/* por sensor */}
          <div className="mt-7 border-t border-border/70 pt-5">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Por sensor
            </p>
            <div className="mt-2.5 flex h-3 max-w-md overflow-hidden rounded-full bg-secondary">
              <span
                className="h-full bg-modis"
                style={{
                  width: `${
                    resumen.total > 0 ? (resumen.modis / resumen.total) * 100 : 0
                  }%`,
                }}
                title={`MODIS: ${resumen.modis}`}
              />
              <span
                className="h-full bg-viirs"
                style={{
                  width: `${
                    resumen.total > 0 ? (resumen.viirs / resumen.total) * 100 : 0
                  }%`,
                }}
                title={`VIIRS: ${resumen.viirs}`}
              />
            </div>
            <div className="mt-2 flex gap-4 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-modis" aria-hidden />
                MODIS · {resumen.modis}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-viirs" aria-hidden />
                VIIRS · {resumen.viirs}
              </span>
              <span className="text-[11px] text-muted-foreground/80">
                conteos comparables; FRP nunca se suma entre sensores
              </span>
            </div>
          </div>

          {/* distribución territorial como barras */}
          <div className="mt-6 border-t border-border/70 pt-5">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Distribución por departamento
            </p>
            <div className="mt-3 max-h-56 space-y-2.5 overflow-y-auto pr-1">
              {resumen.departamentos.map(([d, n]) => (
                <div key={d} className="flex items-center gap-3">
                  <span className="w-32 shrink-0 truncate text-xs text-foreground sm:w-40">
                    {d}
                  </span>
                  <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-secondary">
                    <span
                      className="block h-full rounded-full bg-[#e9a477]"
                      style={{ width: `${(n / maxDep) * 100}%` }}
                    />
                  </span>
                  <span className="w-10 text-right font-mono text-xs tabular-nums text-muted-foreground">
                    {n}
                  </span>
                </div>
              ))}
              {resumen.departamentos.length === 0 && (
                <p className="py-4 text-center text-xs text-muted-foreground">
                  Sin detecciones en la selección actual.
                </p>
              )}
            </div>
          </div>

          {/* pie del informe */}
          <p className="mt-7 border-t border-border/70 pt-4 text-[11px] leading-relaxed text-muted-foreground/85">
            Nota de calidad: esta vista previa agrega únicamente el almacén
            cargado ({datos.health.cobertura.desde} →{" "}
            {datos.health.cobertura.hasta}), de origen{" "}
            {datos.health.data_source}. Los días sin datos del período no se
            cuentan como días sin fuego.
          </p>
        </article>
      </div>
    </div>
  );
}
