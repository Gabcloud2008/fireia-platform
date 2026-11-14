"""Pruebas del adaptador de base real (Misión A de la finalización).

Estrategia:

1. **Mini-base sintética de prueba** (``real_base_mini``): estructura idéntica
   a ``base_real_v1`` (manifiesto + particiones Hive) construida en tmp para
   probar verify/build/query/aislamiento sin depender de los 232 MB reales.
2. **Integración contra la base real** (skipif si no existe): conciliación de
   los 2.691.999 registros del manifiesto M014.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hotspots.storage.real_base import (
    ADAPTER_VERSION,
    MANIFEST_NAME,
    PRODUCTOS_REALES,
    RealBaseAdapter,
    RealBaseError,
    _normalizar_depto,
)

REAL_BASE = Path(__file__).resolve().parents[2] / "data" / "PROCESADA" / "base_real_v1"


# ------------------------------------------------------------------ fixtures
def _escribir_mini_base(root: Path, *, filas_sp: int = 3, filas_nrt: int = 2) -> Path:
    """Construye una mini base real válida con manifiesto conciliado."""
    base = root / "base_real_v1"
    src = root / "SATELLITE_DATA"
    src.mkdir(parents=True)
    schema = pa.schema(
        [
            ("obs_id", pa.string()),
            ("source_file", pa.string()),
            ("source_sha256", pa.string()),
            ("latitude", pa.float64()),
            ("longitude", pa.float64()),
            ("acq_date", pa.string()),
            ("acq_time", pa.int64()),
            ("acq_datetime_utc", pa.timestamp("ns")),
            ("satellite", pa.string()),
            ("satellite_name", pa.string()),
            ("sensor", pa.dictionary(pa.int8(), pa.string())),
            ("instrument", pa.dictionary(pa.int8(), pa.string())),
            ("confidence", pa.int64()),
            ("confidence_band", pa.string()),
            ("frp", pa.float64()),
            ("brightness", pa.float64()),
            ("bright_t31", pa.float64()),
            ("scan", pa.float64()),
            ("track", pa.float64()),
            ("daynight", pa.dictionary(pa.int8(), pa.string())),
            ("version", pa.string()),
            ("es_fuente_industrial", pa.int8()),
            ("dentro_pais", pa.bool_()),
            ("departamento", pa.string()),
        ]
    )

    def _ts(fecha: str):
        return pa.scalar(f"{fecha}T12:00:00").cast(pa.timestamp("ns")).as_py()

    def fila(i: int, producto: str, fecha: str) -> dict:
        sensor = "MODIS" if producto.startswith("MODIS") else "VIIRS"
        return {
            "obs_id": f"{producto}-{i}",
            "source_file": f"{producto.lower()}_mini.csv.gz",
            "source_sha256": "0" * 64,
            "latitude": -23.5 + i * 0.01,
            "longitude": -58.0 + i * 0.01,
            "acq_date": fecha,
            "acq_time": 1200 + i,
            "acq_datetime_utc": _ts(fecha),
            "satellite": "Terra" if sensor == "MODIS" else "N20",
            "satellite_name": "Terra" if sensor == "MODIS" else "NOAA-20",
            "sensor": sensor,
            "instrument": sensor,
            "confidence": 80 if sensor == "MODIS" else 7,
            "confidence_band": "alta",
            "frp": 10.5 + i,
            "brightness": 320.0,
            "bright_t31": 290.0,
            "scan": 1.0,
            "track": 1.0,
            "daynight": "D",
            "version": "6.1",
            "es_fuente_industrial": 0,
            "dentro_pais": True,
            "departamento": "BOQUERON",
        }

    particiones = {
        ("MODIS_SP", 2020): [fila(i, "MODIS_SP", "2020-09-10") for i in range(filas_sp)],
        ("VIIRS_NOAA20_NRT", 2021): [
            fila(i, "VIIRS_NOAA20_NRT", "2021-01-05") for i in range(filas_nrt)
        ],
    }
    por_producto: dict[str, dict] = {}
    total = 0
    for (producto, anio), rows in particiones.items():
        destino = base / "observations" / f"product={producto}" / f"year={anio}"
        destino.mkdir(parents=True)
        tabla = pa.Table.from_pylist(rows, schema=schema)
        pq.write_table(tabla, destino / f"part-{producto}-{anio}.parquet")
        info = por_producto.setdefault(
            producto,
            {"filas": 0, "fecha_min": "9999-99-99", "fecha_max": "0000-00-00"},
        )
        info["filas"] += len(rows)
        info["fecha_min"] = min(info["fecha_min"], min(r["acq_date"] for r in rows))
        info["fecha_max"] = max(info["fecha_max"], max(r["acq_date"] for r in rows))
        total += len(rows)
        # fuente correspondiente
        fuente = src / f"{producto.lower()}_mini.csv.gz"
        fuente.write_bytes(b"contenido-mini-" + producto.encode())
    manifiesto = {
        "schema_version": "base_real_v1",
        "creado_en_utc": "2026-11-13T00:00:00Z",
        "descripcion": "mini base de prueba",
        "fuentes": {
            f"{p.lower()}_mini.csv.gz": {
                "sha256": _sha_bytes((src / f"{p.lower()}_mini.csv.gz").read_bytes()),
                "bytes": len((src / f"{p.lower()}_mini.csv.gz").read_bytes()),
                "producto": p,
            }
            for p in por_producto
        },
        "conteos": {
            "archivos_fuente": len(por_producto),
            "filas_raw": total,
            "filas_base_final": total,
            "cuarentena_total": 0,
            "dedup_exactas": 0,
            "dedup_nrt_sobre_sp": 0,
            "filas_validas_qc": total,
            "filas_dedup_eliminadas": 0,
        },
        "por_producto": por_producto,
    }
    texto = json.dumps(manifiesto, ensure_ascii=False, indent=1)
    (base / MANIFEST_NAME).write_text(texto, encoding="utf-8")
    return base


def _sha_bytes(b: bytes) -> str:
    import hashlib

    return hashlib.sha256(b).hexdigest()


def _adapter(base: Path, sources: Path) -> RealBaseAdapter:
    return RealBaseAdapter(
        base_dir=base, sources_dir=sources, duckdb_path=base.parent / "mini.duckdb"
    )


@pytest.fixture()
def mini_base(tmp_path: Path) -> tuple[Path, Path]:
    base = _escribir_mini_base(tmp_path)
    return base, tmp_path / "SATELLITE_DATA"


# ------------------------------------------------------------------ aislamiento
def test_rechaza_rutas_de_fixtures(tmp_path: Path):
    """El adaptador jamás acepta rutas de fixtures como base productiva."""
    (tmp_path / "processed").mkdir()
    with pytest.raises(RealBaseError, match="aislamiento"):
        RealBaseAdapter(base_dir=tmp_path / "processed")
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    with pytest.raises(RealBaseError, match="aislamiento"):
        RealBaseAdapter(base_dir=tmp_path / "tests" / "fixtures")


def test_rechaza_directorio_sin_manifiesto(tmp_path: Path):
    (tmp_path / "base_sin_manifiesto").mkdir()
    with pytest.raises(RealBaseError, match="manifiesto"):
        RealBaseAdapter(base_dir=tmp_path / "base_sin_manifiesto")


# ------------------------------------------------------------------ verify
def test_verify_ok_en_mini_base(mini_base):
    base, sources = mini_base
    adapter = _adapter(base, sources)
    rep = adapter.verify(check_hashes=True)
    assert rep.ok, rep.problemas
    assert rep.fuentes_totales == 2
    assert rep.fuentes_hash_ok == 2
    assert rep.filas_esperadas == rep.filas_reales == 5
    assert rep.particiones == 2


def test_verify_detecta_conteo_divergente(mini_base):
    base, sources = mini_base
    man = json.loads((base / MANIFEST_NAME).read_text(encoding="utf-8"))
    man["conteos"]["filas_base_final"] = 4  # saboteado
    (base / MANIFEST_NAME).write_text(json.dumps(man), encoding="utf-8")
    adapter = _adapter(base, sources)
    rep = adapter.verify(check_hashes=False)
    assert not rep.ok
    assert any("total divergente" in p for p in rep.problemas)


def test_verify_detecta_hash_divergente(mini_base):
    base, sources = mini_base
    # sabotea una fuente: mismo tamaño, otro contenido → falla el SHA-256
    fuente = next(s for s in sources.rglob("*_mini.csv.gz"))
    contenido = fuente.read_bytes()
    fuente.write_bytes(contenido[:-1] + bytes([contenido[-1] ^ 0xFF]))
    adapter = _adapter(base, sources)
    rep = adapter.verify(check_hashes=True)
    assert not rep.ok
    assert any("SHA-256 divergente" in p for p in rep.problemas)


# ------------------------------------------------------------------ duckdb + queries
def test_build_duckdb_y_queries(mini_base):
    base, sources = mini_base
    duck = base.parent / "mini.duckdb"
    adapter = RealBaseAdapter(base_dir=base, sources_dir=sources, duckdb_path=duck)
    meta = adapter.build_duckdb(force=True)
    assert meta["filas"] == 5
    assert meta["source_kind"] == "real"
    assert meta["adapter_version"] == ADAPTER_VERSION
    # meta legible y reutilizable sin reconstruir
    meta2 = adapter.build_duckdb(force=False)
    assert meta2 == meta
    assert adapter.read_build_meta()["filas"] == 5

    # queries
    assert adapter.count_obs() == 5
    assert adapter.count_obs(producto="MODIS_SP") == 3
    assert adapter.count_obs(sensor="VIIRS") == 2
    assert adapter.count_obs(departamento="Boquerón") == 5  # normalización acentos
    rows = adapter.query_obs(producto="MODIS_SP", limite=10)
    assert len(rows) == 3
    assert all(r["source_kind"] == "real" for r in rows)
    # filtro temporal
    assert adapter.count_obs(fecha_desde="2021-01-01") == 2
    assert adapter.count_obs(anio=2020) == 3
    # bbox
    assert adapter.count_obs(bbox=(-59.0, -24.0, -57.0, -23.0)) >= 1
    # producto inválido rechazado
    with pytest.raises(RealBaseError):
        adapter.count_obs(producto="PRODUCTO_INEXISTENTE")


def test_stats_y_cobertura(mini_base):
    base, sources = mini_base
    adapter = _adapter(base, sources)
    adapter.build_duckdb(force=True)
    st = adapter.stats()
    assert st["total"] == 5
    assert st["source_kind"] == "real"
    assert {p["product"] for p in st["por_producto"]} == {"MODIS_SP", "VIIRS_NOAA20_NRT"}
    assert len(st["por_departamento"]) == 1
    cobertura = adapter.cobertura_anual()
    assert {c["anio"] for c in cobertura} == {2020, 2021}


def test_normalizar_depto():
    assert _normalizar_depto("Boquerón") == "BOQUERON"
    assert _normalizar_depto("Ñeembucú") == "NEEMBUCU"
    assert _normalizar_depto("presidente hayes") == "PRESIDENTE HAYES"


def test_productos_reales_completos():
    assert len(PRODUCTOS_REALES) == 6
    assert "MODIS_SP" in PRODUCTOS_REALES and "VIIRS_NOAA21_NRT" in PRODUCTOS_REALES


# ------------------------------------------------------------------ integración real
@pytest.mark.skipif(not REAL_BASE.exists(), reason="base real M014 no disponible en este entorno")
class TestBaseRealM014:
    """Integración contra la base real (2.691.999 observaciones)."""

    def test_verify_concilia_manifiesto(self, tmp_path: Path):
        sources = REAL_BASE.parents[1] / "SATELLITE_DATA"
        adapter = RealBaseAdapter(
            base_dir=REAL_BASE, sources_dir=sources, duckdb_path=tmp_path / "real.duckdb"
        )
        rep = adapter.verify(check_hashes=False, deep=False)
        assert rep.ok, rep.problemas
        assert rep.filas_reales == 2_691_999
        assert rep.particiones == 45
        d = rep.to_dict()
        assert d["por_producto"]["MODIS_SP"]["filas_real"] == 1_058_738
        assert d["por_producto"]["VIIRS_NOAA21_NRT"]["filas_real"] == 161_095

    def test_duckdb_queries_reales(self, tmp_path: Path):
        duck = tmp_path / "real.duckdb"
        adapter = RealBaseAdapter(base_dir=REAL_BASE, duckdb_path=duck)
        meta = adapter.build_duckdb(force=True)
        assert meta["filas"] == 2_691_999
        assert meta["source_kind"] == "real"
        # conciliación con cifras M014 documentadas (dentro_pais=False = total base)
        assert adapter.count_obs(producto="MODIS_SP", dentro_pais=False) == 1_058_738
        assert adapter.count_obs(producto="VIIRS_NOAA20_SP", dentro_pais=False) == 1_105_418
        assert adapter.count_obs(dentro_pais=False) == 2_691_999
        # el scope nacional excluye las 8.459 detecciones fuera del ADM0
        assert adapter.count_obs(producto="MODIS_SP") == 1_058_738 - 2_228
        assert adapter.count_obs(anio=2020) > 100_000
        assert adapter.count_obs(departamento="Boquerón", anio=2020) == 35_587
        st = adapter.stats()
        assert st["total"] == 2_691_999
        assert len(st["por_departamento"]) == 18
        assert st["fuera_de_pais"] == 8_459
