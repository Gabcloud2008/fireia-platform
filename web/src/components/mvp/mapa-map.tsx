"use client";

// Mapas de FIREIA (M012, tema claro): base cartográfica clara (CARTO
// Positron), departamentos oficiales (geoBoundaries gbOpen, CC BY 4.0),
// detecciones por sensor y eventos de co-detección.
// - MapaNacional: variante de exhibición para el inicio (solo visual).
// - MapaMap (default): variante interactiva con selección de observaciones
//   y eventos (callbacks hacia el panel de detalles) y capas activables.
// Consumidor puro de datos — no dispara ninguna ingesta (contrato Misión 004).

import { useEffect, useRef } from "react";
import {
  config,
  GeoJSONSource,
  Map as MLMap,
  NavigationControl,
  ScaleControl,
  type MapLayerMouseEvent,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { Evento, Observacion } from "@/lib/mvp-types";

// MapLibre v6 resuelve su web worker desde import.meta.url, que bajo el
// bundler de dev no es una URL http y el worker queda vacío (mapa en negro).
// Sirviéndolo desde /public y apuntando config.WORKER_URL al mismo origen
// el worker carga siempre, también dentro del panel de preview.
config.WORKER_URL = "/maplibre-gl-worker.mjs";

// Identidad FIREIA: naranja para MODIS, verde azulado para VIIRS.
const COLOR_MODIS = "#d97c45";
const COLOR_VIIRS = "#3e8e87";

const TEXTO = "#39332f";
const ETIQUETA = "#82766d";
const SUAVE = "#a99a8c";

// Base clara OpenStreetMap estándar: tonos claros que armonizan con el
// tema FIREIA y no requieren API key (CARTO exige key desde 2025).
// Para afinar aún más el contraste, el fondo se lava hacia crema.
const ESTILO: StyleSpecification = {
  version: 8,
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: {
    base: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution:
        '© Colaboradores de <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    },
  },
  layers: [
    { id: "fondo-crema", type: "background", paint: { "background-color": "#fff9f3" } },
    {
      id: "fondo",
      type: "raster",
      source: "base",
      paint: { "raster-saturation": -0.35, "raster-brightness-max": 0.95 },
    },
  ],
};

function obsToGeoJson(obs: Observacion[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: obs.map((o) => ({
      type: "Feature",
      id: undefined,
      geometry: { type: "Point", coordinates: [o.longitude, o.latitude] },
      properties: {
        obs_idx: String(o.obs_id),
        sensor: o.sensor,
        product: o.product,
        satellite_name: o.satellite_name,
        fecha: o.acq_date,
        hora: o.acq_time,
        frp: o.frp,
        confianza: o.confidence_band,
        departamento: o.departamento ?? "—",
        distrito: o.distrito ?? "—",
        daynight: o.daynight,
      },
    })),
  };
}

function eventosToGeoJson(eventos: Evento[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: eventos.map((e) => ({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [e.lon_centroide, e.lat_centroide],
      },
      properties: {
        event_idx: String(e.event_id),
        n_observaciones: e.n_observaciones,
        productos: e.productos.join(" × "),
        duracion: e.duracion_segundos,
        frp_total: e.frp_total,
      },
    })),
  };
}

