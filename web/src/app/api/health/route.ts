// GET /api/health — estado del almacén y origen de los datos.
// Espejo del contrato FastAPI de la Misión 004: el origen (fixture/firms_api)
// viaja SIEMPRE en la respuesta.
import { NextResponse } from "next/server";

import { getAlmacen } from "@/lib/real-store";

export async function GET() {
  const almacen = getAlmacen();
  return NextResponse.json({
    status: "ok",
    servicio: "paraguay-fire-intelligence-mvp",
    data_source: almacen.meta.data_source,
    data_source_nota: almacen.meta.data_source_nota,
    almacen: almacen.meta.almacen,
    exportado_en: almacen.meta.exportado_en,
    cobertura: almacen.meta.cobertura,
    resumen: almacen.resumen,
  });
}
