-- Misión 016 — FIREIA LIVE · Migración 0001: extensiones
-- Idempotente. pg_cron = programador; pg_net = HTTP desde SQL (cron → Edge Function).
-- No destructivo: solo CREATE EXTENSION IF NOT EXISTS.

create extension if not exists pg_cron;
create extension if not exists pg_net;

-- Verificación
do $$
begin
  assert exists(select 1 from pg_extension where extname = 'pg_cron'), 'pg_cron no quedó instalada';
  assert exists(select 1 from pg_extension where extname = 'pg_net'), 'pg_net no quedó instalada';
end $$;
