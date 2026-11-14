"""Fixtures compartidas de las pruebas (100% offline, sin credenciales)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def clean_env(tmp_path, monkeypatch):
    """Entorno aislado: sin credenciales, con data_dir temporal."""
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    monkeypatch.delenv("HOTSPOTS_DATA_DIR", raising=False)
    monkeypatch.setenv("HOTSPOTS_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def settings(clean_env):
    from hotspots.config import Settings

    # env_file=None: hermético aunque exista un .env real en la raíz
    return Settings.load(env_file=None)


class FakeTransport:
    """Transport de prueba: respuestas programadas, cero red."""

    def __init__(self, responses=None):
        # responses: lista de (status_code, body) o FetchResult o Exception
        self.responses = list(responses or [])
        self.calls: list[dict] = []

    def get(self, url, *, params=None, headers=None, timeout=60.0):
        from hotspots.ingestion.base import FetchResult

        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if not self.responses:
            return FetchResult(
                ok=False, status_code=None, body=None, url_redacted=url, error="no_more_responses"
            )
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            return FetchResult(
                ok=False, status_code=None, body=None, url_redacted=url, error=type(item).__name__
            )
        if isinstance(item, FetchResult):
            return item
        status, body = item
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        return FetchResult(
            ok=200 <= status < 300,
            status_code=status,
            body=body_bytes,
            url_redacted=url,
            error=None,
        )


@pytest.fixture
def fake_transport():
    return FakeTransport
