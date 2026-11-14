"""Detección de anomalías en conteos diarios de detecciones (por departamento).

Método (deliberadamente simple, robusto y explicable):

- **Baseline**: mediana móvil CENTRADA HACIA ATRÁS sobre la ventana de
  entrenamiento (solo pasado), con dispersión MAD (desviación absoluta
  mediana — robusta a los propios outliers, a diferencia de la desviación
  estándar).
- **Puntuación**: z-score robusto del día evaluado contra su baseline:
  ``z = (x - mediana) / (1.4826 * MAD)``. El 1.4826 hace el MAD comparable
  con la desviación estándar si la distribución fuera normal.
- **Dia de semana opcional**: los fuegos tienen ciclo semanal humano (fines de
  semana distintos); si hay >= 4 semanas de baseline, se calcula la mediana
  POR DÍA DE SEMANA.
- **Explicabilidad**: cada anomalía reporta su composición (valor observado,
  mediana esperada, MAD, z) — el "por qué" es auditable.
- **Guardas**: mínimo ``min_baseline_days`` de historia; MAD = 0 con el
  valor igual a la mediana => día normal; MAD = 0 con el valor DISTINTO =>
  anomalía con ``z=None`` (``motivo: dispersion_cero``): en un baseline
  plano cualquier desvío es anómalo por definición, pero el z-score no es
  computable. JAMÁS se emiten ``Infinity``/``NaN`` — la serialización JSON es
  estricta (``allow_nan=False``) y está probada.

Lo que NO es: no es un modelo de incendios, no predice nada, no usa variables
ambientales (esa integración viene con datos reales). Solo dice: "este día
tuvo atípicamente más/menos detecciones que lo esperable por su propio
historial reciente".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

MAD_TO_STD = 1.4826
DEFAULT_MIN_BASELINE = 28  # días de historia mínima para poder evaluar


class InsufficientDataError(Exception):
    """La serie no alcanza para construir un baseline honesto."""


def _median_abs_dev(valores: list[float], *, center: float) -> float:
    """MAD de ``valores`` respecto a ``center`` (0 para residuos)."""
    desv = sorted(abs(x - center) for x in valores)
    return _median(desv)


def _median(valores: list[float]) -> float:
    s = sorted(valores)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


@dataclass
class AnomalyDay:
    fecha: date
    valor: int
    esperado_mediana: float
    mad: float
    z: float | None  # None cuando la dispersión es cero (ver motivo)
    dia_semana: int  # 0=lunes .. 6=domingo
    direccion: str  # "alto" | "bajo"
    motivo: str | None = None  # p. ej. "dispersion_cero" cuando z es None

    def explain(self) -> str:
        z_txt = f"z={self.z:+.1f}" if self.z is not None else "z no computable"
        return (
            f"{self.fecha} ({['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'][self.dia_semana]}): "
            f"{self.valor} detecciones vs ~{self.esperado_mediana:.1f} esperadas "
            f"(dispersión MAD={self.mad:.1f}); {z_txt} => atípicamente {self.direccion}"
        )


@dataclass
class AnomalyReport:
    metodo: str = "rolling_median_mad_v1"
    unidad: str = ""  # p. ej. "departamento: ALTO PARANAY" o "nacional"
    dias_evaluados: int = 0
    umbral_z: float = 0.0
    anomalias: list[AnomalyDay] = field(default_factory=list)
    no_evaluables: list[str] = field(default_factory=list)
    datos_sinteticos: bool = False  # EL CALLER lo marca; jamás lo inferimos

    def to_dict(self) -> dict:
        return {
            "metodo": self.metodo,
            "unidad": self.unidad,
            "dias_evaluados": self.dias_evaluados,
            "umbral_z": self.umbral_z,
            "n_anomalias": len(self.anomalias),
            "anomalias": [
                {
                    "fecha": str(a.fecha),
                    "valor": a.valor,
                    "esperado": round(a.esperado_mediana, 2),
                    "mad": round(a.mad, 2),
                    "z": round(a.z, 2) if a.z is not None else None,
                    "direccion": a.direccion,
                    "motivo": a.motivo,
                }
                for a in self.anomalias
            ],
            "no_evaluables": self.no_evaluables,
            "datos_sinteticos": self.datos_sinteticos,
        }


def detect_anomalies(
    serie: list[tuple[str, int]],
    *,
    eval_from: str,
    eval_to: str,
    z_threshold: float = 3.0,
    use_weekday: bool = True,
    min_baseline_days: int = DEFAULT_MIN_BASELINE,
) -> AnomalyReport:
    """Detecta días anómalos en ``serie`` durante [eval_from, eval_to].

    ``serie``: pares (fecha ISO, conteo) ORDENADOS por fecha, sin huecos de
    fechas (rellenar antes si hace falta). El baseline de cada día evaluado
    usa exclusivamente los ``min_baseline_days`` días anteriores.
    """
    if not serie:
        raise InsufficientDataError("serie vacía")

    datos = [(date.fromisoformat(f), int(v)) for f, v in serie]
    for (f1, _), (f2, _) in zip(datos, datos[1:], strict=False):
        if f2 <= f1:
            raise ValueError("la serie debe estar ordenada y sin fechas repetidas")

    ev_from = date.fromisoformat(eval_from)
    ev_to = date.fromisoformat(eval_to)
    if ev_to < ev_from:
        raise ValueError("eval_to debe ser >= eval_from")

    idx = {f: v for f, v in datos}
    report = AnomalyReport(umbral_z=z_threshold)

    d = ev_from
    while d <= ev_to:
        report.dias_evaluados += 1
        if d not in idx:
            report.no_evaluables.append(f"{d}: sin dato")
            d += timedelta(days=1)
            continue

        # baseline: exclusivamente pasado, ventana fija hacia atrás
        ventana = [idx[d - timedelta(days=k)] for k in range(1, min_baseline_days + 1)
                   if (d - timedelta(days=k)) in idx]
        if len(ventana) < min_baseline_days:
            report.no_evaluables.append(
                f"{d}: solo {len(ventana)} días de historia (< {min_baseline_days})"
            )
            d += timedelta(days=1)
            continue

        # --- baseline del día ---
        # Mediana: por día de semana con las muestras de las últimas 8 SEMANAS
        # (n≈8 por weekday, suficiente para que 1-2 días anómalos viejos queden
        # en los extremos y no muevan la mediana — lección del experimento 001,
        # donde con ventana de 4 muestras dos anomalías inyectadas envenenaban
        # la mediana de los jueves siguientes: mediana(4) con 2 outliers = 202).
        # Escala (MAD): residuos de la ventana de min_baseline_days días
        # respecto a la mediana de cada weekday: elimina el ciclo semanal y
        # estima la dispersión con n≈28 (el MAD directo por weekday con pocas
        # muestras subestima σ e infla z).
        weekday_window = max(min_baseline_days * 2, 56)
        if use_weekday:
            medianas_weekday: dict[int, float] = {}
            for wd in range(7):
                muestras_wd = [
                    idx[d - timedelta(days=k)]
                    for k in range(1, weekday_window + 1)
                    if (d - timedelta(days=k)) in idx
                    and (d - timedelta(days=k)).weekday() == wd
                ]
                if len(muestras_wd) >= 4:
                    medianas_weekday[wd] = _median(muestras_wd)
            dias_ventana = [
                (d - timedelta(days=k), idx[d - timedelta(days=k)])
                for k in range(1, min_baseline_days + 1)
                if (d - timedelta(days=k)) in idx
            ]
            if len(medianas_weekday) == 7 and len(dias_ventana) >= min_baseline_days:
                residuos = [
                    v - medianas_weekday[fd.weekday()] for fd, v in dias_ventana
                ]
                mediana_base = medianas_weekday[d.weekday()]
                mad_base = _median_abs_dev(residuos, center=0.0)
            else:
                valores = sorted(v for _, v in dias_ventana)
                mediana_base = _median(valores)
                mad_base = _median_abs_dev([v for _, v in dias_ventana], center=mediana_base)
        else:
            mediana_base = _median(ventana)
            mad_base = _median_abs_dev(ventana, center=mediana_base)

        mediana, mad = mediana_base, mad_base
        valor = idx[d]
        if mad == 0:
            if valor == mediana:
                # baseline plano y el día coincide: normal, nada que reportar
                d += timedelta(days=1)
                continue
            # baseline plano + valor distinto: anómalo POR DEFINICIÓN (cualquier
            # desvío de una serie sin variabilidad histórica es significativo),
            # pero el z-score NO es computable (división por cero). Se registra
            # la anomalía con z=None y motivo explícito — nunca ±Infinity.
            report.anomalias.append(
                AnomalyDay(
                    d,
                    valor,
                    mediana,
                    mad,
                    None,
                    d.weekday(),
                    "alto" if valor > mediana else "bajo",
                    motivo="dispersion_cero",
                )
            )
            d += timedelta(days=1)
            continue
        z = (valor - mediana) / (MAD_TO_STD * mad)

        if z >= z_threshold:
            report.anomalias.append(
                AnomalyDay(d, valor, mediana, mad, z, d.weekday(), "alto")
            )
        elif z <= -z_threshold:
            report.anomalias.append(
                AnomalyDay(d, valor, mediana, mad, z, d.weekday(), "bajo")
            )
        d += timedelta(days=1)

    return report
