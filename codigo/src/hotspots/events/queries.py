"""Consultas de historial de eventos reales (Misión C de la finalización).

Opera sobre los artefactos ``data/PROCESADA/eventos_v1/`` (eventos, membresía,
calendario) unidos a la base real ``hotspots_real.duckdb``. Todo lo que
devuelve es JSON-serializable y marcado con ``source_kind="real"``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

EVENTOS_VERSION = "eventos_v1"


class EventQueries:
    """Consultas: por fecha, por departamento, recurrencia, comparaciones y detalle."""

    def __init__(self, eventos_dir: str | Path, duckdb_real: str | Path) -> None:
        self.eventos_dir = Path(eventos_dir)
        self.duckdb_real = Path(duckdb_real)
        for nombre in ("eventos.parquet", "membresia.parquet", "calendario_nacional.csv"):
            if not (self.eventos_dir / nombre).exists():
                raise FileNotFoundError(
                    f"artefacto de eventos faltante: {self.eventos_dir / nombre}"
                )
        self._con = None

    # ------------------------------------------------------------ conexión
    def _conexion(self):
        if self._con is None:
            self._con = duckdb.connect(str(self.duckdb_real), read_only=False)
            ev = str(self.eventos_dir / "eventos.parquet").replace("'", "")
            mb = str(self.eventos_dir / "membresia.parquet").replace("'", "")
            cal = str(self.eventos_dir / "calendario_nacional.csv").replace("'", "")
            self._con.execute(
                f"CREATE OR REPLACE TABLE eventos AS SELECT * FROM read_parquet('{ev}')"
            )
            self._con.execute(
                f"CREATE OR REPLACE TABLE membresia AS SELECT * FROM read_parquet('{mb}')"
            )
            sql_cal = f"CREATE OR REPLACE TABLE calendario AS " \
                f"SELECT * FROM read_csv('{cal}', header=true)"
            self._con.execute(sql_cal)
            # departamento del evento: el de sus observaciones miembro (mayoría)
            self._con.execute(
                """
                CREATE OR REPLACE TABLE evento_departamento AS
                SELECT event_id, departamento, n,
                       ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY n DESC) AS rk
                FROM (
                    SELECT m.event_id, o.departamento, COUNT(*) AS n
                    FROM membresia m JOIN observations o ON o.obs_id = m.obs_id
                    WHERE o.departamento IS NOT NULL
                    GROUP BY 1, 2
                )
                """
            )
        return self._con

    def cerrar(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    # ------------------------------------------------------------ consultas
    def resumen(self) -> dict[str, Any]:
        con = self._conexion()
        total, dias, alertas = con.execute(
            """
            SELECT (SELECT COUNT(*) FROM eventos),
                   (SELECT COUNT(*) FROM calendario WHERE eventos > 0),
                   (SELECT COUNT(*) FROM eventos WHERE alerta_encadenamiento)
            """
        ).fetchone()
        rango = con.execute(
            "SELECT MIN(primera_obs_utc), MAX(ultima_obs_utc) FROM eventos"
        ).fetchone()
        miembros = con.execute(
            "SELECT AVG(n_observaciones), MAX(n_observaciones), "
            "AVG(duracion_segundos), AVG(diametro_metros) FROM eventos"
        ).fetchone()
        return {
            "source_kind": "real",
            "version": EVENTOS_VERSION,
            "total_eventos": int(total),
            "dias_con_eventos": int(dias),
            "alertas_encadenamiento": int(alertas),
            "primera_obs_utc": rango[0],
            "ultima_obs_utc": rango[1],
            "miembros_mediana": round(float(miembros[0] or 0), 1),
            "miembros_maximo": int(miembros[1] or 0),
            "duracion_media_s": round(float(miembros[2] or 0), 1),
            "diametro_medio_m": round(float(miembros[3] or 0), 1),
        }

    def por_fecha(self, desde: str, hasta: str, *, limite: int = 200) -> list[dict]:
        con = self._conexion()
        filas = con.execute(
            """
            SELECT e.event_id, e.n_observaciones, e.primera_obs_utc, e.ultima_obs_utc,
                   e.duracion_segundos, e.lat_centroide, e.lon_centroide,
                   e.diametro_metros, e.alerta_encadenamiento, e.frp_por_producto,
                   COALESCE(d.departamento, 'SIN ASIGNAR') AS departamento
            FROM eventos e
            LEFT JOIN (SELECT event_id, departamento FROM evento_departamento WHERE rk = 1) d
              ON d.event_id = e.event_id
            WHERE e.primera_obs_utc >= ? AND e.primera_obs_utc <= ?
            ORDER BY e.n_observaciones DESC, e.primera_obs_utc
            LIMIT ?
            """,
            [f"{desde}T00:00:00Z", f"{hasta}T23:59:59Z", limite],
        ).fetchall()
        return [self._evento_a_dict(r) for r in filas]

    def por_departamento(self, departamento: str, *, anio: int | None = None
        , limite: int = 100) -> list[dict]:
        con = self._conexion()
        filtro_anio = "AND strftime(CAST(e.primera_obs_utc AS TIMESTAMP), '%Y') = ?" if anio else ""
        params = [self._norm(departamento)] + ([str(anio)] if anio else []) + [limite]
        filas = con.execute(
            f"""
            SELECT e.event_id, e.n_observaciones, e.primera_obs_utc, e.ultima_obs_utc,
                   e.duracion_segundos, e.lat_centroide, e.lon_centroide,
                   e.diametro_metros, e.alerta_encadenamiento, e.frp_por_producto,
                   d.departamento
            FROM eventos e
            JOIN (SELECT event_id, departamento FROM evento_departamento WHERE rk = 1) d
              ON d.event_id = e.event_id
            WHERE strip_accents(upper(d.departamento)) = ? {filtro_anio}
            ORDER BY e.n_observaciones DESC, e.primera_obs_utc
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [self._evento_a_dict(r) for r in filas]

    def comparacion_anual(self, *, departamento: str | None = None) -> list[dict]:
        con = self._conexion()
        join = ""
        where = ""
        params: list = []
        if departamento:
            join = (
                "JOIN (SELECT event_id, departamento FROM evento_departamento WHERE rk = 1) d"
                " ON d.event_id = e.event_id"
            )
            where = "WHERE strip_accents(upper(d.departamento)) = ?"
            params = [self._norm(departamento)]
        filas = con.execute(
            f"""
            SELECT strftime(CAST(e.primera_obs_utc AS TIMESTAMP), '%Y') AS anio
                , COUNT(*) AS eventos,
                   SUM(e.n_observaciones) AS observaciones,
                   ROUND(AVG(e.n_observaciones), 1) AS miembros_media,
                   ROUND(AVG(e.diametro_metros), 0) AS diametro_medio
            FROM eventos e {join} {where}
            GROUP BY 1 ORDER BY 1
            """,
            params,
        ).fetchall()
        return [
            {
                "anio": r[0],
                "eventos": int(r[1]),
                "observaciones": int(r[2]),
                "miembros_media": float(r[3] or 0),
                "diametro_medio_m": float(r[4] or 0),
            }
            for r in filas
        ]

    def comparacion_mensual(self, anio: int) -> list[dict]:
        con = self._conexion()
        filas = con.execute(
            """
            SELECT strftime(CAST(primera_obs_utc AS TIMESTAMP), '%m') AS mes, COUNT(*) AS eventos,
                   SUM(n_observaciones) AS observaciones
            FROM eventos
            WHERE strftime(CAST(primera_obs_utc AS TIMESTAMP), '%Y') = ?
            GROUP BY 1 ORDER BY 1
            """,
            [str(anio)],
        ).fetchall()
        return [{"mes": r[0], "eventos": int(r[1]), "observaciones": int(r[2])} for r in filas]

    def recurrencia(
        self, *, celda_grados: float = 0.1, anio_desde: int | None = None
    ) -> list[dict]:
        """Celdas con eventos en más de un año (recurrencia espacio-temporal).

        La celda es una malla regular de referencia para agrupar ubicaciones;
        NO es una unidad oficial ni un perímetro de incendio.
        """
        con = self._conexion()
        cond_aniodesde = (
            "AND strftime(CAST(primera_obs_utc AS TIMESTAMP), '%Y') >= ?"
        )
        desde = cond_aniodesde if anio_desde else ""
        params = [str(anio_desde)] if anio_desde else []
        filas = con.execute(
            f"""
            SELECT CAST(FLOOR(lon_centroide / {celda_grados})
                       * {celda_grados} AS DOUBLE) AS lon_celda,
                   CAST(FLOOR(lat_centroide / {celda_grados})
                       * {celda_grados} AS DOUBLE) AS lat_celda,
                   COUNT(*) AS eventos,
                   COUNT(DISTINCT strftime(
                       CAST(primera_obs_utc AS TIMESTAMP), '%Y'
                   )) AS anios_distintos,
                   MIN(strftime(CAST(primera_obs_utc AS TIMESTAMP), '%Y')) AS primer_anio,
                   MAX(strftime(CAST(primera_obs_utc AS TIMESTAMP), '%Y')) AS ultimo_anio
            FROM eventos WHERE 1=1 {desde}
            GROUP BY 1, 2
            HAVING COUNT(DISTINCT strftime(CAST(primera_obs_utc AS TIMESTAMP), '%Y')) > 1
            ORDER BY anios_distintos DESC, eventos DESC
            LIMIT 200
            """,
            params,
        ).fetchall()
        return [
            {
                "celda": f"{r[1]:.1f},{r[0]:.1f}",
                "eventos": int(r[2]),
                "anios_distintos": int(r[3]),
                "primer_anio": r[4],
                "ultimo_anio": r[5],
            }
            for r in filas
        ]

    def detalle(self, event_id: str) -> dict[str, Any] | None:
        """Evento completo + miembros con toda su trazabilidad."""
        con = self._conexion()
        fila = con.execute(
            """
            SELECT event_id, metodo, parametros, n_observaciones, productos, sensores,
                   satelites, primera_obs_utc, ultima_obs_utc, duracion_segundos,
                   lat_centroide, lon_centroide, dispersion_metros, diametro_metros,
                   alerta_encadenamiento, frp_total, frp_max, frp_por_producto,
                   confianzas, run_id
            FROM eventos WHERE event_id = ?
            """,
            [event_id],
        ).fetchone()
        if not fila:
            return None
        miembros = con.execute(
            """
            SELECT o.obs_id, o.product, o.satellite_name, o.acq_datetime_utc,
                   o.latitude, o.longitude, o.frp, o.confidence, o.confidence_band,
                   o.departamento, o.source_file, o.source_sha256
            FROM membresia m JOIN observations o ON o.obs_id = m.obs_id
            WHERE m.event_id = ?
            ORDER BY o.acq_datetime_utc
            """,
            [event_id],
        ).fetchall()
        return {
            "source_kind": "real",
            "event_id": fila[0],
            "metodo": fila[1],
            "parametros": fila[2],
            "n_observaciones": fila[3],
            "productos": fila[4],
            "sensores": fila[5],
            "satelites": fila[6],
            "primera_obs_utc": fila[7],
            "ultima_obs_utc": fila[8],
            "duracion_segundos": fila[9],
            "lat_centroide": fila[10],
            "lon_centroide": fila[11],
            "dispersion_metros": fila[12],
            "diametro_metros": fila[13],
            "alerta_encadenamiento": fila[14],
            "frp_total": fila[15],
            "frp_max": fila[16],
            "frp_por_producto": json.loads(fila[17]) if fila[17] else {},
            "confianzas": fila[18],
            "run_id": fila[19],
            "advertencias": self._advertencias(fila),
            "miembros": [
                {
                    "obs_id": m[0], "producto": m[1], "satelite": m[2],
                    "acq_datetime_utc": str(m[3]), "latitud": m[4], "longitud": m[5],
                    "frp_mw": m[6], "confianza": str(m[7]), "banda": m[8],
                    "departamento": m[9], "source_file": m[10], "source_sha256": m[11],
                }
                for m in miembros
            ],
        }

    def calendario(self, desde: str | None = None, hasta: str | None = None, *,
                   solo_con_eventos: bool = False, limite: int = 400) -> list[dict]:
        con = self._conexion()
        conds, params = [], []
        if desde:
            conds.append("fecha >= ?")
            params.append(desde)
        if hasta:
            conds.append("fecha <= ?")
            params.append(hasta)
        if solo_con_eventos:
            conds.append("eventos > 0")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        filas = con.execute(
            f"SELECT * FROM calendario {where} ORDER BY fecha LIMIT ?",
            [*params, limite],
        ).fetchall()
        cols = [d[0] for d in con.description]
        return [dict(zip(cols, f, strict=True)) for f in filas]

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _norm(nombre: str) -> str:
        import unicodedata

        nfk = unicodedata.normalize("NFKD", nombre)
        return "".join(c for c in nfk if not unicodedata.combining(c)).upper()

    @staticmethod
    def _evento_a_dict(r) -> dict:
        return {
            "source_kind": "real",
            "event_id": r[0],
            "n_observaciones": r[1],
            "primera_obs_utc": r[2],
            "ultima_obs_utc": r[3],
            "duracion_segundos": r[4],
            "lat_centroide": r[5],
            "lon_centroide": r[6],
            "diametro_metros": r[7],
            "alerta_encadenamiento": r[8],
            "frp_por_producto": json.loads(r[9]) if r[9] else {},
            "departamento": r[10],
        }

    @staticmethod
    def _advertencias(fila) -> list[str]:
        avisos = []
        if fila[14]:
            avisos.append(
                "alerta_encadenamiento: el diámetro o la duración exceden 2× los "
                "umbrales; el evento puede agrupar varios focos cercanos "
                "(encadenamiento transitivo)."
            )
        avisos.append(
            "diametro_metros es una cota de extensión espacial de las detecciones, "
            "NO un perímetro real ni área quemada."
        )
        if fila[15]:
            avisos.append(
                "frp_total suma detecciones de sensores distintos y NO es la "
                "potencia física del fuego; ver frp_por_producto."
            )
        return avisos
