"""Adaptador de la base real M014 (``data/PROCESADA/base_real_v1``).

Misión A de la finalización: conectar la base real de 2.691.999 observaciones
al pipeline sin modificar los artefactos originales y con aislamiento
estricto frente a los fixtures sintéticos.

Decisiones de diseño:

- **Solo lectura.** El adaptador JAMÁS escribe dentro de ``base_real_v1/``.
  El DuckDB integrado se materializa fuera (``data/PROCESADA/hotspots_real.duckdb``)
  y es un artefacto derivado reconstruible con :meth:`RealBaseAdapter.build_duckdb`.
- **Verificación primero.** :meth:`verify` concilia el manifiesto M014 contra
  el Parquet real (conteos por producto, rangos de fechas, productos, unicidad
  de ``obs_id``) y opcionalmente los SHA-256 de los 45 archivos fuente.
- **Aislamiento de fixtures.** El directorio base debe contener
  ``manifiesto_base_real.json``; cualquier ruta bajo ``tests/fixtures`` o el
  almacén del pipeline (``processed/``) se rechaza con error explícito. La
  procedencia viaja SIEMPRE: cada respuesta marca ``source_kind="real"``.
- **Particionado explotado.** Las consultas filtran por ``product`` y
  ``acq_datetime_utc`` con predicados que DuckDB empuja a los particiones
  Hive (``product=.../year=...``) del GeoParquet original.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ADAPTER_VERSION = "real_base_v1.0.0"
MANIFEST_NAME = "manifiesto_base_real.json"

# Productos exactos que construyó M014 (orden alfabético).
PRODUCTOS_REALES = frozenset(
    {
        "MODIS_NRT",
        "MODIS_SP",
        "VIIRS_NOAA20_NRT",
        "VIIRS_NOAA20_SP",
        "VIIRS_NOAA21_NRT",
        "VIIRS_NOAA21_SP",
    }
)


class RealBaseError(Exception):
    """Error del adaptador de base real (ruta inválida, conciliación fallida…)."""


def _default_base_dir() -> Path:
    """Ruta por defecto de la base real (hermana del directorio del pipeline)."""
    env = os.environ.get("HOTSPOTS_REAL_BASE_DIR")
    if env:
        return Path(env).expanduser().resolve()
    pipeline_root = Path(__file__).resolve().parents[3]  # …/codigo
    return (pipeline_root.parent / "data" / "PROCESADA" / "base_real_v1").resolve()


def _default_duckdb_path() -> Path:
    env = os.environ.get("HOTSPOTS_REAL_DUCKDB")
    if env:
        return Path(env).expanduser().resolve()
    base = _default_base_dir()
    return base.parent / "hotspots_real.duckdb"


def _default_sources_dir() -> Path:
    env = os.environ.get("HOTSPOTS_REAL_SOURCES_DIR")
    if env:
        return Path(env).expanduser().resolve()
    base = _default_base_dir()
    return base.parents[1] / "SATELLITE_DATA"


def _resolve_opt(value: str | Path | None, default) -> Path:
    return Path(value).expanduser().resolve() if value else default()


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _normalizar_depto(nombre: str) -> str:
    """Normaliza un nombre de departamento: mayúsculas y sin acentos.

    La base usa UPPERCASE sin tildes (``BOQUERON``) pero conserva Ñ
    (``ÑEEMBUCU``); la comparación se hace con ``strip_accents(upper(...))``
    en ambos lados para que "Boquerón" == "BOQUERON" == "boqueron".
    """
    nfk = unicodedata.normalize("NFKD", nombre)
    return "".join(c for c in nfk if not unicodedata.combining(c)).upper()


@dataclass
class RealBaseReport:
    """Resultado verificable de :meth:`RealBaseAdapter.verify`."""

    base_dir: str
    manifiesto: str
    schema_version: str | None = None
    creado_en_utc: str | None = None
    fuentes_totales: int = 0
    fuentes_hash_ok: int = 0
    productos: dict[str, dict[str, Any]] = field(default_factory=dict)
    filas_esperadas: int = 0
    filas_reales: int = 0
    obs_id_duplicados: int = 0
    particiones: int = 0
    problemas: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problemas

    def to_dict(self) -> dict[str, Any]:
        d = {
            "ok": self.ok,
            "base_dir": self.base_dir,
            "manifiesto": self.manifiesto,
            "adapter_version": ADAPTER_VERSION,
            "schema_version": self.schema_version,
            "creado_en_utc": self.creado_en_utc,
            "fuentes_totales": self.fuentes_totales,
            "fuentes_hash_ok": self.fuentes_hash_ok,
            "filas_esperadas": self.filas_esperadas,
            "filas_reales": self.filas_reales,
            "obs_id_duplicados": self.obs_id_duplicados,
            "particiones": self.particiones,
            "por_producto": self.productos,
            "problemas": self.problemas,
        }
        return d


class RealBaseAdapter:
    """Lector eficiente y verificable de la base real M014.

    Ejemplo::

        adapter = RealBaseAdapter()
        report = adapter.verify()          # concilia manifiesto vs parquet
        adapter.build_duckdb()             # materializa hotspots_real.duckdb
        rows = adapter.query_obs(producto="MODIS_SP", anio=2020)
    """

    def __init__(
        self,
        base_dir: str | Path | None = None,
        duckdb_path: str | Path | None = None,
        sources_dir: str | Path | None = None,
    ) -> None:
        self.base_dir = _resolve_opt(base_dir, _default_base_dir)
        self.duckdb_path = _resolve_opt(duckdb_path, _default_duckdb_path)
        self.sources_dir = _resolve_opt(sources_dir, _default_sources_dir)
        self._manifest: dict | None = None
        self._assert_real_base()

    # ------------------------------------------------------------ guardas
    def _assert_real_base(self) -> None:
        """Aislamiento fixtures/real: la base debe ser la real, nunca fixtures."""
        base = self.base_dir
        problemas: list[str] = []
        if not base.exists():
            raise RealBaseError(f"base real inexistente: {base}")
        if not (base / MANIFEST_NAME).exists():
            problemas.append(f"sin {MANIFEST_NAME}: no es una base real M014")
        cadena = str(base).replace("\\", "/")
        if "/tests/fixtures/" in cadena or cadena.endswith("/tests/fixtures"):
            problemas.append("ruta bajo tests/fixtures: los fixtures jamás son fuente productiva")
        if "/data/processed/" in cadena or cadena.endswith("/data/processed"):
            problemas.append("ruta bajo data/processed (almacén de fixtures del pipeline)")
        if problemas:
            detalle = "; ".join(problemas)
            raise RealBaseError(f"ruta rechazada por aislamiento fixture/real: {detalle}")

    # ------------------------------------------------------------ manifiesto
    @property
    def manifest(self) -> dict:
        if self._manifest is None:
            path = self.base_dir / MANIFEST_NAME
            try:
                self._manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RealBaseError(f"manifiesto ilegible ({path}): {exc}") from exc
        return self._manifest

    @property
    def parquet_glob(self) -> str:
        return str(self.base_dir / "observations" / "**" / "*.parquet")

    def _particiones(self) -> list[Path]:
        return sorted((self.base_dir / "observations").rglob("*.parquet"))

    # ------------------------------------------------------------ verify
    def verify(self, *, check_hashes: bool = True, deep: bool = False) -> RealBaseReport:
        """Concilia manifiesto M014 contra el Parquet real.

        ``check_hashes`` valida SHA-256 de los 45 archivos fuente en
        ``sources_dir`` (rápido: ~53 MB). ``deep`` añade unicidad global de
        ``obs_id`` (recorre toda la base; ~2 s).
        """
        man = self.manifest
        report = RealBaseReport(
            base_dir=str(self.base_dir),
            manifiesto=str(self.base_dir / MANIFEST_NAME),
            schema_version=man.get("schema_version"),
            creado_en_utc=man.get("creado_en_utc"),
        )
        conteos = man.get("conteos", {})
        fuentes = man.get("fuentes", {})
        report.fuentes_totales = len(fuentes)
        report.filas_esperadas = int(conteos.get("filas_base_final", -1))

        # 1) productos declarados: deben ser un subconjunto de los reales
        por_producto_man = man.get("por_producto", {})
        declarados = set(por_producto_man)
        desconocidos = declarados - set(PRODUCTOS_REALES)
        if desconocidos:
            report.problemas.append(
                f"productos desconocidos en el manifiesto: {sorted(desconocidos)}"
            )

        # 2) hashes de archivos fuente (SHA-256, tamaño)
        if check_hashes:
            for nombre, meta in fuentes.items():
                ruta = self._localizar_fuente(nombre, meta)
                if ruta is None:
                    report.problemas.append(f"fuente no encontrada: {nombre}")
                    continue
                if ruta.stat().st_size != int(meta.get("bytes", -1)):
                    report.problemas.append(f"tamaño divergente en fuente {nombre}")
                    continue
                if _sha256_file(ruta) != meta.get("sha256"):
                    report.problemas.append(f"SHA-256 divergente en fuente {nombre}")
                    continue
                report.fuentes_hash_ok += 1

        # 3) conteos reales por producto contra el parquet (particiones Hive)
        import duckdb

        con = duckdb.connect()
        try:
            real = con.execute(
                f"""
                SELECT product, COUNT(*) AS filas,
                       MIN(acq_datetime_utc) AS fecha_min, MAX(acq_datetime_utc) AS fecha_max
                FROM read_parquet('{self.parquet_glob}', hive_partitioning=true, union_by_name=true)
                GROUP BY product
                """
            ).fetchall()
        finally:
            con.close()
        por_producto_real = {
            r[0]: {"filas": int(r[1]), "fecha_min": str(r[2])[:10], "fecha_max": str(r[3])[:10]}
            for r in real
        }
        report.productos = {
            p: {
                "filas_manifiesto": int(por_producto_man.get(p, {}).get("filas", -1)),
                "filas_real": por_producto_real.get(p, {}).get("filas", -1),
                "fecha_min_manifiesto": por_producto_man.get(p, {}).get("fecha_min"),
                "fecha_min_real": por_producto_real.get(p, {}).get("fecha_min"),
                "fecha_max_manifiesto": por_producto_man.get(p, {}).get("fecha_max"),
                "fecha_max_real": por_producto_real.get(p, {}).get("fecha_max"),
            }
            for p in sorted(set(por_producto_man) | set(por_producto_real))
        }
        for p, info in report.productos.items():
            if info["filas_manifiesto"] != info["filas_real"]:
                a, b = info["filas_manifiesto"], info["filas_real"]
                report.problemas.append(f"conteo divergente en {p}: manifiesto {a} vs real {b}")
            for k in ("fecha_min", "fecha_max"):
                if info[f"{k}_manifiesto"] != info[f"{k}_real"]:
                    ma, re_ = info[f"{k}_manifiesto"], info[f"{k}_real"]
                    report.problemas.append(f"{k} divergente en {p}: {ma} vs {re_}")

        report.filas_reales = sum(int(r[1]) for r in real)
        if report.filas_esperadas != report.filas_reales:
            report.problemas.append(
                f"total divergente: manifiesto {report.filas_esperadas}"
                f" vs real {report.filas_reales}"
            )
        report.particiones = len(self._particiones())

        # 4) unicidad de obs_id (profunda, opcional)
        if deep:
            con = duckdb.connect()
            try:
                dup = con.execute(
                    f"""
                    SELECT COUNT(*) - COUNT(DISTINCT obs_id) FROM read_parquet(
                        '{self.parquet_glob}', hive_partitioning=true, union_by_name=true)
                    """
                ).fetchone()[0]
            finally:
                con.close()
            report.obs_id_duplicados = int(dup)
            if dup:
                report.problemas.append(f"obs_id duplicados: {dup}")
        return report

    def _localizar_fuente(self, nombre: str, meta: dict) -> Path | None:
        """Localiza un archivo fuente por nombre en sources_dir (recursivo)."""
        for cand in self.sources_dir.rglob(nombre):
            return cand
        return None

    # ------------------------------------------------------------ duckdb
    def build_duckdb(self, *, force: bool = False) -> dict[str, Any]:
        """Materializa ``hotspots_real.duckdb`` (tabla + vistas de cobertura).

        Artefacto derivado reconstruible: NO se publica en los repos y NO
        modifica la base original. Devuelve un resumen con trazabilidad.
        """
        import duckdb

        if self.duckdb_path.exists() and not force:
            meta = self.read_build_meta()
            if meta is not None:
                return meta
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(self.duckdb_path))
        try:
            con.execute(
                f"""
                CREATE OR REPLACE TABLE observations AS
                SELECT * FROM read_parquet('{self.parquet_glob}',
                    hive_partitioning=true, union_by_name=true)
                """
            )
            filas = con.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            con.execute(
                """
                CREATE OR REPLACE VIEW cobertura_producto_mes AS
                SELECT product,
                       strftime(acq_datetime_utc, '%Y-%m') AS mes,
                       COUNT(*) AS detecciones,
                       ROUND(SUM(frp), 1) AS frp_total,
                       MIN(acq_date) AS fecha_min,
                       MAX(acq_date) AS fecha_max
                FROM observations GROUP BY 1, 2
                """
            )
            con.execute(
                """
                CREATE OR REPLACE VIEW cobertura_producto_anio AS
                SELECT product,
                       year AS anio,
                       COUNT(*) AS detecciones,
                       ROUND(SUM(frp), 1) AS frp_total
                FROM observations
                GROUP BY product, year
                """
            )
            con.execute(
                """
                CREATE OR REPLACE VIEW stats_departamento AS
                SELECT departamento, COUNT(*) AS detecciones,
                       MIN(acq_date) AS primera, MAX(acq_date) AS ultima
                FROM observations
                WHERE dentro_pais AND departamento IS NOT NULL
                GROUP BY departamento
                """
            )
            man = self.manifest
            meta = {
                "adapter_version": ADAPTER_VERSION,
                "source_kind": "real",
                "base_dir": str(self.base_dir),
                "manifiesto": man.get("descripcion", MANIFEST_NAME),
                "schema_version": man.get("schema_version"),
                "manifiesto_creado_en_utc": man.get("creado_en_utc"),
                "filas": int(filas),
                "productos": sorted(
                    p
                    for (p,) in con.execute(
                        "SELECT DISTINCT product FROM observations"
                    ).fetchall()
                ),
                "build_en_utc": _utc_now_iso(),
            }
            con.execute(
                "CREATE OR REPLACE TABLE _build_meta AS SELECT * FROM (VALUES (?)) AS t(json)",
                [json.dumps(meta, ensure_ascii=False)],
            )
        finally:
            con.close()
        logger.info("hotspots_real.duckdb construido: %s filas", filas)
        return meta

    def read_build_meta(self) -> dict | None:
        """Lee la tabla ``_build_meta`` del DuckDB (None si no existe)."""
        import duckdb

        if not self.duckdb_path.exists():
            return None
        con = duckdb.connect(str(self.duckdb_path), read_only=True)
        try:
            row = con.execute("SELECT json FROM _build_meta LIMIT 1").fetchone()
            return json.loads(row[0]) if row else None
        except Exception:
            return None
        finally:
            con.close()

    # ------------------------------------------------------------ consultas
    def _connect(self):
        import duckdb

        if not self.duckdb_path.exists():
            raise RealBaseError(
                f"DuckDB real no construido ({self.duckdb_path});"
                " ejecutá build_duckdb() primero"
            )
        return duckdb.connect(str(self.duckdb_path), read_only=True)

    @staticmethod
    def _rows_to_dicts(cur) -> list[dict]:
        cols = [d[0] for d in cur.description]
        out = []
        for row in cur.fetchall():
            out.append({c: _jsonable(v) for c, v in zip(cols, row, strict=False)})
        return out

    def query_obs(
        self,
        *,
        fecha_desde: str | None = None,
        fecha_hasta: str | None = None,
        anio: int | None = None,
        producto: str | None = None,
        satelite: str | None = None,
        sensor: str | None = None,
        departamento: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        dentro_pais: bool = True,
        orden: str = "acq_datetime_utc",
        limite: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Consulta eficiente de observaciones reales con filtros combinables.

        Los filtros de producto y año aprovechan el particionado Hive del
        Parquet original (la tabla DuckDB conserva las columnas ``product`` y
        ``year``). Devuelve dicts JSON-serializables con ``source_kind=real``.
        """
        where, params = self._build_where(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            anio=anio,
            producto=producto,
            satelite=satelite,
            sensor=sensor,
            departamento=departamento,
            bbox=bbox,
            dentro_pais=dentro_pais,
        )
        permitidos = {
            "acq_datetime_utc",
            "-acq_datetime_utc",
            "frp",
            "-frp",
            "confidence",
            "-confidence",
        }
        if orden not in permitidos:
            raise RealBaseError(f"orden no permitido: {orden}")
        con = self._connect()
        try:
            sql = f"SELECT * FROM observations {where} ORDER BY {orden} LIMIT ? OFFSET ?"
            cur = con.execute(sql, [*params, limite, offset])
            rows = self._rows_to_dicts(cur)
        finally:
            con.close()
        for r in rows:
            r["source_kind"] = "real"
        return rows

    def count_obs(
        self,
        *,
        fecha_desde: str | None = None,
        fecha_hasta: str | None = None,
        anio: int | None = None,
        producto: str | None = None,
        satelite: str | None = None,
        sensor: str | None = None,
        departamento: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        dentro_pais: bool = True,
    ) -> int:
        where, params = self._build_where(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            anio=anio,
            producto=producto,
            satelite=satelite,
            sensor=sensor,
            departamento=departamento,
            bbox=bbox,
            dentro_pais=dentro_pais,
        )
        con = self._connect()
        try:
            sql = f"SELECT COUNT(*) FROM observations {where}"
            return int(con.execute(sql, params).fetchone()[0])
        finally:
            con.close()

    def stats(self) -> dict[str, Any]:
        """Estadísticas agregadas: totales, por producto/año/satélite/departamento."""
        con = self._connect()
        try:
            total = con.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            fechas = con.execute("SELECT MIN(acq_date), MAX(acq_date) FROM observations").fetchone()
            por_producto = self._rows_to_dicts(
                con.execute(
                    "SELECT product, COUNT(*) AS detecciones, MIN(acq_date) AS desde,"
                    " MAX(acq_date) AS hasta FROM observations GROUP BY product"
                    " ORDER BY product"
                )
            )
            por_satelite = self._rows_to_dicts(
                con.execute(
                    "SELECT satellite, satellite_name, sensor, COUNT(*) AS detecciones"
                    " FROM observations GROUP BY 1,2,3 ORDER BY detecciones DESC"
                )
            )
            por_departamento = self._rows_to_dicts(
                con.execute(
                    "SELECT departamento, COUNT(*) AS detecciones FROM observations"
                    " WHERE dentro_pais AND departamento IS NOT NULL"
                    " GROUP BY 1 ORDER BY detecciones DESC"
                )
            )
            sql_fp = "SELECT COUNT(*) FROM observations WHERE NOT dentro_pais"
            fuera_pais = con.execute(sql_fp).fetchone()[0]
            industriales = con.execute(
                "SELECT COUNT(*) FROM observations WHERE es_fuente_industrial"
            ).fetchone()[0]
        finally:
            con.close()
        return {
            "source_kind": "real",
            "adapter_version": ADAPTER_VERSION,
            "total": int(total),
            "fecha_min": fechas[0],
            "fecha_max": fechas[1],
            "fuera_de_pais": int(fuera_pais),
            "fuentes_industriales": int(industriales),
            "por_producto": por_producto,
            "por_satelite": por_satelite,
            "por_departamento": por_departamento,
        }

    def cobertura_anual(self) -> list[dict]:
        con = self._connect()
        try:
            return self._rows_to_dicts(
                con.execute(
                    """
                    SELECT year AS anio,
                           SUM(CASE WHEN sensor='MODIS' THEN 1 ELSE 0 END) AS modis,
                           SUM(CASE WHEN sensor='VIIRS' THEN 1 ELSE 0 END) AS viirs,
                           COUNT(*) AS total
                    FROM observations GROUP BY year ORDER BY year
                    """
                )
            )
        finally:
            con.close()

    # ------------------------------------------------------------ interna
    def _build_where(
        self,
        *,
        fecha_desde: str | None,
        fecha_hasta: str | None,
        anio: int | None,
        producto: str | None,
        satelite: str | None,
        sensor: str | None,
        departamento: str | None,
        bbox: tuple[float, float, float, float] | None,
        dentro_pais: bool,
    ) -> tuple[str, list]:
        conds: list[str] = []
        params: list[Any] = []
        if fecha_desde:
            conds.append("acq_datetime_utc >= ?")
            params.append(f"{fecha_desde} 00:00:00")
        if fecha_hasta:
            conds.append("acq_datetime_utc < ?")
            params.append(f"{fecha_hasta} 23:59:59.999999")
        if anio is not None:
            conds.append("year = ?")
            params.append(int(anio))
        if producto:
            if producto not in PRODUCTOS_REALES:
                validos = sorted(PRODUCTOS_REALES)
                raise RealBaseError(f"producto desconocido: {producto} (válidos: {validos})")
            conds.append("product = ?")
            params.append(producto)
        if satelite:
            conds.append("upper(satellite) = upper(?)")
            params.append(satelite)
        if sensor:
            conds.append("upper(sensor) = upper(?)")
            params.append(sensor)
        if departamento:
            conds.append("strip_accents(upper(departamento)) = ?")
            params.append(_normalizar_depto(departamento))
        if bbox is not None:
            lon0, lat0, lon1, lat1 = bbox
            conds.append("longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ?")
            params.extend([lon0, lon1, lat0, lat1])
        if dentro_pais:
            conds.append("dentro_pais")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        return where, params


def _jsonable(v: Any) -> Any:
    import datetime as _dt
    import decimal as _decimal

    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", "replace")
    if isinstance(v, _decimal.Decimal):
        return float(v)
    return v


def _utc_now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
