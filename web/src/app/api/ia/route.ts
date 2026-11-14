// GET /api/ia — IA predictiva REAL (Misión E): modelo de riesgo del mes
// siguiente VALIDADO CON LIMITACIONES DECLARADAS. La etiqueta es una
// agrupación inferida de detecciones, no un incendio confirmado.
// exp_001 (anomalías) es SINTÉTICO y viaja por /api/anomalias.
import { NextResponse } from "next/server";

import { getIA } from "@/lib/real-store";

export async function GET() {
  const a = getIA();
  return NextResponse.json({
    data_source: "real",
    nota: a["nota"],
    version: a["version"],
    semilla: a["semilla"],
    dataset: a["dataset"],
    particiones: a["particiones"],
    modelos: a["modelos"],
    mejor_modelo: a["mejor_modelo"],
    importancia: a["importancia"],
    validacion_geografica: a["validacion_geografica"],
    curvas: a["curvas"],
  });
}
