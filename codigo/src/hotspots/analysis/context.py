"""Contexto ambiental para observaciones de fuego (Misión 006, Objetivo D).

Asocia variables ambientales de rejilla (ERA5-Land, CHIRPS, WorldCover, ...)
a observaciones MODIS/VIIRS **sin alterar las observaciones originales** y
**sin fingir precisiones que las fuentes no tienen**.

Reglas de honestidad (innegociables):

1. Método de asociación: **celda más cercana** (nearest cell). Nada de
   interpolación espacial: el valor ambiental es "el de la celda que contiene
   (o más cerca de) la detección", nunca "el valor en el punto".
2. Cada registro de contexto declara: distancia al centro de la celda,
   tamaño de celda efectivo en metros EN ESA LATITUD (las rejillas
   lat/lon no son cuadradas en metros), y la resolución declarada de la
   fuente. Una detección de 375 m asociada a una celda de ~11 km queda
   explícito: el contexto no hereda la precisión del punto.
3. Las variables con resoluciones distintas NUNCA se mezclan en un mismo
   campo: cada variable tiene su identificador, unidad y procedencia.
4. Si la observación cae fuera de la rejilla disponible, no hay contexto:
   se devuelve ``None`` con el motivo. Nada de extrapolar.
5. La asociación es **append-only**: produce registros nuevos
   (``ContextoAmbiental``); jamás escribe dentro de las observaciones.

Las fuentes reales (CDS, CHC, etc.) quedan tras compuerta de red/credenciales;
este módulo opera con rejillas ya descargadas (o sintéticas en pruebas). El
registro de fuentes vive en ``configs/env_sources.yaml``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

__all__ = [
    "EnvVariableSpec",
    "GridVariable",
    "ContextoAmbiental",
    "ObservacionPunto",
    "asociar_contexto",
    "cargar_registro_fuentes",
]

# radio medio de la Tierra en metros (WGS84)
_R_TIERRA_M = 6_371_008.8


@dataclass(frozen=True)
class EnvVariableSpec:
    """Ficha de una variable ambiental (espejo de configs/env_sources.yaml)."""

    variable_id: str
    fuente: str
    producto: str
    variable: str
    unidad: str
    resolucion_espacial: str  # declarada por la fuente (ej. "0.1° (~9 km)")
    resolucion_temporal: str  # ej. "horaria", "diaria", "estática (2021)"
    licencia: str
    metodo_extraccion: str = "celda_nearest"
    version: str = "1"


@dataclass(frozen=True)
class GridVariable:
    """Rejilla regular lat/lon de una variable, para un paso temporal.

    ``origen`` es (lat_min, lon_min); ``paso`` es (dlat, dlon) en grados
    positivos. ``valores`` es una matriz [ilat][ilon].
    """

    spec: EnvVariableSpec
    fecha: date
    origen: tuple[float, float]
    paso: tuple[float, float]
    valores: list[list[float | None]]

    def en_rejilla(self, lat: float, lon: float) -> bool:
        lat_min, lon_min = self.origen
        dlat, dlon = self.paso
        n_lat = len(self.valores)
        n_lon = len(self.valores[0]) if n_lat else 0
        return (
            lat_min - dlat / 2 <= lat < lat_min + n_lat * dlat + dlat / 2
            and lon_min - dlon / 2 <= lon < lon_min + n_lon * dlon + dlon / 2
        )

    def indice_celda(self, lat: float, lon: float) -> tuple[int, int]:
        lat_min, lon_min = self.origen
        dlat, dlon = self.paso
        i = int((lat - lat_min) // dlat)
        j = int((lon - lon_min) // dlon)
        n_lat = len(self.valores)
        n_lon = len(self.valores[0]) if n_lat else 0
        return min(max(i, 0), n_lat - 1), min(max(j, 0), n_lon - 1)

    def valor(self, i: int, j: int) -> float | None:
        return self.valores[i][j]


@dataclass(frozen=True)
class ObservacionPunto:
    """Vista mínima de una observación para asociar contexto."""

    obs_id: str
    lat: float
    lon: float
    fecha: date


@dataclass(frozen=True)
class ContextoAmbiental:
    """Registro de contexto: lo que la fuente dice EN LA CELDA, no en el punto."""

    obs_id: str
    variable_id: str
    fecha: date
    valor: float | None
    unidad: str
    # honestidad de escala
    celda_ij: tuple[int, int] | None
    distancia_centro_m: float | None
    resolucion_efectiva_m: tuple[float, float] | None
    # procedencia
    fuente: str
    producto: str
    metodo: str
    version: str
    # cuando no hay valor
    sin_contexto_motivo: str | None = None
    extras: dict[str, str] = field(default_factory=dict)

    @property
    def tiene_valor(self) -> bool:
        return self.valor is not None


def _distancia_haversine_m(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    fi1, fi2 = math.radians(lat1), math.radians(lat2)
    dfi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dfi / 2) ** 2 + math.cos(fi1) * math.cos(fi2) * math.sin(dlam / 2) ** 2
    return 2 * _R_TIERRA_M * math.asin(math.sqrt(a))


def _tamano_celda_m(lat: float, dlat: float, dlon: float) -> tuple[float, float]:
    """Tamaño N-S y E-O de una celda lat/lon, en metros, a esa latitud."""
    ns = dlat * math.pi / 180 * _R_TIERRA_M
    eo = dlon * math.pi / 180 * _R_TIERRA_M * math.cos(math.radians(lat))
    return round(ns, 1), round(eo, 1)


def asociar_contexto(
    obs: ObservacionPunto, grid: GridVariable
) -> ContextoAmbiental:
    """Asocia UNA observación a UNA rejilla por celda más cercana.

    Devuelve siempre un ``ContextoAmbiental``; si no hay valor posible,
    ``tiene_valor`` es False y ``sin_contexto_motivo`` explica por qué
    (fuera de rejilla, celda sin dato, fecha incompatible).
    """
    spec = grid.spec
    comunes = {
        "variable_id": spec.variable_id,
        "fecha": grid.fecha,
        "unidad": spec.unidad,
        "fuente": spec.fuente,
        "producto": spec.producto,
        "metodo": spec.metodo_extraccion,
        "version": spec.version,
    }

    es_estatica = spec.resolucion_temporal.startswith("estática")
    if obs.fecha != grid.fecha and not es_estatica:
        return ContextoAmbiental(
            obs_id=obs.obs_id,
            valor=None,
            celda_ij=None,
            distancia_centro_m=None,
            resolucion_efectiva_m=None,
            sin_contexto_motivo=(
                f"fecha obs {obs.fecha.isoformat()} != fecha rejilla "
                f"{grid.fecha.isoformat()} (variable {spec.resolucion_temporal})"
            ),
            **comunes,
        )

    if not grid.en_rejilla(obs.lat, obs.lon):
        return ContextoAmbiental(
            obs_id=obs.obs_id,
            valor=None,
            celda_ij=None,
            distancia_centro_m=None,
            resolucion_efectiva_m=None,
            sin_contexto_motivo="observación fuera de la extensión de la rejilla",
            **comunes,
        )

    i, j = grid.indice_celda(obs.lat, obs.lon)
    dlat, dlon = grid.paso
    lat_min, lon_min = grid.origen
    centro_lat = lat_min + (i + 0.5) * dlat
    centro_lon = lon_min + (j + 0.5) * dlon
    dist = round(
        _distancia_haversine_m(obs.lat, obs.lon, centro_lat, centro_lon), 1
    )
    tam = _tamano_celda_m(centro_lat, dlat, dlon)
    valor = grid.valor(i, j)

    return ContextoAmbiental(
        obs_id=obs.obs_id,
        valor=valor,
        celda_ij=(i, j),
        distancia_centro_m=dist,
        resolucion_efectiva_m=tam,
        sin_contexto_motivo=None if valor is not None else "celda sin dato",
        **comunes,
    )


def cargar_registro_fuentes(ruta_yaml: str) -> dict[str, EnvVariableSpec]:
    """Carga las fichas de configs/env_sources.yaml (requiere PyYAML)."""
    import yaml

    with open(ruta_yaml, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    specs: dict[str, EnvVariableSpec] = {}
    for fuente in data.get("fuentes", []):
        estado = fuente.get("estado", "")
        for var in fuente.get("variables", []):
            spec = EnvVariableSpec(
                variable_id=var["variable_id"],
                fuente=fuente["institucion"],
                producto=var["producto"],
                variable=var["nombre"],
                unidad=var["unidad"],
                resolucion_espacial=(
                    f"{var['resolucion_espacial']} ({var['resolucion_espacial_metros']})"
                ),
                resolucion_temporal=var["resolucion_temporal"],
                licencia=fuente["licencia"],
                version=var.get("version", "1"),
            )
            specs[spec.variable_id] = spec
            if estado and estado != "integrada":
                # se carga la ficha igual (documentación), pero queda marcada
                specs[spec.variable_id] = spec
    return specs
