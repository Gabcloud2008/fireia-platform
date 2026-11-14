"""Pruebas del verificador del piloto (Misión 008, corrección 4.3).

Demuestran que el verificador:

1. Verifica un piloto REAL simulado (transporte falso con respuestas CSV
   válidas) emparejando manifiestos por request_key exacto.
2. Identifica fixtures como ``fixture`` (nunca como real) y los excluye de
   los conteos del piloto — con advertencia explícita.
3. EXCLUYE registros ajenos: fechas fuera de la ventana, y consultas con
   parámetros distintos (detectadas como manifiestos incompatibles).
4. Detecta manifiestos faltantes (piloto no ejecutado).
5. Verifica la correspondencia RAW ↔ procesado y detecta RAW eliminado.
6. Calcula duplicados técnicos con la fórmula corregida
   (sum(rows_valid) − obs distintas), no con rows_raw.
7. La corrección de procedencia: los fixtures ingestedos con
   ``hotspots ingest --fixture`` quedan con ``source_kind='fixture'``
   (antes quedaban mal etiquetados como 'firms_api').

Todo se construye con el pipeline REAL (``run_ingest``) sobre almacenes
temporales: nada se simula por fuera del camino de datos del proyecto.
"""

from __future__ import annotations

import importlib.util
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from hotspots.config import Settings
from hotspots.ingestion.base import FetchResult
from hotspots.ingestion.pipeline import run_ingest
from hotspots.provenance.manifests import request_key
from hotspots.storage.duckdb_store import DuckDBStore

REPO = Path(__file__).resolve().parents[1]
VERIFICADOR = REPO / "mision_007_datos_reales" / "herramientas" / "verificar_piloto.py"
FIXTURES = REPO / "tests" / "fixtures"

DESDE, HASTA = "2026-11-04", "2026-11-10"
PRODUCTOS = ("MODIS_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")
KEY_TEST = "K-TEST-NO-REAL-KEY"


def _cargar_verificador():
    spec = importlib.util.spec_from_file_location("verificar_piloto_m007", VERIFICADOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def verificador():
    return _cargar_verificador()


# ------------------------------------------------------------------ helpers

def _csv_modis(fecha: str, sat: str = "T") -> bytes:
    header = (
        "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_t31,frp,daynight"
    )
    filas = [
        f"-23.50,-58.10,311.7,4.7,1.9,{fecha},1330,{sat},MODIS,83,6.1NRT,290.8,100.9,D",
        f"-22.49,-62.08,326.7,1.0,1.0,{fecha},1233,{sat},MODIS,81,6.1NRT,300.6,17.1,D",
    ]
    return ("\n".join([header, *filas]) + "\n").encode()


def _csv_viirs(fecha: str, sat: str = "1", extra_duplicada: str | None = None) -> bytes:
    header = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_ti5,frp,daynight"
    )
    filas = [f"-23.90,-57.80,340.1,0.9,0.8,{fecha},1331,{sat},VIIRS,n,2.0,298.7,18.3,D"]
    if extra_duplicada:
        # fila idéntica a una de otra consulta (mismo acq_date/hora/coords):
        # duplicado técnico que la deduplicación determinista debe absorber
        filas.append(f"-23.90,-57.80,340.1,0.9,0.8,{extra_duplicada},1331,{sat},VIIRS,n,2.0,298.7,18.3,D")
    return ("\n".join([header, *filas]) + "\n").encode()


