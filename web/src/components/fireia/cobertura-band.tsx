"use client";

// Banda de cobertura diaria (compartida por Historial y Calidad): una
// retícula de celdas por día coloreadas según su clasificación, con
// leyenda y supuestos declarados. Reemplaza la sopa de píldoras.

import { useMemo } from "react";

export const ESTADO_DIA: Record<
  string,
  { label: string; corto: string; celda: string; punto: string }
> = {
  con_detecciones: {
    label: "con detecciones",
    corto: "Fuego",
    celda: "border-[#e6b48c] bg-tint text-flame",
    punto: "bg-flame",
  },
  cero_detecciones_asumido: {
    label: "sin detecciones (cero asumido)",
    corto: "Cero",
    celda: "border-border bg-card text-muted-foreground",
    punto: "bg-[#b7a89c]",
  },
  solo_rechazadas_qc: {
    label: "solo detecciones descartadas por calidad",
    corto: "QC",
    celda: "border-[#e3b7a7] bg-[#f7dfd2] text-[#b5543b]",
    punto: "bg-[#b5543b]",
  },
  sin_datos: {
    label: "sin datos",
    corto: "—",
    celda: "border-border bg-[#f4f0ec] text-[#a99a8c]",
    punto: "bg-[#c9beba]",
  },
};

export function CoberturaBand({
  dias,
  resumen,
  supuestos,
}: {
  dias: Array<{ fecha: string; estado: string }>;
  resumen?: Record<string, number>;
  supuestos?: string[];
}) {
  const semanas = useMemo(() => {
    // Agrupa los días en filas de 7 desde el primero del período.
    const filas: Array<Array<{ fecha: string; estado: string } | null>> = [];
    let fila: Array<{ fecha: string; estado: string } | null> = [];
    dias.forEach((d, i) => {
      fila.push(d);
      if ((i + 1) % 7 === 0) {
        filas.push(fila);
        fila = [];
      }
    });
    if (fila.length > 0) {
      while (fila.length < 7) fila.push(null);
      filas.push(fila);
    }
    return filas;
  }, [dias]);

  if (dias.length === 0) return null;

  return (
    <div className="space-y-3.5">
      <div className="overflow-x-auto pb-1">
        <div className="min-w-[490px] space-y-1.5">
          {semanas.map((fila, i) => (
            <div key={i} className="grid grid-cols-7 gap-1.5">
              {fila.map((d, j) =>
                d ? (
                  (() => {
                    const est = ESTADO_DIA[d.estado] ?? {
                      label: d.estado,
                      corto: "?",
                      celda: "border-border bg-card text-muted-foreground",
                      punto: "bg-[#b7a89c]",
                    };
                    return (
                      <div
                        key={d.fecha}
                        title={`${d.fecha}: ${est.label}`}
                        className={`flex h-11 flex-col items-center justify-center rounded-lg border ${est.celda} transition-transform duration-150 hover:-translate-y-0.5`}
                      >
                        <span className="font-mono text-[11px] font-semibold leading-none">
                          {d.fecha.slice(8)}
                        </span>
                        <span className="mt-0.5 text-[8px] uppercase leading-none opacity-75">
                          {est.corto}
                        </span>
                      </div>
                    );
                  })()
                ) : (
                  <div key={`vacio-${i}-${j}`} className="h-11" aria-hidden />
                ),
              )}
            </div>
          ))}
        </div>
      </div>

      {resumen ? (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
          {Object.entries(resumen).map(([estado, n]) => (
            <span key={estado} className="flex items-center gap-1.5">
              <span
                className={`size-2 rounded-full ${
                  ESTADO_DIA[estado]?.punto ?? "bg-[#b7a89c]"
                }`}
                aria-hidden
              />
              {ESTADO_DIA[estado]?.label ?? estado}: <strong className="text-foreground">{n}</strong>
            </span>
          ))}
        </div>
      ) : null}

      {supuestos && supuestos.length > 0 ? (
        <p className="text-[11px] leading-snug text-[#8a6116]">
          Supuesto declarado: {supuestos.join(" · ")}
        </p>
      ) : null}
    </div>
  );
}
