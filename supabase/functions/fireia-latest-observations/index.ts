// Misión 016 — FIREIA LIVE · fireia-latest-observations
// GET público: detecciones recientes (ventana móvil). Parámetros:
//   producto=VIIRS_NOAA20_NRT · limite=200 (máx 1000) · dias=7
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const json = (b: unknown, s = 200) =>
  new Response(JSON.stringify(b), { status: s, headers: { "Content-Type": "application/json; charset=utf-8" } });

Deno.serve(async (req: Request) => {
  if (req.method !== "GET") return json({ error: { codigo: "metodo_no_permitido", mensaje: "Use GET" } }, 405);
  const params = new URL(req.url).searchParams;
  const limite = Math.max(1, Math.min(1000, Number.parseInt(params.get("limite") ?? "200", 10) || 200));
  const dias = Math.max(1, Math.min(30, Number.parseInt(params.get("dias") ?? "7", 10) || 7));
  const producto = params.get("producto");

  const url = Deno.env.get("SUPABASE_URL") ?? "";
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const sb = createClient(url, key);

  let consulta = sb
    .from("fireia_latest_detections")
    .select("id,product,satellite,latitude,longitude,acq_date,acq_time,confidence,bright_ti31,created_at")
    .gte("acq_date", new Date(Date.now() - dias * 86_400_000).toISOString().slice(0, 10))
    .order("acq_date", { ascending: false })
    .limit(limite);
  if (producto) consulta = consulta.eq("product", producto);

  const { data, error } = await consulta;
  if (error) return json({ error: { codigo: "bd_error", mensaje: error.message } }, 500);

  return json({
    data,
    meta: {
      funcion: "fireia-latest-observations",
      nota: "Detecciones satelitales (hot spots) FIRMS — no son incendios confirmados.",
      limite, dias, filtro_producto: producto ?? "todos",
    },
  });
});
