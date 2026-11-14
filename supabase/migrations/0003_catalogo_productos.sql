-- Misión 016 — FIREIA LIVE · Migración 0003: catálogo inicial de productos
-- Productos objetivo del encargo (Fase G). La disponibilidad REAL se verifica
-- con la MAP_KEY nueva vía GitHub Actions (endpoint data_availability) y se
-- registra en fireia_source_products.availability.

insert into public.fireia_source_products (product, satellite, sensor, description, active) values
  ('VIIRS_NOAA20_NRT', 'NOAA-20', 'VIIRS', 'Detecciones NRT VIIRS NOAA-20 (FIRMS Area API)', true),
  ('VIIRS_NOAA21_NRT', 'NOAA-21', 'VIIRS', 'Detecciones NRT VIIRS NOAA-21 (FIRMS Area API)', true),
  ('MODIS_TERRA_NRT',  'Terra',   'MODIS', 'Detecciones NRT MODIS Terra (FIRMS Area API)', true),
  ('MODIS_AQUA_NRT',   'Aqua',    'MODIS', 'Detecciones NRT MODIS Aqua (FIRMS Area API)', true)
on conflict (product) do nothing;

-- Estado inicial de salud (fila por servicio; se actualiza en cada ciclo)
insert into public.fireia_system_health (service, status, problem, details) values
  ('pipeline',         'desconocido', 'sin corridas registradas aún', '{}'::jsonb),
  ('supabase-cron',    'desconocido', 'cron aún no programado', '{}'::jsonb),
  ('github-actions',   'desconocido', 'sin despachos aún', '{}'::jsonb),
  ('render-ia',        'ok', 'servicio verificado 2026-11-13 (batería 21/21)', '{}'::jsonb),
  ('r2',               'desconocido', 'sin credenciales R2 todavía', '{}'::jsonb)
on conflict (service) do update
  set problem = excluded.problem, updated_at = now();
