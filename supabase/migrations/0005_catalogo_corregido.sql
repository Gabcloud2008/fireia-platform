-- Misión 016 — FIREIA LIVE · Migración 0005: corrección del catálogo de productos
-- El catálogo inicial usó nombres de fuente FIRMS que NO corresponden a la
-- taxonomía del pipeline (configs/sources.yaml): FIRMS sirve MODIS como
-- 'MODIS_NRT' (Terra+Aqua combinados); no existe 'MODIS_TERRA_NRT' ni
-- 'MODIS_AQUA_NRT' en la API Area. Se eliminan las 2 filas erróneas
-- (sembradas minutos antes en 0003, sin corridas asociadas) y se siembra
-- el catálogo correcto. VIIRS_SNPP queda inactivo: NESDIS cesó la serie
-- el 2026-11-02 (documentado en sources.yaml).

delete from public.fireia_source_products
 where product in ('MODIS_TERRA_NRT', 'MODIS_AQUA_NRT');

insert into public.fireia_source_products (product, satellite, sensor, description, active) values
  ('VIIRS_NOAA20_NRT', 'NOAA-20', 'VIIRS', 'Detecciones NRT VIIRS NOAA-20 (FIRMS Area API)', true),
  ('VIIRS_NOAA21_NRT', 'NOAA-21', 'VIIRS', 'Detecciones NRT VIIRS NOAA-21 (FIRMS Area API)', true),
  ('MODIS_NRT',        'Terra+Aqua', 'MODIS', 'Detecciones NRT MODIS Terra+Aqua combinadas (FIRMS Area API)', true),
  ('VIIRS_SNPP_NRT',   'S-NPP',   'VIIRS', 'Serie cesada 2026-11-02 (NESDIS OSPO); backfill solo por portal de archivo', false)
on conflict (product) do update
  set satellite = excluded.satellite,
      sensor = excluded.sensor,
      description = excluded.description,
      active = excluded.active;

-- Verificación: exactamente 3 activos con taxonomía correcta
do $$
declare
  n integer;
begin
  select count(*) into n from public.fireia_source_products where active;
  assert n = 3, 'se esperaban exactamente 3 productos activos, hay ' || n;
end $$;
