// Misión 016 — FIREIA LIVE · Cliente Supabase para el navegador.
// Devuelve null si las variables públicas no están configuradas: la web
// funciona igual (export estático) y se activa en vivo al desplegar en
// Vercel con NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY.
// Solo claves PÚBLICAS (anon): la RLS de Postgres protege la lectura.
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let cliente: SupabaseClient | null = null;
let intentado = false;

export function getSupabase(): SupabaseClient | null {
  if (intentado) return cliente;
  intentado = true;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    if (typeof console !== "undefined") {
      console.info("[fireia-live] sin variables NEXT_PUBLIC_SUPABASE_*: modo export estático");
    }
    return null;
  }
  cliente = createClient(url, key, {
    realtime: { params: { eventsPerSecond: 5 } },
  });
  return cliente;
}

export function liveDisponible(): boolean {
  return getSupabase() !== null;
}
