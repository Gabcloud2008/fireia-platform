"use client";

// Trazabilidad (v3 — bitácora de auditoría): la línea de corridas como
// registro vertical con riel, y las garantías de evidencia como fichas
// compactas. Auditar es poder preguntar «¿por qué?».

import { FileClock, Fingerprint, History, Lock } from "lucide-react";

import { DataGate } from "@/components/fireia/data-gate";
import type { DatosMVP } from "@/components/fireia/data-provider";
import { SectionHero } from "@/components/fireia/section-hero";
import { MODULOS, ETIQUETA_DISPONIBILIDAD } from "@/lib/fireia/disponibilidad";

const GARANTIAS = [
  {
    icon: Fingerprint,
    titulo: "Manifiestos con huella SHA256",
    detalle:
      "Cada corrida del pipeline registra la huella digital de cada artefacto que produce. El comando hotspots verify recomputa todas las huellas: si un byte cambió, se detecta.",
  },
  {
    icon: Lock,
    titulo: "Respaldo crudo inmutable",
    detalle:
      "La respuesta original del satélite se guarda tal como llegó, direccionada por su contenido. Los problemas se corrigen aguas abajo, nunca reescribiendo la evidencia.",
  },
  {
    icon: FileClock,
    titulo: "Motivos registrados",
    detalle:
      "Cada decisión de la ingesta (procesar, omitir, cuarentena) queda registrada con su motivo y su marca de tiempo UTC.",
  },
];

export function TrazabilidadView() {
  const modulo = MODULOS.find((m) => m.clave === "almacen")!;

  return (
    <div className="space-y-5">
      <SectionHero
        indice="03"
        categoria="Sistema · bitácora"
        icon={History}
        title="Todo deja rastro."
        lede="Cada corrida del pipeline quedó registrada con su estado y su motivo, y tres garantías permiten auditar cualquier número hasta su origen."
      />
      <DataGate>{(datos) => <Corridas datos={datos} />}</DataGate>

      <div className="grid gap-3 md:grid-cols-3">
        {GARANTIAS.map((g) => (
          <div
            key={g.titulo}
            className="rounded-2xl border border-border bg-card p-5"
          >
            <span
              className="flex size-10 items-center justify-center rounded-xl bg-tint text-flame"
              aria-hidden
            >
              <g.icon className="size-5" />
            </span>
            <p className="mt-3 font-display text-[16px] font-semibold tracking-tight text-foreground">
              {g.titulo}
            </p>
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
              {g.detalle}
            </p>
          </div>
        ))}
      </div>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Estado del módulo: {ETIQUETA_DISPONIBILIDAD[modulo.disponibilidad].etiqueta.toLowerCase()}{" "}
        — {modulo.nota}
      </p>
    </div>
  );
}

function Corridas({ datos }: { datos: DatosMVP }) {
  const corridas = [...datos.calidad.corridas].reverse();
  return (
    <div className="rounded-3xl border border-border bg-card px-5 py-6 sm:px-7">
      <p className="font-display text-lg font-semibold tracking-tight text-foreground">
        Corridas registradas
      </p>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
        De la más reciente a la más antigua. Cada entrada declara por qué
        terminó en su estado.
      </p>
      <ol className="mt-5 relative space-y-0 border-l-2 border-border/70 pl-6">
        {corridas.map((c, i) => (
          <li key={i} className="relative pb-5 last:pb-0">
            <span
              className={`absolute -left-[31px] top-0.5 size-3 rounded-full border-2 border-card ${
                c.state === "ingested"
                  ? "bg-viirs"
                  : c.state === "skipped"
                    ? "bg-[#b7a89c]"
                    : "bg-[#b5543b]"
              }`}
              aria-hidden
            />
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-mono text-[11px] text-muted-foreground">
                {c.occurred_at_utc.replace("T", " ").slice(0, 19)} UTC
              </span>
              <span className="text-xs font-medium text-foreground">
                {c.product}
              </span>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                  c.state === "ingested"
                    ? "bg-[#e3efe3] text-[#3d6b4f]"
                    : c.state === "skipped"
                      ? "bg-secondary text-muted-foreground"
                      : "bg-[#f7dfd2] text-[#b5543b]"
                }`}
              >
                {c.state}
              </span>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {c.reason}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}
