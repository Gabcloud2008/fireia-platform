# FIREIA — Plataforma (fireia-platform)

**Paraguay Fire Intelligence (FIREIA)** · NASA Space Apps Challenge 2026 · Challenge 1.9 — *Harmonization of MODIS and VIIRS Hot Spots*

Repositorio de la **plataforma operativa**: pipeline científico + web + capa LIVE (Supabase). El repositorio canónico de datos científicos y documentación de misiones sigue siendo [Hugging Face](https://huggingface.co/datasets/p400-full/modis-viirs-hotspots-paraguay).

## Qué hay aquí

| Carpeta | Contenido |
| --- | --- |
| `codigo/` | Pipeline científico Python (ingesta FIRMS → normalización → QC → GeoParquet → DuckDB → eventos). 299 pruebas + 19 skips, offline |
| `web/` | Plataforma Next.js 15 (~20 vistas) con capa **FIREIA LIVE**: Realtime de Supabase, insignia de frescura y proxy de IA |
| `supabase/` | Migraciones versionadas, 6 Edge Functions, smoke tests y config |
| `.github/workflows/` | `ci.yml` (ruff+pytest+build web+deno check+gitleaks) y `ingesta.yml` (workflow_dispatch con concurrencia) |
| `scripts/` | Pegamento operativo (reporte de corridas a Supabase) |

## Arquitectura LIVE (Misión 016)

```
Supabase Cron (cada 30 min)
  → Edge Function fireia-dispatch-ingestion   (registra corrida, idempotente)
  → GitHub Actions ingesta.yml                (workflow_dispatch)
      → pipeline Python: FIRMS → RAW(SHA-256) → QC → Parquet → manifiestos
      → reporta a Supabase: corrida, cobertura, assets, detecciones, alertas
  → Supabase Realtime → web (insignia EN VIVO, datos frescos)
  → Render (solo IA): https://fireia-api.onrender.com ← proxy /api/ia/prediccion
```

- **Postgres guarda SOLO lo operativo** (metadatos, estados, ventana móvil ≤ 7 días de detecciones, alertas). Los 2,69 M de registros históricos viven en Parquet; DuckDB sigue siendo el motor analítico.
- **Ningún secreto en el repo**: GitHub Secrets (Actions) y Supabase Vault (cron).
- La API de IA **no** tiene clave: es pública por diseño, con integridad verificada por SHA-256.

## Arranque rápido

```bash
# Pipeline (offline, sin credenciales)
cd codigo && pip install -r requirements.lock && pip install -e .
python -m pytest -q

# Web (funciona SIN Supabase: usa export estático)
cd web && bun install && bun run build

# Con capa en vivo: definir en el entorno
#   NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, FIREIA_API_BASE
```

## Ingesta

- Manual (fixture, sin red): Actions → *Ingesta FIREIA* → `modo=fixture`.
- Manual (real): `modo=real` (usa `FIRMS_MAP_KEY` de los secrets; área `py`).
- Automática: Supabase Cron cada 30 min (ver `supabase/migrations/0004_cron_dispatch.sql`).

## Seguridad

Ver `13_seguridad.md` de la Misión 016 (repositorio canónico HF). Regla corta: nunca claves en código, logs ni chat; rotar credenciales expuestas.
