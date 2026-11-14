// FIREIA (M012) — Servicio del almacén: contrato + adaptador HTTP.
// Patrón: Pantalla → Servicio frontend → Adaptador → API existente.
// La API espejo del pipeline (Misión 004) NO se altera; este adaptador
// solo la consume. Un futuro adaptador contra la API real del pipeline
// implementará la misma interfaz.

import type {
  Almacen,
  AnomaliasExp001,
  Evento,
  Observacion,
} from "@/lib/mvp-types";

export interface DatosMVP {
  health: {
    status: string;
    data_source: string;
    data_source_nota: string;
    cobertura: { desde: string; hasta: string; dias: number };
    resumen: Almacen["resumen"];
  };
  observaciones: Observacion[];
  stats: Almacen["stats"];
  eventos: Evento[];
  calidad: Almacen["calidad"];
  cobertura: Almacen["cobertura"];
  anomalias: AnomaliasExp001;
  departamentos: GeoJSON.FeatureCollection | null;
}

export interface AlmacenService {
  /** Carga los 8 endpoints del espejo en un solo objeto. */
  cargarTodo(): Promise<DatosMVP>;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json() as Promise<T>;
}

/** Adaptador HTTP contra la API espejo existente (solo lectura). */
export class HttpAlmacenAdapter implements AlmacenService {
  async cargarTodo(): Promise<DatosMVP> {
    const [health, obs, stats, eventos, calidad, cobertura, anomalias, geo] =
      await Promise.all([
        getJson<DatosMVP["health"]>("/api/health"),
        getJson<{ observaciones: Observacion[] }>("/api/observations"),
        getJson<{
          nacional_dia: Almacen["stats"]["nacional_dia"];
          departamento: Almacen["stats"]["departamento"];
        }>("/api/stats"),
        getJson<{ eventos: Evento[] }>("/api/events"),
        getJson<{ calidad: Almacen["calidad"] }>("/api/quality"),
        getJson<Almacen["cobertura"]>("/api/coverage"),
        getJson<AnomaliasExp001>("/api/anomalias"),
        getJson<{ geojson: GeoJSON.FeatureCollection }>(
          "/api/geo/departamentos",
        ),
      ]);

    return {
      health,
      observaciones: obs.observaciones,
      stats: {
        ...stats,
        nacional_semana: [],
        nacional_mes: [],
        departamento_dia: [],
      },
      eventos: eventos.eventos,
      calidad: calidad.calidad,
      cobertura: cobertura ?? undefined,
      anomalias,
      departamentos: geo.geojson,
    };
  }
}

/** Instancia única usada por el proveedor de datos de la SPA. */
export const almacenService: AlmacenService = new HttpAlmacenAdapter();
