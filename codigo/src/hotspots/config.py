"""Configuración centralizada del proyecto.

Tres fuentes, en este orden de prioridad:

1. Variables de entorno reales (secretos): ``FIRMS_MAP_KEY``, ``EARTHDATA_TOKEN``,
   ``HF_TOKEN``, ``HOTSPOTS_DATA_DIR``.
2. Archivo ``.env`` en la raíz del repositorio (no pisa al entorno real).
3. YAMLs no secretos: ``configs/sources.yaml`` y ``configs/qc.yaml``.

Reglas de seguridad:
- Los valores de credenciales JAMÁS se imprimen, se loguean ni se serializan.
  ``Settings`` los guarda en campos privados sin ``repr`` y expone solo
  booleanos de disponibilidad (``describe()`` reporta SET/UNSET).
- ``secret_values()`` existe únicamente para alimentar el filtro de redacción
  de logs; ningún código debe imprimir su resultado.
"""

from __future__ import annotations

import logging
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import dotenv_values

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

ENV_FIRMS_MAP_KEY = "FIRMS_MAP_KEY"
ENV_EARTHDATA_TOKEN = "EARTHDATA_TOKEN"
ENV_HF_TOKEN = "HF_TOKEN"
ENV_DATA_DIR = "HOTSPOTS_DATA_DIR"


class ConfigError(Exception):
    """Error de configuración (archivo faltante o inválido)."""


