// GET /api/stats — estadísticas materializadas del almacén (nacional por
// día/semana/mes y por departamento).
import { NextResponse } from "next/server";

import { getAlmacen } from "@/lib/real-store";

export async function GET() {
  const almacen = getAlmacen();
  return NextResponse.json({
    data_source: almacen.meta.data_source,
    nacional_dia: almacen.stats.nacional_dia,
    nacional_semana: almacen.stats.nacional_semana,
    nacional_mes: almacen.stats.nacional_mes,
    departamento: almacen.stats.departamento,
    departamento_dia: almacen.stats.departamento_dia,
  });
}
