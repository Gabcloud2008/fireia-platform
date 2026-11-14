"use client";

// Inicio (v3 — editorial): el mapa manda, la tipografía tiene voz y cada
// bloque tiene una composición distinta. Nada de muro de tarjetas iguales.

import dynamic from "next/dynamic";
import { useMemo } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Database,
  Map as MapIcon,
  MessagesSquare,
  Radar,
  Satellite,
  ShieldCheck,
} from "lucide-react";

import { DataGate } from "@/components/fireia/data-gate";
import type { DatosMVP } from "@/components/fireia/data-provider";
import { SectionHero, StatDisplay } from "@/components/fireia/section-hero";
import { TickerActividad } from "@/components/fireia/ticker-actividad";
import { CountUp, Reveal } from "@/components/fireia/motion";
import { BannerSintetico } from "@/components/mvp/banner-sintetico";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const MapaInicio = dynamic(
  () =>
    import("@/components/mvp/mapa-map").then((m) => ({
      default: m.MapaNacional,
    })),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full min-h-[380px] items-center justify-center rounded-xl border border-border bg-secondary/40 text-sm text-muted-foreground">
        Cargando el mapa de Paraguay…
      </div>
    ),
  },
);

function ContenidoInicio({ datos }: { datos: DatosMVP }) {
  const ultimas = useMemo(
    () =>
      [...datos.observaciones]
        .sort((a, b) => b.acq_datetime_utc.localeCompare(a.acq_datetime_utc))
        .slice(0, 8),
    [datos.observaciones],
  );
  const diasConDatos = datos.cobertura?.dias.filter(
    (d) => d.estado === "con_detecciones",
  ).length;
  const afectados = datos.health.resumen.departamentos_afectados;

  return (
    <div className="space-y-5">
      {/* ---------- portada editorial ---------- */}
      <SectionHero
        indice="01"
        categoria="Centro de inteligencia"
        icon={Radar}
        title="Paraguay, vigilado desde la órbita."
        lede="FIREIA cruza las detecciones de dos satélites de la NASA —MODIS y VIIRS— y las explica en lenguaje claro: qué se vio, dónde, cuándo y con cuánta confianza. Empezá por el mapa o preguntale a la plataforma."
        meta={
          <div className="flex flex-col items-stretch gap-3 sm:flex-row lg:flex-col">
            <Button
              asChild
              size="lg"
              className="h-11 rounded-full bg-action px-5 text-[15px] text-white shadow-[0_8px_20px_-8px_rgb(192_95_44/0.55)] hover:bg-[#a94f22]"
            >
              <Link href="#/mapa">
                Explorar el mapa
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </Button>
            <Button
              asChild
              size="lg"
              variant="outline"
              className="h-11 rounded-full border-border bg-card/80 px-5 text-[15px] backdrop-blur hover:bg-secondary"
            >
              <Link href="#/inteligencia">
                <MessagesSquare className="size-4 text-flame" aria-hidden />
                Preguntar a FIREIA
              </Link>
            </Button>
          </div>
        }
      />

      {/* ---------- cifra central + ventana ---------- */}
      <div className="grid gap-4 lg:grid-cols-12">
        <Card className="relative overflow-hidden border-border bg-gradient-to-br from-[#fff4e8] to-[#fdeedd] shadow-none lg:col-span-5">
          <CardContent className="relative flex h-full flex-col justify-between gap-5 p-6">
            <div className="flex items-center justify-between gap-3">
              <p className="fireia-kicker text-flame">Detecciones en el país</p>
              <Badge
                variant="outline"
                className="rounded-full border-transparent bg-card px-2.5 py-1 text-[10px] font-medium text-muted-foreground"
              >
                <span className="fireia-pulse mr-1 inline-block size-1.5 rounded-full bg-flame" aria-hidden />
                ventana {datos.health.cobertura.desde} → {datos.health.cobertura.hasta}
              </Badge>
            </div>
            <div className="flex items-end gap-6">
              <StatDisplay
                valor={datos.health.resumen.dentro_pais}
                etiqueta="focos de calor vistos por satélite"
                tono="flame"
              />
              <div className="pb-1 text-xs leading-relaxed text-muted-foreground">
                <p>
                  <strong className="font-display text-lg text-foreground">{diasConDatos ?? datos.health.cobertura.dias}</strong> días
                  con actividad registrada
                </p>
                <p className="mt-1">
                  {afectados.length} de 18 departamentos ·{" "}
                  {datos.health.resumen.total - datos.health.resumen.dentro_pais}{" "}
                  en la franja vecina
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 border-t border-[#eeddc9] pt-4">
              <div className="flex items-center gap-2.5">
                <span className="size-2.5 rounded-full bg-modis" aria-hidden />
                <p className="text-xs text-muted-foreground">
                  <strong className="font-display text-base text-foreground">
                    <CountUp valor={datos.health.resumen.modis} />
                  </strong>{" "}
                  MODIS · 1 km
                </p>
              </div>
              <div className="flex items-center gap-2.5">
                <span className="size-2.5 rounded-full bg-viirs" aria-hidden />
                <p className="text-xs text-muted-foreground">
                  <strong className="font-display text-base text-foreground">
                    <CountUp valor={datos.health.resumen.viirs} />
                  </strong>{" "}
                  VIIRS · 375 m
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ---------- mapa protagonista ---------- */}
        <Card className="min-w-0 overflow-hidden border-border bg-card p-0 shadow-none lg:col-span-7">
          <div className="h-[420px] sm:h-[460px]">
            <MapaInicio
              observaciones={datos.observaciones}
              departamentos={datos.departamentos}
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-3">
            <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-modis" aria-hidden />
                MODIS · 1 km
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-viirs" aria-hidden />
                VIIRS · 375 m
              </span>
              <span className="hidden sm:inline">Tocá un punto para ver su detalle</span>
            </p>
            <Link
              href="#/mapa"
              className="inline-flex items-center gap-1 text-xs font-semibold text-flame underline-offset-4 hover:underline"
            >
              Abrir el mapa completo
              <ArrowRight className="size-3.5" aria-hidden />
            </Link>
          </div>
        </Card>
      </div>

      {/* ---------- ticker ---------- */}
      <TickerActividad items={ultimas} />

      <BannerSintetico
        dataSource={datos.health.data_source}
        nota={datos.health.data_source_nota}
      />

      {/* ---------- cómo funciona: tres pasos editoriales ---------- */}
      <Reveal className="rounded-3xl border border-border bg-card px-5 py-7 sm:px-8">
        <p className="fireia-kicker text-muted-foreground">Cómo trabaja FIREIA</p>
        <div className="mt-5 grid gap-8 md:grid-cols-3 md:gap-5">
          {[
            {
              n: "1",
              t: "Dos satélites miran el suelo",
              d: "MODIS ve fuegos grandes con píxeles de 1 km; VIIRS detecta focos pequeños con 375 m. Cada detección trae su nivel de confianza: una detección no es un incendio confirmado.",
            },
            {
              n: "2",
              t: "El pipeline clasifica todo",
              d: "Cada registro pasa control de calidad, se asigna a su departamento y los cruces MODIS–VIIRS se agrupan en eventos. Lo dudoso va a cuarentena, nunca se borra.",
            },
            {
              n: "3",
              t: "La pantalla lo explica",
              d: "Ves el mapa, los números con contexto y el estado real de cada dato. Si algo es sintético o está en desarrollo, lo dice en el lugar — sin letra chica.",
            },
          ].map((p, i) => (
            <div key={p.n} className="relative md:pl-5">
              {i < 2 ? (
                <span
                  className="absolute left-0 top-1 hidden h-[calc(100%-8px)] w-px bg-border md:block"
                  aria-hidden
                />
              ) : null}
              <p className="fireia-index text-4xl text-[#e5c9ae]" aria-hidden>
                {p.n}
              </p>
              <p className="mt-2.5 font-display text-lg font-semibold tracking-tight text-foreground">
                {p.t}
              </p>
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                {p.d}
              </p>
            </div>
          ))}
        </div>
      </Reveal>

      {/* ---------- accesos: bento asimétrico ---------- */}
      <div className="grid gap-3 md:grid-cols-6">
        {[
          {
            vista: "observaciones",
            icon: Satellite,
            titulo: "Observaciones satelitales",
            texto:
              "Cada foco con su hora, ubicación, sensor, confianza e intensidad. Filtrá y entrá al detalle.",
            clase: "md:col-span-4 bg-gradient-to-br from-[#fff4e8] to-[#fdeedd] border-[#eeddc9]",
            icono: "bg-card text-flame",
          },
          {
            vista: "comparacion",
            icon: Radar,
            titulo: "MODIS vs VIIRS",
            texto: "Qué vio cada sensor y qué coincidencias quedaron confirmadas.",
            clase: "md:col-span-2 bg-card",
            icono: "bg-secondary text-viirs",
          },
          {
            vista: "eventos",
            icon: Radar,
            titulo: "Eventos y evolución",
            texto: "Agrupaciones de co-detección y cómo cambió la actividad día a día.",
            clase: "md:col-span-2 bg-card",
            icono: "bg-secondary text-brown",
          },
          {
            vista: "historial",
            icon: Database,
            titulo: "Historial y calendario",
            texto: "El período completo, día por día, con su calidad declarada.",
            clase: "md:col-span-2 bg-card",
            icono: "bg-secondary text-brown",
          },
          {
            vista: "calidad",
            icon: ShieldCheck,
            titulo: "Calidad y trazabilidad",
            texto:
              "De dónde salió cada número y qué controles atravesó antes de llegar a esta pantalla.",
            clase: "md:col-span-2 bg-gradient-to-br from-[#eef4f1] to-[#e5efec] border-[#d5e3de]",
            icono: "bg-card text-viirs",
          },
        ].map((a) => (
          <Link
            key={a.titulo}
            href={`#/${a.vista}`}
            className={`group block rounded-2xl border border-border p-5 outline-none transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_14px_30px_-18px_rgb(57_51_47/0.35)] focus-visible:ring-2 focus-visible:ring-ring ${a.clase}`}
          >
            <div className="flex h-full flex-col justify-between gap-4">
              <div className="flex items-center justify-between">
                <span
                  className={`flex size-10 items-center justify-center rounded-xl ${a.icono}`}
                  aria-hidden
                >
                  <a.icon className="size-5" />
                </span>
                <ArrowRight
                  className="size-4 -translate-x-1 text-flame opacity-0 transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100"
                  aria-hidden
                />
              </div>
              <div>
                <p className="font-display text-[17px] font-semibold tracking-tight text-foreground">
                  {a.titulo}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {a.texto}
                </p>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* ---------- puente al resto de la plataforma ---------- */}
      <div className="flex flex-col items-start justify-between gap-3 rounded-2xl border border-dashed border-[#e4d5c6] bg-[#fffdfb] px-5 py-4 sm:flex-row sm:items-center">
        <p className="flex items-center gap-2.5 text-sm text-muted-foreground">
          <MapIcon className="size-4 shrink-0 text-flame" aria-hidden />
          ¿Querés ver cómo se construye cada dato? Metodología, procesamiento y
          validación viven en el grupo{" "}
          <strong className="text-foreground">Sistema</strong> del menú.
        </p>
        <Button
          asChild
          variant="outline"
          size="sm"
          className="shrink-0 rounded-full border-border bg-card"
        >
          <Link href="#/metodologia">
            Ver la metodología
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        </Button>
      </div>
    </div>
  );
}

export function InicioView() {
  return (
    <DataGate>{(datos) => <ContenidoInicio datos={datos} />}</DataGate>
  );
}
