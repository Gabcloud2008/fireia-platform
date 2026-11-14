-- Misión 016 — FIREIA LIVE · Migración 0002: esquema operativo FIREIA
-- Diseño: PostgreSQL guarda SOLO metadatos operativos, estados, cobertura,
-- resúmenes y la ventana móvil de detecciones recientes. Los 2.691.999
-- registros históricos PERMANECEN en Parquet (R2/artifacts) y DuckDB sigue
-- siendo el motor analítico (regla fundamental del encargo, Fase D).
-- Idempotente y aditivo: sin DROP, sin borrados.

-- ============================================================
-- 1) fireia_source_products — catálogo de productos/satélites
-- ============================================================
create table if not exists public.fireia_source_products (
  product        text primary key,              -- p. ej. 'VIIRS_NOAA20_NRT'
  satellite      text not null,                 -- 'NOAA-20'
  sensor         text not null,                 -- 'VIIRS' | 'MODIS'
  description    text,
  active         boolean not null default true, -- participar en adquisiciones
  availability   jsonb not null default '{}'::jsonb, -- último chequeo data_availability
  checked_at     timestamptz,
  created_at     timestamptz not null default now()
);

-- ============================================================
-- 2) fireia_ingestion_runs — registro de cada ejecución
-- ============================================================
create table if not exists public.fireia_ingestion_runs (
  run_id          uuid primary key default gen_random_uuid(),
  source          text not null default 'firms-api',
  product         text not null,
  satellite       text,
  started_at      timestamptz not null default now(),
  finished_at     timestamptz,
  status          text not null default 'pendiente'
                  check (status in ('pendiente','despachada','ejecutando','exito','error','parcial','fixture')),
  downloaded      integer,           -- filas crudas descargadas
  valid           integer,           -- filas válidas tras QC
  quarantined     integer,           -- filas en cuarentena
  errors          jsonb not null default '[]'::jsonb,
  request_key     text not null unique,  -- idempotencia: fuente+producto+ventana+modo
  pipeline_version text,
  manifest        jsonb,             -- manifiesto de la corrida (hashes, archivos)
  duration_s      numeric,
  modo            text not null default 'real' check (modo in ('real','fixture')),
  window_start    date,
  window_end      date,
  workflow_run_url text,
  updated_at      timestamptz not null default now()
);
create index if not exists idx_runs_product_started on public.fireia_ingestion_runs (product, started_at desc);
create index if not exists idx_runs_status on public.fireia_ingestion_runs (status) where status in ('pendiente','despachada','ejecutando');

-- ============================================================
-- 3) fireia_coverage — cobertura efectiva por corrida/producto
-- ============================================================
create table if not exists public.fireia_coverage (
  id            bigint generated always as identity primary key,
  run_id        uuid not null references public.fireia_ingestion_runs(run_id) on delete cascade,
  product       text not null,
  interval_lo   date not null,
  interval_hi   date not null,
  gaps          jsonb not null default '[]'::jsonb,  -- huecos detectados
  failures      jsonb not null default '[]'::jsonb,  -- fallos de adquisición clasificados
  state         text not null default 'ok' check (state in ('ok','huecos','fallo','sin_datos','desconocido')),
  obs_count     integer,
  created_at    timestamptz not null default now(),
  unique (run_id, product)
);

-- ============================================================
-- 4) fireia_data_assets — referencias a archivos y sus hashes
-- ============================================================
create table if not exists public.fireia_data_assets (
  id          bigint generated always as identity primary key,
  run_id      uuid references public.fireia_ingestion_runs(run_id) on delete set null,
  asset_type  text not null check (asset_type in ('raw','parquet','geoparquet','manifest','duckdb','export')),
  storage     text not null check (storage in ('gha-artifact','r2','hf','local')),
  path        text not null,             -- URL R2 / clave / nombre de artefacto
  sha256      text,                      -- 64 hex cuando corresponda
  bytes       bigint,
  product     text,
  window_lo   date,
  window_hi   date,
  created_at  timestamptz not null default now()
);
create index if not exists idx_assets_type_created on public.fireia_data_assets (asset_type, created_at desc);
create unique index if not exists uq_assets_path_run on public.fireia_data_assets (path, run_id);

