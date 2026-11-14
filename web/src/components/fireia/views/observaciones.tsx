"use client";

// Observaciones satelitales (v3 — explorador de datos): rail de filtros a
// la izquierda (pegajoso) y resultados a la derecha. Presentación simple
// primero (fecha, ubicación, sensor, confianza, intensidad); el detalle
// completo se abre a pedido. En móvil, tarjetas en lugar de tabla.

import { useMemo, useState } from "react";
import { ChevronRight, RotateCcw, Satellite, SlidersHorizontal } from "lucide-react";

import { DetalleObservacion } from "@/components/fireia/detalle-observacion";
import { DataGate } from "@/components/fireia/data-gate";
import { HeroCompacto } from "@/components/fireia/section-hero";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Observacion } from "@/lib/mvp-types";

function SensorChip({ sensor }: { sensor: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold">
      <span
        className={`size-2 rounded-full ${sensor === "MODIS" ? "bg-modis" : "bg-viirs"}`}
        aria-hidden
      />
      <span className={sensor === "MODIS" ? "text-modis" : "text-viirs"}>
        {sensor}
      </span>
    </span>
  );
}

const CONFIANZA_SIMPLE: Record<string, string> = {
  l: "confianza baja",
  nominal: "confianza media",
  high: "confianza alta",
};

export function ObservacionesView() {
  return (
    <div className="space-y-5">
      <HeroCompacto
        indice="02"
        categoria="Exploración · registro crudo"
        title="Lo que los satélites vieron"
        lede="Cada punto que MODIS o VIIRS detectaron como posible foco de calor: cuándo, dónde, con qué confianza y con qué intensidad estimada. Tocá cualquier registro para verlo completo."
      />
      <DataGate>
        {(datos) => <Observaciones observaciones={datos.observaciones} />}
      </DataGate>
    </div>
  );
}

