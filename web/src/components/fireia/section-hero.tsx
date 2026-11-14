"use client";

// Cabeceras editoriales de FIREIA (v3): reemplazan al PageHeader único.
// Dos modos con personalidad propia:
//  - "stage": bloque escenario con retícula de puntos y titular display
//    (Fraunces) para secciones narrativas.
//  - "compacto": fila app con kicker + titular mediano para pantallas
//    tipo herramienta (mapa, chat, exploradores).
// El índice (01, 02…) y la categoría dan contexto de dónde estás parado.

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function SectionHero({
  indice,
  categoria,
  icon: Icon,
  title,
  lede,
  meta,
}: {
  indice?: string;
  categoria: string;
  icon?: LucideIcon;
  title: string;
  lede?: string;
  meta?: ReactNode;
}) {
  return (
    <section
      className="relative overflow-hidden rounded-3xl border border-border fireia-stage"
      aria-labelledby="fireia-hero-title"
    >
      <div className="absolute inset-0 fireia-dots opacity-55" aria-hidden />
      <div className="relative flex flex-col gap-5 px-5 py-7 sm:px-8 sm:py-9 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <p className="fireia-kicker flex items-center gap-2.5 text-flame">
            {indice ? (
              <span className="fireia-index text-base leading-none" aria-hidden>
                {indice}
              </span>
            ) : null}
            {categoria}
          </p>
          <h1
            id="fireia-hero-title"
            className="mt-2.5 font-display text-[26px] font-semibold leading-[1.12] tracking-tight text-foreground sm:text-4xl sm:leading-[1.08]"
            style={{ fontVariationSettings: '"opsz" 60, "SOFT" 40, "WONK" 1' }}
          >
            {title}
          </h1>
          {lede ? (
            <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
              {lede}
            </p>
          ) : null}
        </div>
        {meta ? <div className="shrink-0 lg:pb-1">{meta}</div> : null}
      </div>
      {Icon ? (
        <Icon
          className="pointer-events-none absolute -right-5 -top-6 size-36 text-[#f0dcc8] sm:size-44"
          strokeWidth={1}
          aria-hidden
        />
      ) : null}
    </section>
  );
}

export function HeroCompacto({
  indice,
  categoria,
  title,
  lede,
  actions,
}: {
  indice?: string;
  categoria: string;
  title: string;
  lede?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        <p className="fireia-kicker flex items-center gap-2.5 text-flame">
          {indice ? (
            <span className="fireia-index text-base leading-none" aria-hidden>
              {indice}
            </span>
          ) : null}
          {categoria}
        </p>
        <h1 className="mt-1.5 font-display text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          {title}
        </h1>
        {lede ? (
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            {lede}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}

/** Cifra display (Fraunces) con etiqueta y contexto. */
export function StatDisplay({
  valor,
  formato,
  etiqueta,
  contexto,
  tono = "foreground",
  className = "",
}: {
  valor: number;
  formato?: (n: number) => string;
  etiqueta: string;
  contexto?: string;
  tono?: "foreground" | "flame" | "viirs";
  className?: string;
}) {
  const color =
    tono === "flame"
      ? "text-flame"
      : tono === "viirs"
        ? "text-viirs"
        : "text-foreground";
  return (
    <div className={className}>
      <p
        className={`fireia-index text-[40px] tracking-tight sm:text-5xl ${color}`}
      >
        {formato ? formato(valor) : new Intl.NumberFormat("es-PY").format(valor)}
      </p>
      <p className="mt-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        {etiqueta}
      </p>
      {contexto ? (
        <p className="mt-1 text-xs leading-snug text-muted-foreground/85">
          {contexto}
        </p>
      ) : null}
    </div>
  );
}
