// Misión 016 — FIREIA LIVE · Proxy seguro a la API de IA en Render.
// POST /api/ia/prediccion — el navegador NUNCA llama directo a Render:
// el proxy de servidor (Vercel) controla timeout, mapea errores y conserva
// el significado científico de la respuesta (probabilidad de detección
// VIIRS por celda-mes, no incendio confirmado).
// FIREIA_API_BASE configurable; por defecto, el servicio verificado 015-K.
import { NextResponse } from "next/server";

const API_BASE = process.env.FIREIA_API_BASE || "https://fireia-api.onrender.com";

export async function POST(request: Request) {
  let entrada: unknown;
  try {
    entrada = await request.json();
  } catch {
    return NextResponse.json(
      { error: { codigo: "cuerpo_invalido", mensaje: "Se esperaba JSON con lat, lon y mes" } },
      { status: 400 },
    );
  }

  // Validación mínima antes de reenviar (la API de IA valida el resto)
  const e = entrada as Record<string, unknown>;
  if (typeof e.lat !== "number" || typeof e.lon !== "number" || typeof e.mes !== "string") {
    return NextResponse.json(
      { error: { codigo: "entrada_invalida", mensaje: "lat (número), lon (número) y mes (YYYY-MM) son obligatorios" } },
      { status: 400 },
    );
  }

  const controlador = new AbortController();
  const timeout = setTimeout(() => controlador.abort(), 90_000); // arranque en frío del plan free ≈ 1 min

  try {
    const r = await fetch(`${API_BASE}/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entrada),
      signal: controlador.signal,
    });
    const cuerpo = await r.text();
    return new NextResponse(cuerpo, {
      status: r.status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  } catch (error) {
    const mensaje =
      error instanceof Error && error.name === "AbortError"
        ? "La API de IA no respondió a tiempo (puede estar despertando de la suspensión del plan free; reintenta en ~1 min)"
        : "No se pudo contactar la API de IA";
    return NextResponse.json({ error: { codigo: "ia_no_disponible", mensaje } }, { status: 504 });
  } finally {
    clearTimeout(timeout);
  }
}
