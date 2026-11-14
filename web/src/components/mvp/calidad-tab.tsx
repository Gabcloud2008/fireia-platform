"use client";

// Calidad de información (v3): banda de cobertura visual + métricas del
// control + estados de ingesta con barras. El camino del dato vive en
// "Procesamiento"; el historial de corridas, en "Trazabilidad".

import { CalendarCheck, FileWarning, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { CoberturaBand } from "@/components/fireia/cobertura-band";
import type { Almacen } from "@/lib/mvp-types";

function colorEstado(state: string): string {
  switch (state) {
    case "ingested":
      return "border-transparent bg-[#e3efe3] text-[#3d6b4f]";
    case "skipped":
      return "border-transparent bg-secondary text-muted-foreground";
    case "quarantined":
      return "border-transparent bg-[#f7dfd2] text-[#b5543b]";
    case "rejected":
      return "border-transparent bg-[#f7dfd2] text-[#b5543b]";
    default:
      return "border-transparent bg-[#fdf3e3] text-[#8a6116]";
  }
}

export function CalidadTab({
  calidad,
  cobertura,
}: {
  calidad: Almacen["calidad"];
  cobertura?: Almacen["cobertura"];
}) {
  const totalEstados = calidad.estados.reduce((acc, e) => acc + e.registros, 0);

  return (
    <div className="space-y-4">
      {cobertura && (
        <Card className="border-border bg-card shadow-none">
          <CardContent className="p-5 sm:p-6">
            <p className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight text-foreground">
              <CalendarCheck className="size-4 text-viirs" aria-hidden />
              Calendario de cobertura
            </p>
            <p className="mb-4 mt-1 max-w-3xl text-xs leading-relaxed text-muted-foreground">
              Un día sin detecciones NO es un día sin fuego, y un día sin datos
              no es un cero. Cada día del período queda clasificado antes de
              entrar a cualquier serie estadística.
            </p>
            <CoberturaBand
              dias={cobertura.dias}
              resumen={cobertura.resumen}
              supuestos={cobertura.supuestos}
            />
          </CardContent>
        </Card>
      )}

      {/* --- métricas del control --- */}
      <div className="grid grid-cols-2 gap-y-5 rounded-2xl border border-border bg-card px-5 py-5 sm:grid-cols-4 sm:divide-x sm:divide-border/70">
        {(
          [
            ["Registros", `${totalEstados}`, "de ingesta en la ventana"],
            ["Cuarentena", `${calidad.cuarentena_registros}`, "íntegra, con errores"],
            ["Pares", `${calidad.pares_candidatos}`, "MODIS↔VIIRS en ventana"],
            ["Manifiestos", "8", "con SHA256 por artefacto"],
          ] as Array<[string, string, string]>
        ).map(([k, v, sub]) => (
          <div key={k} className="px-1 sm:px-4 sm:first:pl-0 sm:last:pr-0">
            <p className="fireia-index text-4xl text-foreground">{v}</p>
            <p className="mt-1.5 text-[10px] font-semibold uppercase tracking-wider text-flame">
              {k}
            </p>
            <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">{sub}</p>
          </div>
        ))}
      </div>

      {/* --- estados de ingesta --- */}
      <Card className="border-border bg-card shadow-none">
        <CardContent className="p-5 sm:p-6">
          <p className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight text-foreground">
            <ShieldCheck className="size-4 text-viirs" aria-hidden />
            Estados de ingesta
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Taxonomía de 10 estados del pipeline; este es el resumen de lo que
            quedó registrado en la ventana.
          </p>
          <div className="mt-4 space-y-2.5">
            {calidad.estados.map((e) => (
              <div
                key={e.state}
                className="flex items-center justify-between gap-3"
              >
                <Badge
                  variant="outline"
                  className={`w-28 shrink-0 justify-center text-[11px] font-normal ${colorEstado(e.state)}`}
                >
                  {e.state}
                </Badge>
                <div className="flex flex-1 items-center gap-2.5">
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
                    <div
                      className="h-full rounded-full bg-flame/70 transition-[width] duration-500"
                      style={{
                        width: `${
                          totalEstados > 0
                            ? Math.max((e.registros / totalEstados) * 100, 2)
                            : 0
                        }%`,
                      }}
                    />
                  </div>
                  <span className="w-10 text-right text-sm tabular-nums text-muted-foreground">
                    {e.registros}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="rounded-2xl border border-border bg-secondary/60 px-5 py-4 text-xs leading-relaxed text-muted-foreground">
        <div className="flex items-start gap-2.5">
          <FileWarning className="mt-0.5 size-4 shrink-0 text-flame" aria-hidden />
          <p>
            <strong className="text-foreground">Compuertas activas:</strong> la
            ingesta real de FIRMS sigue bloqueada tras{" "}
            <code className="rounded bg-card px-1 text-flame">
              --allow-network
            </code>{" "}
            + credenciales + autorización del propietario. Esta plataforma no
            dispara ninguna operación de red: es consumidora de solo lectura del
            almacén exportado.
          </p>
        </div>
      </div>
    </div>
  );
}
