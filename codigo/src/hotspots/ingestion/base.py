"""Transporte HTTP abstracto: la única vía de red del sistema.

Toda la lógica de ingesta depende de la interfaz :class:`Transport`, nunca de
``requests`` directamente. Así las pruebas corren 100% offline con transports
falsos, y el transporte real queda como una pieza intercambiable que solo se
usa (con autorización) en Fase 1B.

Endurecimiento de Misión 004 (etapa 3):

- **Reintentos con backoff exponencial** ante errores transitorios: fallos de
  red (timeout, DNS, conexión) y respuestas HTTP 429/5xx. Máximo
  ``max_retries`` reintentos; espera ``backoff_base * 2^intento`` segundos
  (cap ``backoff_cap``). En 429 se respeta ``Retry-After`` si el servidor lo
  manda (capado al mismo límite: no esperamos minutos por un retry).
- **Nunca se reintenta** lo que no es transitorio: 401/403 (credenciales) y
  otros 4xx van directo a resultado.
- **Rate limit de cliente**: intervalo mínimo entre solicitudes
  (``min_interval_s``). FIRMS documenta 5000 transacciones / 10 min; nuestro
  límite es conservador y evita ráfagas.
- El ``requests.get`` se importa tarde y la espera es inyectable: las pruebas
  no duermen ni tocan la red.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class FetchResult:
    ok: bool
    status_code: int | None
    body: bytes | None
    url_redacted: str  # URL con cualquier secreto reemplazado
    error: str | None = None

    @property
    def text(self) -> str:
        if self.body is None:
            return ""
        return self.body.decode("utf-8", errors="replace")


class TransportError(Exception):
    """Fallo de transporte (red, DNS, timeout)."""


class Transport:
    """Interfaz mínima: GET con parámetros, headers y timeout."""

    def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: float = 60.0,
    ) -> FetchResult:
        raise NotImplementedError


def _is_retryable_status(code: int | None) -> bool:
    return code is not None and (code == 429 or code >= 500)


@dataclass
class _RetryPolicy:
    max_retries: int = 3
    backoff_base: float = 1.5
    backoff_cap: float = 30.0
    min_interval_s: float = 0.25


class RequestsTransport(Transport):
    """Transporte real sobre ``requests``. Solo se usa con autorización (Fase 1B)."""

    def __init__(
        self,
        redact_secrets: list[str] | None = None,
        *,
        max_retries: int = 3,
        backoff_base: float = 1.5,
        backoff_cap: float = 30.0,
        min_interval_s: float = 0.25,
        sleep=None,
        clock=None,
    ):
        self._secrets = [s for s in (redact_secrets or []) if s]
        self.policy = _RetryPolicy(
            max_retries=max_retries,
            backoff_base=backoff_base,
            backoff_cap=backoff_cap,
            min_interval_s=min_interval_s,
        )
        self._sleep = sleep or time.sleep
        self._clock = clock or time.monotonic
        self._last_request_at: float | None = None
        # observabilidad de reintentos (para logs/pruebas; sin secretos)
        self.last_attempts: list[dict] = []

    def _redact(self, url: str) -> str:
        for s in self._secrets:
            if s and s in url:
                url = url.replace(s, "{MAP_KEY}")
        return url

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self._clock() - self._last_request_at
        remaining = self.policy.min_interval_s - elapsed
        if remaining > 0:
            self._sleep(remaining)

    def _backoff_seconds(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.policy.backoff_cap)
            except ValueError:
                pass
        return min(self.policy.backoff_base * (2**attempt), self.policy.backoff_cap)

    def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: float = 60.0,
    ) -> FetchResult:
        import requests  # import tardío: mantener offline la importación del paquete

        self.last_attempts = []
        total = self.policy.max_retries + 1
        for attempt in range(total):
            self._wait_for_rate_limit()
            self._last_request_at = self._clock()
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            except requests.RequestException as exc:  # red/DNS/timeout, sin secretos
                self.last_attempts.append(
                    {"attempt": attempt, "kind": type(exc).__name__}
                )
                if attempt < total - 1:
                    self._sleep(self._backoff_seconds(attempt, None))
                    continue
                return FetchResult(
                    ok=False,
                    status_code=None,
                    body=None,
                    url_redacted=self._redact(url),
                    error=f"{type(exc).__name__}",
                )

            code = resp.status_code
            if 200 <= code < 300:
                return FetchResult(
                    ok=True,
                    status_code=code,
                    body=resp.content,
                    url_redacted=self._redact(url),
                    error=None,
                )
            if _is_retryable_status(code) and attempt < total - 1:
                self.last_attempts.append({"attempt": attempt, "status": code})
                self._sleep(
                    self._backoff_seconds(attempt, resp.headers.get("Retry-After"))
                )
                continue
            # no transitorio (401/403/4xx) o intentos agotados
            return FetchResult(
                ok=False,
                status_code=code,
                body=resp.content,
                url_redacted=self._redact(url),
                error=None,
            )
        # inalcanzable por construcción
        raise TransportError("get: flujo de reintentos terminó sin resultado")
