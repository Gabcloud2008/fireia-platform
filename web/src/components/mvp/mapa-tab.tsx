"use client";

// Mapa de Paraguay (v3 — modo explorador): el mapa ocupa casi toda la
// pantalla; los filtros viven en una barra compacta y la leyenda flota
// sobre el mapa. Al seleccionar una observación o evento se abre el
// panel de detalles (lateral en escritorio, inferior en móvil).

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { Filter, Layers, RotateCcw, X } from "lucide-react";

import { DetalleObservacion } from "@/components/fireia/detalle-observacion";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { useIsMobile } from "@/hooks/use-mobile";
import type { Evento, Observacion } from "@/lib/mvp-types";

const MapaMap = dynamic(() => import("./mapa-map"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[62vh] min-h-[420px] items-center justify-center rounded-2xl border border-border bg-secondary/50 text-sm text-muted-foreground md:h-[calc(100dvh-330px)] md:min-h-[500px]">
      Cargando mapa…
    </div>
  ),
});

interface Props {
  observaciones: Observacion[];
  eventos: Evento[];
  departamentos: GeoJSON.FeatureCollection | null;
}

function ChipSensor({
  activo,
  color,
  onChange,
  children,
}: {
  activo: boolean;
  color: string;
  onChange: (v: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={activo}
      onClick={() => onChange(!activo)}
      className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-[13px] outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring ${
        activo
          ? "border-transparent bg-tint font-medium text-foreground"
          : "border-border bg-card text-muted-foreground hover:bg-secondary"
      }`}
    >
      <span
        className={`inline-block size-2.5 rounded-full transition-opacity ${color} ${
          activo ? "opacity-100" : "opacity-35"
        }`}
        aria-hidden
      />
      {children}
    </button>
  );
}

function ChipCapa({
  activo,
  onChange,
  children,
}: {
  activo: boolean;
  onChange: (v: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex h-9 cursor-pointer items-center gap-2 rounded-full border border-border bg-card px-3 text-[13px] text-muted-foreground transition-colors hover:bg-secondary">
      <Switch checked={activo} onCheckedChange={onChange} className="scale-90" />
      {children}
    </label>
  );
}

export function MapaTab({ observaciones, eventos, departamentos }: Props) {
  const esMovil = useIsMobile();

  const fechas = useMemo(
    () => Array.from(new Set(observaciones.map((o) => o.acq_date))).sort(),
    [observaciones],
  );
  const departamentosAfectados = useMemo(
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

  const [verModis, setVerModis] = useState(true);
  const [verViirs, setVerViirs] = useState(true);
  const [daynight, setDaynight] = useState<"todos" | "D" | "N">("todos");
  const [fecha, setFecha] = useState<string>("todas");
  const [soloDentro, setSoloDentro] = useState(false);
  const [departamento, setDepartamento] = useState<string | null>(null);
  const [capas, setCapas] = useState({
    departamentos: true,
    observaciones: true,
    eventos: true,
  });
  const [detalleObs, setDetalleObs] = useState<Observacion | null>(null);
  const [detalleEvento, setDetalleEvento] = useState<Evento | null>(null);

  const filtradas = useMemo(
    () =>
      observaciones.filter((o) => {
        if (o.sensor === "MODIS" && !verModis) return false;
        if (o.sensor === "VIIRS" && !verViirs) return false;
        if (daynight !== "todos" && o.daynight !== daynight) return false;
        if (fecha !== "todas" && o.acq_date !== fecha) return false;
        if (soloDentro && !o.dentro_pais) return false;
        if (departamento && o.departamento !== departamento) return false;
        return true;
      }),
    [observaciones, verModis, verViirs, daynight, fecha, soloDentro, departamento],
  );

  const hayFiltros =
    fecha !== "todas" ||
    daynight !== "todos" ||
    soloDentro ||
    departamento !== null ||
    !verModis ||
    !verViirs;

  const limpiar = () => {
    setVerModis(true);
    setVerViirs(true);
    setDaynight("todos");
    setFecha("todas");
    setSoloDentro(false);
    setDepartamento(null);
  };

  if (observaciones.length === 0) {
    return (
      <Card className="border-dashed bg-[#fffdfb] shadow-none">
        <CardContent className="flex flex-col items-center gap-2 py-14 text-center">
          <p className="text-sm font-medium text-foreground">
            El almacén no tiene observaciones para mostrar
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            Cuando exista una ingesta real de datos, las detecciones de MODIS y
            VIIRS aparecerán aquí sobre el mapa de Paraguay.
          </p>
        </CardContent>
      </Card>
    );
  }

  const filtros = (
    <div className="flex flex-wrap items-center gap-2">
      <ChipSensor activo={verModis} color="bg-modis" onChange={setVerModis}>
        MODIS (1 km)
      </ChipSensor>
      <ChipSensor activo={verViirs} color="bg-viirs" onChange={setVerViirs}>
        VIIRS (375 m)
      </ChipSensor>

      <span className="hidden h-5 w-px bg-border sm:block" aria-hidden />

      <Select value={fecha} onValueChange={setFecha}>
        <SelectTrigger
          aria-label="Filtrar por fecha de adquisición"
          className="h-9 w-[158px] rounded-full border-border bg-card text-[13px] text-foreground"
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

      <Select
        value={daynight}
        onValueChange={(v) => setDaynight(v as "todos" | "D" | "N")}
      >
        <SelectTrigger
          aria-label="Filtrar por día o noche"
          className="h-9 w-[142px] rounded-full border-border bg-card text-[13px] text-foreground"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="todos">Día y noche</SelectItem>
          <SelectItem value="D">Solo día</SelectItem>
          <SelectItem value="N">Solo noche</SelectItem>
        </SelectContent>
      </Select>

      <Select
        value={departamento ?? "todos"}
        onValueChange={(v) => setDepartamento(v === "todos" ? null : v)}
      >
        <SelectTrigger
          aria-label="Filtrar por departamento"
          className="h-9 w-[182px] rounded-full border-border bg-card text-[13px] text-foreground"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="max-h-72">
          <SelectItem value="todos">Todo el país</SelectItem>
          {departamentosAfectados.map((d) => (
            <SelectItem key={d} value={d}>
              {d}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <label className="flex h-9 cursor-pointer items-center gap-2 rounded-full border border-border bg-card px-3 text-[13px] text-muted-foreground">
        <Switch
          checked={soloDentro}
          onCheckedChange={setSoloDentro}
          aria-label="Mostrar solo detecciones dentro del país"
        />
        Solo dentro del país
      </label>

      <span className="hidden h-5 w-px bg-border sm:block" aria-hidden />

      <ChipCapa
        activo={capas.departamentos}
        onChange={(v) => setCapas((c) => ({ ...c, departamentos: v }))}
      >
        <Layers className="size-3.5" aria-hidden />
        Departamentos
      </ChipCapa>
      <ChipCapa
        activo={capas.eventos}
        onChange={(v) => setCapas((c) => ({ ...c, eventos: v }))}
      >
        <Layers className="size-3.5" aria-hidden />
        Eventos
      </ChipCapa>

      {hayFiltros && (
        <Button
          variant="ghost"
          size="sm"
          onClick={limpiar}
          className="h-9 rounded-full px-3 text-[13px] text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <RotateCcw className="size-3.5" aria-hidden />
          Limpiar
        </Button>
      )}
    </div>
  );

  return (
    <div className="space-y-3">
      {/* --- barra de herramientas: siempre visible en escritorio, plegable en móvil --- */}
      <div className="sticky top-16 z-20 rounded-2xl border border-border bg-card/90 px-3 py-2.5 shadow-[0_10px_24px_-18px_rgb(57_51_47/0.4)] backdrop-blur-md sm:px-4">
        {esMovil ? (
          <Collapsible defaultOpen={false}>
            <div className="flex items-center justify-between gap-2">
              <CollapsibleTrigger asChild>
                <Button
                  variant="ghost"
                  className="gap-2 rounded-full px-3 text-sm font-medium text-foreground hover:bg-secondary"
                >
                  <Filter className="size-4 text-flame" aria-hidden />
                  Filtros y capas
                  {hayFiltros && (
                    <span className="rounded-full bg-tint px-1.5 text-[10px] font-semibold text-flame">
                      activos
                    </span>
                  )}
                </Button>
              </CollapsibleTrigger>
              <p className="text-xs tabular-nums text-muted-foreground">
                {filtradas.length} de {observaciones.length}
              </p>
            </div>
            <CollapsibleContent className="pt-2.5">
              <div className="flex flex-col items-start gap-2">{filtros}</div>
            </CollapsibleContent>
          </Collapsible>
        ) : (
          <>
            {filtros}
            <p className="mt-2 text-[11px] tabular-nums text-muted-foreground">
              {filtradas.length} de {observaciones.length} detecciones visibles ·
              tocá un punto o un evento para ver su detalle
            </p>
          </>
        )}
      </div>

      {/* --- mapa con leyenda flotante --- */}
      <div className="relative">
        <MapaMap
          observaciones={filtradas}
          eventos={eventos}
          departamentos={departamentos}
          departamentoSeleccionado={departamento}
          onSelectDepartamento={(nombre) => setDepartamento(nombre)}
          onSelectObservacion={(o) => {
            setDetalleEvento(null);
            setDetalleObs(o);
          }}
          onSelectEvento={(e) => {
            setDetalleObs(null);
            setDetalleEvento(e);
          }}
          capas={capas}
        />

        <div
          className="pointer-events-none absolute bottom-3 left-3 z-10 hidden flex-col gap-1.5 rounded-xl border border-border bg-card/92 px-3.5 py-3 text-[11px] text-muted-foreground shadow-[0_10px_28px_-16px_rgb(57_51_47/0.45)] backdrop-blur sm:flex"
          aria-hidden
        >
          <span className="flex items-center gap-2">
            <span className="size-2.5 rounded-full bg-modis" />
            Detección MODIS · 1 km
          </span>
          <span className="flex items-center gap-2">
            <span className="size-2.5 rounded-full bg-viirs" />
            Detección VIIRS · 375 m
          </span>
          <span className="flex items-center gap-2">
            <span className="size-3 rounded-full border-2 border-foreground" />
            Evento agrupado (centroide)
          </span>
          <span className="flex items-center gap-2">
            <span className="size-3 rounded-sm border border-[#c4ae97] bg-[#e5d3be]/40" />
            Departamentos — geoBoundaries (CC BY 4.0)
          </span>
        </div>
      </div>

      {filtradas.length === 0 && (
        <Card className="border-dashed bg-[#fffdfb] shadow-none">
          <CardContent className="flex flex-col items-center gap-2 py-8 text-center">
            <p className="text-sm font-medium text-foreground">
              Ninguna detección coincide con los filtros actuales
            </p>
            <p className="text-sm text-muted-foreground">
              Probá ampliar el rango de fechas o quitar el filtro de departamento.
            </p>
            <Button variant="outline" size="sm" onClick={limpiar} className="mt-1 rounded-full">
              <RotateCcw className="size-3.5" aria-hidden />
              Limpiar filtros
            </Button>
          </CardContent>
        </Card>
      )}

      {/* --- panel de detalles: lateral en escritorio, inferior en móvil --- */}
      <Sheet
        open={detalleObs !== null || detalleEvento !== null}
        onOpenChange={(v) => {
          if (!v) {
            setDetalleObs(null);
            setDetalleEvento(null);
          }
        }}
      >
        <SheetContent
          side={esMovil ? "bottom" : "right"}
          aria-describedby={undefined}
          className={
            esMovil
              ? "max-h-[85vh] gap-0 overflow-y-auto rounded-t-2xl border-border bg-card p-0"
              : "w-[440px] max-w-[92vw] gap-0 overflow-y-auto border-border bg-card p-0 sm:max-w-[440px]"
          }
        >
          <SheetHeader className="space-y-0 border-b border-border px-5 py-4 text-left">
            <SheetTitle className="font-display text-base font-semibold tracking-tight text-foreground">
              {detalleObs
                ? "Detección satelital seleccionada"
                : "Evento de co-detección"}
            </SheetTitle>
            <p className="pt-0.5 text-[11px] text-muted-foreground">
              {detalleObs
                ? `${detalleObs.sensor} · ${detalleObs.satellite_name}`
                : detalleEvento
                  ? `${detalleEvento.n_observaciones} observaciones agrupadas`
                  : ""}
            </p>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => {
                setDetalleObs(null);
                setDetalleEvento(null);
              }}
              aria-label="Cerrar panel de detalles"
              className="absolute right-3 top-3 size-8 rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <X className="size-4" aria-hidden />
            </Button>
          </SheetHeader>
          <div className="px-5 py-4">
            {detalleObs && <DetalleObservacion o={detalleObs} />}
            {detalleEvento && <DetalleEvento evento={detalleEvento} />}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function DetalleEvento({ evento }: { evento: Evento }) {
  const frpPorSensor = Object.entries(evento.frp_por_producto ?? {});
  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-secondary/70 px-4 py-3">
        <p className="text-sm leading-relaxed text-foreground">
          Un <strong>evento</strong> es una agrupación analítica: varias
          detecciones de MODIS y VIIRS cayeron en la misma ventana de espacio y
          tiempo y FIREIA las agrupa para estudiarlas juntas. No es
          necesariamente un incendio individual confirmado.
        </p>
      </div>
      <dl className="space-y-2 text-sm">
        {(
          [
            ["Observaciones agrupadas", `${evento.n_observaciones}`],
            [
              "Duración del grupo",
              `${evento.duracion_segundos} segundos`,
            ],
            [
              "Dispersión de los miembros",
              `${evento.dispersion_metros} m (distancia promedio al centro)`,
            ],
            [
              "Diámetro máximo",
              `${evento.diametro_metros?.toFixed(0) ?? "—"} m`,
            ],
            ["Satélites involucrados", evento.satelites.join(", ")],
            [
              "Primera observación",
              evento.primera_obs_utc.replace("T", " ").replace("Z", ""),
            ],
            [
              "Última observación",
              evento.ultima_obs_utc.replace("T", " ").replace("Z", ""),
            ],
          ] as Array<[string, string]>
        ).map(([k, v]) => (
          <div
            key={k}
            className="flex items-start justify-between gap-4 border-b border-border/60 pb-2 last:border-0"
          >
            <dt className="shrink-0 text-xs text-muted-foreground">{k}</dt>
            <dd className="text-right text-xs font-medium text-foreground">{v}</dd>
          </div>
        ))}
      </dl>
      {frpPorSensor.length > 0 && (
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Intensidad por sensor (no se suman)
          </p>
          <div className="mt-1.5 flex flex-wrap gap-2">
            {frpPorSensor.map(([prod, frp]) => (
              <span
                key={prod}
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  prod.startsWith("MODIS")
                    ? "bg-tint text-modis-deep"
                    : "bg-[#e0edec] text-viirs-deep"
                }`}
              >
                {prod.startsWith("MODIS") ? "MODIS" : "VIIRS"} ·{" "}
                {frp.toFixed(1)} MW
              </span>
            ))}
          </div>
        </div>
      )}
      {evento.alerta_encadenamiento && (
        <p className="rounded-xl bg-[#fdf3e3] px-4 py-2.5 text-xs leading-relaxed text-[#8a6116]">
          Este evento creció por alcance en cadena entre detecciones lejanas:
          conviene mirarlo con cuidado antes de interpretarlo como un fenómeno
          compacto.
        </p>
      )}
    </div>
  );
}