@dataclass
class Settings:
    """Configuración de ejecución. Cargar siempre con :meth:`load`.

    Distinción territorial (Misión 005):

    - ``firms_query_bbox`` es el RECTÁNGULO usado para pedir datos a FIRMS
      (con margen para no perder detecciones cercanas al borde). Incluye
      territorio de Argentina, Brasil y Bolivia por construcción.
    - La pertenencia al TERRITORIO NACIONAL la decide EXCLUSIVAMENTE el
      polígono ADM0 de la capa geográfica activa (``obs_geo.dentro_pais``).
      Jamás el bbox.
    - ``query_bbox_margin_deg`` es la tolerancia del chequeo blando de QC
      (``outside_query_bbox``), no una frontera.
    """

    base_url: str
    products: dict
    satellite_codes: dict
    instruments: list
    firms_query_bbox: tuple[float, float, float, float]
    query_bbox_margin_deg: float
    qc: dict
    day_range_limits: tuple[int, int]
    data_dir: Path
    config_dir: Path
    _firms_map_key: str | None = field(default=None, repr=False, compare=False)
    _earthdata_token: str | None = field(default=None, repr=False, compare=False)

    @property
    def paraguay_bbox(self) -> tuple[float, float, float, float]:
        """Alias deprecado de ``firms_query_bbox`` (Misión 005).

        El nombre viejo confundía el rectángulo de CONSULTA con el territorio
        nacional. Mantener el alias evita romper código externo, pero avisa.
        """
        warnings.warn(
            "settings.paraguay_bbox está deprecado: usá firms_query_bbox. "
            "El bbox es un rectángulo de CONSULTA, no el territorio nacional "
            "(la pertenencia la resuelve la capa ADM0).",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.firms_query_bbox

    @property
    def bbox_margin_deg(self) -> float:
        """Alias deprecado de ``query_bbox_margin_deg``."""
        warnings.warn(
            "settings.bbox_margin_deg está deprecado: usá query_bbox_margin_deg.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.query_bbox_margin_deg

    # ------------------------------------------------------------------ creds
    @property
    def firms_map_key(self) -> str | None:
        return self._firms_map_key

    @property
    def earthdata_token(self) -> str | None:
        return self._earthdata_token

    @property
    def has_firms_key(self) -> bool:
        return bool(self._firms_map_key)

    @property
    def has_earthdata_token(self) -> bool:
        return bool(self._earthdata_token)

    def secret_values(self) -> list[str]:
        """Solo para el filtro de redacción de logs. No imprimir jamás."""
        return [v for v in (self._firms_map_key, self._earthdata_token) if v]

    def describe(self) -> str:
        """Resumen seguro de la configuración (sin valores secretos)."""
        activos = sorted(p for p, c in self.products.items() if c.get("active"))
        return (
            f"FIRMS_MAP_KEY: {'SET' if self.has_firms_key else 'UNSET'} | "
            f"EARTHDATA_TOKEN: {'SET' if self.has_earthdata_token else 'UNSET'} | "
            f"data_dir: {self.data_dir} | "
            f"productos activos: {len(activos)} {activos}"
        )

    # ---------------------------------------------------------------- fuentes
    def product_cfg(self, product: str) -> dict:
        try:
            return self.products[product]
        except KeyError:
            disponibles = ", ".join(sorted(self.products))
            raise ValueError(
                f"Producto desconocido: {product!r}. Disponibles: {disponibles}"
            ) from None

    def check_day_range(self, day_range: int) -> int:
        lo, hi = self.day_range_limits
        if not (lo <= day_range <= hi):
            raise ValueError(
                f"DAY_RANGE debe estar entre {lo} y {hi} (documentación FIRMS); "
                f"recibido {day_range}"
            )
        return day_range

    # ------------------------------------------------------------------ load
    @classmethod
    def load(
        cls,
        env: dict | None = None,
        env_file: str | Path | None = "auto",
        data_dir: str | Path | None = None,
        config_dir: str | Path | None = None,
    ) -> Settings:
        """Carga la configuración. Permite ejecutar sin credenciales (modo offline)."""
        merged_env = dict(os.environ if env is None else env)

        if env_file == "auto":
            env_file = REPO_ROOT / ".env"
        if env_file is not None and Path(env_file).exists():
            for key, val in dotenv_values(env_file).items():
                # El entorno real tiene prioridad sobre el archivo
                merged_env.setdefault(key, val or "")

        cfg_dir = Path(config_dir) if config_dir else REPO_ROOT / "configs"
        try:
            sources = yaml.safe_load((cfg_dir / "sources.yaml").read_text(encoding="utf-8"))
            qc = yaml.safe_load((cfg_dir / "qc.yaml").read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigError(f"No se encontró configuración en {cfg_dir}: {exc}") from exc

        firms = sources["firms_api"]
        area = sources.get("area", {})
        query = sources.get("firms_query", {})
        # Misión 005: el rectángulo es de CONSULTA a FIRMS, no el país.
        # Clave nueva 'firms_query.bbox'; la vieja 'area.paraguay_bbox' se
        # acepta con warning de deprecación (compatibilidad con configs viejos).
        bbox_raw = query.get("bbox") or area.get("paraguay_bbox")
        if bbox_raw is None:
            raise ConfigError(
                "falta el bbox de consulta: definí firms_query.bbox en sources.yaml "
                "(W, S, E, N). Es el rectángulo para pedir datos a FIRMS — NO "
                "representa el territorio nacional."
            )
        if query.get("bbox") is None and area.get("paraguay_bbox") is not None:
            warnings.warn(
                "sources.yaml usa la clave vieja 'area.paraguay_bbox': migrá a "
                "'firms_query.bbox' (rectángulo de consulta, no territorio).",
                DeprecationWarning,
                stacklevel=2,
            )
        bbox = tuple(float(x) for x in bbox_raw)
        margin = float(query.get("bbox_margin_deg") or area.get("bbox_margin_deg", 0.5))

        if data_dir is not None:
            data = Path(data_dir)
        elif merged_env.get(ENV_DATA_DIR):
            data = Path(merged_env[ENV_DATA_DIR])
        else:
            data = REPO_ROOT / "data"

        return cls(
            base_url=firms["base_url"].rstrip("/"),
            products=firms["products"],
            satellite_codes=firms.get("satellite_codes", {}),
            instruments=list(firms.get("instruments", [])),
            firms_query_bbox=bbox,
            query_bbox_margin_deg=margin,
            qc=qc,
            day_range_limits=(int(firms["day_range_min"]), int(firms["day_range_max"])),
            data_dir=data,
            config_dir=cfg_dir,
            _firms_map_key=merged_env.get(ENV_FIRMS_MAP_KEY) or None,
            _earthdata_token=merged_env.get(ENV_EARTHDATA_TOKEN) or None,
        )
