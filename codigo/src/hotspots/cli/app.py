"""CLI del pipeline: validate / manifest / ingest / status / test.

Diseño: comandos mínimos, mensajes claros, códigos de salida útiles, secretos
jamás impresos (el logging aplica redacción automática).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from hotspots import __version__
from hotspots.config import REPO_ROOT, Settings
from hotspots.events.engine import build_events
from hotspots.geo.assign import assign_observations
from hotspots.geo.boundaries import BoundarySet, GeoError
from hotspots.geo.export import export_departamentos_geojson, export_points_geojson
from hotspots.ingestion.pipeline import PipelineBlocked, run_ingest
from hotspots.log import setup_logging
from hotspots.normalization.firms_csv import FirmsParseError, parse_firms_csv
from hotspots.provenance.manifests import Artifact, Manifest, ManifestStore, request_key
from hotspots.quality.checks import check_record
from hotspots.quality.states import SUCCESS_STATES
from hotspots.storage.duckdb_store import DuckDBStore
from hotspots.storage.parquet_store import utc_now_iso
from hotspots.storage.raw import RawStore, sha256_bytes

EXIT_OK = 0
EXIT_FAIL = 1


def _settings(args) -> Settings:
    return Settings.load(data_dir=getattr(args, "data_dir", None))


# ------------------------------------------------------------------ validate
def cmd_validate(args) -> int:
    settings = _settings(args)
    total_bad = 0
    for csv_path in args.files:
        path = Path(csv_path)
        print(f"\n== {path} ==")
        if not path.exists():
            print("  ERROR: archivo inexistente")
            total_bad += 1
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            outcome = parse_firms_csv(
                text,
                product=args.product or "MODIS_NRT",
                settings=settings,
                run_id="validate",
                manifest_id="validate",
                ingested_at_utc=utc_now_iso(),
                expected_family=None,  # validate: la familia se infiere del archivo
            )
        except FirmsParseError as exc:
            print(f"  PARSE ERROR: {exc}")
            total_bad += 1
            continue

        flag_counts: dict[str, int] = {}
        for rec in outcome.records:
            result = check_record(rec, settings)
            for f in result.flags:
                flag_counts[f] = flag_counts.get(f, 0) + 1
        print(f"  familia detectada : {outcome.family}")
        print(f"  filas             : {outcome.n_rows}")
        print(f"  válidas           : {len(outcome.records)}")
        print(f"  en cuarentena     : {len(outcome.quarantined)}")
        if flag_counts:
            print(f"  flags soft        : {dict(sorted(flag_counts.items()))}")
        for q in outcome.quarantined[:5]:
            print(f"    [cuarentena] errores={q.errors} fila={q.raw}")
        if len(outcome.quarantined) > 5:
            print(f"    … y {len(outcome.quarantined) - 5} más")
        total_bad += len(outcome.quarantined)
    print()
    if total_bad:
        print(f"RESULTADO: {total_bad} fila(s) inválida(s) o error de parseo.")
        return EXIT_FAIL
    print("RESULTADO: todas las filas válidas.")
    return EXIT_OK


# ------------------------------------------------------------------ manifest
def cmd_manifest(args) -> int:
    settings = _settings(args)
    store = ManifestStore(settings.data_dir / "manifests")
    if args.action == "list":
        entries = store.list_entries()
        if not entries:
            print("Sin manifiestos todavía.")
            return EXIT_OK
        print(f"{'manifest_id':18s} {'producto':20s} {'estado':28s} {'creado (UTC)':20s}")
        for e in entries:
            creada = e["created_at_utc"]
            print(f"{e['manifest_id']:18s} {e['product']:20s} {e['result_state']:28s} {creada:20s}")
        return EXIT_OK
    # show
    m = store.load(args.manifest_id)
    if m is None:
        print(f"No se encontró el manifiesto {args.manifest_id!r}")
        return EXIT_FAIL
    print(json.dumps(m.to_dict(), indent=2, ensure_ascii=False, sort_keys=True))
    return EXIT_OK


# ------------------------------------------------------------------- ingest
def cmd_ingest(args) -> int:
    settings = _settings(args)
    mode = "fixture" if args.fixture else "api"
    if args.fixture and args.source:
        print("ERROR: usá --fixture O --source, no ambos.")
        return EXIT_FAIL
    if not args.fixture and not args.source:
        print("ERROR: falta --fixture <csv> o --source firms-api.")
        return EXIT_FAIL

    area = None
    if args.area and args.area != "py":
        try:
            vals = [float(x) for x in args.area.split(",")]
            if len(vals) != 4:
                raise ValueError
            area = tuple(vals)
        except ValueError:
            print("ERROR: --area debe ser 'py' o 'west,south,east,north'")
            return EXIT_FAIL

    try:
        summary = run_ingest(
            settings,
            mode=mode,
            product=args.product,
            fixture_path=args.fixture,
            date=args.date,
            day_range=args.day_range,
            area=area,
            dry_run=args.dry_run,
            allow_network=args.allow_network,
        )
    except PipelineBlocked as exc:
        print(f"BLOQUEADO: {exc}")
        return EXIT_FAIL
    except Exception as exc:  # credenciales, parseo, IO: mensaje claro, sin secretos
        print(f"ERROR ({type(exc).__name__}): {exc}")
        return EXIT_FAIL

    d = summary.to_dict()
    print(json.dumps(d, indent=2, ensure_ascii=False))
    if summary.state in SUCCESS_STATES or summary.state in ("dry_run", "skipped_already_ingested"):
        return EXIT_OK
    return EXIT_FAIL


# ------------------------------------------------------------------- verify
def cmd_verify(args) -> int:
    """Verifica la coherencia manifiestos <-> artefactos <-> SHA256 (offline).

    Comprueba por cada manifiesto: que cada artefacto referenciado exista,
    que su tamaño y SHA256 coincidan con lo registrado, y que los artefactos
    RAW cumplan la convención content-addressed (nombre == SHA256).

    Misión 005 — manifiestos superseded: los manifiestos son evidencia
    inmutable de lo que FUE. Si un artefacto fue regenerado y un manifiesto
    MÁS NUEVO describe los bytes actuales, el manifiesto viejo no es una
    inconsistencia: es historia. Se reporta como "superseded" y solo falla
    si NI EL MÁS NUEVO coincide con el archivo real.

    M011-C §3 — artefactos RAW vacíos: un RAW de 0 bytes ligado a un
    manifiesto fallido (download_failed, etc.) NO es una inconsistencia de
    integridad (hash y tamaño coinciden) ni una observación: es la evidencia
    de una adquisición fallida. Se lista como información explícita para que
    nadie lo interprete como CSV válido o día sin detecciones. En un
    manifiesto EXITOSO un RAW de 0 bytes sí es una inconsistencia.
    """
    settings = _settings(args)
    store = ManifestStore(settings.data_dir / "manifests")
    entries = store.list_entries()
    if not entries:
        print("Sin manifiestos: nada que verificar (ejecutá una ingesta primero).")
        return EXIT_OK

    # índice: path -> descripciones ordenadas por antigüedad (más nueva al final).
    # Misión 005: los manifiestos viejos pueden registrar rutas relativas al
    # repo y los nuevos absolutas (o al revés): se normaliza resolviendo
    # contra la raíz del repositorio para que el MISMO archivo sea una sola
    # clave, independientemente de cómo se registró.
    repo_root = settings.config_dir.parent

    def _resolver(path_str: str) -> Path:
        p = Path(path_str)
        return p if p.is_absolute() else repo_root / p

    descripciones: dict[str, list[tuple[str, str, str]]] = {}
    manifiestos = {}
    for entry in entries:
        m = store.load(entry["manifest_id"])
        if m is None:
            continue
        manifiestos[m.manifest_id] = m
        for art in m.artifacts:
            descripciones.setdefault(str(_resolver(art.path)), []).append(
                (m.created_at_utc, m.manifest_id, art.sha256)
            )
    for path in descripciones:
        descripciones[path].sort()

    def supersede_valido(path: Path, sha_actual: str) -> str | None:
        """manifest_id del manifiesto MÁS NUEVO que describe `path` con el
        hash actual, si existe (el artefacto fue regenerado y re-registrado)."""
        descs = descripciones.get(str(path), [])
        for _creado, mid, sha in reversed(descs):
            if sha == sha_actual:
                return mid
        return None

    problemas: list[str] = []
    superseded: list[str] = []
    vacios_fallidos: list[str] = []
    vacios_en_exito: list[str] = []
    verificados = 0
    for mid, m in manifiestos.items():
        exitoso = m.result_state in SUCCESS_STATES
        for art in m.artifacts:
            verificados += 1
            p = _resolver(art.path)
            if not p.exists():
                problemas.append(f"{mid}: artefacto inexistente: {art.path}")
                continue
            digest = sha256_bytes(p.read_bytes())
            if digest != art.sha256:
                nuevo = supersede_valido(p, digest)
                if nuevo and nuevo != mid:
                    superseded.append(
                        f"{mid}: {p.name} fue regenerado (descrito por el manifiesto "
                        f"más nuevo {nuevo})"
                    )
                    continue
                problemas.append(f"{mid}: SHA256 difiere: {p.name}")
                continue
            if p.stat().st_size != art.size:
                problemas.append(
                    f"{mid}: tamaño difiere ({p.name}: registrado {art.size}, "
                    f"real {p.stat().st_size})"
                )
            if art.role.startswith("raw") and p.stem != art.sha256:
                problemas.append(
                    f"{mid}: RAW no es content-addressed (nombre {p.name} != SHA256)"
                )
            # M011-C §3: identificar artefactos RAW vacíos (0 bytes).
            if art.role.startswith("raw") and art.size == 0:
                if exitoso:
                    vacios_en_exito.append(
                        f"{mid}: {p.name} (manifiesto EXITOSO {m.result_state}: "
                        "inconsistencia — un CSV válido de FIRMS nunca es de 0 bytes)"
                    )
                else:
                    vacios_fallidos.append(
                        f"{mid}: {p.name} (adquisición fallida {m.result_state}: "
                        "NO es observación, ni CSV válido, ni día sin detecciones)"
                    )

    print(f"Manifiestos verificados : {len(entries)}")
    print(f"Artefactos verificados  : {verificados}")
    if superseded:
        print(f"\nSUPERSEDED ({len(superseded)}) — evidencia histórica, no inconsistencia:")
        for s in superseded:
            print(f"  - {s}")
    if vacios_en_exito:
        print(
            f"\nRAW VACÍOS EN MANIFIESTOS EXITOSOS ({len(vacios_en_exito)}) — "
            "inconsistencia:"
        )
        for v in vacios_en_exito:
            print(f"  - {v}")
        problemas.extend(vacios_en_exito)
    if vacios_fallidos:
        print(
            f"\nRAW VACÍOS DE ADQUISICIONES FALLIDAS ({len(vacios_fallidos)}) — "
            "evidencia histórica identificada (M011-C §3): no son observaciones, "
            "ni CSV válidos, ni días sin detecciones:"
        )
        for v in vacios_fallidos:
            print(f"  - {v}")
    if problemas:
        print(f"\nINCONSISTENCIAS ({len(problemas)}):")
        for pr in problemas:
            print(f"  - {pr}")
        return EXIT_FAIL
    print("Resultado: todos los artefactos coinciden con sus manifiestos (SHA256 OK).")
    return EXIT_OK


# ------------------------------------------------------------------- status
def cmd_status(args) -> int:
    settings = _settings(args)
    print(f"hotspots-paraguay v{__version__} — estado local")
    print(f"  configuración: {settings.describe()}")
    data = settings.data_dir
    print(f"  data_dir: {data}")

    raw = RawStore(data / "raw")
    manifests = ManifestStore(data / "manifests")
    duck = DuckDBStore(data / "processed" / "hotspots.duckdb", data / "processed")

    print(f"\n  RAW        : {raw.count()} archivo(s), {raw.total_bytes()} bytes")
    print(f"  Manifiestos: {manifests.count()}")

    by_product = duck.counts_by_product()
    if by_product:
        print("\n  Observaciones (vista deduplicada por obs_id):")
        for row in by_product:
            print(f"    {row['product']:20s} {row['n']:>10,d}")
        print(f"    {'TOTAL':20s} {duck.observation_count():>10,d}")
        print("\n  Por satélite:")
        for row in duck.counts_by_satellite():
            print(
                f"    {row['product']:18s} {str(row['satellite']):6s} "
                f"-> {row['satellite_name']:10s} {row['n']:>10,d}"
            )
        n_matches = len(duck.candidate_matches())
        if n_matches:
            print(
                f"\n  Pares candidatos entre productos (vista candidate_matches): {n_matches}"
            )
    else:
        print("\n  Observaciones: (vacío — sin ingesta todavía)")

    q = duck.quarantine_count()
    if q:
        print(f"\n  CUARENTENA : {q} fila(s) rechazadas (conservadas íntegras)")

    sc = duck.status_counts()
    if sc:
        print("\n  Estados de ingesta:")
        for row in sc:
            print(f"    {row['state']:28s} {row['n']:>6,d}")

    # capa geográfica (Misión 004)
    gver = duck.geo_version_activa()
    if gver:
        gs = duck.geo_status()
        print(f"\n  Geografía: versión de límites activa {gver}")
        if gs:
            print(f"    cobertura: {gs}")
        else:
            print("    (sin asignaciones todavía: 'hotspots geo assign')")
    return EXIT_OK


# --------------------------------------------------------------------- geo
def _geo_root(settings: Settings):
    return settings.data_dir / "geo"


def _active_version_file(settings: Settings):
    return _geo_root(settings) / "active_version.txt"


def cmd_geo(args) -> int:
    settings = _settings(args)
    geo_root = _geo_root(settings)
    try:
        if args.action == "build":
            return _geo_build(settings, geo_root, args)
        if args.action == "activate":
            return _geo_activate(settings, geo_root, args)
        if args.action == "assign":
            return _geo_assign(settings, args)
        if args.action == "status":
            return _geo_status(settings)
        if args.action == "export":
            return _geo_export(settings, args)
        if args.action == "audit":
            return _geo_audit(settings, args)
    except GeoError as exc:
        print(f"ERROR GEO: {exc}")
        return EXIT_FAIL
    return EXIT_FAIL


def _geo_audit(settings: Settings, args) -> int:
    """Auditoría geométrica de la versión activa (o --version)."""
    version = args.version or _read_active_version(settings)
    if not version:
        print("ERROR: sin versión de límites activa (corré 'hotspots geo build').")
        return EXIT_FAIL
    pq_path = _geo_root(settings) / version / "unidades_admin.parquet"
    if not pq_path.exists():
        print(f"ERROR: no existe {pq_path}")
        return EXIT_FAIL
    bs = BoundarySet.from_parquet(pq_path)
    reporte = bs.audit(overlap_tol_m2=args.overlap_tol_m2)
    print(json.dumps(reporte, indent=2, ensure_ascii=False))

    # registro cartográfico versionado (configs/geo_sources.yaml)
    from hotspots.geo.registry import cargar_registro, ficha_de

    registro = cargar_registro(settings.config_dir)
    ficha = ficha_de(registro, version)
    if ficha:
        print("\n--- Registro cartográfico ---")
        print(json.dumps(ficha, indent=2, ensure_ascii=False))
    else:
        print(
            f"\nAVISO: la versión {version} no está fichada en "
            "configs/geo_sources.yaml — agregala para dejar la procedencia "
            "por escrito (ver docs/cartografia.md)."
        )
    return EXIT_OK


def _geo_build(settings: Settings, geo_root, args) -> int:
    version = args.version
    vdir = geo_root / version
    src = vdir / "source"
    adm0 = Path(args.adm0) if args.adm0 else src / "PRY-ADM0.geojson"
    adm1 = Path(args.adm1) if args.adm1 else src / "PRY-ADM1.geojson"
    adm2 = Path(args.adm2) if args.adm2 else src / "PRY-ADM2.geojson"
    for p in (adm0, adm1, adm2):
        if not p.exists():
            print(f"ERROR: no existe {p} (descargá la fuente a data/geo/{version}/source/)")
            return EXIT_FAIL

    bs = BoundarySet.from_geojson_files(
        version, adm0, adm1, adm2, schema=args.schema
    )
    expected = {
        "ADM0": 1,
        "ADM1": int(args.expected_adm1),
        "ADM2": int(args.expected_adm2),
    }
    bs.validate(expected)
    pq_path = bs.to_parquet(vdir / "unidades_admin.parquet")

    # Procedencia del manifiesto: si la versión está fichada en el registro
    # cartográfico (configs/geo_sources.yaml) se usa SU ficha; si no, el
    # default histórico geoBoundaries (Misión 007: capa INE 2022 vía COD-AB).
    from hotspots.geo.registry import cargar_registro, ficha_de

    registro = cargar_registro(settings.config_dir)
    ficha = ficha_de(registro, version)
    if ficha:
        manifest_source = str(ficha.get("manifest_source") or "registro_geo")
        manifest_notes = [
            f"Fuente: {ficha.get('fuente', 's/d')}",
            f"Institución: {ficha.get('institucion', 's/d')}",
            f"Licencia: {ficha.get('licencia', 's/d')}",
            f"Año representado: {ficha.get('anio_representado', 's/d')} · "
            f"carácter: {ficha.get('caracter', 's/d')}",
        ]
    else:
        manifest_source = "geoboundaries_gbopen"
        manifest_notes = [
            "Fuente: geoBoundaries gbOpen PRY (CC BY 4.0), geometría DGEEC Paraguay.",
            "Cita: geoBoundaries (William & Mary geoLab). https://www.geoboundaries.org",
        ]
    manifest_notes.append(
        "Padres de distritos tomados del campo explícito de la fuente y verificados "
        "espacialmente (esquema codab)."
        if args.schema == "codab"
        else "Padres de distritos derivados espacialmente (punto representativo)."
    )
    manifest_notes.append(f"Esquema de propiedades del fuente: {args.schema}")

    # manifiesto con procedencia completa (mismo esquema que las corridas FIRMS)
    mstore = ManifestStore(settings.data_dir / "manifests")
    arts = [
        Artifact(
            path=str(p), sha256=sha256_bytes(p.read_bytes()), size=p.stat().st_size,
            role=f"geo_source_{lvl.lower()}",
        )
        for lvl, p in (("ADM0", adm0), ("ADM1", adm1), ("ADM2", adm2))
    ]
    arts.append(
        Artifact(
            path=str(pq_path), sha256=sha256_bytes(pq_path.read_bytes()),
            size=pq_path.stat().st_size, role="geo_boundaries",
        )
    )
    counts = bs.counts()
    manifest = Manifest(
        provider="geo",
        source=manifest_source,
        product="admin_boundaries",
        request_key=request_key(
            "geo", manifest_source, "admin_boundaries", {"version": version}
        ),
        result_state="success_with_detections",
        sensor="-",
        satellite_scope=[],
        acquisition_period={"from": "", "to": ""},
        counts={f"n_{k.lower()}": v for k, v in counts.items()},
        artifacts=arts,
        notes=manifest_notes,
        created_at_utc=utc_now_iso(),
    ).finalize()
    mstore.write(manifest)

    _active_version_file(settings).write_text(version, encoding="utf-8")
    print(f"Límites construidos y activados: {version}")
    print(f"  unidades: {counts}")
    print(f"  parquet : {pq_path}")
    print(f"  manifiesto: {manifest.manifest_id}")
    return EXIT_OK


def _geo_activate(settings: Settings, geo_root, args) -> int:
    vdir = geo_root / args.version
    if not (vdir / "unidades_admin.parquet").exists():
        print(f"ERROR: no hay unidades_admin.parquet en {vdir} (corré 'geo build' primero)")
        return EXIT_FAIL
    _active_version_file(settings).write_text(args.version, encoding="utf-8")
    print(f"Versión activa: {args.version}")
    return EXIT_OK


def _geo_assign(settings: Settings, args) -> int:
    version = args.version or _read_active_version(settings)
    if not version:
        print("ERROR: no hay versión activa (corré 'hotspots geo build' o 'geo activate')")
        return EXIT_FAIL
    pq_path = _geo_root(settings) / version / "unidades_admin.parquet"
    bs = BoundarySet.from_parquet(pq_path)

    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb", settings.data_dir / "processed"
    )
    observations = duck.query(
        "SELECT obs_id, longitude, latitude FROM observations"
    )
    if not observations:
        print("No hay observaciones que asignar (corré una ingesta primero).")
        return EXIT_OK

    import uuid

    run_id = uuid.uuid4().hex
    summary = assign_observations(
        bs,
        observations,
        version=version,
        run_id=run_id,
        processed_root=settings.data_dir / "processed",
        assigned_at_utc=utc_now_iso(),
    )
    duck.refresh(geo_version=version, boundaries_parquet=pq_path)
    print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))
    return EXIT_OK


def _read_active_version(settings: Settings) -> str | None:
    f = _active_version_file(settings)
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def _geo_status(settings: Settings) -> int:
    version = _read_active_version(settings)
    if not version:
        print("Sin capa geográfica activa (corré 'hotspots geo build').")
        return EXIT_OK
    print(f"Versión de límites activa: {version}")
    pq_path = _geo_root(settings) / version / "unidades_admin.parquet"
    if pq_path.exists():
        bs = BoundarySet.from_parquet(pq_path)
        print(f"  unidades: {bs.counts()}")
    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb", settings.data_dir / "processed"
    )
    gs = duck.geo_status()
    if gs:
        print(f"  cobertura de observaciones: {gs}")
    else:
        print("  sin asignaciones todavía (corré 'hotspots geo assign')")
    return EXIT_OK


def _geo_export(settings: Settings, args) -> int:
    version = _read_active_version(settings)
    if not version:
        print("ERROR: sin versión de límites activa.")
        return EXIT_FAIL
    bs = BoundarySet.from_parquet(_geo_root(settings) / version / "unidades_admin.parquet")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tol = args.simplify if args.simplify else None
    p1 = export_departamentos_geojson(bs, out / "departamentos.geojson", simplify_tolerance_deg=tol)
    print(f"capa departamentos: {p1}")

    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb", settings.data_dir / "processed"
    )
    gs = duck.geo_status()
    if gs:
        rows = duck.query(
            "SELECT obs_id, latitude, longitude, acq_datetime_utc, product, sensor, "
            "satellite, satellite_name, confidence, frp, dentro_pais, departamento, distrito "
            "FROM observations_geo"
        )
        meta = {
            "version_limites": version,
            "nota": "observaciones del almacén local; fixtures sintéticas si no hubo ingesta real",
        }
        p2 = export_points_geojson(rows, out / "observaciones.geojson", layer_meta=meta)
        print(f"capa observaciones: {p2} ({len(rows)} puntos)")
    else:
        print("(sin observaciones asignadas: solo se exportó la capa de departamentos)")
    return EXIT_OK


# ----------------------------------------------------------------- eventos
def cmd_events(args) -> int:
    settings = _settings(args)
    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb", settings.data_dir / "processed"
    )
    if args.action == "build":
        observations = duck.query(
            "SELECT obs_id, product, sensor, satellite, acq_datetime_utc, "
            "latitude, longitude, frp, confidence FROM observations"
        )
        if not observations:
            print("No hay observaciones (corré una ingesta primero).")
            return EXIT_FAIL
        import uuid

        res = build_events(
            observations,
            dt_seconds=args.dt_seconds,
            distance_m=args.distance_m,
            processed_root=settings.data_dir / "processed",
            run_id=uuid.uuid4().hex,
        )
        duck.refresh()
        print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
        return EXIT_OK
    # list
    rows = duck.query(
        "SELECT event_id, n_observaciones, productos, sensores, primera_obs_utc, "
        "ultima_obs_utc, duracion_segundos, lat_centroide, lon_centroide, "
        "dispersion_metros, frp_total FROM events ORDER BY primera_obs_utc"
    )
    if not rows:
        print("Sin eventos (corré 'hotspots events build').")
        return EXIT_OK
    print(f"{len(rows)} evento(s) de co-detección:")
    for r in rows:
        prods = "+".join(r["productos"])
        print(
            f"  {r['event_id'][:12]}  {r['primera_obs_utc']}  "
            f"n={r['n_observaciones']}  {prods}  "
            f"disp={r['dispersion_metros']:.0f}m  frp={r['frp_total']}"
        )
    return EXIT_OK


def cmd_match_sensitivity(args) -> int:
    """Sensibilidad de los pares candidatos a los umbrales (offline)."""
    settings = _settings(args)
    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb", settings.data_dir / "processed"
    )
    observations = duck.query(
        "SELECT obs_id, product, acq_datetime_utc, latitude, longitude FROM observations"
    )
    if not observations:
        print("No hay observaciones.")
        return EXIT_FAIL

    from hotspots.events.engine import equirect_distance_m

    dts = [int(x) for x in args.dt_grid.split(",")]
    dists = [float(x) for x in args.dist_grid.split(",")]
    obs = sorted(observations, key=lambda o: (o["acq_datetime_utc"], o["obs_id"]))

    # pares entre productos con dt/dist máximos (grid máximo), clasificados
    max_dt, max_d = max(dts), max(dists)
    from datetime import datetime, timezone

    def _ts(s):
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    pairs = []
    for i in range(len(obs)):
        ti = _ts(obs[i]["acq_datetime_utc"])
        for j in range(i + 1, len(obs)):
            dt = abs((_ts(obs[j]["acq_datetime_utc"]) - ti).total_seconds())
            if dt > max_dt:
                break
            if obs[i]["product"] == obs[j]["product"]:
                continue
            d = equirect_distance_m(
                obs[i]["latitude"], obs[i]["longitude"],
                obs[j]["latitude"], obs[j]["longitude"],
            )
            if d <= max_d:
                pairs.append((dt, d))

    print(f"{len(obs)} observaciones, {len(pairs)} pares dentro del grid máximo\n")
    header = "dt\\dist      " + "".join(f"{d:>10.0f}m" for d in dists)
    print(header)
    for dt in dts:
        fila = f"{dt:>6}s      "
        for d in dists:
            n = sum(1 for pdt, pdist in pairs if pdt <= dt and pdist <= d)
            fila += f"{n:>11d}"
        print(fila)
    print(
        "\nLectura: cada celda es la cantidad de pares candidatos entre productos "
        "con esos umbrales. Si el número se dispara al subir una fila/columna, "
        "los resultados son sensibles a ese parámetro (ver docs/harmonization.md)."
    )
    return EXIT_OK


# -------------------------------------------------------------------- serve
def cmd_serve(args) -> int:
    """Levanta la API + dashboard (solo lectura del almacén local)."""
    settings = _settings(args)
    print(f"hotspots-paraguay v{__version__} — API + dashboard")
    print(f"  data_dir: {settings.data_dir}")
    host = '127.0.0.1' if args.host in ('127.0.0.1', 'localhost') else args.host
    print(f"  http://{host}:{args.port}")
    print("  Ctrl+C para cortar")
    try:
        import uvicorn

        from hotspots.api.app import app
    except ImportError as exc:
        print(f"Falta dependencia de API: {exc} (pip install '.[api]')")
        return EXIT_FAIL
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return EXIT_OK


# --------------------------------------------------------------------- test
def cmd_test(args) -> int:
    print("Ejecutando la suite de pruebas (offline)…\n")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(REPO_ROOT / "tests")],
        cwd=str(REPO_ROOT),
        check=False,
    )
    return proc.returncode


# -------------------------------------------------------------------- real
def cmd_real(args) -> int:
    """Misión A: operación sobre la base real M014 (solo lectura + DuckDB derivado)."""
    from hotspots.storage.real_base import RealBaseAdapter, RealBaseError

    try:
        adapter = RealBaseAdapter(
            base_dir=args.base_dir, duckdb_path=args.duckdb, sources_dir=args.sources_dir
        )
    except RealBaseError as exc:
        print(f"ERROR: {exc}")
        return EXIT_FAIL

    if args.action == "verify":
        rep = adapter.verify(check_hashes=not args.no_hashes, deep=args.deep)
        d = rep.to_dict()
        print(f"Base real: {d['base_dir']}")
        print(f"Manifiesto: {d['manifiesto']} (schema {d['schema_version']})")
        print(f"Fuentes: {d['fuentes_hash_ok']}/{d['fuentes_totales']} SHA-256 OK")
        print(f"Filas: {d['filas_reales']:,} (esperadas {d['filas_esperadas']:,})")
        print(f"Particiones: {d['particiones']}")
        for p, info in d["por_producto"].items():
            print(
                f"  {p:20s} {info['filas_real']:>9,}  {info['fecha_min_real']}"
                f" → {info['fecha_max_real']}"
            )
        if d["obs_id_duplicados"]:
            print(f"obs_id duplicados: {d['obs_id_duplicados']:,}")
        if d["problemas"]:
            print("PROBLEMAS:")
            for pr in d["problemas"]:
                print(f"  - {pr}")
            return EXIT_FAIL
        print("VERIFICACIÓN: OK")
        return EXIT_OK

    if args.action == "build":
        meta = adapter.build_duckdb(force=args.force)
        print(f"DuckDB real: {adapter.duckdb_path}")
        print(f"Filas: {meta['filas']:,} | productos: {len(meta['productos'])}")
        print(f"Build: {meta['build_en_utc']}")
        print("Vistas: observations, cobertura_producto_mes/anio, stats_departamento")
        return EXIT_OK

    if args.action == "stats":
        st = adapter.stats()
        print(f"Total: {st['total']:,} ({st['fecha_min']} → {st['fecha_max']})")
        print(f"Fuera de país (conservadas): {st['fuera_de_pais']:,}")
        print(f"Fuentes industriales: {st['fuentes_industriales']:,}")
        print("\nPOR PRODUCTO:")
        for p in st["por_producto"]:
            print(f"  {p['product']:20s} {p['detecciones']:>9,}  {p['desde']} → {p['hasta']}")
        print("\nPOR SATÉLITE:")
        for s in st["por_satelite"]:
            det = s["detecciones"]
            print(f"  {s['satellite']:6s} ({s['satellite_name']:8s}, {s['sensor']})  {det:>9,}")
        print("\nPOR DEPARTAMENTO (top):")
        for d_ in st["por_departamento"][:8]:
            print(f"  {d_['departamento']:18s} {d_['detecciones']:>9,}")
        return EXIT_OK

    if args.action == "query":
        rows = adapter.query_obs(
            fecha_desde=args.desde,
            fecha_hasta=args.hasta,
            anio=args.anio,
            producto=args.producto,
            satelite=args.satelite,
            sensor=args.sensor,
            departamento=args.departamento,
            dentro_pais=not args.incluir_fuera,
            orden=args.orden,
            limite=args.limite,
        )
        print(f"{len(rows)} observaciones (source_kind=real)")
        for r in rows:
            print(
                f"  {r['acq_datetime_utc']}  {r['product']:18s} {r['satellite_name']:8s} "
            f"({r['latitude']:.4f}, {r['longitude']:.4f})  FRP={r['frp']}  "
            f"conf={r['confidence']} [{r['confidence_band']}]  {r.get('departamento') or '-'}"
            )
        return EXIT_OK
    return EXIT_FAIL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hotspots",
        description="Ingesta y validación de focos de calor MODIS/VIIRS (NASA FIRMS) — Paraguay",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("--data-dir", help="Raíz de datos (default: ./data o HOTSPOTS_DATA_DIR)")
    parser.set_defaults(func=None)

    # Opciones comunes replicadas en cada subcomando para que --data-dir
    # funcione también DESPUÉS del subcomando (ergonomía de CLI).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="count", default=0)
    common.add_argument("--data-dir", help="Raíz de datos (default: ./data o HOTSPOTS_DATA_DIR)")

    sub = parser.add_subparsers(dest="command")

    p_val = sub.add_parser(
        "validate", parents=[common], help="Valida CSVs FIRMS contra el esquema y QC"
    )
    p_val.add_argument("files", nargs="+", help="Archivos CSV de FIRMS")
    p_val.add_argument(
        "--product", help="Producto de referencia (default MODIS_NRT; solo define dominios)"
    )
    p_val.set_defaults(func=cmd_validate)

    p_man = sub.add_parser(
        "manifest", parents=[common], help="Lista o muestra manifiestos de ingesta"
    )
    p_man.add_argument("action", choices=["list", "show"])
    p_man.add_argument("manifest_id", nargs="?", help="ID para 'show'")
    p_man.set_defaults(func=cmd_manifest)

    p_ing = sub.add_parser(
        "ingest", parents=[common], help="Ingesta (fixture offline, dry-run o real con compuerta)"
    )
    g = p_ing.add_mutually_exclusive_group()
    g.add_argument("--fixture", help="CSV local (modo offline, Fase 1A)")
    g.add_argument("--source", help="Fuente real (firms-api)")
    p_ing.add_argument("--product", required=True, help="Producto FIRMS (ej. VIIRS_NOAA20_NRT)")
    p_ing.add_argument("--date", help="YYYY-MM-DD (default: más reciente)")
    p_ing.add_argument("--day-range", type=int, default=1, help="Días por request (1-5)")
    p_ing.add_argument("--area", default="py", help="'py' o 'west,south,east,north'")
    p_ing.add_argument("--dry-run", action="store_true", help="Muestra el plan sin ejecutar nada")
    p_ing.add_argument(
        "--allow-network",
        action="store_true",
        help="Compuerta Fase 1B: habilita la primera solicitud real "
        "(requiere autorización del propietario)",
    )
    p_ing.set_defaults(func=cmd_ingest)

    p_st = sub.add_parser("status", parents=[common], help="Resumen del almacén local")
    p_st.set_defaults(func=cmd_status)

    p_ver = sub.add_parser(
        "verify",
        parents=[common],
        help="Verifica manifiestos vs artefactos (existencia, tamaño, SHA256)",
    )
    p_ver.set_defaults(func=cmd_verify)

    p_geo = sub.add_parser(
        "geo", parents=[common], help="Capa geográfica nacional (límites, asignación, capas web)"
    )
    p_geo.add_argument(
        "action",
        choices=["build", "activate", "assign", "status", "export", "audit"],
    )
    p_geo.add_argument(
        "--version",
        help="Etiqueta de versión de límites (ej. geoboundaries-gbOpen-PRY-9469f09)",
    )
    p_geo.add_argument(
        "--adm0", help="Ruta GeoJSON ADM0 (default: data/geo/<v>/source/PRY-ADM0.geojson)"
    )
    p_geo.add_argument("--adm1", help="Ruta GeoJSON ADM1")
    p_geo.add_argument("--adm2", help="Ruta GeoJSON ADM2")
    p_geo.add_argument(
        "--schema", choices=["geoboundaries", "codab"], default="geoboundaries",
        help=(
            "Esquema de propiedades del GeoJSON fuente: geoboundaries "
            "(shapeName/shapeID; default) o codab (adm{N}_name/adm{N}_pcode + "
            "padre explícito adm1_name; OCHA COD-AB / INE 2022) — Misión 007"
        ),
    )
    p_geo.add_argument(
        "--expected-adm1", type=int, default=18,
        help="Validación: unidades ADM1 esperadas (18 para Paraguay)",
    )
    p_geo.add_argument(
        "--expected-adm2", type=int, default=247,
        help=(
            "Validación: unidades ADM2 esperadas según el inventario de la FUENTE "
            "(247 = geoBoundaries gbOpen 2012; el INE Revisión 2025 usa 263 — "
            "ver docs/cartografia.md)"
        ),
    )
    p_geo.add_argument(
        "--overlap-tol-m2", type=float, default=1000.0,
        help="Tolerancia (m²) para reportar superposiciones en 'audit' (default 1000)",
    )
    p_geo.add_argument("--out", default="data/capas", help="Directorio de salida para 'export'")
    p_geo.add_argument(
        "--simplify", type=float, default=None,
        help="Tolerancia de simplificación (grados) para la capa web",
    )
    p_geo.set_defaults(func=cmd_geo)

    p_ev = sub.add_parser(
        "events", parents=[common], help="Eventos de co-detección entre productos"
    )
    p_ev.add_argument("action", choices=["build", "list"])
    p_ev.add_argument(
        "--dt-seconds", type=int, default=600, help="Ventana temporal (default 600)"
    )
    p_ev.add_argument(
        "--distance-m", type=float, default=2000.0, help="Distancia máx en m (default 2000)"
    )
    p_ev.set_defaults(func=cmd_events)

    p_sens = sub.add_parser(
        "match-sensitivity",
        parents=[common],
        help="Sensibilidad de pares candidatos a los umbrales (offline)",
    )
    p_sens.add_argument(
        "--dt-grid", default="300,600,900,1800", help="Valores de dt (s) separados por coma"
    )
    p_sens.add_argument(
        "--dist-grid", default="500,1000,2000,3750", help="Valores de distancia (m)"
    )
    p_sens.set_defaults(func=cmd_match_sensitivity)

    p_srv = sub.add_parser(
        "serve", parents=[common], help="API REST + dashboard web (solo lectura)"
    )
    p_srv.add_argument("--host", default="127.0.0.1", help="Bind (default 127.0.0.1)")
    p_srv.add_argument("--port", type=int, default=8000, help="Puerto (default 8000)")
    p_srv.set_defaults(func=cmd_serve)

    p_t = sub.add_parser("test", parents=[common], help="Ejecuta la suite de pruebas offline")
    p_t.set_defaults(func=cmd_test)

    p_real = sub.add_parser(
        "real",
        parents=[common],
        help="Base real M014 (2,69 M observaciones 2000-2026): verify/build/stats/query",
    )
    p_real.add_argument(
        "action",
        choices=["verify", "build", "stats", "query"],
        help="verify/build/stats/query sobre base_real_v1 (solo lectura)",
    )
    p_real.add_argument("--base-dir", help="Directorio de base_real_v1 (default: hermana)")
    p_real.add_argument("--duckdb", help="Ruta del DuckDB derivado (default: PROCESADA)")
    p_real.add_argument("--sources-dir", help="Directorio de CSV fuente (default: SATELLITE_DATA)")
    p_real.add_argument("--no-hashes", action="store_true", help="verify: omitir SHA-256")
    p_real.add_argument("--deep", action="store_true", help="verify: unicidad global de obs_id")
    p_real.add_argument("--force", action="store_true", help="build: reconstruir aunque exista")
    p_real.add_argument("--desde", help="query: fecha inicial YYYY-MM-DD")
    p_real.add_argument("--hasta", help="query: fecha final YYYY-MM-DD")
    p_real.add_argument("--anio", type=int, help="query: año")
    p_real.add_argument("--producto", help="query: producto FIRMS")
    p_real.add_argument("--satelite", help="query: satélite (Terra/Aqua/N20/N21)")
    p_real.add_argument("--sensor", choices=["MODIS", "VIIRS"], help="query: sensor")
    p_real.add_argument("--departamento", help="query: departamento (acentos insensibles)")
    p_real.add_argument("--incluir-fuera", action="store_true", help="query: incluir fuera de país")
    p_real.add_argument(
        "--orden",
        default="acq_datetime_utc",
        choices=[
            "acq_datetime_utc", "-acq_datetime_utc",
            "frp", "-frp", "confidence", "-confidence",
        ],
        help="query: orden (default: cronológico)",
    )
    p_real.add_argument("--limite", type=int, default=20, help="query: máximo de filas")
    p_real.set_defaults(func=cmd_real)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_OK

    # El logging redacta cualquier valor secreto configurado
    setup_logging(verbosity=args.verbose, secrets=Settings.load().secret_values())
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrumpido.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
