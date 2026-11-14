// GET /api/actualizacion — estado del ciclo de actualización automática
// (Misión C FIREIA 2.0). Estados posibles: ACTUALIZADO, SIN_NUEVOS_DATOS,
// ACTUALIZANDO, RETRASADO, ERROR, COBERTURA_DESCONOCIDA,
// ADQUISICION_NO_DISPONIBLE. Un fallo de adquisición NO es cero detecciones.
import { NextResponse } from "next/server";

import { getActualizacion } from "@/lib/real-store";

export async function GET() {
  const a = getActualizacion();
  return NextResponse.json({
    data_source: "real",
    estado: a["estado"],
    regla: a["regla"],
    estados_posibles: a["estados_posibles"],
    registro_reciente: a["registro_reciente"],
  });
}
