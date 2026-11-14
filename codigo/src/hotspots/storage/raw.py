"""Zona RAW inmutable: los datos originales jamás se modifican.

Implementación content-addressed: el nombre del archivo ES su SHA256. Dos
consecuencias directas:

- Idempotencia por construcción: volver a "subir" el mismo contenido no crea
  un archivo nuevo ni pisa el existente (write-once).
- Integridad verificable: cualquier persona puede recomputar el hash y
  compararlo con el nombre del archivo y con el manifiesto.

Los archivos se marcan como solo lectura (chmod 0444) como salvaguarda contra
modificaciones accidentales. No es protección criptográfica — la inmutabilidad
real la da el versionado (manifests + git del repo de datos en su momento).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StoredRaw:
    path: Path
    sha256: str
    size: int
    already_existed: bool


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RawStore:
    """Almacén RAW inmutable bajo ``<root>/<provider>/<product>/<year>/<sha256>.<ext>``."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def store(
        self,
        data: bytes,
        *,
        provider: str,
        product: str,
        year: str | int,
        suffix: str = ".csv",
    ) -> StoredRaw:
        digest = sha256_bytes(data)
        folder = self.root / provider / product / str(year)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{digest}{suffix}"

        if path.exists():
            # Write-once: el contenido idéntico ya está guardado; no se toca.
            os.chmod(path, 0o444)
            return StoredRaw(path, digest, path.stat().st_size, already_existed=True)

        tmp = path.with_suffix(suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        os.chmod(path, 0o444)  # solo lectura: salvaguarda de inmutabilidad
        return StoredRaw(path, digest, len(data), already_existed=False)

    def _data_files(self) -> list[Path]:
        if not self.root.exists():
            return []
        return [
            p
            for p in self.root.rglob("*")
            if p.is_file() and p.suffix != ".tmp" and p.name != ".gitkeep"
        ]

    def count(self) -> int:
        return len(self._data_files())

    def total_bytes(self) -> int:
        return sum(p.stat().st_size for p in self._data_files())