class TransportFake:
    """Transporte que responde como la FIRMS Area API según la URL pedida.

    Las respuestas se preparan por (producto, fecha, day_range) — exactamente
    los parámetros que el pipeline pone en la URL.
    """

    def __init__(self, respuestas: dict[tuple[str, str | None, int], bytes]):
        self.respuestas = respuestas
        self.llamadas: list[str] = []

    def get(self, url, *, params=None, headers=None, timeout=60.0):
        self.llamadas.append(url)
        # .../api/area/csv/{KEY}/{PRODUCTO}/{BBOX}/{DAY_RANGE}[/{DATE}]
        partes = url.split("/")
        producto = partes[7]
        day_range = int(partes[9])
        fecha = partes[10] if len(partes) > 10 else None
        body = self.respuestas.get((producto, fecha, day_range))
        if body is None:
            # consulta no prevista por el test: encabezado de la familia
            body = (
                b"latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
                b"satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
            )
        return FetchResult(
            ok=True,
            status_code=200,
            body=body,
            url_redacted=url.replace(KEY_TEST, "{MAP_KEY}"),
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings.load(env={"FIRMS_MAP_KEY": KEY_TEST}, data_dir=tmp_path)


def _construir_piloto(tmp_path: Path, duplicado: bool = False) -> TransportFake:
    """Ejecuta las 6 consultas del piloto (split 5+2) con transporte falso."""
    settings = _settings(tmp_path)
    d0 = date.fromisoformat(DESDE)
    d5 = (d0 + timedelta(days=5)).isoformat()
    respuestas = {}
    for producto in PRODUCTOS:
        if producto == "MODIS_NRT":
            respuestas[(producto, DESDE, 5)] = _csv_modis(DESDE, "T")
            respuestas[(producto, DESDE, 5)] = _csv_modis(DESDE, "T")
            respuestas[(producto, d5, 2)] = _csv_modis(HASTA, "A")
        elif producto == "VIIRS_NOAA20_NRT":
            extra = DESDE if duplicado else None
            respuestas[(producto, DESDE, 5)] = _csv_viirs(DESDE, "1")
            respuestas[(producto, d5, 2)] = _csv_viirs(HASTA, "1", extra_duplicada=extra)
        else:
            respuestas[(producto, DESDE, 5)] = _csv_viirs(DESDE, "2")
            respuestas[(producto, d5, 2)] = _csv_viirs(HASTA, "2")
    transporte = TransportFake(respuestas)
    for producto in PRODUCTOS:
        run_ingest(
            settings, mode="api", product=producto,
            date=DESDE, day_range=5, allow_network=True, transport=transporte,
        )
        run_ingest(
            settings, mode="api", product=producto,
            date=d5, day_range=2, allow_network=True, transport=transporte,
        )
    return transporte


# ------------------------------------------------------------------ 1. real

def test_piloto_real_verificado(verificador, tmp_path):
    _construir_piloto(tmp_path)
    reporte, code = verificador.verificar(DESDE, HASTA, data_dir=tmp_path)

    assert code == 0, reporte["advertencias"]
    assert reporte["clasificacion_datos"] == "real"
    # manifiestos: las 6 consultas esperadas, ninguna faltante/incompleta
    assert reporte["manifiestos"]["esperados"] == 6
    assert reporte["manifiestos"]["encontrados"] == 6
    assert reporte["manifiestos"]["faltantes"] == []
    assert reporte["manifiestos"]["incompletos_o_con_problemas"] == []
    assert reporte["manifiestos"]["incompatibles"] == []
    # observaciones: MODIS 2+2, NOAA20 1+1, NOAA21 1+1 = 8
    assert reporte["observaciones_del_piloto"] == 8
    assert reporte["observaciones_en_ventana_fuera_del_piloto"] == 0
    # duplicados con la fórmula corregida
    assert reporte["productos"]["MODIS_NRT"]["duplicados_tecnicos_absorbidos"] == 0
    # FRP por sensor, nunca entre sensores
    assert reporte["productos"]["MODIS_NRT"]["frp_total_del_sensor_solo_piloto"] > 0
    # días cubiertos: solo DESDE y HASTA tienen filas en estas respuestas
    assert reporte["productos"]["MODIS_NRT"]["por_dia"] == {DESDE: 2, HASTA: 2}
    assert len(reporte["productos"]["MODIS_NRT"]["dias_sin_detecciones"]) == 5


def test_manifiestos_emparejados_por_consulta_exacta(verificador, tmp_path):
    """El emparejamiento es por request_key EXACTO: cada manifiesto tiene
    la fecha y el day_range de SU consulta del split."""
    _construir_piloto(tmp_path)
    reporte, _ = verificador.verificar(DESDE, HASTA, data_dir=tmp_path)
    d5 = (date.fromisoformat(DESDE) + timedelta(days=5)).isoformat()
    for producto in PRODUCTOS:
        mans = reporte["productos"][producto]["manifiestos"]
        assert len(mans) == 2
        por_consulta = {(m["fecha_consulta"], m["day_range"]) for m in mans}
        assert por_consulta == {(DESDE, 5), (d5, 2)}


def test_duplicados_tecnicos_fórmula_corregida(verificador, tmp_path):
    """Una fila repetida entre dos consultas del piloto debe aparecer como
    duplicado técnico absorbido (rows_valid − obs distintas), no como
    cuarentena ni como dato extra."""
    _construir_piloto(tmp_path, duplicado=True)
    reporte, code = verificador.verificar(DESDE, HASTA, data_dir=tmp_path)

    assert code == 0
    # NOAA20: rows_valid = 1 (consulta 1) + 2 (consulta 2, una repetida) = 3
    # observaciones distintas del piloto = 2 → duplicados = 1
    assert reporte["productos"]["VIIRS_NOAA20_NRT"]["duplicados_tecnicos_absorbidos"] == 1
    assert reporte["productos"]["VIIRS_NOAA20_NRT"]["observaciones_del_piloto"] == 2
    # el total del piloto sigue siendo 8 (la repetida se absorbió)
    assert reporte["observaciones_del_piloto"] == 8


# ------------------------------------------------------------------ 2. fixtures

def test_fixtures_identificados_y_excluidos(verificador, tmp_path):
    """Los fixtures se clasifican como 'fixture', se excluyen de los conteos
    del piloto y generan advertencia explícita (corrección 4.4)."""
    settings = Settings.load(env={}, data_dir=tmp_path)
    run_ingest(
        settings, mode="fixture",
        fixture_path=FIXTURES / "synthetic_modis_nrt.csv", product="MODIS_NRT",
    )
    run_ingest(
        settings, mode="fixture",
        fixture_path=FIXTURES / "synthetic_viirs_noaa20_nrt.csv",
        product="VIIRS_NOAA20_NRT",
    )

    # corrección de procedencia (causa raíz de 4.4): los fixtures quedan
    # etiquetados 'fixture', NO 'firms_api'
    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb",
        settings.data_dir / "processed",
    )
    kinds = {r["source_kind"] for r in duck.query("SELECT DISTINCT source_kind FROM observations")}
    assert kinds == {"fixture"}

    # ventana de los fixtures (2026-09-15..21): datos presentes, pero NO son
    # un piloto — clasificación 'fixture' y exclusión de los conteos.
    # (los dos fixtures suman 20 filas válidas: 12 MODIS + 8 VIIRS)
    reporte, code = verificador.verificar("2026-09-15", "2026-09-21", data_dir=tmp_path)
    assert reporte["clasificacion_datos"] == "fixture"
    assert reporte["observaciones_del_piloto"] == 0
    assert reporte["observaciones_en_ventana_fuera_del_piloto"] == 20
    assert code == verificador.EXIT_PROCEDENCIA
    assert any("NO verifica un piloto real" in a for a in reporte["advertencias"])
    # los 6 manifiestos del piloto faltan (el piloto no se ejecutó)
    assert len(reporte["manifiestos"]["faltantes"]) == 6


