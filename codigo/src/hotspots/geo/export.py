"""Exportación de capas GeoJSON para visualización (MapLibre y similares).

Lo que sale de acá son DERIVADOS para la web: la geometría original nunca se
modifica y el parquet de unidades queda intacto. La simplificación (si se pide)
es solo para el peso del archivo en el navegador.
"""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import mapping


def export_departamentos_geojson(
    boundaries, path: str | Path, *, simplify_tolerance_deg: float | None = None
) -> Path:
    """Capa ADM1 (18 unidades). Sin simplify por default: geometría completa."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for u in boundaries.units:
        if u.nivel != 1:
            continue
        geom = u.geometry
        if simplify_tolerance_deg:
            geom = geom.simplify(simplify_tolerance_deg, preserve_topology=True)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "admin_id": u.admin_id,
                    "nombre": u.nombre,
                    "nivel": u.nivel,
                },
                "geometry": mapping(geom),
            }
        )
    fc = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {"version_limites": boundaries.version},
    }
    path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    return path


def export_points_geojson(
    rows: list[dict], path: str | Path, *, layer_meta: dict | None = None
) -> Path:
    """Capa de puntos de observaciones con su contexto geográfico.

    ``rows``: dicts con latitude, longitude y cualquier propiedad extra
    (obs_id, product, sensor, satellite, acq_datetime_utc, dentro_pais,
    departamento, …) — las propiedades viajan tal cual.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for r in rows:
        props = {k: v for k, v in r.items() if k not in ("latitude", "longitude")}
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": {
                    "type": "Point",
                    "coordinates": [r["longitude"], r["latitude"]],
                },
            }
        )
    fc = {
        "type": "FeatureCollection",
        "features": features,
        "properties": layer_meta or {},
    }
    path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    return path
