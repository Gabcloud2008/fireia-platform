// GET /api/ambiental — inteligencia ambiental REAL (Misión D): catálogo de
// 7 fuentes INTEGRADAS, relaciones fuego-clima (Spearman, sin futuro) y
// serie nacional mensual celda×mes de la grilla 0,1°.
import { NextResponse } from "next/server";

import { getAmbiental } from "@/lib/real-store";

export async function GET() {
  const a = getAmbiental();
  return NextResponse.json({
    data_source: "real",
    nota: a["nota"],
    catalogo: a["catalogo"],
    relaciones: a["relaciones"],
    serie_nacional_mensual: a["serie_nacional_mensual"],
    obs_por_anio: a["obs_por_anio"],
    cobertura_terrestre: a["cobertura_terrestre"],
  });
}