# ------------------------------------------------------------------ 3. ajenos

def test_registros_ajenos_al_periodo_no_contaminan(verificador, tmp_path):
    """Observaciones FUERA de la ventana del piloto (fixtures de septiembre)
    no entran en ningún conteo del reporte."""
    _construir_piloto(tmp_path)
    # datos ajenos: fixtures con fechas 2026-09-15..21
    settings = _settings(tmp_path)
    run_ingest(
        settings, mode="fixture",
        fixture_path=FIXTURES / "synthetic_modis_nrt.csv", product="MODIS_NRT",
    )

    reporte, code = verificador.verificar(DESDE, HASTA, data_dir=tmp_path)
    assert code == 0
    assert reporte["clasificacion_datos"] == "real"  # en la ventana solo hay real
    assert reporte["observaciones_del_piloto"] == 8
    # los fixtures (17 obs de septiembre) NO aparecen en la ventana
    assert reporte["observaciones_en_ventana_fuera_del_piloto"] == 0
    assert reporte["productos"]["MODIS_NRT"]["por_dia"] == {DESDE: 2, HASTA: 2}


def test_consulta_con_parametros_distintos_es_incompatible(verificador, tmp_path):
    """Una consulta firms_api DENTRO de la ventana pero con parámetros
    distintos a los del split (day_range=1) se detecta como incompatible y
    sus observaciones quedan fuera de los conteos del piloto."""
    _construir_piloto(tmp_path)
    settings = _settings(tmp_path)
    ajena = TransportFake({("MODIS_NRT", "2026-11-05", 1): _csv_modis("2026-11-05")})
    run_ingest(
        settings, mode="api", product="MODIS_NRT",
        date="2026-11-05", day_range=1, allow_network=True, transport=ajena,
    )

    reporte, code = verificador.verificar(DESDE, HASTA, data_dir=tmp_path)
    # el piloto sigue verificable…
    assert reporte["manifiestos"]["encontrados"] == 6
    assert reporte["productos"]["MODIS_NRT"]["observaciones_del_piloto"] == 4
    # …pero la consulta ajena se reporta como incompatible…
    assert len(reporte["manifiestos"]["incompatibles"]) == 1
    incompat = reporte["manifiestos"]["incompatibles"][0]
    assert incompat["producto"] == "MODIS_NRT"
    assert incompat["fecha_consulta"] == "2026-11-05"
    # …y sus observaciones NO entran en los conteos del piloto
    assert reporte["productos"]["MODIS_NRT"]["observaciones_en_ventana_fuera_del_piloto"] == 2
    assert any(
        "incompatible" in a or "distintos de los esperados" in a
        for a in reporte["advertencias"]
    )


