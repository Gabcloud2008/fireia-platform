"use client";

// Eventos de actividad de fuego (v3 — expedientes): cada evento es una
// ficha con acento lateral, sus métricas en una línea de cifras y la línea
// temporal de sus miembros. Un evento es una agrupación analítica, no
// necesariamente un incendio individual confirmado.

import { Clock, Link2, Ruler } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Evento } from "@/lib/mvp-types";

function horaLegible(iso: string): string {
  return iso.replace("T", " ").replace("Z", "");
}

export function EventosTab({ eventos }: { eventos: Evento[] }) {
  if (eventos.length === 0) {
    return (
      <Card className="border-dashed bg-[#fffdfb] shadow-none">
        <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
          <p className="text-sm font-medium text-foreground">
            Sin eventos en el almacén
          </p>
          <p className="max-w-md text-sm text-muted-foreground">
            Los eventos de co-detección se construyen con el comando{" "}
            <code className="rounded bg-secondary px-1.5 py-0.5 text-xs text-flame">
              hotspots events build
            </code>{" "}
            del pipeline. Cuando existan, cada evento agrupará detecciones de
            MODIS y VIIRS de la misma ventana espaciotemporal.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <p className="rounded-2xl border border-border bg-secondary/50 px-5 py-3.5 text-xs leading-relaxed text-muted-foreground">
        Un <strong className="text-foreground">evento</strong> es una agrupación{" "}
        <em>analítica</em>: junta detecciones de{" "}
        <span className="font-medium text-modis">MODIS</span> y{" "}
        <span className="font-medium text-viirs">VIIRS</span> que caen en la
        misma ventana de espacio y tiempo. La{" "}
        <strong className="text-foreground">dispersión</strong> es la distancia
        de los miembros al centro y el{" "}
        <strong className="text-foreground">diámetro</strong> la máxima
        distancia entre ellos — <em>ninguno</em> es un perímetro ni un área
        quemada.
      </p>

      {eventos.map((ev) => {
        const miembros = [...ev.miembros].sort((a, b) =>
          a.acq_datetime_utc.localeCompare(b.acq_datetime_utc),
        );
        return (
          <article
            key={ev.event_id}
            className="overflow-hidden rounded-2xl border border-border border-l-4 border-l-flame bg-card"
          >
            {/* --- encabezado del expediente --- */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/70 bg-[#fffdfb] px-5 py-3.5">
              <div className="min-w-0">
                <p className="flex items-center gap-2 font-display text-[17px] font-semibold tracking-tight text-foreground">
                  Evento {ev.event_id.slice(0, 12)}…
                  <Badge className="border-transparent bg-tint text-[10px] font-semibold text-flame">
                    MODIS × VIIRS
                  </Badge>
                  {ev.alerta_encadenamiento && (
                    <Badge className="border-transparent bg-[#fdf3e3] text-[10px] font-medium text-[#8a6116]">
                      <Link2 className="mr-1 size-3" aria-hidden />
                      encadenamiento
                    </Badge>
                  )}
                </p>
                <p className="mt-0.5 font-mono text-[10px] text-muted-foreground/80">
                  {ev.event_id} · método {ev.metodo}
                </p>
              </div>
              <p className="shrink-0 font-mono text-[11px] text-muted-foreground">
                {horaLegible(ev.primera_obs_utc)} → {horaLegible(ev.ultima_obs_utc)}
              </p>
            </div>

            <CardContent className="space-y-5 p-5">
              {/* --- cifras en línea, con divisores --- */}
              <div className="grid grid-cols-2 gap-y-4 sm:grid-cols-4 sm:divide-x sm:divide-border/70">
                {(
                  [
                    ["Observaciones", `${ev.n_observaciones}`, ""],
                    ["Duración", `${ev.duracion_segundos}`, " s"],
                    ["Dispersión", `${ev.dispersion_metros}`, " m"],
                    ["Diámetro máx.", ev.diametro_metros?.toFixed(0) ?? "—", " m"],
                  ] as Array<[string, string, string]>
                ).map(([k, v, unidad]) => (
                  <div key={k} className="px-1 sm:px-4 sm:first:pl-0 sm:last:pr-0">
                    <p className="fireia-index text-3xl text-foreground">
                      {v}
                      <span className="text-base text-muted-foreground">{unidad}</span>
                    </p>
                    <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      {k}
                    </p>
                  </div>
                ))}
              </div>

              {/* --- intensidad + línea temporal --- */}
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-3">
                  {Object.entries(ev.frp_por_producto ?? {}).length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(ev.frp_por_producto ?? {}).map(
                        ([prod, frp]) => (
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
                        ),
                      )}
                    </div>
                  )}
                  <p className="text-[11px] leading-relaxed text-muted-foreground">
                    La suma entre sensores ({ev.frp_total?.toFixed(1) ?? "—"}{" "}
                    MW) NO es la potencia física del fuego: hay doble conteo
                    esperable. Centro del grupo:{" "}
                    <span className="font-mono">
                      {ev.lat_centroide.toFixed(4)}, {ev.lon_centroide.toFixed(4)}
                    </span>{" "}
                    · satélites {ev.satelites.join(", ")}.
                  </p>
                </div>

                {/* línea temporal horizontal */}
                <div>
                  <p className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    <Clock className="size-3" aria-hidden />
                    Línea temporal del evento
                  </p>
                  <div className="overflow-x-auto rounded-xl border border-border bg-[#fffdfb] px-4 py-3">
                    <div className="relative min-w-[420px]">
                      <div className="absolute left-0 right-0 top-[7px] h-px bg-border" />
                      <div className="relative flex items-start justify-between">
                        {miembros.map((m) => (
                          <div
                            key={m.obs_id}
                            className="flex w-16 flex-col items-center gap-1"
                            title={`${m.sensor} · ${m.acq_datetime_utc}`}
                          >
                            <span
                              className={`size-3.5 rounded-full border-2 border-card ${
                                m.sensor === "MODIS" ? "bg-modis" : "bg-viirs"
                              }`}
                              aria-hidden
                            />
                            <span
                              className={`text-[9px] font-semibold ${
                                m.sensor === "MODIS" ? "text-modis" : "text-viirs"
                              }`}
                            >
                              {m.sensor}
                            </span>
                            <span className="font-mono text-[9px] text-muted-foreground">
                              {m.acq_datetime_utc.slice(11, 16)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* --- observaciones relacionadas --- */}
              <div>
                <p className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  <Ruler className="size-3" aria-hidden />
                  Observaciones que forman este evento
                </p>
                <div className="overflow-x-auto rounded-xl border border-border">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border/70 hover:bg-transparent">
                        <TableHead className="text-muted-foreground">Hora UTC</TableHead>
                        <TableHead className="text-muted-foreground">Sensor</TableHead>
                        <TableHead className="text-muted-foreground">Satélite</TableHead>
                        <TableHead className="text-muted-foreground">Confianza</TableHead>
                        <TableHead className="text-right text-muted-foreground">Intensidad</TableHead>
                        <TableHead className="text-muted-foreground">Departamento</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {miembros.map((m) => (
                        <TableRow key={m.obs_id} className="border-border/60">
                          <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                            {horaLegible(m.acq_datetime_utc)}
                          </TableCell>
                          <TableCell>
                            <span
                              className={
                                m.sensor === "MODIS"
                                  ? "font-semibold text-modis"
                                  : "font-semibold text-viirs"
                              }
                            >
                              {m.sensor}
                            </span>
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {m.satellite_name}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {m.confidence_band}
                          </TableCell>
                          <TableCell className="text-right font-mono text-xs text-muted-foreground">
                            {m.frp?.toFixed(1) ?? "—"} MW
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {m.departamento ?? "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>

              <p className="text-[11px] leading-relaxed text-muted-foreground/90">
                La membresía es conservada: una observación participa de un solo
                evento en este snapshot, y el conjunto completo se reconstruye
                por corrida (los snapshots anteriores quedan como evidencia).
              </p>
            </CardContent>
          </article>
        );
      })}
    </div>
  );
}
