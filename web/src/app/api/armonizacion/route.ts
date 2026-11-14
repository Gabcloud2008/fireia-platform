// GET /api/armonizacion — pares MODIS–VIIRS de la base real (Misión B):
// muestra de pares canónicos (600 s / 2 km), sensibilidad 9 combinaciones,
// histogramas y discrepancias. Una coincidencia NO es un incendio confirmado.
import { NextResponse } from "next/server";

import { getArmonizacion } from "@/lib/real-store";

export async function GET() {
  const a = getArmonizacion();
  return NextResponse.json({
    data_source: "real",
    canonico: a["canonico"],
    nota: a["nota"],
    muestra_pares: a["muestra_pares"],
    sensibilidad: a["sensibilidad"],
    por_anio: a["por_anio"],
    hist_dt: a["hist_dt"],
    hist_dist: a["hist_dist"],
    frp_mediana: a["frp_mediana"],
    analisis: a["analisis"],
    discrepancias: a["discrepancias"],
  });
}
