"""Pruebas del transporte HTTP endurecido (Misión 004, etapa 3).

Sin red y sin esperas reales: ``requests.get`` se monkeypatchea y el sleep
es un grabador.
"""

from __future__ import annotations

import pytest

from hotspots.ingestion.base import RequestsTransport


class _Resp:
    def __init__(self, status, body=b"", headers=None):
        self.status_code = status
        self.content = body
        self.headers = headers or {}


class _FakeRequests:
    """Secuencia de respuestas/errores programados por test."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class _SleepRecorder:
    def __init__(self, clock=None):
        self.waits = []
        self.clock = clock

    def __call__(self, s):
        self.waits.append(s)
        if self.clock is not None:
            self.clock.now += s  # dormir avanza el reloj, como en la vida real


class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture()
def clock():
    return _FakeClock()


@pytest.fixture()
def sleep_rec(clock):
    return _SleepRecorder(clock=clock)


def _transport(sleep_rec, clock, **kw):
    return RequestsTransport(redact_secrets=["SECRETKEY"], sleep=sleep_rec, clock=clock, **kw)


def test_exito_a_la_primera(monkeypatch, sleep_rec, clock):
    fake = _FakeRequests([_Resp(200, b"hola")])
    monkeypatch.setattr("requests.get", fake.get)
    t = _transport(sleep_rec, clock)
    r = t.get("https://x/SECRETKEY/api")
    assert r.ok and r.body == b"hola"
    assert r.url_redacted == "https://x/{MAP_KEY}/api"
    assert sleep_rec.waits == []  # sin reintentos, sin esperas


def test_reintenta_5xx_y_triunfa(monkeypatch, sleep_rec, clock):
    fake = _FakeRequests([_Resp(503), _Resp(502), _Resp(200, b"ok")])
    monkeypatch.setattr("requests.get", fake.get)
    t = _transport(sleep_rec, clock)
    r = t.get("https://x/")
    assert r.ok
    assert len(fake.calls) == 3
    # backoff: 1.5 * 2^0 = 1.5 ; 1.5 * 2^1 = 3.0
    assert sleep_rec.waits == [1.5, 3.0]


def test_agota_reintentos_y_reporta(monkeypatch, sleep_rec, clock):
    fake = _FakeRequests([_Resp(500)] * 4)
    monkeypatch.setattr("requests.get", fake.get)
    t = _transport(sleep_rec, clock)
    r = t.get("https://x/")
    assert not r.ok
    assert r.status_code == 500
    assert len(fake.calls) == 4  # 1 + 3 reintentos
    assert len(sleep_rec.waits) == 3


def test_429_respeta_retry_after(monkeypatch, sleep_rec, clock):
    fake = _FakeRequests(
        [_Resp(429, headers={"Retry-After": "7"}), _Resp(200, b"ok")]
    )
    monkeypatch.setattr("requests.get", fake.get)
    t = _transport(sleep_rec, clock)
    r = t.get("https://x/")
    assert r.ok
    assert sleep_rec.waits == [7.0]  # el Retry-After manda


def test_no_reintenta_401(monkeypatch, sleep_rec, clock):
    fake = _FakeRequests([_Resp(401)])
    monkeypatch.setattr("requests.get", fake.get)
    t = _transport(sleep_rec, clock)
    r = t.get("https://x/")
    assert not r.ok and r.status_code == 401
    assert len(fake.calls) == 1
    assert sleep_rec.waits == []


def test_reintenta_error_de_red(monkeypatch, sleep_rec, clock):
    import requests as real_requests

    fake = _FakeRequests(
        [real_requests.ConnectionError("boom"), _Resp(200, b"ok")]
    )
    monkeypatch.setattr("requests.get", fake.get)
    t = _transport(sleep_rec, clock)
    r = t.get("https://x/")
    assert r.ok
    assert len(fake.calls) == 2


def test_error_de_red_agotado_sin_status(monkeypatch, sleep_rec, clock):
    import requests as real_requests

    fake = _FakeRequests(
        [real_requests.Timeout("t")] * 4
    )
    monkeypatch.setattr("requests.get", fake.get)
    t = _transport(sleep_rec, clock)
    r = t.get("https://x/")
    assert not r.ok
    assert r.status_code is None
    assert r.error == "Timeout"


def test_rate_limit_min_interval(monkeypatch, sleep_rec, clock):
    fake = _FakeRequests([_Resp(200, b"a"), _Resp(200, b"b")])
    monkeypatch.setattr("requests.get", fake.get)
    t = _transport(sleep_rec, clock, min_interval_s=2.0)
    t.get("https://x/")
    clock.now = 0.5  # solo pasaron 0.5 s: debe esperar 1.5
    t.get("https://x/")
    assert sleep_rec.waits == [1.5]
    assert len(fake.calls) == 2


def test_backoff_cap(monkeypatch, sleep_rec, clock):
    fake = _FakeRequests(
        [_Resp(500), _Resp(500), _Resp(500), _Resp(200, b"ok")]
    )
    monkeypatch.setattr("requests.get", fake.get)
    t = _transport(sleep_rec, clock, backoff_base=10.0, backoff_cap=15.0)
    r = t.get("https://x/")
    assert r.ok
    # 10, 20->cap 15, 40->cap 15
    assert sleep_rec.waits == [10.0, 15.0, 15.0]
