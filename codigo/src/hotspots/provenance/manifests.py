"""Manifiestos de trazabilidad: cada descarga o importación deja evidencia.

Un manifiesto registra: qué se pidió (URL sin secretos + parámetros), qué se
obtuvo (estado, conteos), qué artefactos produjo (rutas + SHA256 + tamaño) y
la identidad de la corrida (run_id, manifest_id). Índice JSONL para búsqueda
rápida por ``request_key`` (idempotencia).

El ``request_key`` es el hash canónico de (proveedor, fuente, producto,
parámetros): dos corridas con exactamente la misma petición comparten clave,
que es lo que permite detectar "esto ya está ingestado".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MANIFEST_SCHEMA_VERSION = "1.0"


def request_key(provider: str, source: str, product: str, params: dict) -> str:
    """Hash canónico de la petición (sin secretos)."""
    canonical = json.dumps(
        {"provider": provider, "source": source, "product": product, "params": params},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class Artifact:
    path: str
    sha256: str
    size: int
    role: str  # raw_csv | observations_parquet | quarantine_parquet | status_parquet


@dataclass
class Manifest:
    provider: str
    source: str  # firms_api | fixture | ...
    product: str
    request_key: str
    result_state: str  # IngestState.value o 'skipped_already_ingested'
    sensor: str
    satellite_scope: list[str]
    acquisition_period: dict  # {"from": ..., "to": ...} (fechas de consulta)
    counts: dict  # rows_raw / rows_valid / rows_quarantined
    artifacts: list[Artifact] = field(default_factory=list)
    schema_version: str = MANIFEST_SCHEMA_VERSION
    run_id: str = ""
    created_at_utc: str = ""
    processing_state: str = "completed"  # completed | raw_only | failed
    notes: list[str] = field(default_factory=list)
    manifest_id: str = ""

    def finalize(self) -> Manifest:
        """Calcula manifest_id sobre el contenido canónico (sin el id)."""
        if not self.manifest_id:
            d = asdict(self)
            d.pop("manifest_id")
            canonical = json.dumps(d, sort_keys=True, ensure_ascii=False)
            self.manifest_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return self

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Manifest:
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416 — compatibilidad 3.10
        data = {k: v for k, v in d.items() if k in known}
        # los artefactos se reconstruyen como objetos (no dicts sueltos)
        data["artifacts"] = [
            a if isinstance(a, Artifact) else Artifact(**a) for a in data.get("artifacts", [])
        ]
        return cls(**data)


class ManifestStore:
    """Persistencia de manifiestos + índice JSONL por proveedor."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _dir(self, provider: str) -> Path:
        return self.root / provider

    def write(self, manifest: Manifest) -> Path:
        manifest = manifest.finalize()
        folder = self._dir(manifest.provider)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"manifest-{manifest.manifest_id}.json"
        path.write_text(
            json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        with (folder / "index.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "manifest_id": manifest.manifest_id,
                        "request_key": manifest.request_key,
                        "product": manifest.product,
                        "result_state": manifest.result_state,
                        "created_at_utc": manifest.created_at_utc,
                        "path": str(path),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return path

    def find_by_request_key(self, key: str) -> Manifest | None:
        """Devuelve el manifiesto más reciente con ese request_key, si existe."""
        best: tuple[str, Manifest] | None = None
        if not self.root.exists():
            return None
        for index in sorted(self.root.rglob("index.jsonl")):
            for line in index.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get("request_key") == key:
                    m = self.load(entry["manifest_id"])
                    if m is not None:
                        if best is None or m.created_at_utc >= best[0]:
                            best = (m.created_at_utc, m)
        return best[1] if best else None

    def load(self, manifest_id: str) -> Manifest | None:
        for path in sorted(self.root.rglob(f"manifest-{manifest_id}.json")):
            return Manifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
        return None

    def list_entries(self) -> list[dict]:
        entries: list[dict] = []
        if not self.root.exists():
            return entries
        for index in sorted(self.root.rglob("index.jsonl")):
            for line in index.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entries.append(json.loads(line))
        return sorted(entries, key=lambda e: e.get("created_at_utc", ""))

    def count(self) -> int:
        return len(self.list_entries())
