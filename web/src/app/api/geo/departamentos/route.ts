// GET /api/geo/departamentos — GeoJSON de departamentos (geoBoundaries
// gbOpen, geometría DGEEC, CC BY 4.0), versión hash 9469f09.
import { NextResponse } from "next/server";

import { getDepartamentos } from "@/lib/real-store";

export async function GET() {
  const geo = getDepartamentos() as {
    features: Array<{ properties: { nivel: number } }>;
  };
  const adm1 = geo.features.filter((f) => f.properties.nivel === 1);
  return NextResponse.json({
    fuente: "geoBoundaries gbOpen PRY ADM1 (geometría DGEEC) · CC BY 4.0",
    version: "geoboundaries-gbOpen-PRY-9469f09",
    total: adm1.length,
    geojson: { ...geo, features: adm1 },
  });
}