/** Capas comunes (fuente + estilo) compartidas por ambas variantes. */
function agregarCapas(
  map: MLMap,
  opts: { interactivo: boolean },
  selectObs?: (id: string) => void,
  selectEvento?: (id: string) => void,
) {
  map.addSource("departamentos", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  map.addSource("observaciones", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  map.addSource("eventos", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });

  map.addLayer({
    id: "dep-fill",
    type: "fill",
    source: "departamentos",
    paint: {
      "fill-color": [
        "case",
        ["==", ["get", "seleccionado"], true],
        "#e9a477",
        "#e5d3be",
      ],
      "fill-opacity": [
        "case",
        ["==", ["get", "seleccionado"], true],
        0.22,
        0.14,
      ],
    },
  });
  map.addLayer({
    id: "dep-line",
    type: "line",
    source: "departamentos",
    paint: {
      "line-color": [
        "case",
        ["==", ["get", "seleccionado"], true],
        "#c05f2c",
        "#c4ae97",
      ],
      "line-width": ["case", ["==", ["get", "seleccionado"], true], 2, 0.8],
      "line-opacity": 0.85,
    },
  });
  map.addLayer({
    id: "obs-glow",
    type: "circle",
    source: "observaciones",
    paint: {
      "circle-color": [
        "case",
        ["==", ["get", "sensor"], "MODIS"],
        COLOR_MODIS,
        COLOR_VIIRS,
      ],
      "circle-radius": 13,
      "circle-opacity": 0.14,
    },
  });
  map.addLayer({
    id: "obs-modis",
    type: "circle",
    source: "observaciones",
    filter: ["==", ["get", "sensor"], "MODIS"],
    paint: {
      "circle-color": COLOR_MODIS,
      "circle-radius": 6,
      "circle-stroke-width": 1.5,
      "circle-stroke-color": "#8a4516",
    },
  });
  map.addLayer({
    id: "obs-viirs",
    type: "circle",
    source: "observaciones",
    filter: ["==", ["get", "sensor"], "VIIRS"],
    paint: {
      "circle-color": COLOR_VIIRS,
      "circle-radius": 6,
      "circle-stroke-width": 1.5,
      "circle-stroke-color": "#1f5450",
    },
  });
  map.addLayer({
    id: "evento-ring",
    type: "circle",
    source: "eventos",
    paint: {
      "circle-radius": 13,
      "circle-color": "transparent",
      "circle-stroke-width": 2,
      "circle-stroke-color": "#39332f",
      "circle-stroke-opacity": 0.8,
    },
  });

  if (!opts.interactivo) return;

  // selección: cursor + click → panel de detalles (no popups)
  for (const layer of ["obs-modis", "obs-viirs"]) {
    map.on("click", layer, (e: MapLayerMouseEvent) => {
      const f = e.features?.[0];
      if (!f || !selectObs) return;
      selectObs(String(f.properties?.obs_idx ?? ""));
    });
    map.on("mouseenter", layer, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", layer, () => {
      map.getCanvas().style.cursor = "";
    });
  }
  map.on("click", "evento-ring", (e: MapLayerMouseEvent) => {
    const f = e.features?.[0];
    if (!f || !selectEvento) return;
    selectEvento(String(f.properties?.event_idx ?? ""));
  });
  map.on("mouseenter", "evento-ring", () => {
    map.getCanvas().style.cursor = "pointer";
  });
  map.on("mouseleave", "evento-ring", () => {
    map.getCanvas().style.cursor = "";
  });
}

// ---------------------------------------------------------------------------
// Variante de exhibición: mapa nacional para el inicio.
// ---------------------------------------------------------------------------

export function MapaNacional({
  observaciones,
  departamentos,
}: {
  observaciones: Observacion[];
  departamentos: GeoJSON.FeatureCollection | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = new MLMap({
      container: ref.current,
      style: ESTILO,
      center: [-58.4, -23.5],
      zoom: 4.55,
      minZoom: 4,
      maxZoom: 9,
      attributionControl: { compact: true },
      interactive: false,
    });
    mapRef.current = map;
    map.on("load", () => {
      agregarCapas(map, { interactivo: false });
      if (departamentos) {
        (map.getSource("departamentos") as GeoJSONSource)?.setData(
          departamentos,
        );
      }
      (map.getSource("observaciones") as GeoJSONSource)?.setData(
        obsToGeoJson(observaciones),
      );
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !departamentos) return;
    const aplicar = () =>
      (map.getSource("departamentos") as GeoJSONSource)?.setData(departamentos);
    if (map.isStyleLoaded()) aplicar();
    else map.once("load", aplicar);
  }, [departamentos]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const aplicar = () =>
      (map.getSource("observaciones") as GeoJSONSource)?.setData(
        obsToGeoJson(observaciones),
      );
    if (map.isStyleLoaded()) aplicar();
    else map.once("load", aplicar);
  }, [observaciones]);

  return (
    <div
      ref={ref}
      className="size-full"
      role="img"
      aria-label="Mapa de Paraguay con las detecciones de focos activos del período"
    />
  );
}

// ---------------------------------------------------------------------------
// Variante interactiva: mapa principal de la vista "Mapa de Paraguay".
// ---------------------------------------------------------------------------

export interface CapasMapa {
  departamentos: boolean;
  observaciones: boolean;
  eventos: boolean;
}

interface Props {
  observaciones: Observacion[];
  eventos: Evento[];
  departamentos: GeoJSON.FeatureCollection | null;
  departamentoSeleccionado: string | null;
  onSelectDepartamento: (nombre: string | null) => void;
  onSelectObservacion: (obs: Observacion) => void;
  onSelectEvento: (evento: Evento) => void;
  capas: CapasMapa;
}

