-- Misión 016 — FIREIA LIVE · Migración 0007: idempotencia plena del reporter
-- El upsert REST (PostgREST) resuelve conflictos por PK o por columnas
-- indicadas en on_conflict; un índice único POR EXPRESIÓN no puede
-- usarse así (409). Se sustituye por un índice simple sobre la clave
-- natural (en la práctica acq_time/confidence nunca son nulos en FIRMS).
-- Además: unicidad de alertas por (run_id, rule) para reintentos seguros.

drop index if exists uq_deteccion_natural;
create unique index if not exists uq_deteccion_natural
  on public.fireia_latest_detections (
    product, satellite, latitude, longitude, acq_date, acq_time, confidence
  );

create unique index if not exists uq_alerta_run_regla
  on public.fireia_alerts (run_id, rule);