-- ============================================================
-- 5) fireia_latest_detections — ventana móvil de detecciones recientes
--    (NO es el histórico: solo lo necesario para el mapa en vivo;
--     purga automática > 7 días → volumen acotado en plan free)
-- ============================================================
create table if not exists public.fireia_latest_detections (
  id           bigint generated always as identity primary key,
  run_id       uuid not null references public.fireia_ingestion_runs(run_id) on delete cascade,
  product      text not null,
  satellite    text not null,
  latitude     double precision not null,
  longitude    double precision not null,
  acq_date     date not null,
  acq_time     text,
  confidence   text,
  bright_ti31  double precision,
  created_at   timestamptz not null default now()
);
create index if not exists idx_detections_acq on public.fireia_latest_detections (acq_date desc, product);
create index if not exists idx_detections_product_created on public.fireia_latest_detections (product, created_at desc);

-- ============================================================
-- 6) fireia_events — resúmenes de eventos inferidos (metadatos)
--    El detalle completo vive en Parquet; acá solo lo operativo.
-- ============================================================
create table if not exists public.fireia_events (
  id               bigint generated always as identity primary key,
  run_id           uuid references public.fireia_ingestion_runs(run_id) on delete set null,
  method_version   text not null,          -- versión del motor de eventos
  window_start     date not null,
  window_end       date not null,
  product_pair     text,                   -- p. ej. 'MODIS_TERRA+VIIRS_NOAA20'
  event_count      integer not null default 0,
  obs_involved     integer,
  summary          jsonb not null default '{}'::jsonb, -- top eventos (id, centroide, tamaño, fechas)
  created_at       timestamptz not null default now(),
  unique (run_id, product_pair, window_start)
);

-- ============================================================
-- 7) fireia_alerts — alertas basadas en reglas reproducibles
-- ============================================================
create table if not exists public.fireia_alerts (
  id             bigint generated always as identity primary key,
  created_at_utc timestamptz not null default now(),
  area           jsonb not null,           -- {tipo:'celda'|'pais'|'departamento', id, lat, lon}
  rule           text not null,            -- identificador estable de la regla
  rule_version   text not null,
  severity       text not null check (severity in ('info','aviso','advertencia','critica')),
  evidence       jsonb not null default '{}'::jsonb, -- datos de respaldo
  run_id         uuid references public.fireia_ingestion_runs(run_id) on delete set null,
  review_state   text not null default 'nueva' check (review_state in ('nueva','revisada','descartada')),
  reviewed_at    timestamptz,
  reviewed_by    text
);
create index if not exists idx_alerts_created on public.fireia_alerts (created_at_utc desc);
create index if not exists idx_alerts_rule on public.fireia_alerts (rule, created_at_utc desc);

-- ============================================================
-- 8) fireia_system_health — estado de servicios
-- ============================================================
create table if not exists public.fireia_system_health (
  service     text primary key,             -- 'pipeline','supabase-cron','github-actions','render-ia','r2'
  status      text not null check (status in ('ok','degradado','fallo','desconocido')),
  last_ok_at  timestamptz,
  last_run_at timestamptz,
  problem     text,
  details     jsonb not null default '{}'::jsonb,
  updated_at  timestamptz not null default now()
);

-- ============================================================
-- RLS: lectura pública (anon) de lo operativo; escritura solo
-- service_role / postgres (bypass RLS). Ningún dato personal.
-- ============================================================
alter table public.fireia_source_products    enable row level security;
alter table public.fireia_ingestion_runs     enable row level security;
alter table public.fireia_coverage           enable row level security;
alter table public.fireia_data_assets        enable row level security;
alter table public.fireia_latest_detections  enable row level security;
alter table public.fireia_events             enable row level security;
alter table public.fireia_alerts             enable row level security;
alter table public.fireia_system_health      enable row level security;

