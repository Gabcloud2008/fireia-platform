// Misión 016 — FIREIA LIVE · fireia-ingestion-status
// GET público: últimas corridas de ingesta (límite ≤ 50, default 10).
import { createClient } from "npm:@supabase/supabase-js@2";

const json = (b: unknown, s = 200) =>
  new Response(JSON.stringify(b), { status: s, headers: { "Content-Type": "application/json; charset=utf-8" } });

Deno.serve(async (req: Request) => {
  if (req.method !== "GET") return json({ error: { codigo: "metodo_no_permitido", mensaje: "Use GET" } }, 405);
  const limiteRaw = new URL(req.url).searchParams.get("limite") ?? "10";
  const limite = Math.max(1, Math.min(50, Number.parseInt(limiteRaw, 10) || 10));

  const url = Deno.env.get("SUPABASE_URL") ?? "";
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const sb = createClient(url, key);

  const { data, error } = await sb
    .from("fireia_ingestion_runs")
    .select("run_id,product,satellite,status,modo,started_at,finished_at,downloaded,valid,quarantined,duration_s,workflow_run_url,window_start,window_end")
    .order("started_at", { ascending: false })
    .limit(limite);
  if (error) return json({ error: { codigo: "bd_error", mensaje: error.message } }, 500);

  return json({
    data,
    meta: { funcion: "fireia-ingestion-status", limite, total: data?.length ?? 0 },
  });
});
