"""Motor de consultas: DuckDB sobre los Parquet append-only.

Vistas generadas:

- ``observations``: todas las detecciones, DEDUPLICADAS por ``obs_id``
  (determinista). Re-ingestar la misma fuente no infla conteos.
- ``observations_raw``: sin deduplicar (auditoría de corridas).
- ``quarantine``: filas rechazadas por QC, íntegras.
- ``ingest_status``: historial de estados por corrida/fuente.
- ``candidate_matches``: PAREJAS de observaciones de productos distintos que
  comparten ventana temporal y proximidad espacial (corrección D).
- (con capa geográfica activa) ``observations_geo``, ``stats_departamento_dia``,
  ``stats_nacional_dia``, ``stats_nacional_semana``, ``stats_nacional_mes`` y
  ``cobertura_area`` — Misión 004, etapa 2.

Cada vista conserva TODAS las columnas de sensor/satélite: las consultas
agregadas por sensor son explícitas, nunca implícitas.

Sobre ``candidate_matches`` (Misión 002, corrección D — diseño para la Fase 2):

- Genera CANDIDATOS de coincidencia entre productos (p. ej. una detección
  MODIS_NRT y una VIIRS_NOAA20_NRT del mismo fuego). NO es matching científico:
  es la materia prima sobre la que la Fase 2 aplicará criterios de
  armonización (umbrales por sensor, geometría de píxel, confidence, FRP).
- Preserva la identidad de AMBAS observaciones (``obs_id_a``/``obs_id_b``):
  la coincidencia es una RELACIÓN, nunca una fusión. Ninguna observación se
  borra ni se reescribe.
- Umbrales (convención del proyecto, configurable, no spec de NASA):
  ``match_dt_seconds`` = 600 s y ``match_distance_m`` = 2000 m (ver
  docs/harmonization.md para el fundamento y el análisis de sensibilidad).
- ``a.product < b.product`` garantiza que cada par no ordenado aparece una
  sola vez y que nunca se empareja un producto consigo mismo (Terra/Aqua
  dentro de MODIS_NRT queda como extensión documentada de la Fase 2).

Vistas geográficas (Misión 004):

- La versión de límites activa se persiste en ``processed/geo_views.json``;
  ``refresh()`` sin argumentos la reutiliza, así las corridas de ingesta no
  dejan las vistas geo desincronizadas.
- ``observations_geo`` pega la relación ``obs_geo`` (versión activa) SIN
  tocar la observación; las estadísticas nacionales filtran ``dentro_pais``.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from hotspots.models import KIND_BINARY, KIND_FLOAT, KIND_LIST_STR, KIND_STR
from hotspots.storage.parquet_store import ParquetStore

_DUCK_TYPES = {
    KIND_STR: "VARCHAR",
    KIND_FLOAT: "DOUBLE",
    KIND_LIST_STR: "VARCHAR[]",
    KIND_BINARY: "BLOB",
}

#: Formato ISO de acq_datetime_utc (constante de los datos, no configuración).
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"

#: Expresión SQL de distancia equirectangular en metros (aprox., para candidatos).
_DIST_SQL = (
    "sqrt(pow(a.latitude - b.latitude, 2) + "
    "pow((a.longitude - b.longitude) * cos(radians((a.latitude + b.latitude) / 2.0)), 2)) "
    "* 111320.0"
)


def _sql_files(files: list[Path]) -> str:
    return "[" + ", ".join("'" + str(p).replace("'", "''") + "'" for p in files) + "]"


class DuckDBStore:
    """Base analítica local (un archivo .duckdb) sobre el almacén Parquet."""

    def __init__(
        self,
        db_path: str | Path,
        parquet_root: str | Path,
        *,
        match_dt_seconds: int = 600,
        match_distance_m: float = 2000.0,
    ):
        self.db_path = Path(db_path)
        self.parquet = ParquetStore(parquet_root)
        self.match_dt_seconds = int(match_dt_seconds)
        self.match_distance_m = float(match_distance_m)

    # ------------------------------------------------------------------ refresh
    def _geo_config_file(self) -> Path:
        return self.parquet.root / "geo_views.json"

    def _load_geo_config(
        self, geo_version: str | None, boundaries_parquet: str | Path | None
    ) -> tuple[str | None, str | None]:
        """Resuelve la config geo: argumentos explícitos > archivo persistido."""
        cfg_file = self._geo_config_file()
        if geo_version and boundaries_parquet:
            cfg_file.parent.mkdir(parents=True, exist_ok=True)
            cfg_file.write_text(
                json.dumps(
                    {"version": geo_version, "boundaries_parquet": str(boundaries_parquet)}
                ),
                encoding="utf-8",
            )
            return geo_version, str(boundaries_parquet)
        if cfg_file.exists():
            try:
                cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                return cfg.get("version"), cfg.get("boundaries_parquet")
            except (json.JSONDecodeError, OSError):
                return None, None
        return None, None

    def refresh(
        self,
        geo_version: str | None = None,
        boundaries_parquet: str | Path | None = None,
    ) -> None:
        """(Re)crea las vistas a partir de los Parquet actuales.

        Con ``geo_version`` + ``boundaries_parquet`` activa las vistas
        geográficas (y persiste la elección). Sin argumentos, reutiliza la
        última configuración persistida si existe.
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        gver, gparquet = self._load_geo_config(geo_version, boundaries_parquet)
        con = duckdb.connect(str(self.db_path))
        try:
            obs = self.parquet.observation_files()
            if obs:
                files_sql = _sql_files(obs)
                con.execute(
                    f"""
                    CREATE OR REPLACE VIEW observations AS
                    SELECT * EXCLUDE (rn) FROM (
                        SELECT *, row_number() OVER (
                            PARTITION BY obs_id
                            ORDER BY ingested_at_utc, manifest_id
                        ) AS rn
                        FROM read_parquet({files_sql})
                    ) WHERE rn = 1
                    """
                )
                con.execute(
                    "CREATE OR REPLACE VIEW observations_raw AS "
                    "SELECT * FROM read_parquet(" + files_sql + ")"
                )
                # Corrección D: pares candidatos ENTRE productos (sin fusión).
                con.execute(
                    f"""
                    CREATE OR REPLACE VIEW candidate_matches AS
                    SELECT
                        a.obs_id            AS obs_id_a,
                        b.obs_id            AS obs_id_b,
                        a.product           AS product_a,
                        b.product           AS product_b,
                        a.sensor            AS sensor_a,
                        b.sensor            AS sensor_b,
                        a.satellite         AS satellite_a,
                        b.satellite         AS satellite_b,
                        a.acq_datetime_utc  AS acq_datetime_utc_a,
                        b.acq_datetime_utc  AS acq_datetime_utc_b,
                        abs(date_diff('second',
                            strptime(a.acq_datetime_utc, '{_TS_FMT}'),
                            strptime(b.acq_datetime_utc, '{_TS_FMT}'))) AS dt_seconds,
                        round({_DIST_SQL}, 1) AS distance_m
                    FROM observations a
                    JOIN observations b
                      ON a.product < b.product
                     AND abs(date_diff('second',
                            strptime(a.acq_datetime_utc, '{_TS_FMT}'),
                            strptime(b.acq_datetime_utc, '{_TS_FMT}'))) <= {self.match_dt_seconds}
                     AND {_DIST_SQL} <= {self.match_distance_m}
                    """
                )
            else:
                con.execute("DROP VIEW IF EXISTS observations")
                con.execute("DROP VIEW IF EXISTS observations_raw")
                con.execute("DROP VIEW IF EXISTS candidate_matches")

            for view, files in (
                ("quarantine", self.parquet.quarantine_files()),
                ("ingest_status", self.parquet.status_files()),
            ):
                if files:
                    con.execute(
                        f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet(%s)"
                        % _sql_files(files)
                    )
                else:
                    con.execute(f"DROP VIEW IF EXISTS {view}")

            self._refresh_geo_views(con, gver, gparquet)
            self._refresh_events_views(con)
        finally:
            con.close()

    # --------------------------------------------------------------- eventos
    def _refresh_events_views(self, con) -> None:
        """Vistas de eventos desde el ÚLTIMO snapshot (semántica documentada)."""
        from hotspots.events.engine import latest_events_file, latest_membership_file

        ev = latest_events_file(self.parquet.root)
        mb = latest_membership_file(self.parquet.root)
        if ev:
            con.execute(
                "CREATE OR REPLACE VIEW events AS SELECT * FROM read_parquet('"
                + str(ev).replace("'", "''")
                + "')"
            )
        else:
            con.execute("DROP VIEW IF EXISTS events")
        if mb:
            con.execute(
                "CREATE OR REPLACE VIEW event_observations AS SELECT * FROM read_parquet('"
                + str(mb).replace("'", "''")
                + "')"
            )
        else:
            con.execute("DROP VIEW IF EXISTS event_observations")

    # ------------------------------------------------------------------ geo
    def _refresh_geo_views(self, con, gver: str | None, gparquet: str | None) -> None:
        """Vistas geográficas si hay relación obs_geo y versión activa."""
        from hotspots.geo.assign import obs_geo_files

        files = obs_geo_files(self.parquet.root)
        if (
            not files
            or not gver
            or not gparquet
            or not Path(gparquet).exists()
            or not self._view_exists(con, "observations")
        ):
            for v in (
                "observations_geo",
                "stats_departamento_dia",
                "stats_nacional_dia",
                "stats_nacional_semana",
                "stats_nacional_mes",
                "cobertura_area",
            ):
                con.execute(f"DROP VIEW IF EXISTS {v}")
            return

        geo_sql = _sql_files(files)
        units = "'" + str(gparquet).replace("'", "''") + "'"
        ver = gver.replace("'", "''")
        con.execute(
            f"""
            CREATE OR REPLACE VIEW observations_geo AS
            SELECT
                o.*,
                g.dentro_pais,
                g.admin1_id,
                g.admin2_id,
                a1.nombre AS departamento,
                a2.nombre AS distrito,
                g.version_limites
            FROM observations o
            LEFT JOIN (
                SELECT * FROM read_parquet({geo_sql})
                WHERE version_limites = '{ver}'
            ) g ON g.obs_id = o.obs_id
            LEFT JOIN read_parquet({units}) a1 ON a1.admin_id = g.admin1_id
            LEFT JOIN read_parquet({units}) a2 ON a2.admin_id = g.admin2_id
            """
        )
        con.execute(
            """
            CREATE OR REPLACE VIEW stats_departamento_dia AS
            SELECT departamento, acq_date, product,
                   count(*) AS detecciones, sum(frp) AS frp_total
            FROM observations_geo
            WHERE dentro_pais
            GROUP BY 1, 2, 3
            """
        )
        con.execute(
            """
            CREATE OR REPLACE VIEW stats_nacional_dia AS
            SELECT acq_date, product, count(*) AS detecciones, sum(frp) AS frp_total
            FROM observations_geo
            WHERE dentro_pais
            GROUP BY 1, 2
            """
        )
        con.execute(
            """
            CREATE OR REPLACE VIEW stats_nacional_semana AS
            SELECT strftime(
                       date_trunc('week', strptime(acq_date, '%Y-%m-%d')), '%Y-%m-%d'
                   ) AS semana,
                   product, count(*) AS detecciones, sum(frp) AS frp_total
            FROM observations_geo
            WHERE dentro_pais
            GROUP BY 1, 2
            """
        )
        con.execute(
            """
            CREATE OR REPLACE VIEW stats_nacional_mes AS
            SELECT strftime(date_trunc('month', strptime(acq_date, '%Y-%m-%d')), '%Y-%m') AS mes,
                   product, count(*) AS detecciones, sum(frp) AS frp_total
            FROM observations_geo
            WHERE dentro_pais
            GROUP BY 1, 2
            """
        )
        con.execute(
            """
            CREATE OR REPLACE VIEW cobertura_area AS
            SELECT dentro_pais, count(*) AS n
            FROM observations_geo
            GROUP BY 1
            """
        )

    # ------------------------------------------------------------------ consultas
    def query(self, sql: str, params: dict | None = None) -> list[dict]:
        """Ejecuta una consulta de SOLO LECTURA y devuelve filas como diccionarios.

        La conexión se abre ``read_only=True``: es imposible que una consulta
        modifique el almacén (corrección F2 — antes abría read-write).
        """
        if not self.db_path.exists():
            return []
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            cur = con.execute(sql, params or {})
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]
        finally:
            con.close()

    # ------------------------------------------------------------------ resúmenes
    def _view_exists(self, con, view: str) -> bool:
        r = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [view]
        ).fetchone()
        return bool(r and r[0])

    def counts_by_product(self, dentro_pais: bool | None = None) -> list[dict]:
        """Conteo por producto. ``dentro_pais=True`` filtra al territorio
        nacional (requiere capa geo activa); ``None``/``False`` cuenta todo el
        área de consulta (incluye detecciones de países vecinos)."""
        if not self.db_path.exists():
            return []
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            if dentro_pais:
                if not self._view_exists(con, "observations_geo"):
                    return []
                return self._rows(
                    con,
                    "SELECT product, count(*) AS n FROM observations_geo "
                    "WHERE dentro_pais GROUP BY product ORDER BY product",
                )
            if not self._view_exists(con, "observations"):
                return []
            return self._rows(
                con,
                "SELECT product, count(*) AS n FROM observations GROUP BY product ORDER BY product",
            )
        finally:
            con.close()

    def counts_by_satellite(self, dentro_pais: bool | None = None) -> list[dict]:
        """Conteo por producto/satélite con el mismo criterio de scope que
        :meth:`counts_by_product`."""
        if not self.db_path.exists():
            return []
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            if dentro_pais:
                if not self._view_exists(con, "observations_geo"):
                    return []
                return self._rows(
                    con,
                    "SELECT product, satellite, satellite_name, count(*) AS n "
                    "FROM observations_geo WHERE dentro_pais GROUP BY 1, 2, 3 ORDER BY 1, 2",
                )
            if not self._view_exists(con, "observations"):
                return []
            return self._rows(
                con,
                "SELECT product, satellite, satellite_name, count(*) AS n "
                "FROM observations GROUP BY 1, 2, 3 ORDER BY 1, 2",
            )
        finally:
            con.close()

    def status_counts(self) -> list[dict]:
        if not self.db_path.exists():
            return []
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            if not self._view_exists(con, "ingest_status"):
                return []
            return self._rows(
                con,
                "SELECT state, count(*) AS n FROM ingest_status GROUP BY state ORDER BY state",
            )
        finally:
            con.close()

    def quarantine_count(self) -> int:
        if not self.db_path.exists():
            return 0
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            if not self._view_exists(con, "quarantine"):
                return 0
            return con.execute("SELECT count(*) FROM quarantine").fetchone()[0]
        finally:
            con.close()

    def observation_count(self) -> int:
        if not self.db_path.exists():
            return 0
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            if not self._view_exists(con, "observations"):
                return 0
            return con.execute("SELECT count(*) FROM observations").fetchone()[0]
        finally:
            con.close()

    def candidate_matches(self) -> list[dict]:
        """Pares candidatos entre productos (ver docstring del módulo)."""
        if not self.db_path.exists():
            return []
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            if not self._view_exists(con, "candidate_matches"):
                return []
            return self._rows(
                con,
                "SELECT * FROM candidate_matches "
                "ORDER BY acq_datetime_utc_a, product_a, product_b",
            )
        finally:
            con.close()

    # ------------------------------------------------------------------ geo
    def geo_status(self) -> dict:
        """Resumen de la capa geográfica activa (o vacío si no hay)."""
        if not self.db_path.exists():
            return {}
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            if not self._view_exists(con, "observations_geo"):
                return {}
            out = self._rows(con, "SELECT * FROM cobertura_area")
            n_deptos = self._rows(
                con,
                "SELECT count(DISTINCT departamento) AS n FROM observations_geo "
                "WHERE dentro_pais",
            )
            res = {"cobertura": {str(r["dentro_pais"]): r["n"] for r in out}}
            res["departamentos_con_detecciones"] = n_deptos[0]["n"] if n_deptos else 0
            return res
        finally:
            con.close()

    def geo_version_activa(self) -> str | None:
        cfg = self._load_geo_config(None, None)[0]
        return cfg

    # ------------------------------------------------- cobertura / series
    def fechas_por_producto(self) -> dict[str, set[str]]:
        """Fechas con ≥1 observación válida, por producto."""
        if not self.db_path.exists():
            return {}
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            if not self._view_exists(con, "observations"):
                return {}
            rows = self._rows(
                con, "SELECT DISTINCT product, acq_date FROM observations ORDER BY 1, 2"
            )
            out: dict[str, set[str]] = {}
            for r in rows:
                out.setdefault(r["product"], set()).add(str(r["acq_date"]))
            return out
        finally:
            con.close()

    def fechas_cuarentena(self) -> dict[str, set[str]]:
        """Fechas con filas rechazadas por QC, por producto (de la cuarentena)."""
        if not self.db_path.exists():
            return {}
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            if not self._view_exists(con, "quarantine"):
                return {}
            rows = self._rows(
                con,
                "SELECT DISTINCT product, acq_date FROM quarantine "
                "WHERE acq_date IS NOT NULL ORDER BY 1, 2",
            )
            out: dict[str, set[str]] = {}
            for r in rows:
                out.setdefault(r["product"], set()).add(str(r["acq_date"]))
            return out
        finally:
            con.close()

    def conteos_por_fecha(self, departamento: str | None = None) -> dict[str, int]:
        """Conteo diario de observaciones NACIONALES (dentro_pais), opcionalmente
        filtradas por departamento. Requiere capa geo activa."""
        if not self.db_path.exists():
            return {}
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            if not self._view_exists(con, "observations_geo"):
                return {}
            if departamento:
                rows = self._rows_param(con, departamento)
            else:
                rows = self._rows(
                    con,
                    "SELECT acq_date AS fecha, count(*) AS n FROM observations_geo "
                    "WHERE dentro_pais GROUP BY 1",
                )
            return {str(r["fecha"]): int(r["n"]) for r in rows}
        finally:
            con.close()

    @staticmethod
    def _rows_param(con, departamento: str) -> list[dict]:
        cur = con.execute(
            "SELECT acq_date AS fecha, count(*) AS n FROM observations_geo "
            "WHERE dentro_pais AND departamento = ? GROUP BY 1",
            [departamento],
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]

    @staticmethod
    def _rows(con, sql: str) -> list[dict]:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]
