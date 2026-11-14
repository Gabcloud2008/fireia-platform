"""Conector de NASA FIRMS (Area API + data_availability + missing_data).

Contratos verificados contra la documentación oficial (consultada 2026-11-11,
sin consumir la API; ver configs/sources.yaml y docs/sources.md):

- Area CSV:  GET {base}/api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}[/{DATE}]
             DAY_RANGE: 1-5 · DATE: YYYY-MM-DD (opcional) · límite 5000 trans./10 min
- Data availability: GET {base}/api/data_availability/csv/{MAP_KEY}/{SENSOR|ALL}
- Missing data: GET {base}/api/missing_data/  (página HTML con tabla; sin
  contrato CSV documentado — se descarga y el parseo se resuelve aparte)

Clasificación de respuestas: ver :func:`classify_response` (nivel HTTP) y
:func:`sniff_body` / :func:`header_only_csv` (nivel cuerpo). Los textos
exactos de error de FIRMS (p. ej. MAP_KEY inválida) no están documentados de
forma exhaustiva; los patrones actuales son heurísticas conservadoras marcadas
para verificación en vivo en la primera consulta real (Fase 1B, ítem del
registro de pendientes).

Contrato del cuerpo (documentación pública FIRMS Area CSV): una consulta
exitosa SIN detecciones devuelve el CSV con SOLO la fila de encabezado. Un
cuerpo VACÍO no es "sin detecciones": es una respuesta anómala e
indeterminada (Misión 002, corrección B). No se asume que HTTP 200 implique
CSV válido.
"""

from __future__ import annotations

from hotspots.ingestion.base import FetchResult, Transport
from hotspots.quality.states import IngestState

AREA_PATH = "/api/area/csv"
AVAILABILITY_PATH = "/api/data_availability/csv"
MISSING_DATA_PATH = "/api/missing_data/"

KEY_PLACEHOLDER = "{MAP_KEY}"


class CredentialsError(Exception):
    """Falta la credencial necesaria para la operación."""


class FirmsClient:
    """Cliente de los servicios web de FIRMS. Requiere un Transport inyectado."""

    def __init__(self, base_url: str, map_key: str | None, transport: Transport):
        if not map_key:
            raise CredentialsError(
                "FIRMS_MAP_KEY no está configurada. Configurala en .env "
                "(ver .env.example) para operaciones reales."
            )
        self.base_url = base_url.rstrip("/")
        self._map_key = map_key
        self._transport = transport

    # ------------------------------------------------------------------- URLs
    def area_url(
        self,
        product: str,
        bbox: tuple[float, float, float, float] | list[float],
        day_range: int = 1,
        date: str | None = None,
    ) -> str:
        w, s, e, n = bbox
        area = f"{w},{s},{e},{n}"
        url = f"{self.base_url}{AREA_PATH}/{self._map_key}/{product}/{area}/{int(day_range)}"
        if date:
            url += f"/{date}"
        return url

    def availability_url(self, sensor: str = "ALL") -> str:
        return f"{self.base_url}{AVAILABILITY_PATH}/{self._map_key}/{sensor}"

    def missing_data_url(self) -> str:
        return f"{self.base_url}{MISSING_DATA_PATH}"

    @staticmethod
    def redact(url: str, map_key: str | None) -> str:
        return url.replace(map_key, KEY_PLACEHOLDER) if map_key else url

    # ------------------------------------------------------------------ fetchs
    def fetch_area(
        self,
        product: str,
        bbox: tuple[float, float, float, float] | list[float],
        day_range: int = 1,
        date: str | None = None,
    ) -> FetchResult:
        url = self.area_url(product, bbox, day_range, date)
        result = self._transport.get(url, timeout=60.0)
        result.url_redacted = self.redact(url, self._map_key)
        return result

    def fetch_data_availability(self, sensor: str = "ALL") -> FetchResult:
        url = self.availability_url(sensor)
        result = self._transport.get(url, timeout=60.0)
        result.url_redacted = self.redact(url, self._map_key)
        return result

    def fetch_missing_data_page(self) -> FetchResult:
        """Página HTML de fechas con datos faltantes (parseo diferido)."""
        url = self.missing_data_url()
        result = self._transport.get(url, timeout=60.0)
        result.url_redacted = url  # sin MAP_KEY
        return result


def classify_response(fetch: FetchResult) -> IngestState | None:
    """Clasifica el resultado HTTP.

    Devuelve el estado si es determinable a nivel HTTP/texto, o ``None`` si el
    cuerpo hay que parsearlo como CSV (el caller decide success_with/without).
    """
    if fetch.error is not None:
        return IngestState.DOWNLOAD_FAILED

    status = fetch.status_code
    if status in (401, 403):
        return IngestState.AUTHENTICATION_FAILED
    if status == 429:
        return IngestState.DOWNLOAD_FAILED  # reason: rate_limited (contexto aparte)
    if status is not None and status >= 500:
        return IngestState.DOWNLOAD_FAILED
    if status is not None and status >= 400:
        return IngestState.DOWNLOAD_FAILED

    text = fetch.text.strip()
    lowered = text.lower()
    # Heurística conservadora: FIRMS responde texto plano ante claves inválidas.
    if "map_key" in lowered and ("invalid" in lowered or "not valid" in lowered):
        return IngestState.AUTHENTICATION_FAILED
    if lowered.startswith("invalid") or "not authorized" in lowered:
        return IngestState.AUTHENTICATION_FAILED

    return None  # 2xx: hay que parsear el cuerpo


def header_only_csv(text: str) -> bool:
    """True SOLO si el cuerpo es un CSV de FIRMS con encabezado y cero filas.

    Un cuerpo vacío NO es header-only (corrección B): la ausencia de
    detecciones está documentada por FIRMS como "encabezado sin filas", no
    como cuerpo vacío. Ese caso lo detecta :func:`sniff_body` como ``empty``.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    if len(lines) != 1:
        return False
    first = lines[0].strip().lstrip("\ufeff").lower()
    return first.startswith("latitude")


#: Tipos de cuerpo reconocibles por :func:`sniff_body`.
BODY_KINDS = ("empty", "html", "json", "non_csv", "csv")


def sniff_body(text: str) -> str:
    """Clasifica el CUERPO de una respuesta HTTP 2xx (corrección B).

    Devuelve uno de :data:`BODY_KINDS`:

    - ``empty``   : cuerpo vacío o solo espacios — anómalo e indeterminado
                    (FIRMS documenta "sin detecciones" como encabezado sin
                    filas, no como cuerpo vacío).
    - ``html``    : página HTML (mantenimiento, error del proveedor, portal).
    - ``json``    : JSON inesperado en un endpoint CSV.
    - ``csv``     : primera línea no vacía comienza con ``latitude`` — el
                    contrato documentado de los CSV de FIRMS (MODIS y VIIRS
                    comparten esa primera columna).
    - ``non_csv`` : cualquier otra cosa (texto de error del proveedor, cuerpo
                    corrupto, formato desconocido).

    Es deliberadamente conservadora: no intenta interpretar mensajes del
    proveedor más allá de los patrones de autenticación que ya cubre
    :func:`classify_response`; ante la duda, ``non_csv``.
    """
    if text is None or not text.strip():
        return "empty"
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered.startswith("<!") or "<html" in lowered[:512] or "</html>" in lowered[-512:]:
        return "html"
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"
    first_line = stripped.splitlines()[0].strip().lstrip("\ufeff").lower()
    if first_line.startswith("latitude"):
        return "csv"
    return "non_csv"