drop policy if exists lectura_publica_source_products on public.fireia_source_products;
create policy lectura_publica_source_products on public.fireia_source_products
  for select to anon, authenticated using (true);

drop policy if exists lectura_publica_ingestion_runs on public.fireia_ingestion_runs;
create policy lectura_publica_ingestion_runs on public.fireia_ingestion_runs
  for select to anon, authenticated using (true);

drop policy if exists lectura_publica_coverage on public.fireia_coverage;
create policy lectura_publica_coverage on public.fireia_coverage
  for select to anon, authenticated using (true);

drop policy if exists lectura_publica_data_assets on public.fireia_data_assets;
create policy lectura_publica_data_assets on public.fireia_data_assets
  for select to anon, authenticated using (true);

drop policy if exists lectura_publica_latest_detections on public.fireia_latest_detections;
create policy lectura_publica_latest_detections on public.fireia_latest_detections
  for select to anon, authenticated using (true);

drop policy if exists lectura_publica_events on public.fireia_events;
create policy lectura_publica_events on public.fireia_events
  for select to anon, authenticated using (true);

drop policy if exists lectura_publica_alerts on public.fireia_alerts;
create policy lectura_publica_alerts on public.fireia_alerts
  for select to anon, authenticated using (true);

drop policy if exists lectura_publica_system_health on public.fireia_system_health;
create policy lectura_publica_system_health on public.fireia_system_health
  for select to anon, authenticated using (true);

-- ============================================================
-- Realtime: publicar SOLO tablas operativas de bajo volumen
-- (los cambios notifican al frontend sin polling)
-- ============================================================
do $$
begin
  if not exists (select 1 from pg_publication_tables
                 where pubname = 'supabase_realtime'
                   and schemaname = 'public' and tablename = 'fireia_ingestion_runs') then
    alter publication supabase_realtime add table public.fireia_ingestion_runs;
  end if;
  if not exists (select 1 from pg_publication_tables
                 where pubname = 'supabase_realtime'
                   and schemaname = 'public' and tablename = 'fireia_alerts') then
    alter publication supabase_realtime add table public.fireia_alerts;
  end if;
  if not exists (select 1 from pg_publication_tables
                 where pubname = 'supabase_realtime'
                   and schemaname = 'public' and tablename = 'fireia_system_health') then
    alter publication supabase_realtime add table public.fireia_system_health;
  end if;
end $$;

-- ============================================================
-- Purga de la ventana móvil (la llama el pipeline tras cada run;
-- mantiene fireia_latest_detections ≤ 7 días de datos)
-- ============================================================
create or replace function public.fireia_purge_detections(p_dias integer default 7)
returns integer
language plpgsql
security definer
as $$
declare
  n integer;
begin
  delete from public.fireia_latest_detections
   where acq_date < current_date - p_dias;
  get diagnostics n = row_count;
  return n;
end;
$$;
revoke all on function public.fireia_purge_detections(integer) from public, anon;

-- ============================================================
-- RPC de soporte a la regla R-004 (aumento inusual de detecciones):
-- media y desvío de detecciones por día de los últimos N días.
-- Solo service_role (bypass RLS) puede llamarla.
-- ============================================================
create or replace function public.fireia_media_detecciones_dia(p_product text, p_dias integer default 7)
returns table(media numeric, desvio numeric)
language sql
stable
as $$
  select avg(c)::numeric, coalesce(stddev_pop(c)::numeric, 0)
  from (
    select d.acq_date, count(*)::numeric as c
    from public.fireia_latest_detections d
    where d.product = p_product
      and d.acq_date >= current_date - p_dias
      and d.acq_date < current_date          -- excluye el día en curso (se compara contra él)
    group by d.acq_date
  ) por_dia;
$$;
revoke all on function public.fireia_media_detecciones_dia(text, integer) from public, anon;
