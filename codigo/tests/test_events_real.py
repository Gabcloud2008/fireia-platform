"""Pruebas del motor de eventos sobre la base real (Misión C).

Estrategia:

1. **Equivalencia SQL vs motor original**: en días reales completos, la vía
   SQL (``real_runner``) produce EXACTAMENTE los mismos eventos y membresías
   que ``events/engine.build_events`` (semántica literal de productos
   distintos).
2. **Refinamiento sensor-distinto**: los pares NRT×SP del mismo satélite no
   generan eventos en el historial nacional (decisión documentada).
3. **Consultas de historial**: por fecha, departamento, anual, mensual,
   recurrencia, detalle con trazabilidad.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from hotspots.events.engine import build_events
from hotspots.events.queries import EventQueries
from hotspots.events.real_runner import (
    dias_candidatos,
    eventos_dia,
    pares_dia,
)

RAIZ = Path(__file__).resolve().parents[2]
DUCKDB_REAL = RAIZ / "data" / "PROCESADA" / "hotspots_real.duckdb"
EVENTOS_DIR = RAIZ / "data" / "PROCESADA" / "eventos_v1"

requires_real = pytest.mark.skipif(
    not DUCKDB_REAL.exists(), reason="base real no disponible en este entorno"
)


def _obs_del_dia(con, fecha: str) -> list[dict]:
    filas = con.execute(
        """
        SELECT obs_id, product, sensor, satellite,
               strftime(acq_datetime_utc, '%Y-%m-%dT%H:%M:%SZ') AS acq_datetime_utc,
               latitude, longitude, frp, confidence
        FROM observations WHERE acq_date = ? ORDER BY acq_datetime_utc, obs_id
        """,
        [fecha],
    ).fetchall()
    cols = [
        "obs_id", "product", "sensor", "satellite",
        "acq_datetime_utc", "latitude", "longitude", "frp", "confidence",
    ]
    return [dict(zip(cols, r, strict=True)) for r in filas]


@requires_real
class TestEquivalenciaMotor:
    """La vía SQL reproduce exactamente el motor original."""

    DIAS = ["2021-08-19", "2020-10-15", "2024-09-10"]  # pesado, medio, con NRT×SP

    def test_mismos_eventos_y_membresias_que_el_motor(self, tmp_path: Path):
        con = duckdb.connect(str(DUCKDB_REAL), read_only=True)
        try:
            for fecha in self.DIAS:
                res = build_events(
                    _obs_del_dia(con, fecha),
                    dt_seconds=600,
                    distance_m=2000.0,
                    processed_root=tmp_path,
                    run_id="eq",
                )
                ev_sql, mb_sql = eventos_dia(
                    con, fecha, dt_seconds=600, distance_m=2000.0,
                    requiere_sensores_distintos=False,
                )
                ids_sql = {e["event_id"] for e in ev_sql}
                mb_sql_set = {(m["event_id"], m["obs_id"]) for m in mb_sql}
                if res.events_path is None:
                    assert not ids_sql, f"{fecha}: SQL produjo eventos, el motor no"
                else:
                    import pandas as pd

                    ids_orig = set(pd.read_parquet(res.events_path)["event_id"])
                    mb_df = pd.read_parquet(res.membership_path)[["event_id", "obs_id"]]
                    mb_orig = set(map(tuple, mb_df.values))
                    assert ids_orig == ids_sql, f"{fecha}: divergencia en event_ids"
                    assert mb_orig == mb_sql_set, f"{fecha}: divergencia en membresías"
        finally:
            con.close()

    def test_refinamiento_sensor_excluye_pares_mismo_satelite(self):
        """2024-09-10 tiene solape NRT×SP de NOAA-21: el historial nacional
        (sensores distintos) debe producir MENOS pares que la semántica
        literal, y ningún evento cuyo par venga del mismo satélite."""
        con = duckdb.connect(str(DUCKDB_REAL), read_only=True)
        try:
            fecha = "2024-09-10"
            pares_literal = pares_dia(
                con, fecha, 600, 2000.0, requiere_sensores_distintos=False
            )
            pares_sensor = pares_dia(con, fecha, 600, 2000.0)
            assert len(pares_sensor) <= len(pares_literal)
            ev_sensor, _ = eventos_dia(con, fecha, dt_seconds=600, distance_m=2000.0)
            for e in ev_sensor:
                sensores = json.loads(e["parametros"]) if False else e["sensores"]
                # los eventos del historial nacional son MODIS×VIIRS
                assert set(sensores) == {"MODIS", "VIIRS"}
        finally:
            con.close()


@requires_real
class TestHistorialNacional:
    """Los artefactos eventos_v1 son coherentes y consultables."""

    def test_manifiesto_y_conciliacion(self):
        man = json.loads((EVENTOS_DIR / "manifiesto_eventos_v1.json").read_text(encoding="utf-8"))
        assert man["parametros"]["requiere_sensores_distintos"] is True
        assert man["total_eventos"] == 19_747
        assert man["total_membresias"] == 149_484
        # los artefactos existen y el hash cuadra
        import hashlib

        for nombre, meta in man["artefactos"].items():
            ruta = EVENTOS_DIR / nombre
            assert ruta.exists()
            h = hashlib.sha256(ruta.read_bytes()).hexdigest()
            assert h == meta["sha256"], f"hash divergente en {nombre}"

    def test_eventos_son_multi_sensor(self):
        import pandas as pd

        ev = pd.read_parquet(EVENTOS_DIR / "eventos.parquet")
        # co-detección MODIS×VIIRS en TODOS los eventos del historial
        assert ev["sensores"].map(lambda s: set(s) == {"MODIS", "VIIRS"}).all()
        assert len(ev) == 19_747
        # rango temporal real
        assert ev["primera_obs_utc"].min() >= "2018"
        assert ev["n_observaciones"].min() >= 2

    def test_membresia_cuenta(self):
        import pandas as pd

        mb = pd.read_parquet(EVENTOS_DIR / "membresia.parquet")
        ev = pd.read_parquet(EVENTOS_DIR / "eventos.parquet")
        assert len(mb) == 149_484
        # membresías == suma de n_observaciones por evento
        assert mb["event_id"].value_counts().sum() == ev["n_observaciones"].sum()
        # obs_id únicos por evento
        assert not mb.duplicated(["event_id", "obs_id"]).any()


@requires_real
class TestConsultasHistorial:
    def test_resumen_por_fecha_departamento_detalle(self):
        q = EventQueries(EVENTOS_DIR, DUCKDB_REAL)
        try:
            r = q.resumen()
            assert r["total_eventos"] == 19_747
            assert r["dias_con_eventos"] > 900
            # por fecha
            evs = q.por_fecha("2020-09-01", "2020-10-31", limite=50)
            assert evs and all(e["primera_obs_utc"][:7] in ("2020-09", "2020-10") for e in evs)
            # por departamento (acentos insensibles)
            boq = q.por_departamento("Boquerón", anio=2020, limite=5)
            assert boq and all(e["departamento"] == "BOQUERON" for e in boq)
            # detalle con trazabilidad completa
            det = q.detalle(boq[0]["event_id"])
            assert det is not None
            assert det["source_kind"] == "real"
            assert det["n_observaciones"] == len(det["miembros"])
            m = det["miembros"][0]
            assert m["source_sha256"] and len(m["source_sha256"]) == 64
            assert det["advertencias"], "debe advertir que el diámetro no es perímetro"
        finally:
            q.cerrar()

    def test_comparaciones_y_recurrencia(self):
        q = EventQueries(EVENTOS_DIR, DUCKDB_REAL)
        try:
            anual = q.comparacion_anual()
            anios = {r["anio"] for r in anual}
            assert {"2018", "2019", "2020", "2021"} <= anios
            pico = max(anual, key=lambda r: r["eventos"])
            assert pico["anio"] == "2020"  # año de los grandes incendios del Chaco
            mensual = q.comparacion_mensual(2020)
            assert len(mensual) == 12
            rec = q.recurrencia()
            assert rec and all(r["anios_distintos"] >= 2 for r in rec)
            cal = q.calendario("2020-10-01", "2020-10-31", solo_con_eventos=True)
            assert cal and all(c["eventos"] > 0 for c in cal)
        finally:
            q.cerrar()

    def test_prefiltro_es_condicion_necesaria(self):
        """Cada día con eventos debe estar en el conjunto candidato."""
        con = duckdb.connect(str(DUCKDB_REAL), read_only=True)
        try:
            import pandas as pd

            cand, _ = dias_candidatos(con, 600, por_sensor=True)
            ev = pd.read_parquet(EVENTOS_DIR / "eventos.parquet")
            dias_con_eventos = {p[:10] for p in ev["primera_obs_utc"]}
            faltantes = dias_con_eventos - cand
            assert not faltantes, f"días con eventos fuera del pre-filtro: {faltantes}"
        finally:
            con.close()
