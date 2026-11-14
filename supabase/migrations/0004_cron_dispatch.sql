-- Misión 016 — FIREIA LIVE · Migración 0004: programador de adquisiciones
-- Aplicar SOLO después de crear el secreto 'fireia_cron_secret' en Supabase
-- Vault (ver docs/OPERACION.md). El secreto NO vive en este archivo: el job
-- lo lee de vault.decrypted_secrets en tiempo de ejecución.
-- Cadencia por defecto: cada 30 minutos (configurable; mínimo razonable free).

select cron.unschedule('fireia-dispatch-ingesta')
where exists (select 1 from cron.job where jobname = 'fireia-dispatch-ingesta');

select cron.schedule(
  'fireia-dispatch-ingesta',
  '*/30 * * * *',
  $$
  select net.http_post(
    url := 'https://xpegeuamgupnxulosqlu.supabase.co/functions/v1/fireia-dispatch-ingestion',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-cron-secret', (select decrypted_secret
                          from vault.decrypted_secrets
                         where name = 'fireia_cron_secret')
    ),
    body := jsonb_build_object('origen', 'cron')
  );
  $$
);

-- Estado del cron en system_health
insert into public.fireia_system_health (service, status, last_ok_at, details) values
  ('supabase-cron', 'ok', now(),
   jsonb_build_object('job', 'fireia-dispatch-ingesta', 'cadencia', '*/30 * * * *'))
on conflict (service) do update
  set status = 'ok', last_ok_at = now(), updated_at = now(),
      details = excluded.details, problem = null;
