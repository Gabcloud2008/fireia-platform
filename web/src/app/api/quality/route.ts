// GET /api/quality — estados de ingesta, corridas, cuarentena y pares
// candidatos. Espejo del endpoint quality del pipeline.
import { NextResponse } from "next/server";

import { getAlmacen } from "@/lib/real-store";

export async function GET() {
  const almacen = getAlmacen();
  return NextResponse.json({
    data_source: almacen.meta.data_source,
    data_source_nota: almacen.meta.data_source_nota,
    calidad: almacen.calidad,
  });
}
