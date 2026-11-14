// Lector del almacén REAL exportado (solo servidor). Los JSON los genera
// scripts/exportar_real.py desde hotspots_real.duckdb (Misión A) y los
// artefactos versionados de las misiones B–E. data_source = "real".

import { readFileSync } from "fs";
import path from "path";

import type { Almacen, AnomaliasExp001 } from "@/lib/mvp-types";

let cacheAlmacen: Almacen & Record<string, unknown> | null = null;
let cacheAnomalias: AnomaliasExp001 | null = null;
let cacheDepartamentos: unknown = null;
let cacheArmonizacion: unknown = null;
let cacheAmbiental: unknown = null;
let cacheIA: unknown = null;
let cacheActualizacion: unknown = null;

function leer<T>(nombre: string): T {
  const ruta = path.join(process.cwd(), "src", "data", "real", nombre);
  return JSON.parse(readFileSync(ruta, "utf-8")) as T;
}

export function getAlmacen(): Almacen & Record<string, unknown> {
  if (!cacheAlmacen) cacheAlmacen = leer<Almacen & Record<string, unknown>>("almacen.json");
  return cacheAlmacen;
}

export function getAnomalias(): AnomaliasExp001 {
  if (!cacheAnomalias) cacheAnomalias = leer<AnomaliasExp001>("anomalias_exp001.json");
  return cacheAnomalias;
}

export function getDepartamentos() {
  if (!cacheDepartamentos) cacheDepartamentos = leer("departamentos.geojson");
  return cacheDepartamentos;
}

export function getArmonizacion(): Record<string, unknown> {
  if (!cacheArmonizacion)
    cacheArmonizacion = leer<Record<string, unknown>>("armonizacion.json");
  return cacheArmonizacion as Record<string, unknown>;
}

export function getAmbiental(): Record<string, unknown> {
  if (!cacheAmbiental) cacheAmbiental = leer<Record<string, unknown>>("ambiental.json");
  return cacheAmbiental as Record<string, unknown>;
}

export function getIA(): Record<string, unknown> {
  if (!cacheIA) cacheIA = leer<Record<string, unknown>>("ia.json");
  return cacheIA as Record<string, unknown>;
}

export function getActualizacion(): Record<string, unknown> {
  if (!cacheActualizacion)
    cacheActualizacion = leer<Record<string, unknown>>("actualizacion.json");
  return cacheActualizacion as Record<string, unknown>;
}
