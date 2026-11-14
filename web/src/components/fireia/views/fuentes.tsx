"use client";

// Fuentes de datos (v3 — catálogo tipo registro): filas de catálogo con
// sello de icono, metadatos mono a la derecha y estado real por fuente.

import { Database, Map, Satellite } from "lucide-react";

import { DataGate } from "@/components/fireia/data-gate";
import { SectionHero } from "@/components/fireia/section-hero";
import { Badge } from "@/components/ui/badge";

export function FuentesView() {
  return (
    <div className="space-y-5">
      <SectionHero
        indice="02"
        categoria="Información · de dónde viene cada dato"
        title="El catálogo de fuentes."
        lede="Productos satelitales, límites oficiales y cartografía base: qué alimenta a FIREIA, con qué licencia y en qué estado está cada pieza en esta demo."
      />
      <DataGate>
        {(datos) => {
          const ventanas = datos.cobertura?.cobertura_por_producto ?? {};
          return (
            <div className="space-y-4">
              <div className="divide-y divide-border/70 overflow-hidden rounded-2xl border border-border bg-card">
                {[
                  {
                    icono: (
                      <Satellite className="size-5 text-modis" aria-hidden />
                    ),
                    sello: "bg-tint",
                    nombre: "NASA FIRMS · MODIS C6.1 NRT",
                    descripcion:
                      "Detecciones de focos activos del instrumento MODIS (satélites Terra y Aqua), resolución de 1 km.",
                    filas: [
                      ["Producto", "MODIS_NRT"],
                      ventanas["MODIS_NRT"]
                        ? [
                            "Ventana en el almacén",
                            `${ventanas["MODIS_NRT"].desde} → ${ventanas["MODIS_NRT"].hasta}`,
                          ]
                        : null,
                    ].filter(Boolean) as Array<[string, string]>,
                    estado: "fixtures sintéticos",
                    claseEstado: "bg-tint text-flame",
                  },
                  {
                    icono: (
                      <Satellite className="size-5 text-viirs" aria-hidden />
                    ),
                    sello: "bg-[#e0edec]",
                    nombre: "NASA FIRMS · VIIRS NOAA-20 375 m",
                    descripcion:
                      "Detecciones del instrumento VIIRS (satélite NOAA-20): 375 m de resolución y mayor sensibilidad a fuegos pequeños.",
                    filas: [
                      ["Producto", "VIIRS_NOAA20_NRT"],
                      ventanas["VIIRS_NOAA20_NRT"]
                        ? [
                            "Ventana en el almacén",
                            `${ventanas["VIIRS_NOAA20_NRT"].desde} → ${ventanas["VIIRS_NOAA20_NRT"].hasta}`,
                          ]
                        : null,
                    ].filter(Boolean) as Array<[string, string]>,
                    estado: "fixtures sintéticos",
                    claseEstado: "bg-tint text-flame",
                  },
                  {
                    icono: <Map className="size-5 text-brown" aria-hidden />,
                    sello: "bg-secondary",
                    nombre: "geoBoundaries gbOpen · PRY",
                    descripcion:
                      "Límites departamentales oficiales (geometría DGEEC) para asignar cada detección a su departamento.",
                    filas: [
                      ["Versión de límites", "9469f09"],
                      ["Licencia", "CC BY 4.0"],
                    ],
                    estado: "integrado (real)",
                    claseEstado: "bg-[#e3efe3] text-[#3d6b4f]",
                  },
                  {
                    icono: <Map className="size-5 text-brown" aria-hidden />,
                    sello: "bg-secondary",
                    nombre: "Cartografía base · OpenStreetMap",
                    descripcion:
                      "El mapa claro sobre el que se dibujan las detecciones (tiles estándar).",
                    filas: [
                      ["Colaboradores", "OpenStreetMap"],
                      ["Licencia", "ODbL"],
                    ],
                    estado: "servicio externo (mapa)",
                    claseEstado: "bg-[#e3efe3] text-[#3d6b4f]",
                  },
                ].map((f) => (
                  <div
                    key={f.nombre}
                    className="flex flex-col gap-4 px-5 py-5 sm:flex-row sm:items-center sm:gap-5"
                  >
                    <span
                      className={`flex size-11 shrink-0 items-center justify-center rounded-2xl ${f.sello}`}
                      aria-hidden
                    >
                      {f.icono}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-display text-[16px] font-semibold tracking-tight text-foreground">
                        {f.nombre}
                      </p>
                      <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                        {f.descripcion}
                      </p>
                    </div>
                    <dl className="shrink-0 space-y-1 text-right">
                      {f.filas.map(([k, v]) => (
                        <div key={k} className="text-[11px]">
                          <dt className="inline text-muted-foreground">{k}: </dt>
                          <dd className="inline font-mono text-foreground">{v}</dd>
                        </div>
                      ))}
                    </dl>
                    <Badge
                      className={`shrink-0 rounded-full border-transparent text-[10px] font-medium ${f.claseEstado}`}
                    >
                      {f.estado}
                    </Badge>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border border-border bg-secondary/60 px-5 py-4 text-xs text-muted-foreground">
                <p>
                  <strong className="text-foreground">Origen global:</strong>{" "}
                  {datos.health.data_source} — {datos.health.data_source_nota}
                </p>
                <a
                  href="https://firms.modaps.eosdis.nasa.gov/"
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-flame underline-offset-4 hover:underline"
                >
                  Catálogo completo de FIRMS ↗
                </a>
              </div>
            </div>
          );
        }}
      </DataGate>
    </div>
  );
}
