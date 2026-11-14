// Misión 016 — FIREIA LIVE · fireia-alerts
// GET público: alertas con evidencia. Filtros: severidad · estado · limite (máx 100).
import { createClient } from "npm:@supabase/supabase-js@2";

const json = (b: unknown, s = 200) =>
  new Response(JSON.stringify(b), { status: s, headers: { "Content-Type": "application/json; charset=utf-8" } });

const SEVERIDADES = new Set(["info", "aviso", "advertencia", "critica"]);
const ESTADOS = new Set(["nueva", "revisada", "descartada"]);

Deno.serve(async (req: Request) => {
  if (req.method !== "GET") return json({ error: { codigo: "metodo_no_permitido", mensaje: "Use GET" } }, 405);
  const params = new URL(req.url).searchParams;
  const limite = Math.max(1, Math.min(100, Number.parseInt(params.get("limite") ?? "20", 10) || 20));
  const severidad = params.get("severidad");
  const estado = params.get("estado");

  if (severidad && !SEVERIDADES.has(severidad)) {
    return json({ error: { codigo: "parametro_invalido", mensaje: `severidad debe ser una de: ${[...SEVERIDADES].join(", ")}` } }, 422);
  }
  if (estado && !ESTADOS.has(estado)) {
    return json({ error: { codigo: "parametro_invalido", mensaje: `estado debe ser uno de: ${[...ESTADOS].join(", ")}` } }, 422);
  }

  const url = Deno.env.get("SUPABASE_URL") ?? "";
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const sb = createClient(url, key);

  let consulta = sb
    .from("fireia_alerts")
    .select("id,created_at_utc,area,rule,rule_version,severity,evidence,run_id,review_state,reviewed_at")
    .order("created_at_utc", { ascending: false })
    .limit(limite);
  if (severidad) consulta = consulta.eq("severity", severidad);
  if (estado) consulta = consulta.eq("review_state", estado);

  const { data, error } = await consulta;
  if (error) return json({ error: { codigo: "bd_error", mensaje: error.message } }, 500);

  return json({
    data,
    meta: {
      funcion: "fireia-alerts",
      nota: "Alertas basadas en reglas reproducibles con evidencia; no son predicciones.",
      limite, severidad: severidad ?? "todas", estado: estado ?? "todos",
    },
  });
});