# ------------------------------------------------------------------ 4. faltantes

def test_piloto_no_ejecutado_manifiestos_faltantes(verificador, tmp_path):
    """Almacén vacío: 6 manifiestos faltantes, ventana vacía, código 3."""
    reporte, code = verificador.verificar(DESDE, HASTA, data_dir=tmp_path)
    assert code == verificador.EXIT_PROCEDENCIA
    assert reporte["clasificacion_datos"] == "vacio"
    assert len(reporte["manifiestos"]["faltantes"]) == 6
    assert reporte["observaciones_del_piloto"] == 0
    assert any("SIN manifiesto" in a for a in reporte["advertencias"])


# ------------------------------------------------------------------ 5. RAW

def test_correspondencia_raw_procesado_ok(verificador, tmp_path):
    _construir_piloto(tmp_path)
    reporte, _ = verificador.verificar(DESDE, HASTA, data_dir=tmp_path)
    for producto in PRODUCTOS:
        for m in reporte["productos"][producto]["manifiestos"]:
            assert m["problemas_raw_procesado"] == [], (producto, m)


def test_raw_eliminado_detectado(verificador, tmp_path):
    """Si el RAW de un manifiesto del piloto desaparece, el verificador lo
    reporta y NO da el piloto por verificado."""
    _construir_piloto(tmp_path)
    raws = sorted((tmp_path / "raw" / "firms").rglob("*.csv"))
    assert raws, "el piloto simulado debe haber guardado RAWs"
    os.chmod(raws[0], 0o644)
    raws[0].unlink()

    reporte, code = verificador.verificar(DESDE, HASTA, data_dir=tmp_path)
    assert code == verificador.EXIT_PROCEDENCIA
    incompletos = reporte["manifiestos"]["incompletos_o_con_problemas"]
    assert any("RAW inexistente" in p for m in incompletos for p in m["problemas"])
    assert any("RAW" in a for a in reporte["advertencias"])


# ------------------------------------------------------------------ 6. helper

def test_consultas_esperadas_split_5mas2(verificador):
    """Las consultas esperadas cubren exactamente los 7 días: 5+2, sin
    huecos ni solapamientos, para cada producto."""
    settings = Settings.load(env={}, data_dir=None)
    esperadas = verificador.consultas_esperadas(settings, DESDE)
    assert len(esperadas) == 6
    for producto in PRODUCTOS:
        consultas = sorted(
            (e for e in esperadas if e["producto"] == producto),
            key=lambda e: e["fecha_consulta"],
        )
        assert len(consultas) == 2
        assert consultas[0]["day_range"] == 5
        assert consultas[1]["day_range"] == 2
        # continuidad: la segunda consulta empieza donde termina la primera
        assert consultas[1]["cubre_desde"] == (
            date.fromisoformat(consultas[0]["cubre_hasta"]) + timedelta(days=1)
        ).isoformat()
        # cobertura total = ventana del piloto
        assert consultas[0]["cubre_desde"] == DESDE
        assert consultas[1]["cubre_hasta"] == HASTA


