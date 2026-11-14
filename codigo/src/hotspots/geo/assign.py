"""Asignación geográfica de observaciones: la tabla ``obs_geo``.

Reglas de la Misión 003 (doc 03), implementadas:

- Append-only: una fila por (observación, versión de límites). Cambiar de
  versión de límites NO actualiza filas: escribe una tanda nueva.
- Idempotente: las observaciones ya asignadas bajo la versión activa no se
  reasignan (re-ejecutar es seguro y barato).
- La observación no se toca: ni coordenadas ni flags del registro original
  cambian. ``dentro_pais``/``admin1_id``/``admin2_id`` viven SOLO acá.
- Estar fuera de Paraguay no es ser inválido: es una observación válida que
  pertenece a otro territorio (el bbox de consulta incluye vecinos por
  construcción).
- ``metodo`` versiona el algoritmo para que toda estadística sea reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hotspots.geo.boundaries import BoundarySet

#: Versión del método de asignación (cambia si cambia el algoritmo).
ASSIGN_METHOD = "pip_shapely_strtree_v1"

_OBS_GEO_FIELDS = [
    ("obs_id", pa.string()),
    ("version_limites", pa.string()),
    ("dentro_pais", pa.bool_()),
    ("admin1_id", pa.string()),
    ("admin2_id", pa.string()),
    ("metodo", pa.string()),
    ("asignado_en_utc", pa.string()),
]


@dataclass
class AssignSummary:
    version_limites: str
    total_observaciones: int = 0
    ya_asignadas: int = 0
    asignadas_nuevas: int = 0
    dentro_pais: int = 0
    fuera_pais: int = 0
    con_departamento: int = 0
    con_distrito: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def obs_geo_dir(processed_root: str | Path) -> Path:
    return Path(processed_root) / "obs_geo"


def obs_geo_files(processed_root: str | Path) -> list[Path]:
    base = obs_geo_dir(processed_root)
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("part-*.parquet") if p.is_file())


def assigned_obs_ids(processed_root: str | Path, version: str) -> set[str]:
    """obs_id ya asignados bajo esta versión de límites."""
    ids: set[str] = set()
    for f in obs_geo_files(processed_root):
        tbl = pq.read_table(f, columns=["obs_id", "version_limites"])
        d = tbl.to_pydict()
        for oid, ver in zip(d["obs_id"], d["version_limites"], strict=True):
            if ver == version:
                ids.add(oid)
    return ids


def write_obs_geo(
    rows: list[dict], processed_root: str | Path, *, run_id: str
) -> Path | None:
    """Escribe un part-file atómico de asignaciones (tmp + rename)."""
    if not rows:
        return None
    import os

    folder = obs_geo_dir(processed_root)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"part-{run_id}.parquet"
    tmp = path.with_suffix(".parquet.tmp")
    arrays = {name: [r.get(name) for r in rows] for name, _ in _OBS_GEO_FIELDS}
    schema = pa.schema([pa.field(n, t) for n, t in _OBS_GEO_FIELDS])
    pq.write_table(pa.Table.from_pydict(arrays, schema=schema), tmp)
    os.replace(tmp, path)
    return path


def assign_observations(
    boundaries: BoundarySet,
    observations: list[dict],
    *,
    version: str | None = None,
    run_id: str,
    processed_root: str | Path,
    assigned_at_utc: str,
    already_assigned: set[str] | None = None,
) -> AssignSummary:
    """Asigna observaciones contra el BoundarySet activo.

    ``observations``: filas con ``obs_id``, ``longitude``, ``latitude`` (la
    vista deduplicada de DuckDB). Las observaciones sin coordenadas no existen
    en el almacén válido (van a cuarentena en la ingesta); si aparecieran, se
    dejan sin asignar y se reportan en ``notes`` — nunca se inventa un punto.
    """
    version = version or boundaries.version
    previo = already_assigned if already_assigned is not None else assigned_obs_ids(
        processed_root, version
    )
    summary = AssignSummary(version_limites=version)
    rows: list[dict] = []

    for obs in observations:
        summary.total_observaciones += 1
        oid = obs["obs_id"]
        lon, lat = obs.get("longitude"), obs.get("latitude")
        if oid in previo:
            summary.ya_asignadas += 1
            continue
        if lon is None or lat is None:
            summary.notes.append(f"obs sin coordenadas (no asignada): {oid}")
            continue
        result = boundaries.assign(lon, lat)
        rows.append(
            {
                "obs_id": oid,
                "version_limites": version,
                "dentro_pais": result["dentro_pais"],
                "admin1_id": result["admin1_id"],
                "admin2_id": result["admin2_id"],
                "metodo": ASSIGN_METHOD,
                "asignado_en_utc": assigned_at_utc,
            }
        )

    write_obs_geo(rows, processed_root, run_id=run_id)
    summary.asignadas_nuevas = len(rows)
    for r in rows:
        if r["dentro_pais"]:
            summary.dentro_pais += 1
        else:
            summary.fuera_pais += 1
        if r["admin1_id"]:
            summary.con_departamento += 1
        if r["admin2_id"]:
            summary.con_distrito += 1
    return summary
