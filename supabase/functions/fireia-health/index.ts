// Misión 016 — FIREIA LIVE · fireia-health
// GET público: estado del sistema + frescura real de los datos.
// Honestidad por diseño: reporta antigüedad efectiva, no "tiempo real".
import { createClient } from "npm:@supabase/supabase-js@2";

const json = (b: unknown, s = 200) =>
  new Response(JSON.stringify(b), { status: s, headers: { "Content-Type": "application/json; charset=utf-8" } });

Deno.serve(async (req: Request) => {
  if (req.method !== "GET") return json({ error: { codigo: "metodo_no_permitido", mensaje: "Use GET" } }, 405);

  const url = Deno.env.get("SUPABASE_URL") ?? "";
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  if (!url || !key) return json({ error: { codigo: "config_incompleta", mensaje: "Faltan variables" } }, 500);
  const sb = createClient(url, key);

  const [{ data: salud, error: e1 }, { data: ultimas, error: e2 }, { data: frescura, error: e3 }] =
    await Promise.all([
      sb.from("fireia_system_health").select("*").order("service"),
      sb.from("fireia_ingestion_runs").select("run_id,product,status,started_at,finished_at,downloaded,valid,quarantined,modo").order("started_at", { ascending: false }).limit(1),
      sb.from("fireia_latest_detections").select("acq_date,created_at").order("created_at", { ascending: false }).limit(1),
    ]);
  if (e1 || e2 || e3) return json({ error: { codigo: "bd_error", mensaje: e1?.message ?? e2?.message ?? e3?.message } }, 500);

  const ultimaObs = frescura?.[0] ?? null;
  const ultimaCorrida = ultimas?.[0] ?? null;
  const ahora = Date.now();
  const edadDatosMs = ultimaObs ? ahora - new Date(ultimaObs.created_at).getTime() : null;
  const edadDatosH = edadDatosMs !== null ? +(edadDatosMs / 3_600_000).toFixed(1) : null;

  return json({
    data: {
      estado_general: (() => {
        const estados = (salud ?? []).map((s: { status: string }) => s.status);
        if (estados.includes("fallo")) return "fallo";
        if (estados.includes("degradado")) return "degradado";
        return "ok";
      })(),
      servicios: salud ?? [],
      ultima_corrida: ultimaCorrida,
      datos: {
        ultima_adquisicion_utc: ultimaObs?.created_at ?? null,
        fecha_observacion: ultimaObs?.acq_date ?? null,
        edad_horas: edadDatosH,
        nota: "Las detecciones provienen de NASA FIRMS (NRT: latencia típica de horas, no transmisión instantánea). La antigüedad se calcula sobre la última adquisición real.",
      },
    },
    meta: { funcion: "fireia-health", generado_utc: new Date().toISOString() },
  });
});