# --------------------------------------------- 7. M011-C §3: RAW vacío heredado

def _inyectar_fallido_heredado(tmp_path: Path, settings: Settings) -> str:
    """Reproduce el artefacto heredado de M010 (manifiesto 26184c5d): una
    consulta del piloto con download_failed y un artefacto raw_response de
    0 bytes — SIN borrar nada: es evidencia histórica que el verificador
    debe identificar y clasificar, no interpretar."""
    from hotspots.provenance.manifests import Artifact, Manifest, ManifestStore

    bbox = [float(x) for x in settings.firms_query_bbox]
    params = {
        "bbox": bbox,
        "bbox_rol": "firms_query_bbox (rectángulo de consulta; no es territorio)",
        "day_range": 5,
        "date": DESDE,
        "contract": "area_csv_v1",
    }
    clave = request_key("firms", "firms_api", "MODIS_NRT", params)
    sha_vacio = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    vacio = tmp_path / "raw" / "firms" / "MODIS_NRT" / "2026" / f"{sha_vacio}.csv"
    vacio.parent.mkdir(parents=True, exist_ok=True)
    vacio.write_bytes(b"")
    manifiesto = Manifest(
        provider="firms",
        source="firms_api",
        product="MODIS_NRT",
        request_key=clave,
        result_state="download_failed",
        sensor="MODIS",
        satellite_scope=["Terra", "Aqua"],
        acquisition_period={"from": DESDE, "to": "2026-11-08"},
        counts={"rows_raw": 0, "rows_valid": 0, "rows_quarantined": 0},
        run_id="heredado-m010",
        created_at_utc="2026-11-11T16:23:46Z",
        processing_state="failed",
        notes=[
            "url=https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}"
            "/MODIS_NRT/-62.7,-27.6,-54.2,-19.3/5/2026-11-04",
            "status=None",
        ],
        artifacts=[
            Artifact(path=str(vacio), sha256=sha_vacio, size=0, role="raw_response")
        ],
    ).finalize()
    ManifestStore(tmp_path / "manifests").write(manifiesto)
    return manifiesto.manifest_id


def test_raw_vacio_de_adquisicion_fallida_identificado(verificador, tmp_path):
    """M011-C §3: el verificador identifica el artefacto de 0 bytes como
    'artefacto_vacio_de_adquisicion_fallida', lo lista en el reporte con su
    manifiesto original (trazabilidad preservada) y NO lo interpreta como
    observación, CSV válido ni día sin detecciones."""
    settings = _settings(tmp_path)
    # piloto completo EXCEPTO la consulta MODIS 5d (la fallida heredada)
    d0 = date.fromisoformat(DESDE)
    d5 = (d0 + timedelta(days=5)).isoformat()
    respuestas = {}
    for producto in PRODUCTOS:
        if producto == "MODIS_NRT":
            respuestas[(producto, d5, 2)] = _csv_modis(HASTA, "A")
        elif producto == "VIIRS_NOAA20_NRT":
            respuestas[(producto, DESDE, 5)] = _csv_viirs(DESDE, "1")
            respuestas[(producto, d5, 2)] = _csv_viirs(HASTA, "1")
        else:
            respuestas[(producto, DESDE, 5)] = _csv_viirs(DESDE, "2")
            respuestas[(producto, d5, 2)] = _csv_viirs(HASTA, "2")
    transporte = TransportFake(respuestas)
    for producto in PRODUCTOS:
        consultas = [(DESDE, 5)] if producto == "MODIS_NRT" else [(DESDE, 5), (d5, 2)]
        for fecha, rango in consultas:
            if producto == "MODIS_NRT" and (fecha, rango) == (DESDE, 5):
                continue  # esta es la heredada fallida
            run_ingest(
                settings, mode="api", product=producto,
                date=fecha, day_range=rango, allow_network=True,
                transport=transporte,
            )
    mid = _inyectar_fallido_heredado(tmp_path, settings)

    reporte, code = verificador.verificar(DESDE, HASTA, data_dir=tmp_path)

    # la evidencia histórica sigue en disco (no se borró)
    sha_vacio = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert (tmp_path / "raw" / "firms" / "MODIS_NRT" / "2026" / f"{sha_vacio}.csv").exists()

    # identificada y clasificada, con trazabilidad del manifiesto original
    vacios = reporte["manifiestos"]["artefactos_raw_vacios"]
    assert len(vacios) == 1
    assert vacios[0]["manifest_id"] == mid
    assert vacios[0]["estado_manifiesto"] == "download_failed"
    assert vacios[0]["clasificacion"] == "artefacto_vacio_de_adquisicion_fallida"
    assert "no es observación" in vacios[0]["nota"].replace("no es\n", "no es ")
    # el manifiesto fallido NO se cuenta como exitoso: código de procedencia
    assert code == verificador.EXIT_PROCEDENCIA
    incompletos = reporte["manifiestos"]["incompletos_o_con_problemas"]
    assert any(m["manifest_id"] == mid for m in incompletos)
    assert any("artefacto RAW vacío" in p for m in incompletos for p in m["problemas"])
    assert any("artefacto(s) RAW de 0 bytes" in a for a in reporte["advertencias"])


