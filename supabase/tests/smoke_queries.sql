-- Misión 016 — FIREIA LIVE · Smoke tests del esquema operativo (solo lectura).
-- Ejecutar tras aplicar las migraciones; toda aserción debe devolver 'OK'.

-- 1) Tablas operativas presentes
select case when count(*) = 8 then 'OK' else 'FALTA: ' || count(*)::text end as tablas_operativas
from information_schema.tables
where table_schema = 'public' and table_name like 'fireia_%';

-- 2) Catálogo con 4 productos activos
select case when count(*) = 4 then 'OK' else 'FALTA: ' || count(*)::text end as productos
from public.fireia_source_products where active;

-- 3) RLS activada en todas las tablas fireia_*
select case when count(*) = 0 then 'OK' else 'SIN RLS: ' || string_agg(table_name, ',') end as rls
from information_schema.tables t
where t.table_schema = 'public' and t.table_name like 'fireia_%'
  and not exists (select 1 from pg_class c where c.relname = t.table_name
                  and c.relrowsecurity);

-- 4) Realtime publicando las 3 tablas operativas
select case when count(*) >= 3 then 'OK' else 'FALTA: ' || count(*)::text end as realtime
from pg_publication_tables where pubname = 'supabase_realtime'
  and schemaname = 'public' and tablename like 'fireia_%';

-- 5) Extensiones del programador
select case when count(*) = 2 then 'OK' else 'FALTA ext' end as extensiones_cron
from pg_extension where extname in ('pg_cron', 'pg_net');

-- 6) Restricción de estados válidos (prueba negativa controlada)
select case when count(*) = 0 then 'OK' else 'CHECK roto' end as check_estados
from public.fireia_ingestion_runs where status not in
  ('pendiente','despachada','ejecutando','exito','error','parcial','fixture');
