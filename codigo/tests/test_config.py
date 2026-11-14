"""Pruebas de configuración y seguridad de credenciales."""

from __future__ import annotations

import logging

import pytest

from hotspots.config import Settings
from hotspots.log import RedactingFilter


def test_settings_load_sin_credenciales(clean_env):
    s = Settings.load(env_file=None)
    assert s.has_firms_key is False
    assert s.has_earthdata_token is False
    # El sistema debe poder ejecutarse offline (regla 9 de la misión)
    assert s.base_url.startswith("https://")
    # Misión 005: el rectángulo es de CONSULTA, no el territorio nacional
    assert s.firms_query_bbox == (-62.7, -27.6, -54.2, -19.3)
    assert s.query_bbox_margin_deg == 0.5


def test_bbox_viejo_deprecado(clean_env):
    """El nombre viejo sigue funcionando pero avisa (compatibilidad)."""
    import warnings

    s = Settings.load(env_file=None)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert s.paraguay_bbox == s.firms_query_bbox
        assert s.bbox_margin_deg == s.query_bbox_margin_deg
    assert len(w) == 2 and all(issubclass(x.category, DeprecationWarning) for x in w)


def test_bbox_clave_vieja_en_yaml(tmp_path, monkeypatch):
    """Un sources.yaml viejo (solo area.paraguay_bbox) sigue cargando, con warning."""
    import warnings

    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    monkeypatch.delenv("HOTSPOTS_DATA_DIR", raising=False)
    cfg = tmp_path / "configs"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text(
        "firms_api:\n"
        "  base_url: https://firms.modaps.eosdis.nasa.gov\n"
        "  day_range_min: 1\n"
        "  day_range_max: 5\n"
        "  products: {}\n"
        "area:\n"
        "  paraguay_bbox: [-62.7, -27.6, -54.2, -19.3]\n"
        "  bbox_margin_deg: 0.5\n",
        encoding="utf-8",
    )
    (cfg / "qc.yaml").write_text("{}\n", encoding="utf-8")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        s = Settings.load(env_file=None, config_dir=cfg)
    assert s.firms_query_bbox == (-62.7, -27.6, -54.2, -19.3)
    assert any(issubclass(x.category, DeprecationWarning) for x in w)


def test_bbox_ausente_falla_claro(tmp_path, monkeypatch):
    """Sin ningún bbox: error explícito, no un silencio."""
    from hotspots.config import ConfigError

    monkeypatch.delenv("HOTSPOTS_DATA_DIR", raising=False)
    cfg = tmp_path / "configs"
    cfg.mkdir()
    (cfg / "sources.yaml").write_text(
        "firms_api:\n"
        "  base_url: https://firms.modaps.eosdis.nasa.gov\n"
        "  day_range_min: 1\n"
        "  day_range_max: 5\n"
        "  products: {}\n",
        encoding="utf-8",
    )
    (cfg / "qc.yaml").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="bbox de consulta"):
        Settings.load(env_file=None, config_dir=cfg)


def test_settings_lee_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("FIRMS_MAP_KEY=clave_de_prueba_123\n", encoding="utf-8")
    s = Settings.load(env_file=env_file)
    assert s.has_firms_key is True
    assert s.firms_map_key == "clave_de_prueba_123"


def test_entorno_real_pisa_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "del_entorno")
    env_file = tmp_path / ".env"
    env_file.write_text("FIRMS_MAP_KEY=del_archivo\n", encoding="utf-8")
    s = Settings.load(env_file=env_file)
    assert s.firms_map_key == "del_entorno"


def test_describe_jamas_revela_secretos(monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "SECRETO_SUPER_LARGO_12345")
    monkeypatch.setenv("EARTHDATA_TOKEN", "TOKEN_SECRETO_67890")
    s = Settings.load(env_file=None)
    texto = s.describe()
    assert "SECRETO_SUPER_LARGO_12345" not in texto
    assert "TOKEN_SECRETO_67890" not in texto
    assert "SET" in texto  # reporta disponibilidad, no valores


def test_repr_de_settings_no_contiene_secretos(monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "SECRETO_REPR_999")
    s = Settings.load(env_file=None)
    assert "SECRETO_REPR_999" not in repr(s)
    assert "SECRETO_REPR_999" not in s.describe()


def test_filtro_redaccion_de_logs():
    filtro = RedactingFilter(["CLAVE-ABC-123"])
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="petition with key CLAVE-ABC-123 failed",
        args=(),
        exc_info=None,
    )
    assert filtro.filter(record) is True
    assert "CLAVE-ABC-123" not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


def test_filtro_redaccion_en_handler_real():
    """El filtro aplicado a un handler real redacta el mensaje emitido."""
    import io

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(RedactingFilter(["XYZ-SECRET-1"]))
    logger = logging.getLogger("prueba.filtro")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("mensaje con XYZ-SECRET-1 dentro")
    finally:
        logger.removeHandler(handler)
    salida = buf.getvalue()
    assert "XYZ-SECRET-1" not in salida
    assert "***REDACTED***" in salida


def test_productos_configurados(settings):
    for p in ("MODIS_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "VIIRS_SNPP_NRT"):
        assert p in settings.products
    # S-NPP está inactivo: distribución cesada 2026-11-02 (Fase 0)
    assert settings.products["VIIRS_SNPP_NRT"]["active"] is False
    assert settings.products["MODIS_NRT"]["family"] == "modis"
    assert settings.products["VIIRS_NOAA20_NRT"]["family"] == "viirs"


def test_producto_desconocido_da_error_claro(settings):
    try:
        settings.product_cfg("PRODUCTO_INEXISTENTE")
    except ValueError as exc:
        assert "PRODUCTO_INEXISTENTE" in str(exc)
        assert "MODIS_NRT" in str(exc)  # lista los disponibles
    else:
        raise AssertionError("debía lanzar ValueError")


def test_day_range_validado(settings):
    settings.check_day_range(1)
    settings.check_day_range(5)
    for malo in (0, 6, 10):
        try:
            settings.check_day_range(malo)
        except ValueError:
            pass
        else:
            raise AssertionError(f"day_range={malo} debía rechazarse")
