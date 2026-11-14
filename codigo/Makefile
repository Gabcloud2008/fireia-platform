.PHONY: install test lint format demo status lock

install:  ## Instala el paquete en modo editable con dependencias de desarrollo
	pip install -e ".[dev]"

test:  ## Suite completa (100% offline: sin credenciales y sin red)
	python -m pytest -q

lint:  ## Análisis estático
	ruff check src tests scripts

format:  ## Formateo automático
	ruff format src tests scripts

demo:  ## Hito Fase 1A: validar + ingesta offline + idempotencia + dry-run + status
	bash scripts/demo_phase1a.sh

status:  ## Estado del almacén local
	hotspots status

lock:  ## Congela versiones exactas de las dependencias directas
	pip freeze | grep -Ei '^(requests|python-dotenv|pyyaml|duckdb|pyarrow|pytest|ruff)==' > requirements.lock
