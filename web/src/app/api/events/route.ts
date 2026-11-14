// GET /api/events — eventos de co-detección MODIS–VIIRS con sus miembros.
import { NextResponse } from "next/server";

import { getAlmacen } from "@/lib/real-store";

export async function GET() {
  const almacen = getAlmacen();
  return NextResponse.json({
    total: almacen.eventos.length,
    data_source: almacen.meta.data_source,
    eventos: almacen.eventos,
  });
}
