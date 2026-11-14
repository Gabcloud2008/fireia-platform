"""API REST de Paraguay Fire Intelligence (Misión 004, etapa 12).

Contratos REALES: cada endpoint expone datos que existen en el almacén local
(DuckDB/Parquet) — no hay endpoints decorativos. Si una vista no existe, el
endpoint responde 404 con un mensaje honesto en vez de datos vacíos que
aparenten contenido.

Honestidad sobre el origen de los datos: ``/api/health`` reporta
``data_source`` según los manifiestos de ingesta ("fixture" => sintético,
"firms_api" => real). Los endpoints que sirven observaciones propagan ese
flag, y el dashboard lo muestra en pantalla. Lo que es sintético se VE
sintético.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from hotspots import __version__
from hotspots.config import Settings
from hotspots.storage.duckdb_store import DuckDBStore

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Paraguay Fire Intelligence API",
    description=(
        "Observaciones de focos de calor MODIS/VIIRS sobre Paraguay: consultas, "
        "eventos reconstruidos, calendario histórico, estadísticas y calidad de "
        "datos. Los puntos calientes NO son incendios confirmados."
    ),
    version=__version__,
)


# ------------------------------------------------------------------ helpers

def _settings() -> Settings:
    return Settings.load()


def _store() -> DuckDBStore:
    s = _settings()
    return DuckDBStore(
        s.data_dir / "processed" / "hotspots.duckdb", s.data_dir / "processed"
    )


def _view(store: DuckDBStore, name: str) -> None:
    """Garantiza que la vista exista; si no, 404 honesto."""
    if not store.db_path.exists():
        raise HTTPException(404, "almacén inexistente: corré una ingesta primero")
    import duckdb

    con = duckdb.connect(str(store.db_path), read_only=True)
    try:
        r = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
        ).fetchone()
        if not (r and r[0]):
            raise HTTPException(
                404,
                f"la vista '{name}' no existe todavía "
                "(¿corriste la ingesta/geo/events correspondiente?)",
            )
    finally:
        con.close()


def _data_source(store: DuckDBStore) -> str:
    """fixture | firms_api | mixto | vacío — según los manifiestos reales."""
    rows = store.query("SELECT source, count(*) AS n FROM ingest_status GROUP BY 1")
    if not rows:
        return "vacio"
    fuentes = {r["source"] for r in rows}
    if fuentes == {"fixture"}:
        return "fixture"
    if fuentes == {"firms_api"}:
        return "firms_api"
    return "mixto"


def _modo_datos_desde_observaciones(store: DuckDBStore) -> tuple[str, str]:
    """(modo_datos, clasificacion) DERIVADOS del source_kind de las filas.

    Misión 009 §11: la procedencia declarada se lee de los datos, no de una
    constante. Devuelve ("desconocido", "unknown") si la vista no está.
    """
    try:
        _view(store, "observations")
    except HTTPException:
        return "desconocido", "unknown"
    n = store.observation_count()
    if not n:
        return "sin_datos", "vacio"
    kinds_rows = store.query("SELECT DISTINCT source_kind FROM observations")
    kinds = sorted({r["source_kind"] or "unknown" for r in kinds_rows})
    if kinds == ["fixture"]:
        return "sintetico", "fixture"
    if kinds == ["firms_api"]:
        return "real", "real"
    if set(kinds) == {"fixture", "firms_api"}:
        return "mixto", "mixto_real_fixture"
    return "desconocido", "+".join(kinds)


class Page(BaseModel):
    total: int
    limit: int
    offset: int
    items: list


class ErrorResponse(BaseModel):
    detail: str


# ------------------------------------------------------------------ health

@app.get("/api/health", tags=["sistema"])
def health() -> dict:
    store = _store()
    out: dict[str, Any] = {
        "version": __version__,
        "pais": "Paraguay",
        "nota": "punto caliente ≠ incendio confirmado",
        # scope explícito (Misión 005): el total del almacén es el ÁREA DE
        # CONSULTA (rectángulo FIRMS, incluye vecinos); lo nacional es solo
        # lo asignado al polígono ADM0. Nunca más un número sin etiqueta.
        "observaciones": store.observation_count(),
        "observaciones_scope": "area_consulta",
        "observaciones_nacionales": 0,
        "cuarentena": store.quarantine_count(),
        "eventos": 0,
        "geo_version_activa": store.geo_version_activa(),
        "data_source": _data_source(store),
    }
    try:
        _view(store, "observations_geo")
        out["observaciones_nacionales"] = store.query(
            "SELECT count(*) AS n FROM observations_geo WHERE dentro_pais"
        )[0]["n"]
    except HTTPException:
        out["observaciones_nacionales"] = None  # sin capa geo: indeterminado
    try:
        _view(store, "events")
        out["eventos"] = store.query("SELECT count(*) AS n FROM events")[0]["n"]
    except HTTPException:
        pass

    # Misión 009 §11: ventana, modo explícito, validación y limitaciones.
    modo, clasificacion = _modo_datos_desde_observaciones(store)
    out["modo_datos"] = modo
    out["clasificacion_datos"] = clasificacion
    try:
        _view(store, "observations")
        rango = store.query(
            "SELECT min(acq_date) AS d1, max(acq_date) AS d2, "
            "count(DISTINCT acq_date) AS nd FROM observations"
        )[0]
        out["cobertura_temporal"] = {
            "desde": str(rango["d1"]) if rango["d1"] else None,
            "hasta": str(rango["d2"]) if rango["d2"] else None,
            "dias": rango["nd"],
        }
    except HTTPException:
        out["cobertura_temporal"] = None
    out["ventana_piloto_objetivo"] = {
        "desde": "2026-11-04",
        "hasta": "2026-11-10",
        "zonahoraria": "UTC",
        "estado": "bloqueado_red_entorno",
    }
    if modo == "real":
        out["estado_validacion"] = (
            "datos reales en el almacén; validar con verificar_piloto.py (código 0) "
            "antes de cualquier análisis"
        )
    else:
        out["estado_validacion"] = (
            "solo validación offline sobre fixtures (M008/M009); SIN datos reales: "
            "piloto nacional FIRMS bloqueado por red en el entorno (ver mision_009)"
        )
    out["limitaciones"] = [
        "El total del almacén es el ÁREA DE CONSULTA (rectángulo FIRMS, incluye "
        "vecinos); lo nacional es solo el polígono ADM0.",
        "punto caliente ≠ incendio confirmado",
        "Sin modelo predictivo validado: sin predicciones.",
    ]
    return out


# ------------------------------------------------------------------ observations

_OBS_ORDER = {"acq_datetime_utc", "obs_id", "product", "latitude", "longitude"}


@app.get("/api/observations", response_model=Page, tags=["observaciones"])
def observations(
    product: str | None = None,
    sensor: str | None = None,
    satellite: str | None = None,
    date_from: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    departamento: str | None = None,
    dentro_pais: bool | None = None,
    order: str = "acq_datetime_utc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page:
    store = _store()
    base = "observations" if departamento is None and dentro_pais is None else None
    if base is None:
        _view(store, "observations_geo")
        tabla = "observations_geo"
        extra_where = []
        params: dict[str, Any] = {}
        if departamento is not None:
            extra_where.append("departamento = $departamento")
            params["departamento"] = departamento
        if dentro_pais is not None:
            extra_where.append("dentro_pais = $dentro_pais")
            params["dentro_pais"] = dentro_pais
        where_sql = (" AND " + " AND ".join(extra_where)) if extra_where else ""
    else:
        _view(store, "observations")
        tabla = "observations"
        where_sql = ""
        params = {}

    conds = []
    if product:
        conds.append("product = $product")
        params["product"] = product
    if sensor:
        conds.append("sensor = $sensor")
        params["sensor"] = sensor
    if satellite:
        conds.append("satellite = $satellite")
        params["satellite"] = satellite
    if date_from:
        conds.append("acq_date >= $date_from")
        params["date_from"] = date_from
    if date_to:
        conds.append("acq_date <= $date_to")
        params["date_to"] = date_to

    full_where = ""
    if conds or where_sql:
        partes = conds + [where_sql.replace(" AND ", "", 1) if where_sql else None]
        partes = [p for p in partes if p]
        full_where = " WHERE " + " AND ".join(partes)

    if order.lstrip("-") not in _OBS_ORDER:
        raise HTTPException(422, f"order debe ser uno de {sorted(_OBS_ORDER)}")
    desc = " DESC" if order.startswith("-") else ""

    total = store.query(
        f"SELECT count(*) AS n FROM {tabla}{full_where}", params
    )[0]["n"]
    rows = store.query(
        f"SELECT * FROM {tabla}{full_where} ORDER BY {order.lstrip('-')}{desc} "
        f"LIMIT $limit OFFSET $offset",
        {**params, "limit": limit, "offset": offset},
    )
    # serializar geometría WKB no: se excluye explícitamente
    for r in rows:
        r.pop("geometry", None)
        r.pop("quality_flags", None)
    return Page(total=total, limit=limit, offset=offset, items=rows)


@app.get("/api/observations/{obs_id}", tags=["observaciones"])
def observation(obs_id: str) -> dict:
    store = _store()
    _view(store, "observations")
    rows = store.query("SELECT * FROM observations WHERE obs_id = $id", {"id": obs_id})
    if not rows:
        raise HTTPException(404, f"observación {obs_id} inexistente")
    r = dict(rows[0])
    r.pop("geometry", None)
    # relaciones con otras detecciones (si hay eventos)
    try:
        _view(store, "event_observations")
        rel = store.query(
            "SELECT e.* FROM events e JOIN event_observations eo "
            "ON eo.event_id = e.event_id WHERE eo.obs_id = $id",
            {"id": obs_id},
        )
        r["eventos_relacionados"] = rel
    except HTTPException:
        r["eventos_relacionados"] = []
    return r


# ------------------------------------------------------------------ events

@app.get("/api/events", response_model=Page, tags=["eventos"])
def events(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)) -> Page:
    store = _store()
    _view(store, "events")
    total = store.query("SELECT count(*) AS n FROM events")[0]["n"]
    rows = store.query(
        "SELECT * FROM events ORDER BY primera_obs_utc LIMIT $l OFFSET $o",
        {"l": limit, "o": offset},
    )
    return Page(total=total, limit=limit, offset=offset, items=rows)


@app.get("/api/events/{event_id}", tags=["eventos"])
def event(event_id: str) -> dict:
    store = _store()
    _view(store, "events")
    rows = store.query("SELECT * FROM events WHERE event_id = $id", {"id": event_id})
    if not rows:
        raise HTTPException(404, f"evento {event_id} inexistente")
    out = dict(rows[0])
    _view(store, "event_observations")
    out["observaciones"] = store.query(
        "SELECT o.obs_id, o.product, o.sensor, o.satellite, o.acq_datetime_utc, "
        "o.latitude, o.longitude, o.frp, o.confidence "
        "FROM event_observations eo JOIN observations o ON o.obs_id = eo.obs_id "
        "WHERE eo.event_id = $id ORDER BY o.acq_datetime_utc",
        {"id": event_id},
    )
    return out


# ------------------------------------------------------------------ calendar

_GRAN = {
    "dia": "stats_nacional_dia",
    "semana": "stats_nacional_semana",
    "mes": "stats_nacional_mes",
}


@app.get("/api/calendar", tags=["calendario"])
def calendar(
    granularity: str = Query("dia", pattern="^(dia|semana|mes)$"),
    product: str | None = None,
) -> dict:
    """Series históricas NACIONALES (dentro_pais, vistas stats_nacional_*).

    El response declara su scope: acá solo entran observaciones asignadas al
    territorio paraguayo por la capa ADM0 — las detecciones de países vecinos
    que caen dentro del rectángulo de consulta quedan afuera.
    """
    store = _store()
    vista = _GRAN[granularity]
    _view(store, vista)
    if product:
        datos = store.query(
            f"SELECT * FROM {vista} WHERE product = $p ORDER BY 1", {"p": product}
        )
    else:
        datos = store.query(f"SELECT * FROM {vista} ORDER BY 1, 2")
    return {
        "scope": "nacional",
        "criterio": (
            "observaciones con dentro_pais=true (polígono ADM0, versión "
            f"{store.geo_version_activa() or 'desconocida'})"
        ),
        "granularity": granularity,
        "datos": datos,
    }


# ------------------------------------------------------------------ statistics

_SCOPE_CRITERIO = {
    "nacional": (
        "observaciones con dentro_pais=true: asignadas al polígono ADM0 de la "
        "capa geográfica activa. Las detecciones de Argentina/Brasil/Bolivia "
        "que caen dentro del rectángulo de consulta QUEDAN FUERA."
    ),
    "area_consulta": (
        "todas las observaciones del almacén (rectángulo de consulta FIRMS, "
        "incluye territorio de países vecinos)"
    ),
}


@app.get("/api/statistics", tags=["estadísticas"])
def statistics(
    by: str = Query("product", pattern="^(product|satellite|departamento)$"),
    scope: str = Query("nacional", pattern="^(nacional|area_consulta)$"),
) -> dict:
    """Estadísticas con scope territorial EXPLÍCITO.

    Antes (Misión 004) by=product|satellite contaba TODAS las observaciones
    del almacén — incluidas las de países vecinos que caen en el rectángulo
    de consulta — mientras by=departamento filtraba dentro_pais: una misma
    pantalla podía mostrar dos criterios incompatibles sin decirlo. Ahora el
    scope es un parámetro y viaja en cada respuesta.
    """
    store = _store()
    if by == "departamento" and scope != "nacional":
        raise HTTPException(
            422,
            "by=departamento solo tiene sentido con scope=nacional: los "
            "departamentos son unidades del territorio paraguayo.",
        )
    if scope == "nacional":
        # requiere capa geo: sin asignación territorial no hay "nacional"
        _view(store, "observations_geo")
        if by == "product":
            datos = store.query(
                "SELECT product, count(*) AS detecciones, "
                "round(sum(frp), 1) AS frp_total "
                "FROM observations_geo WHERE dentro_pais GROUP BY 1 ORDER BY 2 DESC"
            )
        elif by == "satellite":
            datos = store.counts_by_satellite(dentro_pais=True)
        else:
            _view(store, "stats_departamento_dia")
            datos = store.query(
                "SELECT departamento, count(*) AS detecciones, "
                "round(sum(frp_total), 1) AS frp_total "
                "FROM stats_departamento_dia GROUP BY 1 ORDER BY 2 DESC"
            )
    else:
        _view(store, "observations")
        if by == "product":
            datos = store.query(
                "SELECT product, count(*) AS detecciones, "
                "round(sum(frp), 1) AS frp_total "
                "FROM observations GROUP BY 1 ORDER BY 2 DESC"
            )
        elif by == "satellite":
            datos = store.counts_by_satellite()
        else:  # inalcanzable (validado arriba), defensa en profundidad
            raise HTTPException(422, "combinación inválida")
    return {"scope": scope, "criterio": _SCOPE_CRITERIO[scope], "by": by, "datos": datos}


# ------------------------------------------------------------------ quality

@app.get("/api/quality", tags=["calidad"])
def quality() -> dict:
    store = _store()
    out: dict[str, Any] = {
        "data_source": _data_source(store),
        "estados_ingesta": [],
        "cuarentena": store.quarantine_count(),
        "pares_candidatos": len(store.candidate_matches()),
    }
    try:
        _view(store, "ingest_status")
        out["estados_ingesta"] = store.status_counts()
    except HTTPException:
        pass
    s = _settings()
    from hotspots.provenance.manifests import ManifestStore

    mstore = ManifestStore(s.data_dir / "manifests")
    out["manifiestos"] = mstore.count()
    return out


# ------------------------------------------------------------------ geo

@app.get("/api/geo/departamentos", tags=["geografía"])
def geo_departamentos() -> JSONResponse:
    """GeoJSON de departamentos de la versión activa (para el mapa)."""
    s = _settings()
    capas = s.data_dir / "capas" / "departamentos.geojson"
    if not capas.exists():
        raise HTTPException(
            404, "capa de departamentos inexistente (corré 'hotspots geo export')"
        )
    return FileResponse(capas, media_type="application/geo+json")


@app.get("/api/geo/units", tags=["geografía"])
def geo_units(nivel: int = Query(1, ge=0, le=2)) -> list[dict]:
    s = _settings()
    store = _store()
    version = store.geo_version_activa()
    if not version:
        raise HTTPException(404, "sin capa geográfica activa (corré 'hotspots geo build')")
    from hotspots.geo.boundaries import BoundarySet

    pq = s.data_dir / "geo" / version / "unidades_admin.parquet"
    bs = BoundarySet.from_parquet(pq)
    return [
        {"admin_id": u.admin_id, "nombre": u.nombre, "padre": u.padre_admin_id}
        for u in bs.units
        if u.nivel == nivel
    ]


# ------------------------------------------------------------------ coverage

@app.get("/api/coverage", tags=["calidad"])
def coverage(
    date_from: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> dict:
    """Calendario de cobertura: distingue 'cero detecciones' de 'sin datos'.

    Estados por día: con_detecciones / cero_detecciones_asumido /
    solo_rechazadas_qc / sin_datos. La cobertura se infiere del intervalo de
    fechas observadas por producto (los supuestos viajan en la respuesta).
    """
    store = _store()
    _view(store, "observations")
    fechas = store.fechas_por_producto()
    if not fechas:
        raise HTTPException(404, "sin observaciones en el almacén")
    todas = sorted(f for s in fechas.values() for f in s)
    desde = date_from or todas[0]
    hasta = date_to or todas[-1]
    from hotspots.analysis.calendar import build_coverage_calendar

    cal = build_coverage_calendar(
        fechas_obs_por_producto=fechas,
        fechas_cuarentena_por_producto=store.fechas_cuarentena(),
        desde=desde,
        hasta=hasta,
    )
    cal["data_source"] = _data_source(store)
    cal["nota"] = (
        "cero_detecciones_asumido NO es lo mismo que sin_datos: el primero es "
        "un cero comparable dentro del intervalo cubierto; el segundo es un "
        "hueco que no debe entrar a ninguna serie estadística."
    )
    return cal


# ------------------------------------------------------------------ anomalías

@app.get("/api/anomalies", tags=["inteligencia"])
def anomalies(
    departamento: str | None = None,
    date_from: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    z: float = Query(3.0, ge=1.0, le=10.0),
) -> dict:
    """Anomalías de conteo diario. Requiere historia previa suficiente.

    La serie se construye con el CALENDARIO DE COBERTURA (Misión 005, §6.2):
    los días dentro del intervalo cubierto sin detecciones entran como 0
    (cero real), los días sin datos quedan FUERA (el detector los reporta
    como no evaluables) y los días con solo rechazos de QC tampoco se
    inventan como ceros. La respuesta incluye el resumen de cobertura y sus
    supuestos.
    """
    store = _store()
    _view(store, "observations_geo")  # las anomalías son NACIONALES por diseño
    conteos = store.conteos_por_fecha(departamento=departamento)
    if not conteos:
        raise HTTPException(
            404,
            "sin observaciones asignadas al territorio: no hay serie nacional "
            "(corré 'hotspots geo assign' primero)",
        )

    fechas = store.fechas_por_producto()
    todas = sorted(f for s in fechas.values() for f in s)
    desde_serie = min(todas[0], date_from)
    hasta_serie = max(todas[-1], date_to)

    from hotspots.analysis.calendar import build_coverage_calendar, serie_comparable

    cal = build_coverage_calendar(
        fechas_obs_por_producto=fechas,
        fechas_cuarentena_por_producto=store.fechas_cuarentena(),
        desde=desde_serie,
        hasta=hasta_serie,
    )
    serie, dias_excluidos = serie_comparable(conteos, cal)

    from hotspots.analysis.anomaly import InsufficientDataError, detect_anomalies

    try:
        rep = detect_anomalies(serie, eval_from=date_from, eval_to=date_to, z_threshold=z)
    except (InsufficientDataError, ValueError) as exc:
        raise HTTPException(422, f"no se puede evaluar: {exc}") from exc
    if rep.dias_evaluados == len(rep.no_evaluables) and not rep.anomalias:
        # nada evaluable: no devolvamos un 200 que aparente análisis
        raise HTTPException(
            422,
            "historia insuficiente: "
            + (rep.no_evaluables[0] if rep.no_evaluables else "serie vacía"),
        )
    rep.unidad = f"departamento: {departamento}" if departamento else "nacional"
    rep.datos_sinteticos = _data_source(_store()) == "fixture"
    out = rep.to_dict()
    out["cobertura"] = {
        "resumen": cal["resumen"],
        "supuestos": cal["supuestos"],
        "dias_excluidos_de_la_serie": dias_excluidos,
        "nota": (
            "los días cero_detecciones_asumido entraron a la serie como 0; "
            "los sin_datos y solo_rechazadas_qc quedaron fuera (ver /api/coverage)"
        ),
    }
    return out


# ------------------------------------------------------------------ dashboard

@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "dashboard no empaquetado")
    return FileResponse(index, media_type="text/html")


@app.exception_handler(HTTPException)
def http_error_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.status_code, "message": exc.detail}},
    )
