// Misión 016 — FIREIA LIVE · Edge Function fireia-dispatch-ingestion
// POST (solo cron/servicio): coordina una nueva adquisición.
//   1) Lee productos activos de fireia_source_products.
//   2) Registra la corrida en fireia_ingestion_runs (request_key idempotente).
//   3) Dispara workflow_dispatch en GitHub Actions (repo fireia-platform).
//   4) Responde JSON {data:{run_id,...}} o error clasificado.
// Autenticación: header x-cron-secret == env FIREIA_CRON_SECRET (Vault/secrets).
// Nunca registra secretos en logs.
import { createClient } from "npm:@supabase/supabase-js@2";

const GH_REPO = "Gabcloud2008/fireia-platform";
const GH_WORKFLOW = "ingesta.yml";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

function errorJson(codigo: string, mensaje: string, status: number): Response {
  return json({ error: { codigo, mensaje } }, status);
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return errorJson("metodo_no_permitido", "Use POST", 405);
  }
  const secreto = req.headers.get("x-cron-secret") ?? "";
  const esperado = Deno.env.get("FIREIA_CRON_SECRET") ?? "";
  if (!esperado || secreto !== esperado) {
    return errorJson("no_autorizado", "Credencial de coordinación inválida", 401);
  }

  const url = Deno.env.get("SUPABASE_URL") ?? "";
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const ghToken = Deno.env.get("FIREIA_GH_DISPATCH_TOKEN") ?? "";
  if (!url || !key) return errorJson("config_incompleta", "Faltan variables del proyecto", 500);
  if (!ghToken) return errorJson("config_incompleta", "Falta token de dispatch de GitHub", 500);

  const sb = createClient(url, key);

  // 1) productos activos
  const { data: productos, error: errProd } = await sb
    .from("fireia_source_products")
    .select("product,satellite")
    .eq("active", true);
  if (errProd) return errorJson("bd_error", errProd.message, 500);
  if (!productos || productos.length === 0) {
    return errorJson("sin_productos", "Ningún producto activo en el catálogo", 409);
  }

  // 2) ventana objetivo: día en curso (UTC) — adquisición incremental
  const hoy = new Date().toISOString().slice(0, 10);
  let body: { origen?: string; modo?: string } = {};
  try { body = await req.json(); } catch { /* cuerpo opcional */ }
  const modo = body.modo === "fixture" ? "fixture" : "real";

  const respuestas: Record<string, unknown>[] = [];
  let fallos = 0;

  for (const p of productos) {
    const requestKey = `firms|${p.product}|${hoy}|${modo}`;
    // idempotencia: si ya existe una corrida igual HOY, no duplicar
    const { data: previa } = await sb
      .from("fireia_ingestion_runs")
      .select("run_id,status,request_key")
      .eq("request_key", requestKey)
      .maybeSingle();
    if (previa) {
      respuestas.push({ product: p.product, run_id: previa.run_id, estado: previa.status, duplicado: true });
      continue;
    }

    const { data: corrida, error: errRun } = await sb
      .from("fireia_ingestion_runs")
      .insert({
        source: "firms-api",
        product: p.product,
        satellite: p.satellite,
        status: "pendiente",
        modo,
        request_key: requestKey,
        window_start: hoy,
        window_end: hoy,
      })
      .select("run_id")
      .single();
    if (errRun || !corrida) {
      fallos++;
      respuestas.push({ product: p.product, error: errRun?.message ?? "insert falló" });
      continue;
    }

    // 3) disparar GitHub Actions
    const ghResp = await fetch(
      `https://api.github.com/repos/${GH_REPO}/actions/workflows/${GH_WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${ghToken}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ref: "main",
          inputs: { run_id: corrida.run_id, modo, product: p.product, fecha: hoy },
        }),
      },
    );

    if (ghResp.status === 204) {
      await sb.from("fireia_ingestion_runs")
        .update({ status: "despachada", updated_at: new Date().toISOString() })
        .eq("run_id", corrida.run_id);
      respuestas.push({ product: p.product, run_id: corrida.run_id, estado: "despachada" });
    } else {
      fallos++;
      const detalle = await ghResp.text();
      await sb.from("fireia_ingestion_runs")
        .update({
          status: "error",
          errors: [{ codigo: "dispatch_fallido", http: ghResp.status }],
          finished_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
        .eq("run_id", corrida.run_id);
      // solo clasificación, sin tokens en el detalle
      respuestas.push({ product: p.product, run_id: corrida.run_id, estado: "error", http: ghResp.status, detalle: detalle.slice(0, 200) });
    }
  }

  // salud del sistema
  await sb.from("fireia_system_health").upsert({
    service: "github-actions",
    status: fallos === 0 ? "ok" : (fallos === productos.length ? "fallo" : "degradado"),
    last_run_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });

  return json({
    data: { modo, fecha: hoy, corridas: respuestas, fallos },
    meta: { funcion: "fireia-dispatch-ingestion", origen: body.origen ?? "manual" },
  }, fallos === productos.length ? 502 : 200);
});
