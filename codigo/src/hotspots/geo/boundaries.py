"""Unidades administrativas de Paraguay: carga, validación y point-in-polygon.

Fuente inicial: geoBoundaries gbOpen (PRY ADM0/ADM1/ADM2), CC BY 4.0, geometría
original de la DGEEC (Paraguay). Diseño de la Misión 003 (doc 03), implementado
acá sin cambios de concepto:

- Los archivos GeoJSON originales quedan intactos como evidencia en
  ``data/geo/<version>/source/`` con su SHA256 en el manifiesto.
- La tabla operativa es ``unidades_admin.parquet`` (WKB, OGC:CRS84).
- ``admin_id`` es estable y versionado: ``<version>:ADM1:ALTO-PARAGUAY``.
- El enlace distrito→departamento NO viene en la fuente (los GeoJSON de
  geoBoundaries no traen campo padre): se DERIVA con el punto representativo
  de cada distrito contra los polígonos ADM1, y queda documentado como
  relación derivada en el propio parquet (columna ``padre_derivado``).
- Convención de frontera: un punto SOBRE el límite cuenta como dentro
  (``covers``). Es una convención nuestra, documentada; la fuente no define
  semántica de borde.

La geometría real la maneja Shapely (multipolígonos, huecos, índice espacial
STRtree y geometrías preparadas). Improvisar ray-casting propio con esta
complejidad disponible sería elegir la versión peor probada.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from shapely import wkb as shapely_wkb
from shapely.geometry import shape
from shapely.prepared import prep
from shapely.strtree import STRtree
from shapely.validation import make_valid

#: Niveles administrativos que soportamos.
LEVELS = ("ADM0", "ADM1", "ADM2")

#: Esquemas de propiedades de los GeoJSON fuente soportados (Misión 007).
#:
#: - ``geoboundaries``: ``shapeName`` / ``shapeID`` (gbOpen PRY; sin campo
#:   padre en la fuente → el padre se DERIVA espacialmente).
#: - ``codab``: ``adm{N}_name`` / ``adm{N}_pcode`` + ``adm1_name`` como padre
#:   EXPLÍCITO de cada distrito (OCHA COD-AB, redistribución de la cartografía
#:   INE 2022; el padre viene en la fuente y se verifica espacialmente).
SOURCE_SCHEMAS = {
    "geoboundaries": {
        "name_prop": "shapeName",
        "id_prop": "shapeID",
        "parent_prop": None,
    },
    "codab": {
        "name_prop": "adm{nivel}_name",
        "id_prop": "adm{nivel}_pcode",
        "parent_prop": "adm1_name",
    },
}

#: Conteos esperados para Paraguay (validación de activación).
#: ADM2 = 247 es el inventario de la FUENTE geoBoundaries gbOpen (capa que
#: representa el año 2012, geometría DGEEC), NO el número oficial de distritos
#: del INE Revisión 2025 (263, incluyendo Asunción). Validar contra 247
#: detecta truncamientos/corrupciones de la capa; la discrepancia territorial
#: está documentada en docs/cartografia.md y configs/geo_sources.yaml.
EXPECTED_PRY = {"ADM0": 1, "ADM1": 18, "ADM2": 247}

_SCHEMA_FIELDS = [
    ("admin_id", pa.string()),
    ("shape_id", pa.string()),
    ("nombre", pa.string()),
    ("nivel", pa.int8()),
    ("padre_admin_id", pa.string()),
    ("padre_derivado", pa.bool_()),
    ("bbox_w", pa.float64()),
    ("bbox_s", pa.float64()),
    ("bbox_e", pa.float64()),
    ("bbox_n", pa.float64()),
    ("geometry", pa.binary()),
]


class GeoError(Exception):
    """Error de la capa geográfica (fuente inválida, validación, formato)."""


def _slug(nombre: str) -> str:
    """Normaliza un nombre a identificador estable (mayúsculas, sin acentos)."""
    norm = unicodedata.normalize("NFKD", nombre)
    sin_acento = "".join(c for c in norm if not unicodedata.combining(c))
    slug = re.sub(r"[^A-Za-z0-9]+", "-", sin_acento.strip()).strip("-")
    return slug.upper()


@dataclass
class AdminUnit:
    admin_id: str
    shape_id: str
    nombre: str
    nivel: int  # 0 = país, 1 = departamento, 2 = distrito
    geometry: object  # shapely geometry (Polygon | MultiPolygon)
    padre_admin_id: str | None = None
    padre_derivado: bool = False

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        w, s, e, n = self.geometry.bounds
        return (w, s, e, n)


@dataclass
class BoundarySet:
    """Conjunto versionado de unidades administrativas + índice espacial."""

    version: str
    units: list[AdminUnit] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ build
    @classmethod
    def from_geojson_files(
        cls,
        version: str,
        adm0_path: str | Path,
        adm1_path: str | Path,
        adm2_path: str | Path,
        *,
        source_meta: dict | None = None,
        schema: str = "geoboundaries",
    ) -> BoundarySet:
        """Carga los tres niveles y resuelve el padre de cada distrito.

        ``schema`` selecciona el esquema de propiedades del GeoJSON fuente
        (:data:`SOURCE_SCHEMAS`). Con ``geoboundaries`` (default) el padre se
        deriva espacialmente; con ``codab`` se usa el campo explícito de la
        fuente (``adm1_name``) y se verifica espacialmente — las divergencias
        quedan registradas en ``meta`` (no se descartan en silencio).

        Las geometrías inválidas se reparan con ``make_valid`` (conserva el
        área). El conteo de reparaciones se registra ANTES de reparar: las
        métricas del meta reflejan tanto el estado ORIGINAL (cuántas llegaron
        inválidas de la fuente) como el estado FINAL (todas válidas tras la
        reparación). Cada reparación queda identificada por unidad.
        """
        if schema not in SOURCE_SCHEMAS:
            raise GeoError(
                f"Esquema de fuente desconocido: {schema!r} "
                f"(soportados: {', '.join(sorted(SOURCE_SCHEMAS))})"
            )
        cfg = SOURCE_SCHEMAS[schema]
        explicit_prop = cfg["parent_prop"]
        units: list[AdminUnit] = []
        by_level: dict[str, list[AdminUnit]] = {}
        reparaciones: list[dict] = []
        explicit_padres: list[tuple[AdminUnit, str | None]] = []
        for nivel, path in (("ADM0", adm0_path), ("ADM1", adm1_path), ("ADM2", adm2_path)):
            feats = _read_features(Path(path))
            # "adm{nivel}_name" con el DÍGITO del nivel: adm0/adm1/adm2_name
            name_prop = cfg["name_prop"].format(nivel=nivel[-1])
            id_prop = cfg["id_prop"].format(nivel=nivel[-1])
            level_units = []
            for f in feats:
                props = f["properties"] or {}
                nombre = str(props.get(name_prop, "")).strip()
                if not nombre:
                    raise GeoError(f"{path}: feature sin {name_prop}")
                geom = shape(f["geometry"])
                if geom.geom_type not in ("Polygon", "MultiPolygon"):
                    raise GeoError(f"{path}: geometría {geom.geom_type} no soportada")
                if geom.is_empty:
                    raise GeoError(f"{path}: geometría vacía en {nombre!r}")
                if not geom.is_valid:
                    # registro ANTES de reparar: la incidencia original no se
                    # pierde — cada reparación es auditable por unidad.
                    from shapely.validation import explain_validity
                    reparaciones.append(
                        {
                            "admin_id": f"{version}:{nivel}:{_slug(nombre)}",
                            "nivel": nivel,
                            "nombre": nombre,
                            "motivo_original": explain_validity(geom),
                        }
                    )
                    geom = make_valid(geom)
                unit = AdminUnit(
                    admin_id=f"{version}:{nivel}:{_slug(nombre)}",
                    shape_id=str(props.get(id_prop, "")),
                    nombre=nombre,
                    nivel=LEVELS.index(nivel),
                    geometry=geom,
                )
                level_units.append(unit)
                if nivel == "ADM2" and explicit_prop:
                    explicit_padres.append(
                        (unit, str(props.get(explicit_prop, "") or "").strip() or None)
                    )
            by_level[nivel] = level_units
            units.extend(level_units)

        bs = cls(version=version, units=units, meta=dict(source_meta or {}))
        bs.meta["geometrias_invalidas_originales"] = len(reparaciones)
        bs.meta["geometrias_reparadas"] = len(reparaciones)
        bs.meta["detalle_reparaciones"] = reparaciones
        bs.meta["esquema_fuente"] = schema
        if explicit_prop:
            bs._assign_parents_explicit(by_level, explicit_padres, parent_prop=explicit_prop)
        else:
            bs._derive_parents(by_level)
        bs._desambiguar_ids_duplicados(by_level)
        bs._build_index()
        return bs

    def _derive_parents(self, by_level: dict[str, list[AdminUnit]]) -> None:
        """ADM0←ADM1←ADM2. El padre de los distritos se deriva espacialmente.

        Nota: el conteo de geometrías reparadas NO se hace acá (las geometrías
        ya llegan reparadas de ``from_geojson_files``): viviría siempre en 0.
        El registro real — estado original + reparación por unidad — está en
        ``meta['detalle_reparaciones']``, calculado ANTES de reparar.
        """
        pais = by_level["ADM0"][0]
        adm1 = by_level["ADM1"]
        for u in adm1:
            u.padre_admin_id = pais.admin_id
        tree_adm1 = STRtree([u.geometry for u in adm1])
        for dist in by_level["ADM2"]:
            rp = dist.geometry.representative_point()
            padre: AdminUnit | None = None
            for idx in tree_adm1.query(rp):
                cand = adm1[int(idx)]
                if cand.geometry.covers(rp):
                    padre = cand
                    break
            if padre is None:
                raise GeoError(
                    f"Distrito {dist.nombre!r} no cae dentro de ningún departamento "
                    "(¿geometrías inconsistentes entre ADM1 y ADM2?)"
                )
            dist.padre_admin_id = padre.admin_id
            dist.padre_derivado = True

    def _assign_parents_explicit(
        self,
        by_level: dict[str, list[AdminUnit]],
        explicit_padres: list[tuple[AdminUnit, str | None]],
        *,
        parent_prop: str,
    ) -> None:
        """Padres declarados por la fuente (esquema ``codab``) + verificación.

        El padre de cada distrito se toma del campo explícito de la fuente
        (``parent_prop``, p. ej. ``adm1_name``). Se verifica espacialmente con
        el punto representativo: divergencias y huérfanos quedan registrados en
        ``meta`` para la auditoría — nunca se descartan en silencio.

        - ``padres_explicitos_usados``: distritos cuyo padre vino en la fuente.
        - ``padres_derivados_fallback``: distritos sin padre utilizable en la
          fuente (campo vacío o sin match) → padre derivado espacialmente y
          marcado ``padre_derivado=True``.
        - ``inconsistencias_padre_explicito_vs_espacial``: distritos donde el
          padre explícito y el espacial NO coinciden (se conserva el explícito).
        """
        pais = by_level["ADM0"][0]
        adm1 = by_level["ADM1"]
        for u in adm1:
            u.padre_admin_id = pais.admin_id
        tree_adm1 = STRtree([u.geometry for u in adm1])
        por_slug = {_slug(u.nombre): u for u in adm1}

        def _espacial(dist: AdminUnit) -> AdminUnit | None:
            rp = dist.geometry.representative_point()
            for idx in tree_adm1.query(rp):
                cand = adm1[int(idx)]
                if cand.geometry.covers(rp):
                    return cand
            return None

        usados = 0
        fallback = 0
        inconsistencias: list[dict] = []
        for dist, pname in explicit_padres:
            padre_exp = por_slug.get(_slug(pname)) if pname else None
            padre_esp = _espacial(dist)
            if padre_esp is None:
                raise GeoError(
                    f"Distrito {dist.nombre!r} no cae dentro de ningún departamento "
                    "(¿geometrías inconsistentes entre ADM1 y ADM2?)"
                )
            if padre_exp is None:
                # campo ausente/vacío o sin match: fallback espacial marcado
                dist.padre_admin_id = padre_esp.admin_id
                dist.padre_derivado = True
                fallback += 1
                continue
            dist.padre_admin_id = padre_exp.admin_id
            dist.padre_derivado = False
            usados += 1
            if padre_exp.admin_id != padre_esp.admin_id:
                inconsistencias.append(
                    {
                        "admin_id": dist.admin_id,
                        "nombre": dist.nombre,
                        f"padre_{parent_prop}": padre_exp.nombre,
                        "padre_espacial": padre_esp.nombre,
                    }
                )
        self.meta["padres_explicitos_usados"] = usados
        self.meta["padres_derivados_fallback"] = fallback
        self.meta["inconsistencias_padre_explicito_vs_espacial"] = inconsistencias

    def _desambiguar_ids_duplicados(self, by_level: dict[str, list[AdminUnit]]) -> None:
        """IDs únicos ante nombres repetidos dentro de un nivel (Misión 007).

        La capa INE 2022 tiene DOS distritos llamados "Bella Vista" (Amambay
        e Itapúa): el slug del nombre solo no identifica. Ante una colisión de
        ``admin_id`` dentro de un nivel se recalifica el ID con el slug del
        padre (ADM2: departamento); si el padre no distingue (ADM1: mismo
        país), con el ``shape_id`` de la fuente.

        Los IDs SIN colisión no cambian: la capa 2012 y sus referencias
        (``obs_geo``, eventos) quedan intactas. La colisión de NOMBRES sigue
        reportándose en la auditoría (``nombre_duplicado_en_nivel``): es un
        hecho de la fuente, no un error.
        """
        for nivel, unidades in by_level.items():
            por_slug: dict[str, list[AdminUnit]] = {}
            for u in unidades:
                por_slug.setdefault(_slug(u.nombre), []).append(u)
            for slug, grupo in por_slug.items():
                if len(grupo) == 1:
                    continue
                for u in grupo:
                    if u.nivel == 2 and u.padre_admin_id:
                        padre_slug = u.padre_admin_id.rsplit(":", 1)[-1]
                        u.admin_id = f"{self.version}:ADM2:{slug}--{padre_slug}"
                    else:
                        sufijo = u.shape_id or "SIN-ID"
                        u.admin_id = f"{self.version}:{nivel}:{slug}--{sufijo}"

    # ------------------------------------------------------------------ index
    def _build_index(self) -> None:
        self._pais = next((u for u in self.units if u.nivel == 0), None)
        if self._pais is None:
            raise GeoError("No hay unidad ADM0 en el conjunto")
        self._pais_prep = prep(self._pais.geometry)
        self._adm1 = [u for u in self.units if u.nivel == 1]
        self._adm2 = [u for u in self.units if u.nivel == 2]
        self._tree1 = STRtree([u.geometry for u in self._adm1])
        self._tree2 = STRtree([u.geometry for u in self._adm2])

    # ------------------------------------------------------------- consultas
    def inside_country(self, lon: float, lat: float) -> bool:
        """Pertenencia al polígono ADM0. Borde cuenta como dentro (covers)."""
        return bool(self._pais_prep.covers(_pt(lon, lat)))

    def assign(self, lon: float, lat: float) -> dict:
        """Asignación completa de un punto: país, departamento y distrito.

        Devuelve ``{dentro_pais, admin1_id, admin2_id}``. Un punto fuera del
        país tiene departamentos null (aunque caiga en el bbox de consulta).
        """
        p = _pt(lon, lat)
        if not self._pais_prep.covers(p):
            return {"dentro_pais": False, "admin1_id": None, "admin2_id": None}
        a1 = self._cover(self._tree1, self._adm1, p)
        a2 = self._cover(self._tree2, self._adm2, p) if a1 else None
        return {
            "dentro_pais": True,
            "admin1_id": a1.admin_id if a1 else None,
            "admin2_id": a2.admin_id if a2 else None,
        }

    @staticmethod
    def _cover(tree: STRtree, units: list[AdminUnit], p) -> AdminUnit | None:
        for idx in tree.query(p):
            u = units[int(idx)]
            if u.geometry.covers(p):
                return u
        return None

    def counts(self) -> dict[str, int]:
        out = {"ADM0": 0, "ADM1": 0, "ADM2": 0}
        for u in self.units:
            out[LEVELS[u.nivel]] += 1
        return out

    def validate(self, expected: dict[str, int] | None = None) -> None:
        """Valida conteos por nivel. Falla si no coincide con lo esperado."""
        exp = expected or EXPECTED_PRY
        got = self.counts()
        for lvl, want in exp.items():
            if got.get(lvl) != want:
                raise GeoError(
                    f"Validación de límites falló: {lvl} esperado={want}, "
                    f"obtenido={got.get(lvl)}. No activamos una fuente que no "
                    "cuadra con el inventario declarado de la fuente "
                    "(ver docs/cartografia.md para la discrepancia 247 vs 263)."
                )

    # ------------------------------------------------------------- auditoría
    def audit(self, *, overlap_tol_m2: float = 1000.0) -> dict:
        """Auditoría geométrica completa del conjunto. NO corrige nada.

        Devuelve un reporte con hallazgos clasificados. Cada hallazgo registra
        las unidades involucradas: nada se descarta ni se repara silenciosamente.

        ``overlap_tol_m2``: área mínima (m²) de una superposición para contarla
        como hallazgo — por debajo se considera ruido de digitalización
        (sliver). Aproximación equirectangular local, suficiente para esto.
        """
        hallazgos: list[dict] = []

        def add(tipo: str, detalle: str, gravedad: str, unidades: list[str]) -> None:
            hallazgos.append(
                {"tipo": tipo, "gravedad": gravedad, "detalle": detalle, "unidades": unidades}
            )

        # 1. vacías / inválidas (tras reparación deberían ser 0; si no, registrar)
        for u in self.units:
            if u.geometry.is_empty:
                add("geometria_vacia", f"{u.nombre} ({LEVELS[u.nivel]})", "critica", [u.admin_id])
            elif not u.geometry.is_valid:
                add(
                    "geometria_invalida_residual",
                    f"{u.nombre} sigue inválida tras make_valid",
                    "critica",
                    [u.admin_id],
                )

        # 2. duplicados por admin_id / shape_id / nombre dentro del nivel
        for campo in ("admin_id", "shape_id"):
            vistos: dict[str, AdminUnit] = {}
            for u in self.units:
                val = getattr(u, campo)
                if not val:
                    continue
                if val in vistos:
                    add(
                        f"{campo}_duplicado",
                        f"{campo}={val!r} repetido ({vistos[val].nombre} y {u.nombre})",
                        "critica",
                        [vistos[val].admin_id, u.admin_id],
                    )
                else:
                    vistos[val] = u
        por_nivel_nombre: dict[tuple[int, str], list[str]] = {}
        for u in self.units:
            por_nivel_nombre.setdefault((u.nivel, u.nombre), []).append(u.admin_id)
        for (nivel, nombre), ids in por_nivel_nombre.items():
            if len(ids) > 1:
                add(
                    "nombre_duplicado_en_nivel",
                    f"{LEVELS[nivel]} tiene {len(ids)} unidades llamadas {nombre!r}",
                    "media",
                    ids,
                )

        # 3. ADM1/ADM2 fuera del país (por punto representativo)
        pais = self._pais
        if pais is not None:
            pais_prep = prep(pais.geometry)
            for u in (*self._adm1, *self._adm2):
                rp = u.geometry.representative_point()
                if not pais_prep.covers(rp):
                    add(
                        "unidad_fuera_del_pais",
                        f"{u.nombre} ({LEVELS[u.nivel]}): punto representativo fuera del ADM0",
                        "alta",
                        [u.admin_id],
                    )

        # 4. superposiciones entre pares del mismo nivel (STRtree + intersección)
        for nivel, unidades in (("ADM1", self._adm1), ("ADM2", self._adm2)):
            tree = STRtree([u.geometry for u in unidades])
            ya: set[tuple[str, str]] = set()
            for u in unidades:
                for j in tree.query(u.geometry):
                    v = unidades[int(j)]
                    if v is u:
                        continue
                    par = tuple(sorted((u.admin_id, v.admin_id)))
                    if par in ya:
                        continue
                    inter = u.geometry.intersection(v.geometry)
                    if inter.is_empty:
                        continue
                    m2 = abs(inter.area) * (111320.0**2)
                    if m2 >= overlap_tol_m2:
                        ya.add(par)
                        add(
                            "superposicion",
                            f"{nivel}: {u.nombre} ∩ {v.nombre} ≈ {m2 / 1e6:.2f} km²",
                            "alta" if nivel == "ADM1" else "media",
                            list(par),
                        )

        # 5. consistencia ADM1 vs ADM0 (huecos/sobrantes por diferencia simétrica)
        if pais is not None and self._adm1:
            union = self._adm1[0].geometry
            for u in self._adm1[1:]:
                union = union.union(u.geometry)
            dif = union.symmetric_difference(pais.geometry)
            m2 = abs(dif.area) * (111320.0**2)
            if m2 >= overlap_tol_m2:
                add(
                    "diferencia_adm1_vs_adm0",
                    f"diferencia simétrica ≈ {m2 / 1e6:.2f} km² "
                    "(huecos o excedentes entre departamentos y el polígono nacional)",
                    "media",
                    [pais.admin_id],
                )

        # 6. distritos sin padre
        for u in self._adm2:
            if not u.padre_admin_id:
                add("distrito_sin_departamento", u.nombre, "alta", [u.admin_id])

        # 6b. padre explícito vs espacial (esquemas con padre en la fuente,
        # p. ej. COD-AB): divergencias registradas al cargar (Misión 007)
        incons = self.meta.get("inconsistencias_padre_explicito_vs_espacial", [])
        if incons:
            add(
                "padre_explicito_vs_espacial",
                f"{len(incons)} distritos con padre declarado distinto del espacial "
                "(se conserva el declarado por la fuente; ver meta)",
                "media",
                [i["admin_id"] for i in incons],
            )

        # 7. reparaciones registradas al cargar (evidencia, no error)
        n_rep = self.meta.get("geometrias_reparadas", 0)
        if n_rep:
            add(
                "geometrias_reparadas_en_carga",
                f"{n_rep} geometrías llegaron inválidas de la fuente y fueron "
                "reparadas con make_valid (ver detalle_reparaciones)",
                "informativo",
                [r["admin_id"] for r in self.meta.get("detalle_reparaciones", [])],
            )

        return {
            "version": self.version,
            "conteos": self.counts(),
            "n_hallazgos": len(hallazgos),
            "por_gravedad": {
                g: sum(1 for h in hallazgos if h["gravedad"] == g)
                for g in ("critica", "alta", "media", "informativo")
            },
            "hallazgos": hallazgos,
        }

    def department_names(self) -> dict[str, str]:
        return {u.admin_id: u.nombre for u in self._adm1}

    # ------------------------------------------------------------- parquet IO
    def to_parquet(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {
            "admin_id": [u.admin_id for u in self.units],
            "shape_id": [u.shape_id for u in self.units],
            "nombre": [u.nombre for u in self.units],
            "nivel": [u.nivel for u in self.units],
            "padre_admin_id": [u.padre_admin_id for u in self.units],
            "padre_derivado": [u.padre_derivado for u in self.units],
            "bbox_w": [u.bbox[0] for u in self.units],
            "bbox_s": [u.bbox[1] for u in self.units],
            "bbox_e": [u.bbox[2] for u in self.units],
            "bbox_n": [u.bbox[3] for u in self.units],
            "geometry": [shapely_wkb.dumps(u.geometry) for u in self.units],
        }
        schema = pa.schema([pa.field(n, t) for n, t in _SCHEMA_FIELDS])
        table = pa.Table.from_pydict(arrays, schema=schema)
        geo_meta = {
            "version": "1.0.0",
            "primary_column": "geometry",
            "columns": {
                "geometry": {
                    "encoding": "WKB",
                    "geometry_types": ["Polygon", "MultiPolygon"],
                }
            },
            "creator": "hotspots-paraguay/geo",
        }
        kv = {
            b"geo": json.dumps(geo_meta).encode("utf-8"),
            b"hotspots_geo_version": self.version.encode("utf-8"),
            # auditoría persistida: el registro de reparaciones sobrevive al
            # roundtrip parquet (antes se perdía en el meta en memoria)
            b"hotspots_geo_audit": json.dumps(
                {
                    "geometrias_invalidas_originales": self.meta.get(
                        "geometrias_invalidas_originales", 0
                    ),
                    "geometrias_reparadas": self.meta.get("geometrias_reparadas", 0),
                    "detalle_reparaciones": self.meta.get("detalle_reparaciones", []),
                    # verificación de padres (Misión 007, esquemas con padre
                    # explícito): la evidencia sobrevive al roundtrip parquet
                    "esquema_fuente": self.meta.get("esquema_fuente", "geoboundaries"),
                    "padres_explicitos_usados": self.meta.get("padres_explicitos_usados"),
                    "padres_derivados_fallback": self.meta.get("padres_derivados_fallback"),
                    "inconsistencias_padre_explicito_vs_espacial": self.meta.get(
                        "inconsistencias_padre_explicito_vs_espacial", []
                    ),
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        }
        pq.write_table(table.replace_schema_metadata(kv), path)
        return path

    @classmethod
    def from_parquet(cls, path: str | Path) -> BoundarySet:
        path = Path(path)
        if not path.exists():
            raise GeoError(f"No existe el archivo de límites: {path}")
        table = pq.read_table(path)
        d = table.to_pydict()
        n = table.num_rows
        units = [
            AdminUnit(
                admin_id=d["admin_id"][i],
                shape_id=d["shape_id"][i],
                nombre=d["nombre"][i],
                nivel=d["nivel"][i],
                geometry=shapely_wkb.loads(d["geometry"][i]),
                padre_admin_id=d["padre_admin_id"][i],
                padre_derivado=d["padre_derivado"][i],
            )
            for i in range(n)
        ]
        version = (
            table.schema.metadata.get(b"hotspots_geo_version", b"").decode("utf-8")
            or "desconocida"
        )
        audit_raw = table.schema.metadata.get(b"hotspots_geo_audit", b"")
        meta: dict = {}
        if audit_raw:
            try:
                meta = json.loads(audit_raw.decode("utf-8"))
            except json.JSONDecodeError:
                meta = {}
        bs = cls(version=version, units=units, meta=meta)
        bs._build_index()
        return bs


def _pt(lon: float, lat: float):
    from shapely.geometry import Point

    return Point(lon, lat)


def _read_features(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GeoError(f"No se pudo leer {path}: {exc}") from exc
    feats = data.get("features")
    if not feats:
        raise GeoError(f"{path}: GeoJSON sin features")
    return feats
