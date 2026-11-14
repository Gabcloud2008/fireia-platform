"""Calendario de cobertura: "cero detecciones" NO es "sin datos".

Problema que resuelve (Misión 005, §6.2): una serie temporal construida solo
con los días que tienen observaciones confunde dos situaciones opuestas:

- Día con cobertura satelital válida y **cero** detecciones → un cero REAL,
  comparable, que entra al baseline y puede ser anómalo (p. ej. un día
  cubierto de nubes puede reportar cero detecciones — eso es un hecho).
- Día **sin datos** (no se descargó, falló la descarga, no hubo cobertura) →
  un hueco: meterlo como cero inventaría "no hubo fuego" sin evidencia.

Estados por día:

- ``con_detecciones``: ≥ 1 observación válida.
- ``cero_detecciones_asumido``: sin observaciones válidas, pero dentro del
  intervalo cubierto de ≥ 1 producto. Es un cero comparable (con la
  limitación documentada de que "cobertura del intervalo" es un supuesto:
  MODIS/VIIRS no garantizan paso diario sobre cada punto).
- ``solo_rechazadas_qc``: ese día solo hubo filas rechazadas por control de
  calidad (están en cuarentena, con sus errores). No es un cero ni un hueco:
  es datos observados que el QC no aceptó.
- ``sin_datos``: fuera de todo intervalo cubierto. Hueco.

La cobertura por producto se toma de los ``acquisition_period`` de los
manifiestos cuando están completos; si vienen vacíos (fixtures) se infiere
como el intervalo [min, max] de fechas observadas, marcado como supuesto.
"""

from __future__ import annotations

from datetime import date, timedelta

ESTADO_CON_DETECCIONES = "con_detecciones"
ESTADO_CERO_ASUMIDO = "cero_detecciones_asumido"
ESTADO_SOLO_RECHAZADAS = "solo_rechazadas_qc"
ESTADO_SIN_DATOS = "sin_datos"

ESTADOS = (
    ESTADO_CON_DETECCIONES,
    ESTADO_CERO_ASUMIDO,
    ESTADO_SOLO_RECHAZADAS,
    ESTADO_SIN_DATOS,
)


def _días(desde: str, hasta: str):
    d = date.fromisoformat(desde)
    fin = date.fromisoformat(hasta)
    if fin < d:
        raise ValueError(f"desde ({desde}) > hasta ({hasta})")
    while d <= fin:
        yield d
        d += timedelta(days=1)


def _intervalo_producto(
    producto: str,
    fechas_obs: set[str],
    fechas_cuarentena: set[str],
    periodo: tuple[str, str] | None,
) -> tuple[str, str, bool] | None:
    """Intervalo cubierto por producto: (desde, hasta, inferido) o None.

    Las fechas de cuarentena CUENTAN como evidencia de adquisición (ese día
    llegó data del proveedor, aunque el QC la haya rechazado toda): extienden
    el intervalo inferido. El estado del día sigue siendo ``solo_rechazadas_qc``,
    no un cero comparable.
    """
    if periodo and periodo[0] and periodo[1]:
        return periodo[0], periodo[1], False
    evidencia = fechas_obs | fechas_cuarentena
    if not evidencia:
        return None  # producto sin ninguna evidencia: no aporta cobertura
    ordenadas = sorted(evidencia)
    return ordenadas[0], ordenadas[-1], True


def build_coverage_calendar(
    *,
    fechas_obs_por_producto: dict[str, set[str]],
    fechas_cuarentena_por_producto: dict[str, set[str]] | None = None,
    periodos_adquisicion: dict[str, tuple[str, str]] | None = None,
    desde: str,
    hasta: str,
) -> dict:
    """Construye el calendario de estados por día entre ``desde`` y ``hasta``.

    ``fechas_obs_por_producto``: {producto: fechas ISO con ≥ 1 observación
    válida}. ``fechas_cuarentena_por_producto``: ídem con filas rechazadas
    (opcional). ``periodos_adquisicion``: {producto: (from, to)} de los
    manifiestos; strings vacíos cuentan como ausentes.
    """
    cuarentena = fechas_cuarentena_por_producto or {}
    periodos = periodos_adquisicion or {}

    cobertura: dict[str, dict] = {}
    for producto, fechas in fechas_obs_por_producto.items():
        intervalo = _intervalo_producto(
            producto, fechas, cuarentena.get(producto, set()), periodos.get(producto)
        )
        if intervalo is not None:
            cobertura[producto] = {
                "desde": intervalo[0],
                "hasta": intervalo[1],
                "inferida": intervalo[2],
            }

    dias: list[dict] = []
    resumen = {e: 0 for e in ESTADOS}
    for d in _días(desde, hasta):
        iso = d.isoformat()
        con_obs = any(iso in fechas for fechas in fechas_obs_por_producto.values())
        if con_obs:
            estado = ESTADO_CON_DETECCIONES
        else:
            solo_rechazadas = any(
                iso in fechas for fechas in cuarentena.values()
            )
            cubierto = any(
                c["desde"] <= iso <= c["hasta"] for c in cobertura.values()
            )
            if solo_rechazadas:
                estado = ESTADO_SOLO_RECHAZADAS
            elif cubierto:
                estado = ESTADO_CERO_ASUMIDO
            else:
                estado = ESTADO_SIN_DATOS
        resumen[estado] += 1
        dias.append({"fecha": iso, "estado": estado})

    supuestos: list[str] = []
    if any(c["inferida"] for c in cobertura.values()):
        supuestos.append(
            "cobertura inferida del intervalo [min, max] de fechas observadas "
            "(manifiestos sin acquisition_period): asume paso satelital diario "
            "dentro del intervalo, lo cual MODIS/VIIRS no garantizan"
        )

    return {
        "desde": desde,
        "hasta": hasta,
        "dias": dias,
        "resumen": resumen,
        "cobertura_por_producto": cobertura,
        "supuestos": supuestos,
    }


def serie_comparable(
    conteos_por_fecha: dict[str, int],
    calendario: dict,
) -> tuple[list[tuple[str, int]], list[str]]:
    """Serie para el detector: solo días comparables (cero asumido incluido).

    Devuelve (serie, dias_excluidos). Los días ``sin_datos`` y
    ``solo_rechazadas_qc`` quedan FUERA de la serie (el detector los reportará
    como no evaluables "sin dato" — que es la verdad); los días
    ``cero_detecciones_asumido`` entran como 0.
    """
    serie: list[tuple[str, int]] = []
    excluidos: list[str] = []
    for dia in calendario["dias"]:
        iso, estado = dia["fecha"], dia["estado"]
        if estado in (ESTADO_SIN_DATOS, ESTADO_SOLO_RECHAZADAS):
            excluidos.append(iso)
        else:
            serie.append((iso, int(conteos_por_fecha.get(iso, 0))))
    return serie, excluidos
