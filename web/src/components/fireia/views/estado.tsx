"use client";

// Estado de la plataforma (v3 — tablero de estado): franja de salud
// grande, fichas del sistema en mono, módulos con su disponibilidad real.

import { Flame, Github, RefreshCw, Settings } from "lucide-react";

import { useEffect, useState } from "react";

import { DataGate } from "@/components/fireia/data-gate";
import { SectionHero } from "@/components/fireia/section-hero";
import { Badge } from "@/components/ui/badge";
import {
  MODULOS,
  ETIQUETA_DISPONIBILIDAD,
} from "@/lib/fireia/disponibilidad";

type EstadoActualizacion = {
  estado: string;
  ultima_actualizacion_exitosa?: string | null;
  ultima_comprobacion?: string;
  proxima_ejecucion_programada?: string;
  antiguedad_datos_dias?: number | null;
  fuente_consultada?: string;
  periodo_cubierto?: string;
  registros?: Record<string, unknown>;
  errores?: string[];
  nota?: string;
};

const CLASE_ESTADO: Record<string, string> = {
  ACTUALIZADO: "border-emerald-300 bg-emerald-50 text-emerald-900",
  SIN_NUEVOS_DATOS: "border-border bg-muted text-muted-foreground",
  ACTUALIZANDO: "border-sky-300 bg-sky-50 text-sky-900",
  RETRASADO: "border-amber-300 bg-amber-50 text-amber-900",
  ERROR: "border-red-300 bg-red-50 text-red-900",
  COBERTURA_DESCONOCIDA: "border-border bg-muted text-muted-foreground",
  ADQUISICION_NO_DISPONIBLE: "border-amber-300 bg-amber-50 text-amber-900",
};

function PanelActualizacion() {
  const [estado, setEstado] = useState<EstadoActualizacion | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    fetch("/api/actualizacion")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: { estado: EstadoActualizacion }) => {
        if (vivo) setEstado(d.estado);
      })
      .catch((e: Error) => {
        if (vivo) setError(e.message);
      });
    return () => {
      vivo = false;
    };
  }, []);

  if (error) {
    return (
      <p className="text-xs text-muted-foreground">
        Estado de actualización no disponible ({error}).
      </p>
    );
  }
  if (!estado) {
    return <p className="text-xs text-muted-foreground">Cargando estado de actualización…</p>;
  }
  const clase = CLASE_ESTADO[estado.estado] ?? "border-border bg-muted text-muted-foreground";
  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 font-display text-base font-semibold tracking-tight text-foreground">
          <RefreshCw className="size-4 text-flame" aria-hidden />
          Actualización de datos
        </p>
        <span
          className={`rounded-full border px-3 py-1 text-[11px] font-semibold ${clase}`}
        >
          {estado.estado.replaceAll("_", " ")}
        </span>
      </div>
      <dl className="mt-4 grid gap-x-6 gap-y-2 text-xs leading-relaxed text-muted-foreground sm:grid-cols-2">
        <div>
          <dt className="font-medium text-foreground">Última actualización exitosa</dt>
          <dd>{estado.ultima_actualizacion_exitosa ?? "sin registro aún"}</dd>
        </div>
        <div>
          <dt className="font-medium text-foreground">Última comprobación</dt>
          <dd>{estado.ultima_comprobacion ?? "—"}</dd>
        </div>
        <div>
          <dt className="font-medium text-foreground">Próxima ejecución programada</dt>
          <dd>{estado.proxima_ejecucion_programada ?? "—"}</dd>
        </div>
        <div>
          <dt className="font-medium text-foreground">Antigüedad de los datos</dt>
          <dd>
            {estado.antiguedad_datos_dias === null || estado.antiguedad_datos_dias === undefined
              ? "desconocida"
              : `${estado.antiguedad_datos_dias} día(s)`}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-foreground">Fuente consultada</dt>
          <dd>{estado.fuente_consultada ?? "—"}</dd>
        </div>
        <div>
          <dt className="font-medium text-foreground">Periodo cubierto</dt>
          <dd>{estado.periodo_cubierto ?? "—"}</dd>
        </div>
      </dl>
      {estado.errores && estado.errores.length > 0 && (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-900">
          {estado.errores.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
      {estado.nota && <p className="mt-3 text-xs text-muted-foreground">{estado.nota}</p>}
      <p className="mt-3 border-t border-border/60 pt-2.5 text-[11px] leading-relaxed text-muted-foreground/90">
        Regla del sistema: un fallo de adquisición no significa cero detecciones;
        la ausencia de datos no significa ausencia de incendios.
      </p>
    </div>
  );
}

export function EstadoView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="05"
        categoria="Sistema · estado"
        icon={Settings}
        title="Qué funciona y qué espera."
        lede="Cada módulo declara su estado real: nada se presenta como conectado si no lo está."
      />
      <DataGate>{(datos) => <ContenidoEstado datos={datos} />}</DataGate>

      <section aria-label="Actualización de datos">
        <PanelActualizacion />
      </section>



      {/* --- actualización --- */}
{/* --- módulos --- */}
      <section aria-labelledby="est-modulos">
        <h2
          id="est-modulos"
          className="mb-3 font-display text-xl font-semibold tracking-tight text-foreground"
        >
          Módulos y disponibilidad
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {MODULOS.map((m) => {
            const d = ETIQUETA_DISPONIBILIDAD[m.disponibilidad];
            return (
              <div
                key={m.clave}
                className="flex items-start justify-between gap-3 rounded-2xl border border-border bg-card p-5"
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground">
                    {m.nombre}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {m.descripcion}
                  </p>
                  <p className="mt-2.5 border-t border-border/60 pt-2.5 text-[11px] leading-relaxed text-muted-foreground/90">
                    {m.nota}
                  </p>
                </div>
                <Badge
                  variant="outline"
                  className={`shrink-0 text-[10px] font-medium ${d.clase}`}
                >
                  {d.etiqueta}
                </Badge>
              </div>
            );
          })}
        </div>
      </section>

      {/* --- acerca de --- */}
      <div className="rounded-2xl border border-border bg-card px-5 py-5">
        <p className="flex items-center gap-2 font-display text-base font-semibold tracking-tight text-foreground">
          <Flame className="size-4 text-flame" aria-hidden />
          Acerca de FIREIA
        </p>
        <div className="mt-3 grid gap-4 text-xs leading-relaxed text-muted-foreground sm:grid-cols-2">
          <p>
            FIREIA (Paraguay Fire Intelligence) es el frontend del proyecto{" "}
            <span className="inline-flex items-center gap-1 font-medium text-foreground">
              <Github className="size-3" aria-hidden />
              p400/modis-viirs-hotspots-paraguay
            </span>
            , del equipo P400 para el NASA Space Apps Challenge 2026 (reto
            1.9). Rediseño integral M012: identidad naranja pastel y blanca,
            menú lateral desplegable, navegación por categorías, laboratorio
            de simulaciones y arquitectura modular de servicios. El backend y
            el pipeline científico permanecen intactos.
          </p>
          <p>
            El frontend consume la API espejo en modo de solo lectura. Las
            futuras integraciones (ambiental, conversacional, riesgo) se
            conectan sustituyendo adaptadores en la capa de servicios
            (src/lib/fireia/services) sin reconstruir las pantallas.
          </p>
        </div>
      </div>
    </div>
  );
}

