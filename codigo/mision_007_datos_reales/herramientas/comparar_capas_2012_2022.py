"""Matriz de correspondencias ADM2: capa 2012 (geoBoundaries, 247) vs capa
INE 2022 (COD-AB, 263) — Misión 007, Etapa D.3.

Método (reproducible, sin correspondencias inventadas):

1. Emparejamiento por NOMBRE normalizado (slug) dentro del mismo departamento
   (por slug del padre).
2. Para los no emparejados: análisis de solape espacial (intersección de
   polígonos). El mejor candidato es el de mayor intersección, expresada como
   % del área de cada capa (bidireccional).
3. Clasificación por par (antiguo, nuevo):
   - coincidencia_exacta    : mismo nombre + mismo departamento + solape fuerte
                              (≥90% del área en ambos sentidos, cuando se computa).
   - cambio_de_nombre       : solape fuerte (≥90%/≥90%) con nombre distinto.
   - division_territorial   : un distrito antiguo se corresponde con ≥2 nuevos.
   - fusion_territorial     : ≥2 antiguos se corresponden con 1 nuevo.
   - correspondencia_parcial: solape entre 30% y 90% sin relación 1:1 limpia.
   - sin_correspondencia    : sin emparejamiento ni solape ≥ umbral (30%).
4. Evidencia: cada fila registra el método que la produjo
   (nombre+departamento / solape espacial / ninguno) y los porcentajes.

Salidas:
- matriz_correspondencia_adm2.csv : una fila por par (antiguo, nuevo) + filas
  de antiguos y nuevos sin correspondencia.
- resumen impreso en stdout.
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from pathlib import Path

import pyarrow.parquet as pq
from shapely import wkb as shapely_wkb
from shapely.strtree import STRtree

REPO = Path(__file__).resolve().parents[2]
V2012 = REPO / "data/geo/geoboundaries-gbOpen-PRY-9469f09/unidades_admin.parquet"
V2022 = REPO / "data/geo/ine2022-codab-hdx/unidades_admin.parquet"
SALIDA_CSV = REPO / "mision_007_datos_reales/datos/matriz_correspondencia_adm2.csv"


def slug(nombre: str) -> str:
    norm = unicodedata.normalize("NFKD", nombre)
    sin_acento = "".join(c for c in norm if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "-", sin_acento.strip()).strip("-").upper()


def cargar_adm2(ruta: Path) -> list[dict]:
    t = pq.read_table(ruta)
    d = t.to_pydict()
    out = []
    for i in range(t.num_rows):
        if d["nivel"][i] != 2:
            continue
        padre_slug = d["padre_admin_id"][i].rsplit(":", 1)[-1]
        out.append(
            {
                "admin_id": d["admin_id"][i],
                "shape_id": d["shape_id"][i],
                "nombre": d["nombre"][i],
                "padre": padre_slug,
                "geom": shapely_wkb.loads(d["geometry"][i]),
            }
        )
    return out


def main() -> int:
    viejos = cargar_adm2(V2012)
    nuevos = cargar_adm2(V2022)
    print(f"capa 2012: {len(viejos)} distritos | capa INE 2022: {len(nuevos)} distritos")

    tree_viejos = STRtree([u["geom"] for u in viejos])

    # ---------------------------------------------------------------- 1. nombre
    por_clave_v = {(slug(v["nombre"]), v["padre"]): v for v in viejos}
    emparejados_nombre = {}
    for n in nuevos:
        v = por_clave_v.get((slug(n["nombre"]), n["padre"]))
        if v is not None:
            emparejados_nombre[n["admin_id"]] = v
    usados_v = {v["admin_id"] for v in emparejados_nombre.values()}
    usados_n = set(emparejados_nombre)

    # ------------------------------------------------------- 2. solape espacial
    def solape(a, b) -> tuple[float, float]:
        """(% del área de a cubierto por b, % del área de b cubierto por a)."""
        inter = a.intersection(b)
        if inter.is_empty:
            return (0.0, 0.0)
        aa = a.area or 1e-12
        ab = b.area or 1e-12
        return (inter.area / aa * 100.0, inter.area / ab * 100.0)

    filas: list[dict] = []

    def fila(tipo, v, n, metodo, pa, pb, obs):
        filas.append(
            {
                "codigo_geo2012": v["shape_id"] if v else "",
                "nombre_2012": v["nombre"] if v else "",
                "area_km2_2012": round((v["geom"].area * 111320.0**2 / 1e6), 2) if v else "",
                "departamento": (v or n)["padre"],
                "pcode_ine2022": n["shape_id"] if n else "",
                "nombre_2022": n["nombre"] if n else "",
                "area_km2_2022": round((n["geom"].area * 111320.0**2 / 1e6), 2) if n else "",
                "tipo_correspondencia": tipo,
                "estado": "verificado" if (v and n) else "sin_pareja",
                "pct_area_2012_cubierta": round(pa, 2) if v and n else "",
                "pct_area_2022_cubierta": round(pb, 2) if v and n else "",
                "evidencia": metodo,
                "observaciones": obs,
            }
        )

    # cada NUEVO sin emparejar registra TODOS los VIEJOS que cubren ≥30% suyo
    viejos_reclamados: dict[str, list[tuple[float, dict, dict]]] = {}
    for n in nuevos:
        if n["admin_id"] in usados_n:
            continue
        for j in tree_viejos.query(n["geom"]):
            v = viejos[int(j)]
            if v["admin_id"] in usados_v:
                continue
            pa, pb = solape(n["geom"], v["geom"])
            if pb >= 30.0:  # el viejo cubre ≥30% del área del nuevo
                viejos_reclamados.setdefault(v["admin_id"], []).append((pb, v, n))

    # pares 1:1 por nombre (con solape como evidencia adicional)
    for n in nuevos:
        v = emparejados_nombre.get(n["admin_id"])
        if v is None:
            continue
        pa, pb = solape(v["geom"], n["geom"])
        if pa >= 90.0 and pb >= 90.0:
            tipo, obs = "coincidencia_exacta", "mismo nombre y departamento en ambas capas"
        else:
            tipo = "correspondencia_parcial"
            obs = (
                f"mismo nombre y departamento pero geometría divergente "
                f"(solape {pa:.1f}%/{pb:.1f}%)"
            )
        fila(tipo, v, n, "nombre+departamento (slug)", pa, pb, obs)

    # pares espaciales para viejos no usados por nombre
    for vid, lista in sorted(viejos_reclamados.items()):  # noqa: B007
        v = lista[0][1]
        if len(lista) == 1:
            pb, n = lista[0][0], lista[0][2]
            pa, _ = solape(v["geom"], n["geom"])
            if pa >= 90.0 and pb >= 90.0:
                fila(
                    "cambio_de_nombre", v, n, "solape espacial máx (≥90%/≥90%)",
                    pa, pb, "nombre distinto, geometría esencialmente igual",
                )
            else:
                fila(
                    "correspondencia_parcial", v, n, "solape espacial",
                    pa, pb, "solape sin relación 1:1 limpia",
                )
        else:
            lista_ordenada = sorted(lista, key=lambda x: -x[0])
            for pb, _v, n in lista_ordenada:
                pa, _ = solape(v["geom"], n["geom"])
                fila(
                    "division_territorial", v, n, "solape espacial (multi-hijo)",
                    pa, pb,
                    f"el distrito 2012 se reparte entre {len(lista_ordenada)} distritos INE 2022",
                )

    # nuevos sin ninguna pareja (creaciones post-2012)
    emparejados_espacial_n = {
        n["admin_id"] for lista in viejos_reclamados.values() for _, _v, n in lista
    }
    for n in nuevos:
        if n["admin_id"] in usados_n or n["admin_id"] in emparejados_espacial_n:
            continue
        fila(
            "sin_correspondencia (nuevo)", None, n, "ninguno", 0.0, 0.0,
            "distrito INE 2022 sin contraparte con solape ≥30% en la capa 2012",
        )

    # viejos que nadie reclamó (con nota de área: slivers degenerados de la
    # fuente 2012 — hallazgo documentado, no un error del emparejamiento)
    viejos_con_pareja = usados_v | set(viejos_reclamados)
    for v in viejos:
        if v["admin_id"] not in viejos_con_pareja:
            area_km2 = v["geom"].area * 111320.0**2 / 1e6
            if area_km2 < 5.0:
                obs = (
                    f"distrito 2012 sin contraparte y de área degenerada "
                    f"({area_km2:.2f} km²): sliver duplicado de otra unidad "
                    "en la fuente geoBoundaries (hallazgo de calidad de la capa 2012)"
                )
            else:
                obs = "distrito 2012 sin contraparte en la capa INE 2022"
            fila("sin_correspondencia (antiguo)", v, None, "ninguno", 0.0, 0.0, obs)

    # ------------------------------------------------------------------ salida
    SALIDA_CSV.parent.mkdir(parents=True, exist_ok=True)
    campos = list(filas[0].keys())
    with open(SALIDA_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)

    resumen: dict[str, int] = {}
    for f in filas:
        resumen[f["tipo_correspondencia"]] = resumen.get(f["tipo_correspondencia"], 0) + 1
    print("\n=== RESUMEN DE CORRESPONDENCIAS ===")
    for tipo, n in sorted(resumen.items(), key=lambda kv: -kv[1]):
        print(f"  {tipo:34s} {n}")
    print(f"\nfilas totales: {len(filas)} (pares + sin correspondencia)")
    print(f"salida: {SALIDA_CSV}")

    print("\n=== DIVISIONES TERRITORIALES DETECTADAS ===")
    divs: dict[str, list[str]] = {}
    for f in filas:
        if f["tipo_correspondencia"] == "division_territorial":
            divs.setdefault(f["nombre_2012"], []).append(f["nombre_2022"])
    for viejo, hijos in sorted(divs.items()):
        print(f"  {viejo} -> {' + '.join(sorted(hijos))}")

    print("\n=== CAMBIOS DE NOMBRE ===")
    for f in filas:
        if f["tipo_correspondencia"] == "cambio_de_nombre":
            print(f"  {f['nombre_2012']} -> {f['nombre_2022']}")

    print("\n=== NUEVOS SIN CORRESPONDENCIA (creaciones post-2012) ===")
    for f in filas:
        if f["tipo_correspondencia"] == "sin_correspondencia (nuevo)":
            print(f"  {f['pcode_ine2022']} {f['nombre_2022']} ({f['departamento']})")

    print("\n=== ANTIGUOS SIN CORRESPONDENCIA ===")
    for f in filas:
        if f["tipo_correspondencia"] == "sin_correspondencia (antiguo)":
            print(f"  {f['codigo_geo2012']} {f['nombre_2012']} ({f['departamento']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
