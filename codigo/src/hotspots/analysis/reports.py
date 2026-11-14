"""Comparación de sensores MODIS vs VIIRS sobre el almacén real (Misión 004, D).

Genera un informe consultable de las diferencias sistemáticas OBSERVADAS en
los datos almacenados: conteos por producto/satélite, distribución de FRP,
confianza, y solapamiento temporal de co-detecciones. Es descriptivo: dice lo
que hay en el almacén, no lo que los sensores "pueden".
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SensorComparison:
    por_producto: list[dict] = field(default_factory=list)
    frp_por_producto: list[dict] = field(default_factory=list)
    confianza_por_producto: list[dict] = field(default_factory=list)
    pares_entre_productos: int = 0
    nota_sintetico: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def compare_sensors(duck) -> SensorComparison:
    """Consulta el almacén DuckDB (read-only) y arma el comparativo."""
    out = SensorComparison()
    out.por_producto = duck.query(
        "SELECT product, sensor, count(*) AS n, min(acq_date) AS desde, "
        "max(acq_date) AS hasta FROM observations GROUP BY 1, 2 ORDER BY 1"
    )
    out.frp_por_producto = duck.query(
        "SELECT product, count(frp) AS n_con_frp, round(avg(frp), 2) AS frp_prom, "
        "round(median(frp), 2) AS frp_mediana, round(max(frp), 2) AS frp_max "
        "FROM observations WHERE frp IS NOT NULL GROUP BY 1 ORDER BY 1"
    )
    out.confianza_por_producto = duck.query(
        "SELECT product, confidence, count(*) AS n FROM observations "
        "GROUP BY 1, 2 ORDER BY 1, 3 DESC"
    )
    out.pares_entre_productos = len(duck.candidate_matches())
    return out