export default function MapaMap({
  observaciones,
  eventos,
  departamentos,
  departamentoSeleccionado,
  onSelectDepartamento,
  onSelectObservacion,
  onSelectEvento,
  capas,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const selectDepRef = useRef(onSelectDepartamento);
  const selectObsRef = useRef(onSelectObservacion);
  const selectEventoRef = useRef(onSelectEvento);
  const obsIndexRef = useRef(new Map<string, Observacion>());
  const eventoIndexRef = useRef(new Map<string, Evento>());

  useEffect(() => {
    selectDepRef.current = onSelectDepartamento;
  }, [onSelectDepartamento]);
  useEffect(() => {
    selectObsRef.current = onSelectObservacion;
  }, [onSelectObservacion]);
  useEffect(() => {
    selectEventoRef.current = onSelectEvento;
  }, [onSelectEvento]);

  useEffect(() => {
    obsIndexRef.current = new Map(
      observaciones.map((o) => [o.obs_id, o] as const),
    );
  }, [observaciones]);
  useEffect(() => {
    eventoIndexRef.current = new Map(
      eventos.map((e) => [e.event_id, e] as const),
    );
  }, [eventos]);

  // --- inicialización (una sola vez) ---
  useEffect(() => {
    if (!ref.current || mapRef.current) return;

    const map = new MLMap({
      container: ref.current,
      style: ESTILO,
      center: [-58.4, -23.4],
      zoom: 5.3,
      minZoom: 4,
      maxZoom: 12,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(
      new ScaleControl({ maxWidth: 120, unit: "metric" }),
      "bottom-right",
    );

    map.on("load", () => {
      agregarCapas(
        map,
        { interactivo: true },
        (id) => {
          const o = obsIndexRef.current.get(id);
          if (o) selectObsRef.current(o);
        },
        (id) => {
          const e = eventoIndexRef.current.get(id);
          if (e) selectEventoRef.current(e);
        },
      );

      // click en departamento → filtro (y click en vacío deselecciona)
      map.on("click", "dep-fill", (e: MapLayerMouseEvent) => {
        const nombre = e.features?.[0]?.properties?.nombre as
          | string
          | undefined;
        selectDepRef.current(nombre ?? null);
      });
      map.on("mouseenter", "dep-fill", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "dep-fill", () => {
        map.getCanvas().style.cursor = "";
      });
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // --- datos de departamentos + selección ---
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !departamentos) return;
    const aplicar = () => {
      const data: GeoJSON.FeatureCollection = {
        ...departamentos,
        features: departamentos.features.map((f) => ({
          ...f,
          properties: {
            ...f.properties,
            seleccionado: f.properties?.nombre === departamentoSeleccionado,
          },
        })),
      };
      (map.getSource("departamentos") as GeoJSONSource)?.setData(data);
    };
    if (map.isStyleLoaded()) aplicar();
    else map.once("load", aplicar);
  }, [departamentos, departamentoSeleccionado]);

  // --- observaciones filtradas ---
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const aplicar = () =>
      (map.getSource("observaciones") as GeoJSONSource)?.setData(
        obsToGeoJson(observaciones),
      );
    if (map.isStyleLoaded()) aplicar();
    else map.once("load", aplicar);
  }, [observaciones]);

  // --- eventos ---
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const aplicar = () =>
      (map.getSource("eventos") as GeoJSONSource)?.setData(
        eventosToGeoJson(eventos),
      );
    if (map.isStyleLoaded()) aplicar();
    else map.once("load", aplicar);
  }, [eventos]);

  // --- visibilidad de capas ---
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const aplicar = () => {
      const vis = (v: boolean) => (v ? "visible" : "none");
      for (const id of ["dep-fill", "dep-line"])
        map.setLayoutProperty(id, "visibility", vis(capas.departamentos));
      for (const id of ["obs-glow", "obs-modis", "obs-viirs"])
        map.setLayoutProperty(id, "visibility", vis(capas.observaciones));
      map.setLayoutProperty("evento-ring", "visibility", vis(capas.eventos));
    };
    if (map.isStyleLoaded()) aplicar();
    else map.once("load", aplicar);
  }, [capas]);

  return (
    <div
      ref={ref}
      className="h-[62vh] min-h-[420px] w-full overflow-hidden rounded-xl border border-border md:h-[calc(100dvh-330px)] md:min-h-[500px]"
      role="application"
      aria-label="Mapa de detecciones de focos activos en Paraguay"
    />
  );
}
