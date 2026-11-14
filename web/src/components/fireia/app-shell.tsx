"use client";

// Armazón de FIREIA (M012): barra superior con botón hamburguesa, menú
// lateral desplegable por categorías (Sheet de Radix: animación suave,
// foco atrapado, cierre con Esc y con click fuera), indicador del origen
// de los datos y pie de página claro. La navegación usa hash (#/vista):
// nunca recarga la aplicación.

import { useEffect, useState, type ReactNode } from "react";
import { HashLink as Link } from "@/components/fireia/hash-link";
import { LiveStatus } from "@/components/fireia/live-status";
import { Flame, Menu, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

import { useFireia } from "./data-provider";
import { NAV, VISTA_LABEL, type Vista } from "./nav-config";

function Marca({ compacto = false }: { compacto?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <span
        className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-b from-[#f4c5a5] to-[#e9a477] text-[#6b3312] shadow-[inset_0_1px_0_rgb(255_255_255/0.45)]"
        aria-hidden
      >
        <Flame className="size-5" />
      </span>
      <span className="leading-tight">
        <span
          className="block font-display text-[17px] font-bold tracking-tight text-foreground"
          style={{ fontVariationSettings: '"opsz" 30, "SOFT" 40' }}
        >
          FIREIA
        </span>
        {!compacto && (
          <span className="hidden text-[10.5px] font-medium uppercase tracking-[0.13em] text-muted-foreground sm:block">
            Inteligencia de incendios · Paraguay
          </span>
        )}
      </span>
    </span>
  );
}

function InsigniaOrigenDatos() {
  const { datos, cargando, error } = useFireia();

  let estilo = "bg-secondary text-muted-foreground";
  let texto = "Conectando con el almacén…";
  if (error && !datos) {
    estilo = "bg-[#f7dfd2] text-[#b5543b]";
    texto = "Almacén no disponible";
  } else if (datos) {
    if (datos.health.data_source === "fixture") {
      estilo = "bg-tint text-flame";
      texto = "Datos de demostración";
    } else {
      estilo = "bg-[#e3efe3] text-[#3d6b4f]";
      texto = "Datos reales";
    }
  }

  return (
    <Badge
      variant="outline"
      aria-live="polite"
      className={`gap-1.5 rounded-full border-transparent px-3 py-1 text-[11px] font-medium ${estilo}`}
    >
      {cargando && !datos ? (
        <span
          className="size-1.5 animate-pulse rounded-full bg-current"
          aria-hidden
        />
      ) : (
        <span className="size-1.5 rounded-full bg-current" aria-hidden />
      )}
      {texto}
    </Badge>
  );
}

function NavLateral({
  vistaActiva,
  onNavigate,
}: {
  vistaActiva: Vista;
  onNavigate?: () => void;
}) {
  return (
    <nav aria-label="Navegación principal" className="flex flex-col gap-5 px-3 pb-6">
      {NAV.map((grupo) => (
        <div key={grupo.titulo}>
          <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/80">
            {grupo.titulo}
          </p>
          <ul className="space-y-0.5">
            {grupo.items.map((item) => {
              const activa = item.vista === vistaActiva;
              const Icono = item.icon;
              return (
                <li key={item.vista}>
                  <SheetClose asChild>
                    <Link
                      href={`#/${item.vista}`}
                      onClick={onNavigate}
                      aria-current={activa ? "page" : undefined}
                      className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring ${
                        activa
                          ? "bg-tint font-medium text-foreground"
                          : "text-brown hover:bg-secondary hover:text-foreground"
                      }`}
                    >
                      <Icono
                        className={`size-4 shrink-0 transition-colors ${
                          activa
                            ? "text-flame"
                            : "text-muted-foreground group-hover:text-brown"
                        }`}
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1 truncate">{item.label}</span>
                      {item.badge ? (
                        <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                          {item.badge}
                        </span>
                      ) : activa ? (
                        <span
                          className="size-1.5 shrink-0 rounded-full bg-flame"
                          aria-hidden
                        />
                      ) : null}
                    </Link>
                  </SheetClose>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
      <p className="px-3 pt-2 text-[10px] leading-relaxed text-muted-foreground/70">
        FIREIA · Inteligencia geoespacial de incendios — los datos de esta demo
        son sintéticos (fixtures de NASA FIRMS) hasta la ingesta real (Fase 1B).
      </p>
    </nav>
  );
}

export function AppShell({
  vista,
  children,
}: {
  vista: Vista;
  children: ReactNode;
}) {
  const [menuAbierto, setMenuAbierto] = useState(false);

  // Al cambiar de vista, subir al inicio de la página. El menú se cierra
  // solo (SheetClose en cada enlace), sin estados en cascada.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [vista]);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* --- barra superior --- */}
      <header className="sticky top-0 z-40 border-b border-border bg-card/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 w-full max-w-7xl items-center gap-2 px-4 sm:px-6">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMenuAbierto(true)}
            aria-label="Abrir menú de navegación"
            aria-controls="fireia-nav"
            aria-expanded={menuAbierto}
            className="rounded-lg text-brown hover:bg-secondary hover:text-foreground"
          >
            <Menu className="size-5" aria-hidden />
          </Button>

          <Link
            href="#/inicio"
            className="rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="FIREIA — ir al inicio"
          >
            <Marca />
          </Link>

          <span
            className="ml-2 hidden min-w-0 items-center gap-2 md:flex"
            aria-hidden
          >
            <span className="h-4 w-px bg-border" />
            <span className="truncate text-sm text-muted-foreground">
              {VISTA_LABEL[vista]}
            </span>
          </span>

          <div className="ml-auto flex items-center gap-2">
            <LiveStatus />
            <InsigniaOrigenDatos />
          </div>
        </div>
      </header>

      {/* --- menú lateral desplegable --- */}
      <Sheet open={menuAbierto} onOpenChange={setMenuAbierto}>
        <SheetContent
          side="left"
          id="fireia-nav"
          className="w-[300px] max-w-[88vw] gap-0 border-r border-border bg-card p-0 sm:w-[320px]"
        >
          <SheetHeader className="space-y-0 border-b border-border px-5 py-4 text-left">
            <SheetTitle className="sr-only">Menú de navegación</SheetTitle>
            <div className="flex items-center justify-between gap-2">
              <Marca />
              <SheetClose
                asChild
                aria-label="Cerrar menú"
              >
                <Button
                  variant="ghost"
                  size="icon"
                  className="rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
                >
                  <X className="size-4.5" aria-hidden />
                </Button>
              </SheetClose>
            </div>
            <p className="pt-1 text-[11px] text-muted-foreground">
              Explorá la plataforma por categorías
            </p>
          </SheetHeader>
          <div className="overflow-y-auto pt-4">
            <NavLateral vistaActiva={vista} />
          </div>
        </SheetContent>
      </Sheet>

      {/* --- contenido principal --- */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        {children}
      </main>

      {/* --- pie de página --- */}
      <footer className="mt-auto border-t border-border bg-card">
        <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6">
          <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <div className="max-w-sm">
              <Marca />
              <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
                Vigilancia del territorio con los satélites MODIS y VIIRS de la
                NASA (FIRMS). Proyecto P400 — NASA Space Apps Challenge 2026,
                reto 1.9.
              </p>
            </div>
            <div className="grid gap-6 text-xs leading-relaxed text-muted-foreground sm:grid-cols-2 md:max-w-xl md:flex-1">
              <div>
                <p className="font-semibold text-foreground">Fuentes</p>
                <ul className="mt-2 space-y-1">
                  <li>Detecciones: NASA FIRMS · MODIS C6.1 + VIIRS NOAA-20</li>
                  <li>Límites: geoBoundaries gbOpen PRY · CC BY 4.0</li>
                  <li>Base cartográfica: OpenStreetMap</li>
                </ul>
                <Link
                  href="#/fuentes"
                  className="mt-2 inline-block font-medium text-flame underline-offset-4 hover:underline"
                >
                  Ver todas las fuentes
                </Link>
              </div>
              <div>
                <p className="font-semibold text-foreground">Honestidad de los datos</p>
                <ul className="mt-2 space-y-1">
                  <li>Esta demo usa fixtures sintéticos, declarados en pantalla</li>
                  <li>Sin modelos predictivos validados: no hay pronósticos</li>
                  <li>Navegar no dispara descargas ni consume cuota</li>
                </ul>
              </div>
            </div>
          </div>
          <div className="mt-7 flex flex-col gap-2 border-t border-border/70 pt-4 text-[11px] text-muted-foreground/80 sm:flex-row sm:items-center sm:justify-between">
            <p>FIREIA · Paraguay Fire Intelligence</p>
            <p className="font-mono">p400/modis-viirs-hotspots-paraguay</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
