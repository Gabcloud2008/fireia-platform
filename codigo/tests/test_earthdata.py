"""Pruebas de la sesión Earthdata (offline)."""

from __future__ import annotations

import pytest

from hotspots.earthdata.session import EarthdataAuthenticationError, EarthdataSession
from tests.conftest import FakeTransport


def test_estrategia_bearer_con_token(clean_env):
    s = EarthdataSession(token="tok-super-secreto-1")
    assert s.strategy == "bearer"
    headers = s.headers()
    assert headers == {"Authorization": "Bearer tok-super-secreto-1"}


def test_sin_credenciales_error_claro(tmp_path, clean_env):
    s = EarthdataSession(netrc_path=tmp_path / "no_existe.netrc")
    assert s.strategy is None
    with pytest.raises(EarthdataAuthenticationError, match="EARTHDATA_TOKEN"):
        s.headers()


def test_401_lanza_excepcion_sin_filtrar_token(tmp_path):
    s = EarthdataSession(token="tok-abc-123", netrc_path=tmp_path / "x")
    transport = FakeTransport([(401, "Unauthorized")])
    with pytest.raises(EarthdataAuthenticationError) as exc:
        s.get("https://example.nasa.gov/api/x", transport=transport)
    assert "tok-abc-123" not in str(exc.value)
    assert "401" in str(exc.value)


def test_200_pasa_limpio(tmp_path):
    s = EarthdataSession(token="tok-abc-123", netrc_path=tmp_path / "x")
    transport = FakeTransport([(200, '{"ok": true}')])
    result = s.get("https://example.nasa.gov/api/x", transport=transport)
    assert result.ok
    # el header viajó con el token (pero nunca a un log)
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer tok-abc-123"


def test_repr_no_contiene_token():
    s = EarthdataSession(token="MUY-SECRETO-XYZ")
    assert "MUY-SECRETO-XYZ" not in repr(s)
    assert "token=***" in repr(s)


def test_403_tambien_es_error_de_autenticacion(tmp_path):
    s = EarthdataSession(token="tok-abc", netrc_path=tmp_path / "x")
    transport = FakeTransport([(403, "Forbidden")])
    with pytest.raises(EarthdataAuthenticationError, match="403"):
        s.get("https://example.nasa.gov/api/x", transport=transport)
