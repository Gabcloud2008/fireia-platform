"""Pruebas del conector FIRMS (offline, con transport falso)."""

from __future__ import annotations

import pytest

from hotspots.ingestion.firms import CredentialsError, FirmsClient
from tests.conftest import FIXTURES, FakeTransport

BASE = "https://firms.modaps.eosdis.nasa.gov"
KEY = "TEST-KEY-123"


def _client(transport):
    return FirmsClient(BASE, KEY, transport)


def test_area_url_formato_documentado():
    client = _client(FakeTransport())
    url = client.area_url(
        "VIIRS_NOAA21_NRT", (-62.7, -27.6, -54.2, -19.3), day_range=2, date="2026-09-15"
    )
    assert url == (
        f"{BASE}/api/area/csv/{KEY}/VIIRS_NOAA21_NRT/-62.7,-27.6,-54.2,-19.3/2/2026-09-15"
    )
    # sin DATE: los datos más recientes (comportamiento documentado)
    assert client.area_url("MODIS_NRT", (-62.7, -27.6, -54.2, -19.3)).endswith("/1")


def test_url_redactada_no_contiene_clave():
    client = _client(FakeTransport())
    url = client.area_url("MODIS_NRT", (-62.7, -27.6, -54.2, -19.3))
    redacted = FirmsClient.redact(url, KEY)
    assert KEY not in redacted
    assert "{MAP_KEY}" in redacted


def test_sin_map_key_error_claro():
    with pytest.raises(CredentialsError, match="FIRMS_MAP_KEY"):
        FirmsClient(BASE, None, FakeTransport())


def test_fetch_area_con_transport_falso():
    body = (FIXTURES / "synthetic_viirs_noaa20_nrt.csv").read_text(encoding="utf-8")
    transport = FakeTransport([(200, body)])
    client = _client(transport)
    result = client.fetch_area("VIIRS_NOAA20_NRT", (-62.7, -27.6, -54.2, -19.3), date="2026-09-15")
    assert result.ok is True
    assert result.status_code == 200
    assert result.body.decode().startswith("latitude,")
    assert KEY not in result.url_redacted
    # una sola request, URL con el contrato documentado
    assert len(transport.calls) == 1
    assert "/api/area/csv/" in transport.calls[0]["url"]


def test_fetch_data_availability_endpoint_documentado():
    transport = FakeTransport(
        [(200, "Count,Sensor,StartDate,EndDate\n1,MODIS_NRT,2000-11-01,2026-11-10\n")]
    )
    client = _client(transport)
    result = client.fetch_data_availability("ALL")
    assert "/api/data_availability/csv/" in transport.calls[0]["url"]
    assert transport.calls[0]["url"].endswith("/ALL")
    assert result.ok


def test_fetch_missing_data_pagina_html():
    transport = FakeTransport([(200, "<html>missing data table</html>")])
    client = _client(transport)
    result = client.fetch_missing_data_page()
    assert "/api/missing_data/" in transport.calls[0]["url"]
    assert result.ok


def test_error_de_red_se_reporta_sin_secreto():
    transport = FakeTransport([ConnectionError("boom")])
    client = _client(transport)
    result = client.fetch_area("MODIS_NRT", (-62.7, -27.6, -54.2, -19.3))
    assert result.ok is False
    assert result.error == "ConnectionError"
    assert KEY not in result.url_redacted


def test_repr_y_atributos_no_filtran_clave():
    client = _client(FakeTransport())
    # el cliente no expone la clave como atributo público ni en su repr
    assert not hasattr(client, "map_key")
    assert KEY not in repr(client)
