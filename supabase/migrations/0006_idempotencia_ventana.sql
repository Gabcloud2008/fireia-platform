-- Misión 016 — FIREIA LIVE · Migración 0006: idempotencia de la ventana móvil
-- 1) Índice único por clave natural de detección: re-adquisiciones de la misma
--    ventana NRT no duplican puntos (upsert desde el reporter).
-- 2) Estado 'sin_cambios' en cobertura: corrida exitosa cuyo contenido ya
--    estaba ingerido (pipeline: skipped_already_ingested) — distinto de
--    'sin_datos' (respuesta vacía) y de 'ok' (datos nuevos).

-- índice único (idempotencia de insert; COALESCE por columnas nulables)
create unique index if not exists uq_deteccion_natural
  on public.fireia_latest_detections (
    product, satellite, latitude, longitude, acq_date,
    coalesce(acq_time, ''), coalesce(confidence, '')
  );

-- ampliar el dominio de estados de cobertura (drop+add del check: tabla
-- operativa nueva de esta misión, sin datos que preservar más allá de hoy)
alter table public.fireia_coverage
  drop constraint if exists fireia_coverage_state_check;
alter table public.fireia_coverage
  add constraint fireia_coverage_state_check
  check (state in ('ok','huecos','fallo','sin_datos','sin_cambios','desconocido'));
