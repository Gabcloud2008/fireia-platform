"""Sesión de NASA Earthdata Login (Fase 1B: CMR/LAADS).

Estrategias de autenticación (NO todos los servicios aceptan lo mismo):

- ``bearer``: header ``Authorization: Bearer <token>`` — token del perfil de
  Earthdata Login. Aceptado por varios endpoints de CMR/LAADS; hay que
  verificarlo POR ENDPOINT antes de usarlo (la misión lo exige explícito).
- ``netrc``: ``~/.netrc`` con credenciales básicas (mecanismo clásico de
  Earthdata, requisito de la mayoría de portales de descarga).

Seguridad: el token jamás aparece en ``repr``, logs ni mensajes de error.
"""

from __future__ import annotations

import logging
from pathlib import Path

from hotspots.ingestion.base import FetchResult, Transport

logger = logging.getLogger(__name__)

ENV_EARTHDATA_TOKEN = "EARTHDATA_TOKEN"


class EarthdataAuthenticationError(Exception):
    """Autenticación fallida (token ausente/expirado/sin permisos o netrc inválido)."""


class EarthdataSession:
    """Sesión con estrategia de autenticación explícita."""

    def __init__(
        self,
        token: str | None = None,
        netrc_path: str | Path | None = None,
        env: dict | None = None,
    ):
        import os

        env = env if env is not None else dict(os.environ)
        self._token = token or env.get(ENV_EARTHDATA_TOKEN) or None
        self._netrc_path = Path(netrc_path) if netrc_path else Path.home() / ".netrc"

        if self._token:
            self.strategy = "bearer"
        elif self._netrc_path.exists():
            self.strategy = "netrc"
        else:
            self.strategy = None

    @property
    def token_configured(self) -> bool:
        return bool(self._token)

    def headers(self) -> dict:
        """Headers de autenticación según estrategia. Sin token en ningún log."""
        if self.strategy == "bearer":
            return {"Authorization": f"Bearer {self._token}"}
        if self.strategy == "netrc":
            return {}  # requests maneja .netrc automáticamente; verificación aparte
        raise EarthdataAuthenticationError(
            "Sin credenciales de Earthdata: configurá EARTHDATA_TOKEN en .env "
            "(para endpoints compatibles con Bearer) o ~/.netrc (mecanismo clásico)."
        )

    def get(self, url: str, *, transport: Transport, timeout: float = 60.0) -> FetchResult:
        """GET autenticado. 401/403 se traducen a excepción clara sin filtrar secretos."""
        headers = self.headers()
        result = transport.get(url, headers=headers, timeout=timeout)
        if result.status_code in (401, 403):
            raise EarthdataAuthenticationError(
                f"Earthdata rechazó la autenticación (HTTP {result.status_code}) "
                f"con estrategia {self.strategy!r}. Verificá que el token sea "
                "válido, no haya expirado y que el endpoint acepte este mecanismo."
            )
        return result

    def __repr__(self) -> str:  # nunca incluye el token
        return f"<EarthdataSession strategy={self.strategy!r} token=***>"