function Observaciones({ observaciones }: { observaciones: Observacion[] }) {
  const [sensor, setSensor] = useState<string>("todos");
  const [fecha, setFecha] = useState<string>("todas");
  const [departamento, setDepartamento] = useState<string>("todos");
  const [daynight, setDaynight] = useState<string>("todos");
  const [detalle, setDetalle] = useState<Observacion | null>(null);

  const fechas = useMemo(
    () => Array.from(new Set(observaciones.map((o) => o.acq_date))).sort(),
    [observaciones],
  );
  const departamentos = useMemo(
    () =>
      Array.from(
        new Set(
          observaciones
            .filter((o) => o.departamento)
            .map((o) => o.departamento as string),
        ),
      ).sort(),
    [observaciones],
  );

  const conteoSensor = useMemo(() => {
    const modis = observaciones.filter((o) => o.sensor === "MODIS").length;
    return { MODIS: modis, VIIRS: observaciones.length - modis };
  }, [observaciones]);

  const filtradas = useMemo(() => {
    const base = observaciones.filter((o) => {
      if (sensor !== "todos" && o.sensor !== sensor) return false;
      if (fecha !== "todas" && o.acq_date !== fecha) return false;
      if (departamento !== "todos" && o.departamento !== departamento)
        return false;
      if (daynight !== "todos" && o.daynight !== daynight) return false;
      return true;
    });
    return [...base].sort((a, b) =>
      b.acq_datetime_utc.localeCompare(a.acq_datetime_utc),
    );
  }, [observaciones, sensor, fecha, departamento, daynight]);

  const hayFiltros =
    sensor !== "todos" ||
    fecha !== "todas" ||
    departamento !== "todos" ||
    daynight !== "todos";

  const limpiar = () => {
    setSensor("todos");
    setFecha("todas");
    setDepartamento("todos");
    setDaynight("todos");
  };

  if (observaciones.length === 0) {
    return (
      <Card className="border-dashed bg-[#fffdfb] shadow-none">
        <CardContent className="flex flex-col items-center gap-2 py-14 text-center">
          <p className="text-sm font-medium text-foreground">
            No hay observaciones en el almacén
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            Cuando exista una ingesta real, cada detección de MODIS y VIIRS
            aparecerá aquí con su detalle completo.
          </p>
        </CardContent>
      </Card>
    );
  }

  const rail = (
    <div className="space-y-3.5">
      <p className="fireia-kicker flex items-center gap-2 text-muted-foreground">
        <SlidersHorizontal className="size-3.5" aria-hidden />
        Refinar
      </p>
      <div>
        <label htmlFor="obs-sensor" className="mb-1 block text-[11px] font-medium text-muted-foreground">
          Sensor
        </label>
        <Select value={sensor} onValueChange={setSensor}>
          <SelectTrigger
            id="obs-sensor"
            className="h-9 w-full rounded-xl border-border bg-card text-[13px]"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Todos los sensores</SelectItem>
            <SelectItem value="MODIS">MODIS ({conteoSensor.MODIS})</SelectItem>
            <SelectItem value="VIIRS">VIIRS ({conteoSensor.VIIRS})</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <label htmlFor="obs-fecha" className="mb-1 block text-[11px] font-medium text-muted-foreground">
          Fecha
        </label>
        <Select value={fecha} onValueChange={setFecha}>
          <SelectTrigger
            id="obs-fecha"
            className="h-9 w-full rounded-xl border-border bg-card text-[13px]"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todas">Todas las fechas</SelectItem>
            {fechas.map((f) => (
              <SelectItem key={f} value={f}>
                {f}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div>
        <label htmlFor="obs-dep" className="mb-1 block text-[11px] font-medium text-muted-foreground">
          Departamento
        </label>
        <Select value={departamento} onValueChange={setDepartamento}>
          <SelectTrigger
            id="obs-dep"
            className="h-9 w-full rounded-xl border-border bg-card text-[13px]"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-h-72">
            <SelectItem value="todos">Todo el país</SelectItem>
            {departamentos.map((d) => (
              <SelectItem key={d} value={d}>
                {d}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div>
        <label htmlFor="obs-dn" className="mb-1 block text-[11px] font-medium text-muted-foreground">
          Momento del pase
        </label>
        <Select value={daynight} onValueChange={setDaynight}>
          <SelectTrigger
            id="obs-dn"
            className="h-9 w-full rounded-xl border-border bg-card text-[13px]"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Día y noche</SelectItem>
            <SelectItem value="D">Solo día</SelectItem>
            <SelectItem value="N">Solo noche</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* distribución por sensor, siempre honesta */}
      <div className="space-y-2 border-t border-border pt-3.5">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          En el almacén
        </p>
        {(
          [
            ["MODIS", conteoSensor.MODIS, "bg-modis"],
            ["VIIRS", conteoSensor.VIIRS, "bg-viirs"],
          ] as Array<[string, number, string]>
        ).map(([nombre, n, color]) => (
          <div key={nombre} className="flex items-center gap-2 text-xs">
            <span className={`size-2 rounded-full ${color}`} aria-hidden />
            <span className="w-12 shrink-0 font-semibold text-foreground">{nombre}</span>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
              <span
                className={`block h-full rounded-full ${color}`}
                style={{
                  width: `${
                    observaciones.length > 0
                      ? Math.max((n / observaciones.length) * 100, 3)
                      : 0
                  }%`,
                }}
              />
            </span>
            <span className="w-8 text-right tabular-nums text-muted-foreground">{n}</span>
          </div>
        ))}
      </div>

      {hayFiltros && (
        <Button
          variant="outline"
          size="sm"
          onClick={limpiar}
          className="w-full rounded-full border-border bg-card"
        >
          <RotateCcw className="size-3.5" aria-hidden />
          Limpiar filtros
        </Button>
      )}
    </div>
  );

  return (
    <div className="grid gap-5 lg:grid-cols-12">
      {/* --- rail de filtros (pegajoso en escritorio) --- */}
      <aside className="min-w-0 lg:col-span-3">
        <div className="rounded-2xl border border-border bg-card p-4 lg:sticky lg:top-24">
          {rail}
        </div>
      </aside>

      {/* --- resultados --- */}
      <div className="min-w-0 space-y-3 lg:col-span-9">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            <strong className="font-display text-xl text-foreground">
              {filtradas.length}
            </strong>{" "}
            de {observaciones.length} observaciones
            {hayFiltros ? " con los filtros activos" : ""}
          </p>
          <Badge
            variant="outline"
            className="rounded-full border-transparent bg-secondary px-2.5 py-1 text-[10px] text-muted-foreground"
          >
            hora en UTC
          </Badge>
        </div>

        {/* --- tabla (escritorio) --- */}
        <div className="hidden overflow-x-auto rounded-2xl border border-border bg-card md:block">
          <Table>
            <TableHeader>
              <TableRow className="border-border/70 hover:bg-transparent">
                <TableHead className="text-muted-foreground">Cuándo (UTC)</TableHead>
                <TableHead className="text-muted-foreground">Sensor</TableHead>
                <TableHead className="text-muted-foreground">Dónde</TableHead>
                <TableHead className="text-muted-foreground">Confianza</TableHead>
                <TableHead className="text-right text-muted-foreground">
                  Intensidad
                </TableHead>
                <TableHead className="text-muted-foreground">Fuente</TableHead>
                <TableHead className="w-10" aria-label="Ver detalle" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtradas.map((o) => (
                <TableRow
                  key={o.obs_id}
                  className="cursor-pointer border-border/60 transition-colors hover:bg-[#fdf6ee]"
                  onClick={() => setDetalle(o)}
                >
                  <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                    {o.acq_datetime_utc.slice(0, 16).replace("T", " ")}
                  </TableCell>
                  <TableCell>
                    <SensorChip sensor={o.sensor} />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {o.departamento ?? "fuera del país"}
                    {o.distrito ? ` · ${o.distrito}` : ""}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {CONFIANZA_SIMPLE[o.confidence_band] ?? o.confidence_band}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs text-muted-foreground">
                    {o.frp !== null ? `${o.frp.toFixed(1)} MW` : "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {o.satellite_name}
                  </TableCell>
                  <TableCell>
                    <ChevronRight
                      className="size-4 text-[#c4ae97]"
                      aria-hidden
                    />
                  </TableCell>
                </TableRow>
              ))}
              {filtradas.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    Ninguna observación coincide con los filtros actuales.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        {/* --- tarjetas (móvil) --- */}
        <div className="space-y-2 md:hidden">
          {filtradas.map((o) => (
            <button
              key={o.obs_id}
              type="button"
              onClick={() => setDetalle(o)}
              className="w-full rounded-xl border border-border bg-card px-4 py-3 text-left outline-none transition-colors hover:bg-[#fffdfb] focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex items-center justify-between gap-2">
                <SensorChip sensor={o.sensor} />
                <span className="font-mono text-[11px] text-muted-foreground">
                  {o.acq_datetime_utc.slice(0, 16).replace("T", " ")}
                </span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="truncate">
                  {o.departamento ?? "fuera del país"}
                  {o.distrito ? ` · ${o.distrito}` : ""}
                </span>
                <span className="shrink-0 tabular-nums">
                  {o.frp !== null ? `${o.frp.toFixed(1)} MW` : "—"}
                </span>
              </div>
            </button>
          ))}
          {filtradas.length === 0 && (
            <Card className="border-dashed bg-[#fffdfb] shadow-none">
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                Ninguna observación coincide con los filtros actuales.
              </CardContent>
            </Card>
          )}
        </div>

        <p className="flex items-center gap-1.5 text-[11px] leading-relaxed text-muted-foreground/85">
          <Satellite className="size-3 shrink-0" aria-hidden />
          Una detección no es un incendio confirmado: es un píxel más caliente
          de lo normal, con su confianza declarada.
        </p>
      </div>

      {/* --- detalle completo --- */}
      <Dialog open={detalle !== null} onOpenChange={(v) => !v && setDetalle(null)}>
        <DialogContent
          aria-describedby={undefined}
          className="max-h-[85vh] overflow-y-auto rounded-2xl border-border bg-card sm:max-w-lg"
        >
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2.5 font-display text-lg tracking-tight text-foreground">
              {detalle && <SensorChip sensor={detalle.sensor} />}
              Detección satelital
            </DialogTitle>
            <DialogDescription className="break-all font-mono text-[11px] text-muted-foreground">
              {detalle?.obs_id}
            </DialogDescription>
          </DialogHeader>
          {detalle && <DetalleObservacion o={detalle} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

export { SensorChip };
