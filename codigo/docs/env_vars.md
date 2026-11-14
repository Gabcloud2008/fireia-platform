# Variables de entorno

Todas las credenciales viven SOLO en `.env` (copia de `.env.example`) o en variables de entorno del proceso. `.env` está en `.gitignore`. Nunca se escriben en código, documentación, commits o logs (el logging aplica redacción automática con `RedactingFilter`).

| Variable | Obligatoria | Descripción |
|---|---|---|
| `FIRMS_MAP_KEY` | Fase 1B | MAP_KEY gratuita de NASA FIRMS (registro por email en https://firms.modaps.eosdis.nasa.gov/api/map_key/). Requerida solo para la ingesta real. |
| `EARTHDATA_TOKEN` | Fase 1B | Token Bearer de NASA Earthdata Login (https://urs.earthdata.nasa.gov/) para endpoints compatibles. La sesión verifica la estrategia por endpoint. |
| `HF_TOKEN` | No | Reservada para la sincronización futura con Hugging Face. |
| `HOTSPOTS_DATA_DIR` | No | Raíz de datos del pipeline (default: `./data` del repo). Equivalente CLI: `--data-dir`. |

## Reglas implementadas en el código

1. Sin credenciales el sistema sigue funcionando (modo offline: validate, ingest de fixtures, dry-run, status, tests).
2. `Settings.describe()` reporta `SET`/`UNSET`, jamás valores.
3. `Settings` guarda los secretos en campos privados sin `repr`.
4. Los URLs se redactan (`{MAP_KEY}`) antes de loguearse o imprimirse.
5. `RequestsTransport` y el filtro de logs reciben los valores solo para redactar; nada los imprime.
6. Los errores de credenciales (ausente/inválida/sin permisos) tienen mensajes claros que indican cómo configurarlas sin revelar nada.

## Seguridad operativa (reglas del proyecto)

- Las credenciales compartidas por chat se consideran expuestas: revocar/regenerar antes de la Fase 1B.
- No pegar secretos en el chat ni en issues; usar el archivo `.env` local.
- Si un log llegara a contener un secreto por accidente, el filtro lo reemplaza por `***REDACTED***`; de todas formas, revisar el origen.
