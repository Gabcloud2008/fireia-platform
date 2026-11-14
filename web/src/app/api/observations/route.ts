// GET /api/observations — detecciones con filtros (producto, sensor,
// día/noche, fechas, departamento, dentro_pais). Espejo del endpoint
// homónimo de la API FastAPI del pipeline.
import { NextRequest, NextResponse } from "next/server";

import { getAlmacen } from "@/lib/real-store";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const almacen = getAlmacen();

  const product = searchParams.get("product");
  const sensor = searchParams.get("sensor");
  const daynight = searchParams.get("daynight");
  const dateFrom = searchParams.get("date_from");
  const dateTo = searchParams.get("date_to");
  const departamento = searchParams.get("departamento");
  const dentro = searchParams.get("dentro_pais");

  let obs = almacen.observaciones;

  if (product) obs = obs.filter((o) => o.product === product);
  if (sensor) obs = obs.filter((o) => o.sensor === sensor);
  if (daynight) obs = obs.filter((o) => o.daynight === daynight);
  if (dateFrom) obs = obs.filter((o) => o.acq_date >= dateFrom);
  if (dateTo) obs = obs.filter((o) => o.acq_date <= dateTo);
  if (departamento) obs = obs.filter((o) => o.departamento === departamento);
  if (dentro !== null && dentro !== "") obs = obs.filter((o) => o.dentro_pais === (dentro === "true"));

  return NextResponse.json({
    total: obs.length,
    data_source: almacen.meta.data_source,
    observaciones: obs,
  });
}
