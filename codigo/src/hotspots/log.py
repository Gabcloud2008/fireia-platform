"""Logging estructurado con redacción automática de secretos.

Regla dura del proyecto: ninguna credencial aparece en un log, un informe o la
terminal. `RedactingFilter` reemplaza cualquier ocurrencia de los valores
secretos conocidos por ***REDACTED***, incluso si un mensaje los incluyera por
accidente.
"""

from __future__ import annotations

import logging

REDACTED = "***REDACTED***"


class RedactingFilter(logging.Filter):
    """Reemplaza en el mensaje cualquier valor secreto configurado."""

    def __init__(self, secrets: list[str] | tuple[str, ...] = ()):
        super().__init__()
        # Descarta valores vacíos (un string vacío reemplazaría todo por nada)
        self._secrets = tuple(s for s in secrets if s)

    @property
    def secrets(self) -> tuple[str, ...]:
        return self._secrets

    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        for s in self._secrets:
            if s and s in msg:
                msg = msg.replace(s, REDACTED)
                record.msg = msg
                record.args = ()
                break
        return True


def setup_logging(verbosity: int = 0, secrets: list[str] | tuple[str, ...] = ()) -> None:
    """Configura el logger raíz. verbosity: 0=WARNING, 1=INFO, 2+=DEBUG."""
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s", "%H:%M:%S")
        )
        handler.addFilter(RedactingFilter(secrets))
        root.addHandler(handler)
    root.setLevel(level)
