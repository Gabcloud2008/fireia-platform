"""Pruebas de almacenamiento: RAW inmutable, manifiestos y GeoParquet."""

from __future__ import annotations

import json
import struct

import pyarrow.parquet as pq

from hotspots.models import wkb_point
from hotspots.normalization.firms_csv import parse_firms_csv
from hotspots.provenance.manifests import Artifact, Manifest, ManifestStore, request_key
from hotspots.storage.parquet_store import ParquetStore
from hotspots.storage.raw import RawStore, sha256_bytes
from tests.conftest import FIXTURES


# --------------------------------------------------------------------- RAW
def test_raw_content_addressed_y_write_once(tmp_path):
    store = RawStore(tmp_path / "raw")
    a = store.store(b"contenido-uno", provider="firms", product="MODIS_NRT", year="2026")
    b = store.store(b"contenido-uno", provider="firms", product="MODIS_NRT", year="2026")
    assert a.path == b.path
    assert b.already_existed is True
    assert a.sha256 == sha256_bytes(b"contenido-uno")
    assert a.path.name == f"{a.sha256}.csv"
    # write-once: el archivo no se duplica
    archivos = list((tmp_path / "raw").rglob("*.csv"))
    assert len(archivos) == 1


def test_raw_contenido_distinto_archivo_distinto(tmp_path):
    store = RawStore(tmp_path / "raw")
    a = store.store(b"uno", provider="firms", product="P", year="2026")
    b = store.store(b"dos", provider="firms", product="P", year="2026")
    assert a.path != b.path
    assert a.sha256 != b.sha256


def test_raw_solo_lectura(tmp_path):
    store = RawStore(tmp_path / "raw")
    a = store.store(b"datos", provider="firms", product="P", year="2026")
    modo = a.path.stat().st_mode & 0o777
    assert modo == 0o444  # r--r--r--: inmutabilidad salvaguardada


# --------------------------------------------------------------- manifiestos
def test_manifest_roundtrip_y_indice(tmp_path):
    store = ManifestStore(tmp_path / "manifests")
    m = Manifest(
        provider="firms",
        source="fixture",
        product="MODIS_NRT",
        request_key=request_key("firms", "fixture", "MODIS_NRT", {"x": 1}),
        result_state="success_with_detections",
        sensor="MODIS",
        satellite_scope=["Terra", "Aqua"],
        acquisition_period={"from": "", "to": ""},
        counts={"rows_raw": 12, "rows_valid": 12, "rows_quarantined": 0},
        artifacts=[Artifact(path="/x.csv", sha256="ab" * 32, size=10, role="raw_csv")],
        run_id="r1",
        created_at_utc="2026-11-11T00:00:00Z",
    )
    path = store.write(m)
    assert path.exists()
    leido = store.load(m.manifest_id)
    assert leido is not None
    assert leido.product == "MODIS_NRT"
    assert leido.counts["rows_valid"] == 12
    assert leido.artifacts[0].sha256 == "ab" * 32
    entries = store.list_entries()
    assert len(entries) == 1
    assert entries[0]["manifest_id"] == m.manifest_id


def test_request_key_determinista_y_sensible():
    k1 = request_key("firms", "firms_api", "MODIS_NRT", {"date": "2026-09-15", "day_range": 1})
    k2 = request_key("firms", "firms_api", "MODIS_NRT", {"day_range": 1, "date": "2026-09-15"})
    k3 = request_key("firms", "firms_api", "MODIS_NRT", {"date": "2026-09-16", "day_range": 1})
    assert k1 == k2  # orden de claves no importa (canónico)
    assert k1 != k3  # parámetros distintos => clave distinta


def test_find_by_request_key(tmp_path):
    store = ManifestStore(tmp_path / "manifests")
    key = request_key("firms", "fixture", "MODIS_NRT", {"fixture_sha256": "aa"})
    m = Manifest(
        provider="firms",
        source="fixture",
        product="MODIS_NRT",
        request_key=key,
        result_state="success_with_detections",
        sensor="MODIS",
        satellite_scope=[],
        acquisition_period={},
        counts={},
        run_id="r1",
        created_at_utc="2026-11-11T00:00:00Z",
    )
    store.write(m)
    assert store.find_by_request_key(key) is not None
    assert store.find_by_request_key("clave-inexistente") is None


# ------------------------------------------------------------------ GeoParquet
def _records(settings):
    return parse_firms_csv(
        (FIXTURES / "synthetic_modis_nrt.csv").read_text(encoding="utf-8"),
        product="MODIS_NRT",
        settings=settings,
        run_id="r",
        manifest_id="m",
        ingested_at_utc="2026-11-11T00:00:00Z",
    ).records


