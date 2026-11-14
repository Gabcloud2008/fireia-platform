// Navegación de FIREIA (M012 — dirección premium): seis grupos, ~20 vistas.
// La SPA vive en la ruta única "/"; las secciones se representan con
// "#/vista". Las vistas antiguas de M011 mantienen alias para no romper
// enlaces existentes.

import {
  Activity,
  ArrowLeftRight,
  BadgeCheck,
  CalendarClock,
  CloudSun,
  Database,
  FileText,
  FlaskConical,
  History,
  Home,
  Layers,
  Map,
  MessageCircle,
  Radar,
  Satellite,
  Settings,
  ShieldCheck,
  TrendingUp,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export type Vista =
  | "inicio"
  | "mapa"
  | "observaciones"
  | "comparacion"
  | "eventos"
  | "historial"
  | "ambiental"
  | "anomalias"
  | "inteligencia"
  | "simulaciones"
  | "riesgo"
  | "informes"
  | "fuentes"
  | "metodologia"
  | "documentacion"
  | "procesamiento"
  | "calidad"
  | "trazabilidad"
  | "validacion"
  | "estado";

export interface NavItem {
  vista: Vista;
  label: string;
  icon: LucideIcon;
  badge?: string;
}

export interface NavGroup {
  titulo: string;
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    titulo: "Inicio",
    items: [{ vista: "inicio", label: "Resumen general", icon: Home }],
  },
  {
    titulo: "Explorar",
    items: [
      { vista: "mapa", label: "Mapa de Paraguay", icon: Map },
      { vista: "observaciones", label: "Observaciones satelitales", icon: Satellite },
      { vista: "comparacion", label: "Comparación MODIS y VIIRS", icon: ArrowLeftRight },
    ],
  },
  {
    titulo: "Analizar",
    items: [
      { vista: "eventos", label: "Eventos de actividad de fuego", icon: Layers },
      { vista: "historial", label: "Historial y calendario", icon: CalendarClock },
      { vista: "ambiental", label: "Inteligencia ambiental", icon: CloudSun },
      { vista: "anomalias", label: "Anomalías", icon: Activity },
    ],
  },
  {
    titulo: "Inteligencia",
    items: [
      { vista: "inteligencia", label: "Centro de inteligencia", icon: MessageCircle },
      { vista: "simulaciones", label: "Simulaciones y escenarios", icon: FlaskConical, badge: "Sintético" },
      { vista: "riesgo", label: "Riesgo y estimaciones futuras", icon: TrendingUp, badge: "En desarrollo" },
    ],
  },
  {
    titulo: "Información",
    items: [
      { vista: "informes", label: "Informes", icon: FileText },
      { vista: "fuentes", label: "Fuentes de datos", icon: Database },
      { vista: "metodologia", label: "Metodología", icon: BadgeCheck },
      { vista: "documentacion", label: "Documentación", icon: FileText },
    ],
  },
  {
    titulo: "Sistema",
    items: [
      { vista: "procesamiento", label: "Ingestión y procesamiento", icon: Workflow },
      { vista: "calidad", label: "Calidad de información", icon: ShieldCheck },
      { vista: "trazabilidad", label: "Trazabilidad", icon: History },
      { vista: "validacion", label: "Validación científica", icon: Radar },
      { vista: "estado", label: "Estado de la plataforma", icon: Settings },
    ],
  },
];

/** Alias de vistas de la iteración anterior → vista actual. */
export const ALIAS_VISTAS: Record<string, Vista> = {
  panel: "inicio",
  actividad: "historial",
  territorio: "historial",
  factores: "ambiental",
  configuracion: "estado",
  pronosticos: "riesgo",
};

export const VISTA_LABEL: Record<Vista, string> = Object.fromEntries(
  NAV.flatMap((g) => g.items.map((it) => [it.vista, it.label])),
) as Record<Vista, string>;

export const VISTAS_VALIDAS: Set<string> = new Set(
  NAV.flatMap((g) => g.items.map((it) => it.vista)),
);