function ContenidoEstado({
  datos,
}: {
  datos: {
    health: {
      status: string;
      data_source: string;
      cobertura: { desde: string; hasta: string; dias: number };
    };
  };
}) {
  const operativo = datos.health.status === "ok";
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* --- franja de salud --- */}
      <div
        className={`rounded-3xl border p-6 ${
          operativo
            ? "border-[#cfe0dc] bg-gradient-to-b from-[#eef4f1] to-[#e5efec]"
            : "border-[#ecc7b3] bg-[#fdf3ec]"
        }`}
      >
        <div className="flex items-center gap-3">
          <span
            className={`fireia-pulse inline-block size-3 rounded-full ${
              operativo ? "bg-[#3d6b4f]" : "bg-flame"
            }`}
            aria-hidden
          />
          <p className="font-display text-2xl font-semibold tracking-tight text-foreground">
            {operativo ? "Operativo, en solo lectura" : `Estado: ${datos.health.status}`}
          </p>
        </div>
        <dl className="mt-4 space-y-2.5 text-xs">
          {(
            [
              ["Origen de los datos", datos.health.data_source],
              [
                "Ventana de cobertura",
                `${datos.health.cobertura.desde} → ${datos.health.cobertura.hasta} (${datos.health.cobertura.dias} días con detecciones)`,
              ],
              ["Servicio", "paraguay-fire-intelligence-mvp"],
            ] as Array<[string, string]>
          ).map(([k, v]) => (
            <div
              key={k}
              className="flex items-start justify-between gap-4 border-b border-[#00000010] pb-2.5 last:border-0 last:pb-0"
            >
              <dt className="shrink-0 text-muted-foreground">{k}</dt>
              <dd className="text-right font-medium text-foreground">{v}</dd>
            </div>
          ))}
        </dl>
      </div>

      {/* --- compuertas --- */}
      <div className="rounded-3xl border border-border bg-card p-6">
        <p className="fireia-kicker text-muted-foreground">Compuertas de ingesta</p>
        <p className="mt-3 font-display text-lg font-semibold tracking-tight text-foreground">
          Bloqueado a propósito
        </p>
        <div className="mt-2.5 space-y-3 text-xs leading-relaxed text-muted-foreground">
          <p>
            La ingesta real de NASA FIRMS está bloqueada detrás de la compuerta{" "}
            <code className="rounded bg-secondary px-1 py-0.5 text-flame">
              --allow-network
            </code>
            . Habilitarla requiere credenciales válidas y autorización
            explícita del propietario del proyecto.
          </p>
          <p>
            Esta plataforma es un <strong className="text-foreground">consumidor de solo lectura</strong>:
            navegar, filtrar o explorar nunca dispara una descarga ni consume
            cuota de la API.
          </p>
        </div>
      </div>
    </div>
  );
}