def test_parquet_geo_metadata_y_wkb(tmp_path, settings):
    store = ParquetStore(tmp_path / "processed")
    path = store.append_observations(
        _records(settings), product="MODIS_NRT", year="2026", run_id="r1"
    )
    assert path is not None and path.exists()
    schema = pq.read_schema(path)
    geo = json.loads(schema.metadata[b"geo"])
    assert geo["primary_column"] == "geometry"
    assert geo["columns"]["geometry"]["encoding"] == "WKB"
    assert geo["columns"]["geometry"]["geometry_types"] == ["Point"]
    # CRS implícito: sin 'crs' la spec GeoParquet 1.0 define OGC:CRS84 (lon/lat)
    assert "crs" not in geo["columns"]["geometry"]
    # bbox coherente con los datos
    assert geo["columns"]["geometry"]["bbox"][0] == min(r.longitude for r in _records(settings))


def test_wkb_point_roundtrip():
    lon, lat = -57.5759, -25.2637
    wkb = wkb_point(lon, lat)
    byte_order, geom_type, x, y = struct.unpack("<BIdd", wkb)
    assert byte_order == 1 and geom_type == 1
    assert (x, y) == (lon, lat)


def test_parquet_dos_corridas_dos_partes(tmp_path, settings):
    store = ParquetStore(tmp_path / "processed")
    recs = _records(settings)
    p1 = store.append_observations(recs, product="MODIS_NRT", year="2026", run_id="run-a")
    p2 = store.append_observations(recs, product="MODIS_NRT", year="2026", run_id="run-b")
    assert p1 != p2
    t1 = pq.read_table(p1)
    t2 = pq.read_table(p2)
    assert t1.num_rows == t2.num_rows == 12


def test_parquet_cuarentena(tmp_path, settings):
    store = ParquetStore(tmp_path / "processed")
    out = parse_firms_csv(
        (FIXTURES / "synthetic_invalid_rows.csv").read_text(encoding="utf-8"),
        product="MODIS_NRT",
        settings=settings,
        run_id="r",
        manifest_id="m",
        ingested_at_utc="2026-11-11T00:00:00Z",
    )
    path = store.append_quarantine(out.quarantined, run_id="r")
    assert path is not None
    t = pq.read_table(path)
    assert t.num_rows == 7
    # las filas rechazadas conservan sus columnas originales
    assert "latitude" in t.column_names
    assert "errors" in t.column_names


# --------------------------------------------- casos límite (Misión 008, §5)

def test_raw_ignora_tmp_residual_de_escritura_interrumpida(tmp_path):
    """Una escritura interrumpida deja un .tmp: el almacén lo ignora y una
    reejecución con el mismo contenido completa el write-once sin corromperse."""
    from hotspots.storage.raw import RawStore

    store = RawStore(tmp_path)
    # simulamos la interrupción: quedó solo el .tmp (sin os.replace)
    carpeta = tmp_path / "firms" / "MODIS_NRT" / "2026"
    carpeta.mkdir(parents=True)
    (carpeta / "abc.csv.tmp").write_bytes(b"latitude,longitude\n-23.5,-58.1\n")

    # el conteo de datos ignora el tmp…
    assert store.count() == 0
    # …y una ingesta del mismo contenido crea el archivo definitivo
    data = b"latitude,longitude\n-23.5,-58.1\n"
    stored = store.store(data, provider="firms", product="MODIS_NRT", year="2026")
    assert stored.already_existed is False
    assert store.count() == 1
    # el tmp residual NO cuenta ni rompe la verificación de bytes
    assert (carpeta / "abc.csv.tmp").exists()  # queda como basura inerte
    assert stored.path.read_bytes() == data


def test_raw_reemplazo_atomico_no_pisa_contenido_previo(tmp_path):
    """Si el destino ya existe (write-once), store() no lo toca: ni tamaño ni
    permisos cambian — la interrupción/reejecución es segura por diseño."""
    import os

    from hotspots.storage.raw import RawStore

    store = RawStore(tmp_path)
    data = b"latitude,longitude\n-23.5,-58.1\n"
    first = store.store(data, provider="firms", product="MODIS_NRT", year="2026")
    mtime_prev = first.path.stat().st_mtime_ns
    # reejecución con contenido idéntico
    second = store.store(data, provider="firms", product="MODIS_NRT", year="2026")
    assert second.already_existed is True
    assert second.path == first.path
    assert first.path.stat().st_mtime_ns == mtime_prev  # no se reescribió
    assert oct(os.stat(first.path).st_mode & 0o777) == "0o444"  # solo lectura
