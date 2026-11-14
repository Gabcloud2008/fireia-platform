"""Registro cartográfico versionado (Misión 005, §3.2).

Cada versión de límites usada por la plataforma queda fichada en
``configs/geo_sources.yaml`` con su procedencia completa: fuente, versión,
año representado, fechas, licencia, hash, estado de validación y — lo más
importante — el CARÁCTER de los límites (estadístico / administrativo de
referencia / catastral) y sus limitaciones.

Nada de esto reemplaza la evidencia en ``data/geo/<version>/source/`` ni los
manifiestos SHA256: es la capa legible que responde "¿qué geometría es esta
y para qué sirve?" sin abrir el almacén.
"""

from __future__ import annotations

from pathlib import Path

import yaml


class RegistryError(Exception):
    """El registro cartográfico no existe o está mal formado."""


def cargar_registro(config_dir: str | Path) -> dict:
    """Lee configs/geo_sources.yaml. Registro ausente = {} (no es error:
    proyectos viejos no lo tienen; el CLI avisa)."""
    ruta = Path(config_dir) / "geo_sources.yaml"
    if not ruta.exists():
        return {}
    try:
        data = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RegistryError(f"geo_sources.yaml inválido: {exc}") from exc
    return data or {}


def ficha_de(registro: dict, version: str) -> dict | None:
    """Ficha de una versión específica (o None si no está fichada)."""
    for ficha in registro.get("fuentes", []):
        if ficha.get("version") == version:
            return ficha
    return None


def fuentes_activas(registro: dict) -> list[dict]:
    """Fichas con estado 'activa'."""
    return [f for f in registro.get("fuentes", []) if f.get("estado") == "activa"]


def validar_ficha(ficha: dict) -> list[str]:
    """Campos obligatorios presentes (para pruebas y auditoría)."""
    requeridos = [
        "version",
        "institucion",
        "fuente",
        "anio_representado",
        "fecha_descarga",
        "fecha_incorporacion",
        "licencia",
        "sha256",
        "estado",
        "caracter",
        "limitaciones",
    ]
    faltan = [c for c in requeridos if not ficha.get(c)]
    return faltan
