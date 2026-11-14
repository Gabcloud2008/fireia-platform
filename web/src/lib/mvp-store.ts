// Lector del almacén exportado (solo servidor). Los JSON los genera
// scripts/exportar_mvp.py desde el DuckDB del pipeline de la Misión 004.

import { readFileSync } from "fs";
import path from "path";

import type { Almacen, AnomaliasExp001 } from "@/lib/mvp-types";

let cacheAlmacen: Almacen | null = null;
let cacheAnomalias: AnomaliasExp001 | null = null;
let cacheDepartamentos: unknown = null;

function leer<T>(nombre: string): T {
  const ruta = path.join(process.cwd(), "src", "data", "mvp", nombre);
  return JSON.parse(readFileSync(ruta, "utf-8")) as T;
}

export function getAlmacen(): Almacen {
  if (!cacheAlmacen) cacheAlmacen = leer<Almacen>("almacen.json");
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
