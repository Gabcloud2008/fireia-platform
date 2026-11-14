// Tipos del almacén exportado por scripts/exportar_mvp.py (Misión 004).
// El origen de los datos es FIXTURE (datos sintéticos) y el banner de la UI
// lo muestra sin excepciones.

export type Sensor = "MODIS" | "VIIRS";

export interface Observacion {
  obs_id: string;
  product: string;
  sensor: Sensor;
  satellite: string;
  satellite_name: string;
  instrument: string;
  latitude: number;
  longitude: number;
  acq_date: string;
  acq_time: string;
  acq_datetime_utc: string;
  confidence: string;
  confidence_band: string;
  frp: number | null;
  brightness: number | null;
  bright_t31: number | null;
  bright_ti4: number | null;
  bright_ti5: number | null;
  scan: number | null;
  track: number | null;
  daynight: "D" | "N";
  version: string;
  dentro_pais: boolean;
  departamento: string | null;
  distrito: string | null;
  version_limites: string;
}

export interface MiembroEvento {
  event_id: string;
  obs_id: string;
  product: string;
  sensor: Sensor;
  satellite_name: string;
  latitude: number;
  longitude: number;
  acq_datetime_utc: string;
  confidence: string;
  confidence_band: string;
  frp: number | null;
  daynight: string;
  departamento: string | null;
  distrito: string | null;
}

export interface Evento {
  event_id: string;
  metodo: string;
  n_observaciones: number;
  productos: string[];
  sensores: Sensor[];
  satelites: string[];
  primera_obs_utc: string;
  ultima_obs_utc: string;
  duracion_segundos: number;
  lat_centroide: number;
  lon_centroide: number;
  dispersion_metros: number;
  diametro_metros: number;
  alerta_encadenamiento: boolean;
  frp_total: number | null;
  frp_max: number | null;
  frp_por_producto: Record<string, number>;
  miembros: MiembroEvento[];
}

export interface StatDia {
  acq_date: string;
  product: string;
  detecciones: number;
  frp_total: number;
}

export interface StatDepartamento {
  departamento: string;
  product: string;
  detecciones: number;
  frp_total: number;
}

export interface EstadoIngesta {
  state: string;
  registros: number;
}

export interface CorridaIngesta {
  provider: string;
  product: string;
  state: string;
  reason: string;
  occurred_at_utc: string;
}

export interface Almacen {
  meta: {
    exportado_en: string;
    data_source: "fixture" | "firms_api" | "mixto";
    data_source_nota: string;
    almacen: string;
    cobertura: { desde: string; hasta: string; dias: number };
  };
  observaciones: Observacion[];
  stats: {
    nacional_dia: StatDia[];
    nacional_semana: Record<string, unknown>[];
    nacional_mes: Record<string, unknown>[];
    departamento: StatDepartamento[];
    departamento_dia: Record<string, unknown>[];
  };
  resumen: {
    total: number;
    modis: number;
    viirs: number;
    dentro_pais: number;
    eventos: number;
    departamentos_afectados: string[];
    pares_candidatos: number;
  };
  eventos: Evento[];
  cobertura?: {
    desde: string;
    hasta: string;
    dias: { fecha: string; estado: string }[];
    resumen: Record<string, number>;
    cobertura_por_producto: Record<string, { desde: string; hasta: string; inferida: boolean }>;
    supuestos: string[];
  };
  calidad: {
    estados: EstadoIngesta[];
    corridas: CorridaIngesta[];
    cuarentena_registros: number;
    pares_candidatos: number;
  };
}

export interface DetalleAnomalia {
  fecha: string;
  valor: number;
  esperado: number;
  z: number;
  direccion: string;
  es_anomalia: boolean;
  inyectada: boolean;
}

export interface PuntoSerie {
  fecha: string;
  valor: number;
  en_evaluacion: boolean;
}

export interface AnomaliasExp001 {
  experimento: string;
  datos: string;
  metodo: string;
  umbral_z: number;
  dias_evaluados: number;
  anomalias_inyectadas: string[];
  anomalias_detectadas: string[];
  verdaderos_positivos: number;
  falsos_positivos: number;
  recall: number;
  precision: number | null;
  mae_persistencia_baseline: number;
  detalle: DetalleAnomalia[];
  serie_completa: PuntoSerie[];
  nota: string;
}