def test_fallo_de_adquisicion_no_es_dia_sin_detecciones(verificador, tmp_path):
    """M011-C §3: los días cubiertos SOLO por la adquisición fallida van a
    'dias_sin_cobertura_exitosa' (estado de cobertura), JAMÁS a
    'dias_sin_detecciones' (que exige adquisición exitosa)."""
    settings = _settings(tmp_path)
    d0 = date.fromisoformat(DESDE)
    d5 = (d0 + timedelta(days=5)).isoformat()
    respuestas = {}
    for producto in PRODUCTOS:
        if producto == "MODIS_NRT":
            respuestas[(producto, d5, 2)] = _csv_modis(HASTA, "A")
        elif producto == "VIIRS_NOAA20_NRT":
            respuestas[(producto, DESDE, 5)] = _csv_viirs(DESDE, "1")
            respuestas[(producto, d5, 2)] = _csv_viirs(HASTA, "1")
        else:
            respuestas[(producto, DESDE, 5)] = _csv_viirs(DESDE, "2")
            respuestas[(producto, d5, 2)] = _csv_viirs(HASTA, "2")
    transporte = TransportFake(respuestas)
    for producto in PRODUCTOS:
        consultas = [(DESDE, 5), (d5, 2)]
        for fecha, rango in consultas:
            if producto == "MODIS_NRT" and (fecha, rango) == (DESDE, 5):
                continue
            run_ingest(
                settings, mode="api", product=producto,
                date=fecha, day_range=rango, allow_network=True,
                transport=transporte,
            )
    _inyectar_fallido_heredado(tmp_path, settings)

    reporte, _ = verificador.verificar(DESDE, HASTA, data_dir=tmp_path)
    modis = reporte["productos"]["MODIS_NRT"]
    dias_04_a_08 = ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08"]
    # los días de la consulta fallida: SIN cobertura exitosa...
    assert modis["dias_sin_cobertura_exitosa"] == dias_04_a_08
    # ...y NINGUNO cuenta como día sin detecciones
    for d in dias_04_a_08:
        assert d not in modis["dias_sin_detecciones"], (
            f"{d}: un fallo de adquisición NO es un día sin detecciones"
        )
    # los días con adquisición exitosa se evalúan normalmente: la consulta
    # 2d (09-10) trajo detecciones SOLO el 10 → el 09 es un día sin
    # detecciones LEGÍTIMO (cubierto y sin filas), el resto no aparece
    assert modis["dias_sin_detecciones"] == ["2026-11-09"]
    # los otros productos, con cobertura completa, no reportan huecos
    for producto in ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"):
        assert reporte["productos"][producto]["dias_sin_cobertura_exitosa"] == []
    assert any("SIN adquisición exitosa" in a for a in reporte["advertencias"])
