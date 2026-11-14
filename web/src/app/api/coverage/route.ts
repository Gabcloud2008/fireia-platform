// GET /api/coverage — calendario de cobertura del almacén exportado
// (Misión 005): distingue "cero detecciones" de "sin datos".
import { NextResponse } from "next/server";

import { getAlmacen } from "@/lib/real-store";

export async function GET() {
  const almacen = getAlmacen();
  if (!almacen.cobertura) {
    return NextResponse.json(
      { error: { code: 404, message: "sin calendario de cobertura en el almacén" } },
      { status: 404 },
    );
  }
  return NextResponse.json({
    data_source: almacen.meta.data_source,
    ...almacen.cobertura,
    nota:
      "cero_detecciones_asumido NO es lo mismo que sin_datos: el primero es " +
      "un cero comparable dentro del intervalo cubierto; el segundo es un " +
      "hueco que no debe entrar a ninguna serie estadística.",
  });
}
