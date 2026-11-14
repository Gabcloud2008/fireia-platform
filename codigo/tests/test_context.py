"""Pruebas del módulo de contexto ambiental (Misión 006, Objetivo D).

Rejillas sintéticas diminutas: sin red, sin archivos externos.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from hotspots.analysis.context import (
    EnvVariableSpec,
    GridVariable,
    ObservacionPunto,
    _tamano_celda_m,
    asociar_contexto,
    cargar_registro_fuentes,
)

REPO = Path(__file__).resolve().parents[1]

SPEC_ERA5 = EnvVariableSpec(
    variable_id="era5land_t2m_test",
    fuente="test",
    producto="ERA5-Land",
    variable="temperatura 2m",
    unidad="K",
    resolucion_espacial="0.1° (~9 km)",
    resolucion_temporal="horaria",
    licencia="CC-BY 4.0",
)
SPEC_ESTATICA = EnvVariableSpec(
    variable_id="worldcover_test",
    fuente="test",
    producto="WorldCover 2021",
    variable="cobertura del suelo",
    unidad="categoría",
    resolucion_espacial="10 m",
    resolucion_temporal="estática (2021)",
    licencia="CC BY 4.0",
)


def _grid(
    spec: EnvVariableSpec = SPEC_ERA5,
    fecha: date | None = None,
    origen: tuple[float, float] = (-25.0, -60.0),
    paso: tuple[float, float] = (0.1, 0.1),
    valor: float = 300.0,
) -> GridVariable:
    fecha = fecha or date(2026, 7, 15)
    valores = [[valor for _ in range(5)] for _ in range(5)]
    return GridVariable(
        spec=spec, fecha=fecha, origen=origen, paso=paso, valores=valores
    )


class TestAsociacionCelda:
    def test_punto_dentro_de_rejilla(self):
        grid = _grid()
        obs = ObservacionPunto("obs-1", -24.95, -59.95, date(2026, 7, 15))
        ctx = asociar_contexto(obs, grid)
        assert ctx.tiene_valor
        assert ctx.valor == 300.0
        assert ctx.obs_id == "obs-1"
        assert ctx.variable_id == "era5land_t2m_test"
        assert ctx.metodo == "celda_nearest"
        assert ctx.celda_ij is not None

    def test_distancia_al_centro_de_celda_declarada(self):
        grid = _grid()
        # punto casi en el centro de la celda (0,0): centro (-24.95, -59.95)
        obs = ObservacionPunto("obs-2", -24.949, -59.949, date(2026, 7, 15))
        ctx = asociar_contexto(obs, grid)
        assert ctx.tiene_valor
        assert ctx.distancia_centro_m is not None
        assert ctx.distancia_centro_m < 500  # muy cerca del centro

    def test_resolucion_efectiva_no_hereda_la_del_punto(self):
        """Una detección 'de 375 m' sobre celda de 0.1° debe declarar ~11 km."""
        grid = _grid()
        obs = ObservacionPunto("obs-3", -24.7, -59.7, date(2026, 7, 15))
        ctx = asociar_contexto(obs, grid)
        ns, eo = ctx.resolucion_efectiva_m
        assert 10_000 < ns < 12_000  # 0.1° N-S ~ 11.1 km
        assert 9_500 < eo < 11_500  # 0.1° E-O a ~25°S ~ 10.1 km

    def test_punto_fuera_de_rejilla_sin_contexto(self):
        grid = _grid()
        obs = ObservacionPunto("obs-4", -19.0, -58.0, date(2026, 7, 15))
        ctx = asociar_contexto(obs, grid)
        assert not ctx.tiene_valor
        assert ctx.valor is None
        assert "fuera de la extensión" in (ctx.sin_contexto_motivo or "")

    def test_celda_sin_dato_none_con_motivo(self):
        valores = [[None for _ in range(5)] for _ in range(5)]
        grid = GridVariable(
            spec=SPEC_ERA5, fecha=date(2026, 7, 15),
            origen=(-25.0, -60.0), paso=(0.1, 0.1), valores=valores,
        )
        obs = ObservacionPunto("obs-5", -24.95, -59.95, date(2026, 7, 15))
        ctx = asociar_contexto(obs, grid)
        assert not ctx.tiene_valor
        assert ctx.sin_contexto_motivo == "celda sin dato"

    def test_fecha_incompatible_rechazada(self):
        grid = _grid(fecha=date(2026, 7, 15))
        obs = ObservacionPunto("obs-6", -24.95, -59.95, date(2026, 7, 16))
        ctx = asociar_contexto(obs, grid)
        assert not ctx.tiene_valor
        assert "fecha obs" in (ctx.sin_contexto_motivo or "")

    def test_variable_estatica_acepta_cualquier_fecha(self):
        """WorldCover es de 2021: una detección de 2026 SÍ puede usarla
        (la aproximación 'cobertura 2021' queda declarada en la fuente)."""
        grid = _grid(spec=SPEC_ESTATICA, fecha=date(2021, 1, 1))
        obs = ObservacionPunto("obs-7", -24.95, -59.95, date(2026, 7, 20))
        ctx = asociar_contexto(obs, grid)
        assert ctx.tiene_valor


class TestProcedencia:
    def test_la_procedencia_viaja_completa(self):
        grid = _grid()
        obs = ObservacionPunto("obs-8", -24.9, -59.9, date(2026, 7, 15))
        ctx = asociar_contexto(obs, grid)
        assert ctx.fuente == "test"
        assert ctx.producto == "ERA5-Land"
        assert ctx.unidad == "K"
        assert ctx.version == "1"

    def test_resoluciones_distintas_no_se_mezclan(self):
        """La misma detección sobre CHIRPS (0.05°) y ERA5-Land (0.1°) produce
        DOS registros con resoluciones distintas, no un promedio."""
        obs = ObservacionPunto("obs-9", -24.9, -59.9, date(2026, 7, 15))
        grid_era = _grid()
        spec_chirps = EnvVariableSpec(
            variable_id="chirps_test", fuente="test", producto="CHIRPS",
            variable="precipitación", unidad="mm/día",
            resolucion_espacial="0.05° (~5 km)", resolucion_temporal="diaria",
            licencia="libre con atribución",
        )
        grid_chirps = _grid(spec=spec_chirps, paso=(0.05, 0.05))
        ctx_era = asociar_contexto(obs, grid_era)
        ctx_chirps = asociar_contexto(obs, grid_chirps)
        assert ctx_era.resolucion_efectiva_m != ctx_chirps.resolucion_efectiva_m
        assert ctx_era.variable_id != ctx_chirps.variable_id


class TestTamanoCelda:
    def test_celdas_latlon_no_son_cuadradas_en_metros(self):
        ns, eo = _tamano_celda_m(-25.0, 0.1, 0.1)
        assert ns > eo  # a 25°S el ancho E-O es menor que el alto N-S

    def test_celda_10m_es_10m(self):
        ns, eo = _tamano_celda_m(-25.0, 0.00009, 0.00009)
        assert 9 < ns < 11 and 9 < eo < 11


class TestRegistroYaml:
    def test_el_registro_carga_y_trae_las_fichas(self):
        ruta = REPO / "configs" / "env_sources.yaml"
        specs = cargar_registro_fuentes(str(ruta))
        assert "era5land_t2m" in specs
        assert "chirps_precip_diaria" in specs
        assert "worldcover_clase_2021" in specs
        assert specs["era5land_t2m"].unidad == "K"
        assert specs["chirps_precip_diaria"].resolucion_temporal == "diaria"

    def test_el_registro_no_declara_ninguna_fuente_integrada(self):
        """Ninguna variable ambiental está integrada con datos reales todavía:
        el registro no debe afirmar lo contrario."""
        import yaml

        data = yaml.safe_load((REPO / "configs" / "env_sources.yaml").read_text())
        for fuente in data["fuentes"]:
            assert fuente["estado"] in {"investigada", "preparada"}, (
                f"{fuente['institucion']} declara estado {fuente['estado']}"
            )


class TestAppendOnly:
    def test_la_asociacion_no_toca_la_observacion(self):
        obs = ObservacionPunto("obs-10", -24.95, -59.95, date(2026, 7, 15))
        antes = (obs.lat, obs.lon, obs.fecha, obs.obs_id)
        asociar_contexto(obs, _grid())
        assert (obs.lat, obs.lon, obs.fecha, obs.obs_id) == antes
