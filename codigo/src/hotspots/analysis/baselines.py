"""Baselines simples para series diarias: el listón que cualquier modelo debe saltar.

- **Persistencia**: "mañana será igual a hoy". El baseline más barato y el más
  difícil de vencer en series con mucha inercia.
- **Climatología diaria**: mediana por día del año con los años anteriores.
  Requiere >= 2 años de historia (guarda explícita); con un solo año no hay
  climatología posible.

Ambos operan sobre series (fecha ISO, valor) y SOLO miran el pasado respecto
del día a estimar (sin fuga).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from hotspots.analysis.anomaly import InsufficientDataError  # excepción compartida

__all__ = [
    "ForecastResult",
    "InsufficientDataError",
    "climatology_forecast",
    "mae",
    "persistence_forecast",
]


@dataclass
class ForecastResult:
    fecha: str
    valor_estimado: float
    metodo: str


def persistence_forecast(serie: list[tuple[str, int]], *, for_date: str) -> ForecastResult:
    """Estima el valor de ``for_date`` como el del día anterior disponible."""
    target = date.fromisoformat(for_date)
    previos = [(date.fromisoformat(f), v) for f, v in serie if date.fromisoformat(f) < target]
    if not previos:
        raise InsufficientDataError("sin historia previa a la fecha objetivo")
    f, v = max(previos, key=lambda x: x[0])
    return ForecastResult(str(target), float(v), "persistence")


def climatology_forecast(
    serie: list[tuple[str, int]],
    *,
    for_date: str,
    min_years: int = 2,
    window_days: int = 7,
) -> ForecastResult:
    """Mediana de los valores en ±window_days del mismo día del año, años previos."""
    target = date.fromisoformat(for_date)
    datos = [(date.fromisoformat(f), v) for f, v in serie if date.fromisoformat(f) < target]
    años = {d.year for d, _ in datos}
    if len(años) < min_years:
        raise InsufficientDataError(
            f"climatología necesita >= {min_years} años de historia; hay {len(años)}"
        )
    doy = target.timetuple().tm_yday
    vecinos = [
        v
        for d, v in datos
        if abs(d.timetuple().tm_yday - doy) <= window_days and d.year < target.year
    ]
    if not vecinos:
        raise InsufficientDataError("sin valores comparables en la ventana del día del año")
    vecinos.sort()
    n = len(vecinos)
    mediana = vecinos[n // 2] if n % 2 else (vecinos[n // 2 - 1] + vecinos[n // 2]) / 2
    return ForecastResult(str(target), float(mediana), "climatology_doy")


def mae(estimaciones: list[float], reales: list[float]) -> float:
    """Error absoluto medio — métrica honesta para conteos."""
    if not estimaciones or len(estimaciones) != len(reales):
        raise ValueError("listas vacías o de distinto largo")
    return sum(abs(e - r) for e, r in zip(estimaciones, reales, strict=True)) / len(reales)
