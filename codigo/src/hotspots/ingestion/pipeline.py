"""Pipeline de ingesta: orquesta RAW -> normalización -> QC -> Parquet -> DuckDB.

Modos de operación (Misión 002):

- ``dry-run`` (api): muestra EXACTAMENTE qué haría (URL redactada, cantidad de
  requests, rutas destino) sin escribir ni pedir nada por red.
- ``fixture``: ingesta offline de un CSV local — usada en Fase 1A y en las
  pruebas. Mismo camino de datos que la ingesta real, sin red.
- ``api``: ingesta real de FIRMS. REQUIERE ``allow_network=True`` y
  ``FIRMS_MAP_KEY`` configurada; sin eso se bloquea con error explícito
  (compuerta de la Fase 1B: primera solicitud real solo con autorización).

Idempotencia (tres niveles):

1. RAW content-addressed: mismo contenido => mismo archivo (write-once).
2. ``request_key``: misma petición ya exitosa => la corrida se salta.
3. ``obs_id`` determinista: la vista de DuckDB deduplica por observación.

Ningún paso borra o sobrescribe datos previos.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date as _date
from datetime import timedelta
from pathlib import Path

from hotspots.config import Settings
from hotspots.ingestion.base import RequestsTransport, Transport
from hotspots.ingestion.firms import (
    CredentialsError,
    FirmsClient,
    classify_response,
    header_only_csv,
    sniff_body,
)
from hotspots.normalization.firms_csv import FirmsParseError, ParseOutcome, parse_firms_csv
from hotspots.provenance.manifests import Artifact, Manifest, ManifestStore, request_key
from hotspots.quality.states import (
    SUCCESS_STATES,
    IngestState,
    IngestStatusRecord,
    processing_state_of,
)
from hotspots.storage.duckdb_store import DuckDBStore
from hotspots.storage.parquet_store import ParquetStore, utc_now_iso
from hotspots.storage.raw import RawStore, sha256_bytes

logger = logging.getLogger(__name__)

KEY_PLACEHOLDER = "{MAP_KEY}"

#: Nota estándar M011-C §3: un cuerpo de 0 bytes NO produce artefacto RAW
#: (un archivo vacío content-addressed colisiona para TODAS las respuestas
#: vacías y crea la ambigüedad de "RAW vacío de adquisición fallida"). La
#: anomalía queda declarada en el manifiesto; sin evidencia fabricada.
NOTA_RAW_VACIO = (
    "raw=cuerpo_vacio_anomalo (0 bytes; no se crea artefacto RAW vacío — "
    "M011-C §3: un cuerpo vacío no es observación, ni CSV válido, ni día "
    "sin detecciones; el manifiesto declara la anomalía)"
)


class PipelineBlocked(Exception):
    """La operación requiere autorización o credenciales que no están disponibles."""


@dataclass
class IngestSummary:
    mode: str  # fixture | api | dry-run
    product: str
    state: str  # IngestState.value o 'skipped_already_ingested' o 'dry_run'
    rows_raw: int = 0
    rows_valid: int = 0
    rows_quarantined: int = 0
    raw_path: str | None = None
    raw_sha256: str | None = None
    raw_already_existed: bool = False
    manifest_id: str | None = None
    manifest_path: str | None = None
    parquet_path: str | None = None
    quarantine_path: str | None = None
    planned_url: str | None = None
    planned_requests: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def notas_dry_run(settings: Settings, product: str) -> list[str]:
    lo, hi = settings.day_range_limits
    return [
        "DRY-RUN: no se escribe nada ni se hace ninguna petición de red.",
        f"Destino RAW: {settings.data_dir}/raw/firms/{product}/<año>/<sha256>.csv",
        f"Destino analítico: {settings.data_dir}/processed/observations/",
        f"Límite del servicio: {lo}-{hi} días por request (documentación FIRMS); "
        "esta corrida haría 1 request.",
    ]


def _year_of(date: str | None) -> str:
    if date and len(date) >= 4 and date[:4].isdigit():
        return date[:4]
    return utc_now_iso()[:4]


def _periodo_solicitado(date: str | None, day_range: int) -> tuple[dict[str, str], str | None]:
    """Período de adquisición SOLICITADO a FIRMS (Misión 009, contrato §6).

    Con fecha explícita: ``from=date`` y ``to=date+day_range-1`` — la consulta
    Area de FIRMS cubre ``day_range`` días desde la fecha indicada. Sin fecha,
    FIRMS devuelve los "últimos day_range días" al momento de la consulta: el
    límite superior no es declarable a priori y se deja vacío con nota
    explícita (nunca se inventa el período).
    """
    if date:
        desde = _date.fromisoformat(date)
        hasta = (desde + timedelta(days=day_range - 1)).isoformat()
        return {"from": date, "to": hasta}, None
    return {"from": "", "to": ""}, (
        f"ventana_relativa=day_range_{day_range} ('últimos N días' al momento "
        "de la consulta; límite superior no declarable a priori)"
    )


#: Cuerpos que NO se intentan parsear como CSV de FIRMS (corrección B): se
#: clasifican directamente y la evidencia queda en RAW para reprocesar.
_NON_PARSE_KINDS = {"html": "html_body", "json": "json_body", "non_csv": "non_csv_body"}


def _outcome_state(
    outcome: ParseOutcome | None, parse_error: str | None
) -> tuple[IngestState, str]:
    """Estado final a partir del resultado del parseo (corrección C).

    Distinción explícita de tres situaciones que antes se conflaban:

    - ``parse_failed``          : el archivo NO se pudo interpretar (error de
                                  archivo: encabezado roto, columnas faltantes,
                                  familia incompatible, cuerpo no-CSV).
    - ``success_all_quarantined``: el archivo se interpretó bien y tenía filas,
                                  pero NINGUNA superó el QC de registro.
    - ``unknown``               : cuerpo anómalo (vacío) — no se puede afirmar
                                  ni detecciones ni ausencia (corrección B).

    Invariante de :func:`parse_firms_csv`: ``n_rows == len(records) +
    len(quarantined)`` — toda fila va a válidos o a cuarentena, nunca se
    descarta en silencio.
    """
    if parse_error is not None:
        return IngestState.PARSE_FAILED, parse_error
    assert outcome is not None  # sin error de parseo siempre hay outcome
    if outcome.n_rows == 0:
        if "empty_body" in outcome.notes:
            return IngestState.UNKNOWN, "empty_body"
        return IngestState.SUCCESS_NO_DETECTIONS, "header_only_csv"
    if outcome.records:
        return IngestState.SUCCESS_WITH_DETECTIONS, ""
    # n_rows > 0 sin registros válidos: por el invariante, todas en cuarentena.
    return IngestState.SUCCESS_ALL_QUARANTINED, ""


def _classify_and_parse(
    text: str,
    *,
    product: str,
    settings: Settings,
    run_id: str,
    manifest_id: str,
    ingested_at_utc: str,
    expected_family: str | None,
    source_kind: str | None = None,
) -> tuple[IngestState, str, ParseOutcome | None]:
    """Clasifica el cuerpo de una respuesta/fixture y lo parsea si procede.

    Orden de decisiones (corrección B — no se asume que 2xx implique CSV):

    1. cuerpo vacío        => ``unknown`` (razón ``empty_body``): respuesta
       anómala e indeterminada; FIRMS documenta "sin detecciones" como
       encabezado sin filas, no como cuerpo vacío.
    2. HTML / JSON / texto => ``parse_failed`` con razón explícita
       (``html_body``/``json_body``/``non_csv_body``).
    3. CSV solo encabezado => ``success_no_detections`` (contrato documentado).
    4. CSV con filas       => se parsea; el estado sale de :func:`_outcome_state`
       (con filas válidas / todas en cuarentena / error de parseo).

    ``source_kind`` se propaga al parseo para que la procedencia de cada
    observación refleje el MODO de la corrida (fixture vs firms_api) —
    Misión 008: integridad de procedencia.
    """
    kind = sniff_body(text)
    if kind == "empty":
        return IngestState.UNKNOWN, "empty_body", None
    if kind in _NON_PARSE_KINDS:
        return IngestState.PARSE_FAILED, _NON_PARSE_KINDS[kind], None
    if header_only_csv(text):
        return IngestState.SUCCESS_NO_DETECTIONS, "header_only_csv", None
    try:
        outcome = parse_firms_csv(
            text,
            product=product,
            settings=settings,
            run_id=run_id,
            manifest_id=manifest_id,
            ingested_at_utc=ingested_at_utc,
            expected_family=expected_family,
            source_kind=source_kind,
        )
    except FirmsParseError as exc:
        logger.error("Error de parseo: %s", exc)
        return IngestState.PARSE_FAILED, str(exc), None
    state, reason = _outcome_state(outcome, None)
    return state, reason, outcome


def run_ingest(
    settings: Settings,
    *,
    mode: str,
    product: str,
    fixture_path: str | Path | None = None,
    date: str | None = None,
    day_range: int = 1,
    area: tuple[float, float, float, float] | None = None,
    dry_run: bool = False,
    allow_network: bool = False,
    transport: Transport | None = None,
    run_id: str | None = None,
) -> IngestSummary:
    """Ejecuta una ingesta. Ver modos en el docstring del módulo."""
    if mode not in ("fixture", "api"):
        raise ValueError(f"mode debe ser 'fixture' o 'api'; recibido {mode!r}")

    product_cfg = settings.product_cfg(product)
    # bbox de CONSULTA a FIRMS (rectángulo): incluye vecinos por diseño.
    # La pertenencia territorial la resuelve la capa ADM0, jamás esto.
    bbox = tuple(area) if area else settings.firms_query_bbox
    run_id = run_id or uuid.uuid4().hex
    ingested_at = utc_now_iso()

    raw_store = RawStore(settings.data_dir / "raw")
    parquet_store = ParquetStore(settings.data_dir / "processed")
    manifest_store = ManifestStore(settings.data_dir / "manifests")
    duck = DuckDBStore(
        settings.data_dir / "processed" / "hotspots.duckdb",
        settings.data_dir / "processed",
    )

    # ---------------------------------------------------------------- dry-run
    if mode == "api" and dry_run:
        settings.check_day_range(day_range)
        url = FirmsClient.redact(
            f"{settings.base_url}/api/area/csv/{settings.firms_map_key or KEY_PLACEHOLDER}"
            f"/{product}/{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}/{day_range}"
            + (f"/{date}" if date else ""),
            settings.firms_map_key,
        )
        summary = IngestSummary(
            mode="dry-run",
            product=product,
            state="dry_run",
            planned_url=url,
            planned_requests=1,
            notes=notas_dry_run(settings, product),
        )
        if not settings.has_firms_key:
            summary.notes.append(
                "FIRMS_MAP_KEY no está configurada: la ejecución real la requiere."
            )
        if product_cfg.get("active") is False:
            summary.notes.append(f"Producto inactivo: {product_cfg.get('note', '')}")
        return summary

    # ------------------------------------------------------------- compuerta 1B
    if mode == "api":
        settings.check_day_range(day_range)
        if not allow_network:
            raise PipelineBlocked(
                "Ingesta real bloqueada (compuerta de Fase 1B): se requiere el flag "
                "--allow-network y autorización explícita del propietario para la "
                "primera solicitud real. Usá --dry-run para ver el plan."
            )
        if not settings.has_firms_key:
            raise CredentialsError(
                "FIRMS_MAP_KEY no está configurada. Fase 1B: configurala en .env "
                "(regenerada, nunca la compartida por chat)."
            )

    # ------------------------------------------------------------- fixture mode
    if mode == "fixture":
        if not fixture_path:
            raise ValueError("mode=fixture requiere --fixture <ruta al CSV>")
        fixture_path = Path(fixture_path)
        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture inexistente: {fixture_path}")

        data = fixture_path.read_bytes()
        digest = sha256_bytes(data)
        key = request_key(
            "firms",
            "fixture",
            product,
            {"fixture_name": fixture_path.name, "fixture_sha256": digest},
        )
        prev = manifest_store.find_by_request_key(key)
        if prev is not None and prev.result_state in SUCCESS_STATES:
            logger.info("Fixture ya ingestado (manifest %s): se omite", prev.manifest_id)
            return IngestSummary(
                mode="fixture",
                product=product,
                state="skipped_already_ingested",
                manifest_id=prev.manifest_id,
                manifest_path=str(
                    manifest_store._dir("firms") / f"manifest-{prev.manifest_id}.json"
                ),
                notes=["Idempotencia: la misma petición ya completó con éxito."],
            )

        manifest = Manifest(
            provider="firms",
            source="fixture",
            product=product,
            request_key=key,
            result_state=IngestState.UNKNOWN.value,
            sensor=product_cfg["sensor"],
            satellite_scope=list(product_cfg.get("satellites_expected", [])),
            acquisition_period={"from": date or "", "to": date or ""},
            counts={},
            run_id=run_id,
            created_at_utc=ingested_at,
        ).finalize()

        # M011-C §3: un fixture de 0 bytes tampoco fabrica artefacto RAW vacío.
        if data:
            stored = raw_store.store(
                data, provider="firms", product=product, year=_year_of(date)
            )
            raw_path_f = str(stored.path)
            raw_sha_f = stored.sha256
            raw_ya_exis = stored.already_existed
        else:
            stored = None
            raw_path_f = raw_sha_f = None
            raw_ya_exis = False
            manifest.notes.append(NOTA_RAW_VACIO)
        text = data.decode("utf-8", errors="replace")

        # Clasificación unificada del cuerpo (correcciones B y C): misma lógica
        # para fixture y api — el fixture es el gemelo offline de la respuesta.
        # source_kind explícito: un fixture se etiqueta "fixture" (Misión 008).
        state, reason, outcome = _classify_and_parse(
            text,
            product=product,
            settings=settings,
            run_id=run_id,
            manifest_id=manifest.manifest_id,
            ingested_at_utc=ingested_at,
            expected_family=product_cfg["family"],
            source_kind="fixture",
        )

        rows_raw = outcome.n_rows if outcome else 0
        rows_valid = len(outcome.records) if outcome else 0
        rows_q = len(outcome.quarantined) if outcome else 0

        artifacts: list[Artifact] = []
        if stored is not None:
            artifacts.append(
                Artifact(
                    path=str(stored.path),
                    sha256=stored.sha256,
                    size=stored.size,
                    role="raw_csv",
                )
            )
        pq_path = q_path = None
        if outcome and outcome.records:
            year = _year_of(date) if date else (outcome.records[0].acq_date[:4] or _year_of(None))
            pq_path = parquet_store.append_observations(
                outcome.records, product=product, year=year, run_id=run_id
            )
            if pq_path:
                artifacts.append(
                    Artifact(
                        path=str(pq_path),
                        sha256=_file_sha(pq_path),
                        size=pq_path.stat().st_size,
                        role="observations_parquet",
                    )
                )
        if outcome and outcome.quarantined:
            q_path = parquet_store.append_quarantine(outcome.quarantined, run_id=run_id)
            if q_path:
                artifacts.append(
                    Artifact(
                        path=str(q_path),
                        sha256=_file_sha(q_path),
                        size=q_path.stat().st_size,
                        role="quarantine_parquet",
                    )
                )

        manifest.result_state = state.value
        manifest.processing_state = processing_state_of(state)
        manifest.counts = {
            "rows_raw": rows_raw,
            "rows_valid": rows_valid,
            "rows_quarantined": rows_q,
        }
        manifest.artifacts = artifacts
        # las notas PREVIAS (p. ej. raw=cuerpo_vacio_anomalo, M011-C §3) se
        # conservan y se les añaden la razón del estado y las del parseo.
        notas_previas = list(manifest.notes)
        manifest.notes = (
            notas_previas
            + ([reason] if reason else [])
            + (list(outcome.notes) if outcome else [])
        )
        manifest_path = manifest_store.write(manifest)

        # UN solo registro de estado por corrida (corrección E1: antes un error
        # de parseo en fixture dejaba dos registros idénticos en ingest_status).
        parquet_store.append_status(
            [
                IngestStatusRecord(
                    provider="firms",
                    source="fixture",
                    product=product,
                    state=state.value,
                    reason=reason or f"fixture={Path(fixture_path).name}",
                    occurred_at_utc=ingested_at,
                    run_id=run_id,
                    manifest_id=manifest.manifest_id,
                    context={
                        "rows_raw": rows_raw,
                        "rows_valid": rows_valid,
                        "rows_quarantined": rows_q,
                    },
                ).to_row()
            ],
            run_id=run_id,
        )
        duck.refresh()

        return IngestSummary(
            mode="fixture",
            product=product,
            state=state.value,
            rows_raw=rows_raw,
            rows_valid=rows_valid,
            rows_quarantined=rows_q,
            raw_path=raw_path_f,
            raw_sha256=raw_sha_f,
            raw_already_existed=raw_ya_exis,
            manifest_id=manifest.manifest_id,
            manifest_path=str(manifest_path),
            parquet_path=str(pq_path) if pq_path else None,
            quarantine_path=str(q_path) if q_path else None,
        )

    # ----------------------------------------------------------------- api mode
    # (alcanzable solo con allow_network=True y MAP_KEY configurada)
    transport = transport or RequestsTransport(redact_secrets=settings.secret_values())
    client = FirmsClient(settings.base_url, settings.firms_map_key, transport)
    key = request_key(
        "firms",
        "firms_api",
        product,
        {
            "bbox": list(bbox),
            "bbox_rol": "firms_query_bbox (rectángulo de consulta; no es territorio)",
            "day_range": day_range,
            "date": date,
            "contract": "area_csv_v1",
        },
    )
    prev = manifest_store.find_by_request_key(key)
    if prev is not None and prev.result_state in SUCCESS_STATES:
        return IngestSummary(
            mode="api",
            product=product,
            state="skipped_already_ingested",
            manifest_id=prev.manifest_id,
            notes=["Idempotencia: esta petición exacta ya completó con éxito."],
        )

    fetch = client.fetch_area(product, bbox, day_range=day_range, date=date)
    http_state = classify_response(fetch)
    # Notas completas desde el primer momento (Misión 009: la evidencia del
    # fallo vive en el manifiesto, no solo en el log de sesión).
    notas_api = [f"url={fetch.url_redacted}", f"status={fetch.status_code}"]
    if fetch.error:
        notas_api.append(f"error={fetch.error}")
    intentos = getattr(transport, "last_attempts", []) or []
    if intentos:
        resumen_intentos: dict[str, int] = {}
        for a in intentos:
            k = a.get("kind") or f"http={a.get('status')}"
            resumen_intentos[k] = resumen_intentos.get(k, 0) + 1
        notas_api.append(
            "intentos=" + ", ".join(f"{k} x{v}" for k, v in resumen_intentos.items())
        )
    periodo, nota_periodo = _periodo_solicitado(date, day_range)
    if nota_periodo:
        notas_api.append(nota_periodo)
    manifest = Manifest(
        provider="firms",
        source="firms_api",
        product=product,
        request_key=key,
        result_state=(http_state.value if http_state else IngestState.UNKNOWN.value),
        sensor=product_cfg["sensor"],
        satellite_scope=list(product_cfg.get("satellites_expected", [])),
        acquisition_period=periodo,
        counts={},
        run_id=run_id,
        created_at_utc=ingested_at,
        notes=notas_api,
    ).finalize()

    status_records: list[IngestStatusRecord] = []

    def _status(state: IngestState, reason: str, context: dict | None = None):
        status_records.append(
            IngestStatusRecord(
                provider="firms",
                source="firms_api",
                product=product,
                state=state.value,
                reason=reason,
                occurred_at_utc=ingested_at,
                run_id=run_id,
                manifest_id=manifest.manifest_id,
                context=context or {},
            )
        )

    if http_state is not None:
        _status(http_state, f"http={fetch.status_code}", {"error": fetch.error})
        manifest.processing_state = "failed"
        manifest.counts = {"rows_raw": 0, "rows_valid": 0, "rows_quarantined": 0}
        # Evidencia del fallo (Misión 009, contrato de manifiestos fallidos):
        # solo se conserva RAW cuando la respuesta HTTP trajo bytes REALES
        # (p. ej. 4xx/5xx con cuerpo). Un fallo de transporte (sin respuesta)
        # NO fabrica un artefacto vacío: el manifiesto lo declara explícito.
        artifacts: list[Artifact] = []
        raw_path_f: str | None = None
        raw_sha_f: str | None = None
        if fetch.body:
            stored = raw_store.store(
                fetch.body, provider="firms", product=product, year=_year_of(date)
            )
            artifacts.append(
                Artifact(
                    path=str(stored.path),
                    sha256=stored.sha256,
                    size=stored.size,
                    role="raw_response",
                )
            )
            raw_path_f, raw_sha_f = str(stored.path), stored.sha256
            manifest.notes.append(f"raw_bytes={len(fetch.body)}")
        else:
            manifest.notes.append(
                "raw=no_hubo_cuerpo_de_respuesta (fallo de transporte: sin bytes)"
            )
        manifest.artifacts = artifacts
        manifest_store.write(manifest)
        parquet_store.append_status([r.to_row() for r in status_records], run_id=run_id)
        duck.refresh()
        return IngestSummary(
            mode="api",
            product=product,
            state=http_state.value,
            raw_path=raw_path_f,
            raw_sha256=raw_sha_f,
            manifest_id=manifest.manifest_id,
            manifest_path=str(
                manifest_store._dir("firms") / f"manifest-{manifest.manifest_id}.json"
            ),
            notes=[
                f"status={fetch.status_code}",
                *( [f"error={fetch.error}"] if fetch.error else [] ),
            ],
        )

    # 2xx: guardar evidencia y clasificar el CUERPO (corrección B: HTTP 200 no
    # implica CSV válido; el sniff precede al parseo y distingue vacío/HTML/
    # JSON/texto/CSV). M011-C §3: un cuerpo VACÍO no fabrica artefacto RAW
    # vacío — la anomalía se declara en el manifiesto (estado ``unknown``),
    # el request NO se marca exitoso y puede reintentarse (idempotencia solo
    # con estados exitosos).
    if fetch.body:
        stored = raw_store.store(
            fetch.body, provider="firms", product=product, year=_year_of(date)
        )
        raw_path_ok = str(stored.path)
        raw_sha_ok = stored.sha256
        raw_ya_exis = stored.already_existed
    else:
        stored = None
        raw_path_ok = raw_sha_ok = None
        raw_ya_exis = False
        manifest.notes.append(NOTA_RAW_VACIO)
    text = fetch.text
    state, reason, outcome = _classify_and_parse(
        text,
        product=product,
        settings=settings,
        run_id=run_id,
        manifest_id=manifest.manifest_id,
        ingested_at_utc=ingested_at,
        expected_family=product_cfg["family"],
        source_kind="firms_api",
    )

    rows_raw = outcome.n_rows if outcome else 0
    rows_valid = len(outcome.records) if outcome else 0
    rows_q = len(outcome.quarantined) if outcome else 0
    _status(
        state,
        reason or "ok",
        {
            "rows_raw": rows_raw,
            "rows_valid": rows_valid,
            "rows_quarantined": rows_q,
            "http_status": fetch.status_code,
            "body_kind": sniff_body(text),
        },
    )

    artifacts: list[Artifact] = []
    if stored is not None:
        artifacts.append(
            Artifact(path=str(stored.path), sha256=stored.sha256, size=stored.size, role="raw_csv")
        )
    pq_path = q_path = None  # q_path: bug latente corregido (NameError en parse_failed)
    if outcome and outcome.records:
        year = _year_of(date) if date else (outcome.records[0].acq_date[:4] or _year_of(None))
        pq_path = parquet_store.append_observations(
            outcome.records, product=product, year=year, run_id=run_id
        )
        if pq_path:
            artifacts.append(
                Artifact(
                    path=str(pq_path),
                    sha256=_file_sha(pq_path),
                    size=pq_path.stat().st_size,
                    role="observations_parquet",
                )
            )
    if outcome and outcome.quarantined:
        q_path = parquet_store.append_quarantine(outcome.quarantined, run_id=run_id)
        if q_path:
            artifacts.append(
                Artifact(
                    path=str(q_path),
                    sha256=_file_sha(q_path),
                    size=q_path.stat().st_size,
                    role="quarantine_parquet",
                )
            )

    manifest.result_state = state.value
    manifest.processing_state = processing_state_of(state)
    manifest.counts = {"rows_raw": rows_raw, "rows_valid": rows_valid, "rows_quarantined": rows_q}
    if reason:
        manifest.notes.append(reason)
    manifest.artifacts = artifacts
    manifest_path = manifest_store.write(manifest)
    parquet_store.append_status([r.to_row() for r in status_records], run_id=run_id)
    duck.refresh()

    return IngestSummary(
        mode="api",
        product=product,
        state=state.value,
        rows_raw=rows_raw,
        rows_valid=rows_valid,
        rows_quarantined=rows_q,
        raw_path=raw_path_ok,
        raw_sha256=raw_sha_ok,
        raw_already_existed=raw_ya_exis,
        manifest_id=manifest.manifest_id,
        manifest_path=str(manifest_path),
        parquet_path=str(pq_path) if pq_path else None,
        quarantine_path=str(q_path) if q_path else None,
        planned_url=fetch.url_redacted,
    )


def _file_sha(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()
