// Misión 016 — FIREIA LIVE · fireia-events
// GET público: resúmenes de eventos inferidos (metadatos; el detalle vive en Parquet).
import { createClient } from "npm:@supabase/supabase-js@2";

const json = (b: unknown, s = 200) =>
  new Response(JSON.stringify(b), { status: s, headers: { "Content-Type": "application/json; charset=utf-8" } });

Deno.serve(async (req: Request) => {
  if (req.method !== "GET") return json({ error: { codigo: "metodo_no_permitido", mensaje: "Use GET" } }, 405);
  const limite = Math.max(1, Math.min(50, Number.parseInt(new URL(req.url).searchParams.get("limite") ?? "20", 10) || 20));

  const url = Deno.env.get("SUPABASE_URL") ?? "";
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const sb = createClient(url, key);

  const { data, error } = await sb
    .from("fireia_events")
    .select("id,run_id,method_version,window_start,window_end,product_pair,event_count,obs_involved,summary,created_at")
    .order("created_at", { ascending: false })
    .limit(limite);
  if (error) return json({ error: { codigo: "bd_error", mensaje: error.message } }, 500);

  return json({
    data,
    meta: {
      funcion: "fireia-events",
      nota: "Eventos = agrupaciones inferidas de detecciones (co-detección 600 s / 2 km). No son incendios confirmados.",
      limite,
    },
  });
});
