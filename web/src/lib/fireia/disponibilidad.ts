// FIREIA (M012) — Arquitectura modular del frontend.
// Estados de disponibilidad de cada módulo de la plataforma y registro
// central. Las pantallas consultan este registro; los adaptadores concretos
// viven en ./services. Sustituir un adaptador sintético por uno real no
// debe requerir reconstruir la interfaz.

export type Disponibilidad =
  | "conectado" // servicio real conectado y respondiendo
  | "sin_datos" // conectado, pero el almacén no tiene datos para mostrar
  | "en_desarrollo" // función planificada, en construcción
  | "pendiente" // esperando conexión con el servicio real
  | "error" // el servicio respondió con error
  | "simulacion"; // demostración con datos sintéticos controlados

export interface InfoModulo {
  clave: string;
  nombre: string;
  descripcion: string;
  disponibilidad: Disponibilidad;
  nota: string;
}

export const MODULOS: InfoModulo[] = [
  {
    clave: "almacen",
    nombre: "Almacén de observaciones",
    descripcion:
      "Espejo de solo lectura de la API del pipeline: observaciones, eventos, estadísticas, calidad y cobertura.",
    disponibilidad: "conectado",
    nota: "BASE REAL NACIONAL M014: 2.691.999 observaciones FIRMS 2000–2026 (SHA-256 verificado). Muestra web: últimos 30 días + series agregadas.",
  },
  {
    clave: "cartografia",
    nombre: "Cartografía oficial",
    descripcion: "Límites departamentales de Paraguay (geoBoundaries gbOpen, CC BY 4.0).",
    disponibilidad: "conectado",
    nota: "Geometrías reales DGEEC, versión 9469f09.",
  },
  {
    clave: "ambiental",
    nombre: "Inteligencia ambiental",
    descripcion:
      "Variables meteorológicas y de cobertura del suelo (CHIRPS, ERA5-Land, FWI, WorldCover, MCD64A1).",
    disponibilidad: "conectado",
    nota: "7 fuentes REALES integradas y trazables (Misión D): asociación celda×mes sobre grilla nacional 0,1°.",
  },
  {
    clave: "conversacional",
    nombre: "Centro de inteligencia",
    descripcion:
      "Consultas en lenguaje natural sobre la información disponible.",
    disponibilidad: "simulacion",
    nota:
      "Modo demostración local: respuestas por reglas sobre el almacén cargado, sin IA conectada.",
  },
  {
    clave: "riesgo",
    nombre: "Riesgo y estimaciones futuras",
    descripcion:
      "Probabilidad de detección VIIRS por celda el mes siguiente, con evaluación honesta.",
    disponibilidad: "conectado",
    nota: "IA VALIDADA CON LIMITACIONES: RF ROC-AUC 0,797 (evaluación temporal 2025–26, base real M014). La etiqueta es detección, no incendio confirmado.",
  },
  {
    clave: "simulaciones",
    nombre: "Laboratorio de simulaciones",
    descripcion:
      "Demostraciones interactivas con datos sintéticos controlados.",
    disponibilidad: "simulacion",
    nota: "Todo lo que se muestra aquí es sintético y está etiquetado como tal.",
  },
  {
    clave: "informes",
    nombre: "Informes y exportaciones",
    descripcion: "Resúmenes por período y región, y exportación de documentos.",
    disponibilidad: "pendiente",
    nota: "La vista previa se calcula localmente; la exportación requiere backend.",
  },
  {
    clave: "validacion",
    nombre: "Validación científica",
    descripcion:
      "Métricas de evaluación, reproducibilidad y comparación con fuentes independientes.",
    disponibilidad: "conectado",
    nota: "IA evaluada con partición temporal + geográfica; MCD64A1×FireCCI51 ρ=0,876; exp_001 queda como evidencia SINTÉTICA.",
  },
];

export const ETIQUETA_DISPONIBILIDAD: Record<
  Disponibilidad,
  { etiqueta: string; clase: string }
> = {
  conectado: {
    etiqueta: "Conectado",
    clase: "border-transparent bg-[#e3efe3] text-[#3d6b4f]",
  },
  sin_datos: {
    etiqueta: "Sin datos aún",
    clase: "border-transparent bg-secondary text-muted-foreground",
  },
  en_desarrollo: {
    etiqueta: "En desarrollo",
    clase: "border-transparent bg-[#fdf3e3] text-[#8a6116]",
  },
  pendiente: {
    etiqueta: "Pendiente de conexión",
    clase: "border-transparent bg-secondary text-muted-foreground",
  },
  error: {
    etiqueta: "Error de conexión",
    clase: "border-transparent bg-[#f7dfd2] text-[#b5543b]",
  },
  simulacion: {
    etiqueta: "Simulación",
    clase: "border-transparent bg-tint text-flame",
  },
};
