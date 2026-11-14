// GET /api/anomalias — resultado del experimento 001 (serie sintética,
// método rolling_median_mad_v1). La respuesta declara que los datos son
// SINTÉTICOS y que las métricas aplican solo a esa serie.
import { NextResponse } from "next/server";

import { getAnomalias } from "@/lib/real-store";

export async function GET() {
  const anomalias = getAnomalias();
  return NextResponse.json({
    ...anomalias,
    disponible: true,
    nota_disponibilidad:
      "Con datos reales del piloto (Fase 1B) el mismo método correrá sobre el almacén real.",
  });
}
