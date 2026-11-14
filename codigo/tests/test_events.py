"""Pruebas del motor de eventos de co-detección (Misión 004, etapa 5).

Escenarios sintéticos:

- Un fuego visto por MODIS y VIIRS casi simultáneo -> 1 evento.
- Dos fuegos lejanos simultáneos -> 2 eventos.
- Detecciones de un solo producto -> NO forman evento (nivel 1).
- Cadena temporal (A-B-C dentro de la ventana por pares) -> 1 evento
  (componente conexa), aunque el extremo A-C exceda la ventana.
- Determinismo e idempotencia de event_id.
- Consistencia con la vista candidate_matches (mismos pares en Python y SQL).
"""

from __future__ import annotations

from datetime import datetime, timezone

from hotspots.events.engine import build_events, equirect_distance_m
from hotspots.storage.duckdb_store import DuckDBStore


def _ts_min(base: str, minutes: float) -> str:
    dt = datetime.strptime(base, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    from datetime import timedelta

    return (dt + timedelta(minutes=minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _obs(oid, product, ts, lat, lon, frp=10.0, sensor=None, satellite="T", confidence="80"):
    return {
        "obs_id": oid,
        "product": product,
        "sensor": sensor or ("MODIS" if "MODIS" in product else "VIIRS"),
        "satellite": satellite,
        "acq_datetime_utc": ts,
        "latitude": lat,
        "longitude": lon,
        "frp": frp,
        "confidence": confidence,
    }


BASE = "2026-09-10T13:30:00Z"
# Asunción aprox.
LAT, LON = -25.28, -57.63


def _offset_m(lat_m=0.0, lon_m=0.0):
    """Desplazamiento en metros -> delta de grados."""
    return lat_m / 111320.0, lon_m / (111320.0 * 0.9)  # ~cos(25°)


def test_evento_simple_dos_productos(tmp_path):
    dlat, dlon = _offset_m(lon_m=300)
    obs = [
        _obs("m1", "MODIS_NRT", BASE, LAT, LON, frp=40.0, satellite="T", confidence="80"),
        _obs("v1", "VIIRS_NOAA20_NRT", _ts_min(BASE, 4), LAT + dlat, LON + dlon,
             frp=25.0, satellite="1", confidence="h"),
    ]
    res = build_events(obs, processed_root=tmp_path, run_id="r1")
    assert res.eventos == 1
    assert res.pares_candidatos == 1
    assert res.observaciones_en_eventos == 2


def test_dos_fuegos_separados_dos_eventos(tmp_path):
    dlat, dlon = _offset_m(lon_m=300)
    obs = [
        # fuego 1 en Asunción
        _obs("m1", "MODIS_NRT", BASE, LAT, LON),
        _obs("v1", "VIIRS_NOAA20_NRT", _ts_min(BASE, 4), LAT + dlat, LON + dlon),
        # fuego 2 a ~50 km
        _obs("m2", "MODIS_NRT", BASE, LAT + 0.5, LON),
        _obs("v2", "VIIRS_NOAA20_NRT", _ts_min(BASE, 4), LAT + 0.5, LON + dlon),
    ]
    res = build_events(obs, processed_root=tmp_path, run_id="r1")
    assert res.eventos == 2
    assert res.pares_candidatos == 2


def test_sin_pareja_no_hay_evento(tmp_path):
    obs = [
        _obs("m1", "MODIS_NRT", BASE, LAT, LON),
        _obs("m2", "MODIS_NRT", _ts_min(BASE, 1), LAT, LON),
    ]
    res = build_events(obs, processed_root=tmp_path, run_id="r1")
    assert res.eventos == 0
    assert res.observaciones_en_eventos == 0
    assert res.escritas is False


def test_cadena_temporal_una_componente(tmp_path):
    """MODIS 13:30 -> VIIRS 13:38 -> MODIS 13:45: cadena de pares -> 1 evento."""
    dlat, dlon = _offset_m(lon_m=200)
    obs = [
        _obs("m1", "MODIS_NRT", BASE, LAT, LON),
        _obs("v1", "VIIRS_NOAA20_NRT", _ts_min(BASE, 8), LAT + dlat, LON + dlon),
        # a 17 min del primero (fuera de 600s) pero a 9 del segundo: entra por cadena
        _obs("m2", "MODIS_NRT", _ts_min(BASE, 17), LAT, LON),
    ]
    res = build_events(obs, processed_root=tmp_path, run_id="r1")
    assert res.pares_candidatos == 2
    assert res.eventos == 1
    assert res.observaciones_en_eventos == 3


def test_event_id_determinista_y_snapshot(tmp_path):
    dlat, dlon = _offset_m(lon_m=300)
    obs = [
        _obs("m1", "MODIS_NRT", BASE, LAT, LON),
        _obs("v1", "VIIRS_NOAA20_NRT", _ts_min(BASE, 4), LAT + dlat, LON + dlon),
    ]
    r1 = build_events(obs, processed_root=tmp_path, run_id="r1",
                      created_at_utc="2026-01-01T00:00:00Z")
    r2 = build_events(obs, processed_root=tmp_path, run_id="r2",
                      created_at_utc="2026-01-02T00:00:00Z")
    import pyarrow.parquet as pq

    t1 = pq.read_table(r1.events_path).to_pydict()
    t2 = pq.read_table(r2.events_path).to_pydict()
    assert t1["event_id"] == t2["event_id"]  # mismo contenido -> mismo id
    # el snapshot nuevo es el último; el viejo queda como evidencia
    from hotspots.events.engine import events_files

    assert len(events_files(tmp_path)) == 2


def test_umbral_distancia_excluye(tmp_path):
    # 3 km de distancia: fuera del umbral default de 2000 m
    dlat, dlon = _offset_m(lon_m=3000)
    obs = [
        _obs("m1", "MODIS_NRT", BASE, LAT, LON),
        _obs("v1", "VIIRS_NOAA20_NRT", BASE, LAT + dlat, LON + dlon),
    ]
    assert equirect_distance_m(LAT, LON, LAT + dlat, LON + dlon) > 2000
    res = build_events(obs, processed_root=tmp_path, run_id="r1")
    assert res.eventos == 0
    # con umbral más ancho, aparece
    res2 = build_events(obs, distance_m=5000, processed_root=tmp_path, run_id="r2")
    assert res2.eventos == 1


def test_campos_del_evento(tmp_path):
    dlat, dlon = _offset_m(lon_m=300)
    obs = [
        _obs("m1", "MODIS_NRT", BASE, LAT, LON, frp=40.0),
        _obs("v1", "VIIRS_NOAA20_NRT", _ts_min(BASE, 4), LAT + dlat, LON + dlon, frp=25.0),
    ]
    res = build_events(obs, processed_root=tmp_path, run_id="r1")
    import pyarrow.parquet as pq

    ev = pq.read_table(res.events_path).to_pydict()
    assert ev["n_observaciones"][0] == 2
    assert set(ev["productos"][0]) == {"MODIS_NRT", "VIIRS_NOAA20_NRT"}
    assert ev["duracion_segundos"][0] == 4 * 60
    assert ev["frp_total"][0] == 65.0
    assert ev["frp_max"][0] == 40.0
    assert 0 < ev["dispersion_metros"][0] < 500  # ~300 m, no es perímetro


def test_consistencia_con_vista_sql(tmp_path):
    """El motor Python y la vista candidate_matches deben producir los mismos pares."""
    from hotspots.config import Settings
    from hotspots.ingestion.pipeline import run_ingest

    settings = Settings.load(env={}, env_file=None, data_dir=tmp_path / "data")
    (tmp_path / "data").mkdir(exist_ok=True)

    # MODIS y VIIRS el mismo minuto, a ~200 m
    dlat, dlon = _offset_m(lon_m=200)
    modis_csv = (
        "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_t31,frp,daynight\n"
        f"{LAT},{LON},320.1,1.2,1.2,2026-09-10,1330,T,MODIS,85,6.1,300.5,40.0,D\n"
    )
    viirs_csv = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_ti5,frp,daynight\n"
        f"{LAT + dlat},{LON + dlon},305.0,0.4,0.4,2026-09-10,1334,1,VIIRS,h,2,290.5,25.0,D\n"
    )
    (tmp_path / "m.csv").write_text(modis_csv, encoding="utf-8")
    (tmp_path / "v.csv").write_text(viirs_csv, encoding="utf-8")
    run_ingest(settings, mode="fixture", product="MODIS_NRT", fixture_path=tmp_path / "m.csv")
    run_ingest(
        settings, mode="fixture", product="VIIRS_NOAA20_NRT", fixture_path=tmp_path / "v.csv"
    )

    duck = DuckDBStore(
        tmp_path / "data" / "processed" / "hotspots.duckdb",
        tmp_path / "data" / "processed",
    )
    pares_sql = duck.candidate_matches()
    assert len(pares_sql) == 1

    obs = duck.query(
        "SELECT obs_id, product, sensor, satellite, acq_datetime_utc, "
        "latitude, longitude, frp, confidence FROM observations"
    )
    res = build_events(
        obs, processed_root=tmp_path / "data" / "processed", run_id="r1"
    )
    assert res.pares_candidatos == len(pares_sql) == 1
    assert res.eventos == 1

    # y las vistas de eventos quedan servidas
    duck.refresh()
    ev = duck.query("SELECT * FROM events")
    assert len(ev) == 1
    members = duck.query("SELECT * FROM event_observations")
    assert len(members) == 2


# ------------------------------------------------------------------ v2 (Misión 005)


def test_cadena_transitiva_con_alerta(tmp_path):
    """A-B-C-D encadenados: UN evento (por reachabilidad) con alerta visible.

    Cada eslabón cumple los umbrales (600 s / 2000 m), pero el evento completo
    los desborda: diámetro y duración superan 2x los parámetros. La semántica
    de agrupamiento NO cambia; la alerta lo hace visible.
    """
    import datetime as dt

    base = dt.datetime(2026, 9, 20, 13, 0, 0)
    dlat = 1900.0 / 111320.0  # ~1.9 km por eslabón (margen del umbral de 2 km)

    obs = []
    for i, (prod, sat) in enumerate(
        [
            ("MODIS_NRT", "T"),
            ("VIIRS_NOAA20_NRT", "1"),
            ("MODIS_NRT", "A"),
            ("VIIRS_NOAA20_NRT", "2"),
        ]
    ):
        t_i = base + dt.timedelta(seconds=550 * i)  # < 600 s entre eslabones
        obs.append(
            {
                "obs_id": f"e{i}",
                "product": prod,
                "sensor": "MODIS" if prod.startswith("MODIS") else "VIIRS",
                "satellite": sat,
                "acq_datetime_utc": t_i.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "latitude": -25.0 + dlat * i,
                "longitude": -57.5,
                "frp": 10.0 + i,
                "confidence": "h",
            }
        )
    r = build_events(obs, processed_root=tmp_path, run_id="cadena")
    assert r.eventos == 1
    import pyarrow.parquet as pq

    fila = pq.read_table(r.events_path).to_pydict()
    assert fila["n_observaciones"][0] == 4
    # ~5.7 km de diámetro (> 2x2000) y ~1650 s de duración (> 2x600): alerta
    assert fila["diametro_metros"][0] > 4000
    assert fila["duracion_segundos"][0] > 1200
    assert fila["alerta_encadenamiento"][0] is True


def test_evento_compacto_sin_alerta(tmp_path):
    """El evento normal (2 observaciones cerca) no levanta alertas falsas."""
    dlat = 500.0 / 111320.0
    obs = [
        {
            "obs_id": "m1", "product": "MODIS_NRT", "sensor": "MODIS", "satellite": "T",
            "acq_datetime_utc": "2026-09-20T13:00:00Z",
            "latitude": -25.0, "longitude": -57.5, "frp": 30.0, "confidence": "h",
        },
        {
            "obs_id": "v1", "product": "VIIRS_NOAA20_NRT", "sensor": "VIIRS", "satellite": "1",
            "acq_datetime_utc": "2026-09-20T13:00:05Z",
            "latitude": -25.0 + dlat, "longitude": -57.5, "frp": 20.0, "confidence": "h",
        },
    ]
    r = build_events(obs, processed_root=tmp_path, run_id="compacto")
    assert r.eventos == 1
    import json as _json

    import pyarrow.parquet as pq

    fila = pq.read_table(r.events_path).to_pydict()
    assert fila["alerta_encadenamiento"][0] is False
    # FRP desglosado por producto: la suma total no se presenta como potencia
    frp_prod = _json.loads(fila["frp_por_producto"][0])
    assert frp_prod == {"MODIS_NRT": 30.0, "VIIRS_NOAA20_NRT": 20.0}
    assert fila["frp_total"][0] == 50.0  # agregado documentado, no física


def test_metodo_v2_versionado():
    from hotspots.events.engine import EVENTS_METHOD

    assert EVENTS_METHOD == "co_detection_component_v2"
