// FIREIA (M014+Misión D) — Servicio de inteligencia ambiental: catálogo
// de las 7 fuentes REALES integradas y trazables (asociación celda×mes
// sobre la grilla nacional 0,1°). Los datos fluyen por /api/ambiental.

export type EstadoFuente =
  | "investigada" // documentada, sin descarga
  | "disponible" // publicada y accesible, sin consumir
  | "descargada" // archivada localmente, sin integrar
  | "integrada" // fluye al almacén
  | "pendiente"; // por investigar

export interface VariableAmbiental {
  id: string;
  nombre: string;
  descripcion: string;
  unidad: string;
  fuente: string;
  licencia: string;
  estado: EstadoFuente;
  resolucion: string;
}

export interface AmbientalService {
  listarVariables(): VariableAmbiental[];
}

const CATALOGO: VariableAmbiental[] = [
  {
    id: "temperatura",
    nombre: "Temperatura del aire",
    descripcion:
      "Temperatura a 2 metros del suelo (media y máxima). Los días de calor extremo habilitan el fuego.",
    unidad: "°C",
    fuente: "ERA5-Land (Copernicus Climate Data Store)",
    licencia: "Licencia abierta CMEMS",
    estado: "integrada",
    resolucion: "0,1° · mensual agregada",
  },
  {
    id: "precipitacion",
    nombre: "Precipitación",
    descripcion:
      "Lluvia acumulada mensual por celda. La sequía prolongada seca la vegetación y facilita la propagación.",
    unidad: "mm",
    fuente: "CHIRPS v2.0 (Climate Hazards Group)",
    licencia: "Uso público con atribución",
    estado: "integrada",
    resolucion: "0,05° · mensual agregada",
  },
  {
    id: "humedad_suelo",
    nombre: "Humedad de suelo",
    descripcion:
      "Agua en las capas superficiales (m³/m³). Es la variable con la asociación más fuerte con el fuego nacional (ρ = −0,39).",
    unidad: "m³/m³",
    fuente: "ERA5-Land (Copernicus Climate Data Store)",
    licencia: "Licencia abierta CMEMS",
    estado: "integrada",
    resolucion: "0,1° · mensual agregada",
  },
  {
    id: "fwi",
    nombre: "Índice de riesgo FWI",
    descripcion:
      "Fire Weather Index del GFWED: riesgo meteorológico de incendio agregado por celda y mes.",
    unidad: "índice",
    fuente: "FWI GFWED (NASA GES DISC / ECMWF)",
    licencia: "Uso libre con atribución",
    estado: "integrada",
    resolucion: "0,25° re-muestreado · mensual",
  },
  {
    id: "viento",
    nombre: "Viento",
    descripcion:
      "Velocidad a 10 metros. El viento aviva los focos activos y dispersa el humo.",
    unidad: "m/s",
    fuente: "ERA5-Land (Copernicus Climate Data Store)",
    licencia: "Licencia abierta CMEMS",
    estado: "integrada",
    resolucion: "0,1° · mensual agregada",
  },
  {
    id: "humedad",
    nombre: "Humedad relativa y VPD",
    descripcion:
      "Humedad del aire y déficit de presión de vapor: cuánta agua pide la atmósfera (ρ = +0,26 con el fuego).",
    unidad: "% · kPa",
    fuente: "ERA5-Land (Copernicus Climate Data Store)",
    licencia: "Licencia abierta CMEMS",
    estado: "integrada",
    resolucion: "0,1° · mensual agregada",
  },
  {
    id: "cobertura",
    nombre: "Cobertura del suelo",
    descripcion:
      "Bosque, pastizal, cultivo por celda. El fuego nacional se concentra en bosque y pastizal del Chaco.",
    unidad: "categorías",
    fuente: "ESA WorldCover v200",
    licencia: "CC BY 4.0",
    estado: "integrada",
    resolucion: "10 m · anual (2020-2021)",
  },
  {
    id: "area_quemada",
    nombre: "Área quemada",
    descripcion:
      "Superficie quemada mensual por celda; MCD64A1 y FireCCI51 validados entre sí (ρ = 0,876). Contexto, no predicción.",
    unidad: "km²",
    fuente: "MCD64A1 v6.1 (NASA) · FireCCI51 (ESA CCI)",
    licencia: "Uso libre con atribución",
    estado: "integrada",
    resolucion: "500 m · mensual",
  },
  {
    id: "goes",
    nombre: "Detecciones geoestacionarias",
    descripcion:
      "Focos y FRP del ABI GOES-16/19: cobertura continua desde el este, complemento a las órbitas polares.",
    unidad: "detecciones · MW",
    fuente: "GOES ABI FDCF (NOAA/NASA)",
    licencia: "Uso libre con atribución",
    estado: "integrada",
    resolucion: "~2 km · por escena",
  },
];

export class CatalogoAmbientalAdapter implements AmbientalService {
  listarVariables(): VariableAmbiental[] {
    return CATALOGO;
  }
}

export const ambientalService: AmbientalService =
  new CatalogoAmbientalAdapter();

export const ETIQUETA_ESTADO_FUENTE: Record<
  EstadoFuente,
  { etiqueta: string; clase: string }
> = {
  investigada: {
    etiqueta: "Investigada",
    clase: "border-transparent bg-[#fdf3e3] text-[#8a6116]",
  },
  disponible: {
    etiqueta: "Disponible",
    clase: "border-transparent bg-[#e3efe3] text-[#3d6b4f]",
  },
  descargada: {
    etiqueta: "Descargada",
    clase: "border-transparent bg-[#e3efe3] text-[#3d6b4f]",
  },
  integrada: {
    etiqueta: "Integrada",
    clase: "border-transparent bg-[#e3efe3] text-[#3d6b4f]",
  },
  pendiente: {
    etiqueta: "Pendiente",
    clase: "border-transparent bg-secondary text-muted-foreground",
  },
};
