#!/usr/bin/env python3
"""Cliente HTTP de FIRMS que lee la MAP_KEY SOLO del entorno — M011-C §1.

Problema que resuelve: ``preflight_firms.sh`` pasaba la clave dentro de URLs
entregadas como argumentos a ``curl`` (visible en la lista de procesos,
``ps``/``/proc/*/cmdline``). Este cliente construye las URLs DENTRO del
proceso, con la clave leída de la variable de entorno ``FIRMS_MAP_KEY``:
la clave nunca aparece en ``argv``, ni en stdout, ni en mensajes de error.

Contrato de seguridad (M011-C §1, verificable con las pruebas de
``tests/test_seguridad_m011c.py``):

- La clave se lee EXCLUSIVAMENTE de ``os.environ["FIRMS_MAP_KEY"]``.
- No existe opción alguna para pasar la clave por argumento; un intento de
  hacerlo se rechaza con código 2.
- Todo texto de error se redacta (``{MAP_KEY}``) antes de imprimirse o
  persistirse — urllib incluye la URL completa en sus excepciones, y la URL
  de los endpoints autenticados contiene la clave.
- El cuerpo de la respuesta se escribe en un archivo (``--out``) para que el
  llamador lo valide; stdout recibe SOLO el código HTTP (3 dígitos, ``000``
  si falló el transporte), para que el shell decida sin parsear secretos.
- HTTPS obligatorio: la base debe ser ``https://`` salvo ``localhost``/
  ``127.0.0.1``/``::1`` (excepción exclusiva para las pruebas offline con
  servidor local; documentada y restringida a esos hosts).

Subcomandos:

  probe              GET {base}/api/area/  — sondeo de TRANSPORTE (sin clave
                     en la URL; mide que el host responde por HTTPS, no la
                     validez del API: eso lo confirma ``mapkey-status`` con
                     su esquema documentado — M011-C §4).
  mapkey-status      GET {base}/mapserver/mapkey_status/?MAP_KEY=...  —
                     estado de transacciones de la clave (saldo real).
  data-availability  GET {base}/api/data_availability/csv/{KEY}/ALL —
                     disponibilidad NRT por producto.

Uso::

    FIRMS_MAP_KEY=... python3 firms_http.py mapkey-status --out estado.json
    # -> imprime el código HTTP (p. ej. 200) y escribe el cuerpo en estado.json

Salidas: 0 si pudo ejecutarse (el código HTTP va por stdout; el llamador
decide), 2 ante uso inválido (argumentos, base no HTTPS, clave por argv).
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "https://firms.modaps.eosdis.nasa.gov"
MARKER = "{MAP_KEY}"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

EXIT_OK = 0
EXIT_USO = 2


def _redact(texto: str, clave: str | None) -> str:
    """Reemplaza cualquier aparición de la clave por el marcador público."""
    if clave and clave in texto:
        return texto.replace(clave, MARKER)
    return texto


def _validar_base(base: str) -> tuple[bool, str]:
    """HTTPS obligatorio, salvo localhost (pruebas offline documentadas)."""
    try:
        parsed = urllib.parse.urlparse(base)
    except ValueError as exc:
        return False, f"base ilegible: {exc}"
    if parsed.scheme == "https" and parsed.netloc:
        return True, ""
    if parsed.scheme == "http" and (parsed.hostname or "") in LOCAL_HOSTS:
        return True, ""
    return False, (
        f"base debe ser https:// (recibido esquema {parsed.scheme or 'vacío'}; "
        "http:// solo se admite en localhost para pruebas offline)"
    )


def _get(
    url: str,
    *,
    timeout: float,
    out_path: str | None,
    err_path: str | None,
    clave: str | None,
) -> str:
    """Ejecuta GET; devuelve el código HTTP como texto (000 = sin transporte).

    Escribe el cuerpo en ``out_path`` solo si hubo respuesta HTTP. Escribe el
    error de transporte (REDACTADO) en ``err_path`` si se pidió. Ninguna de
    las dos salidas contiene jamás la clave.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fireia-m011c/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            cuerpo = resp.read()
            codigo = resp.getcode()
    except urllib.error.HTTPError as exc:
        # Respuesta HTTP de error: el cuerpo ES evidencia del proveedor.
        try:
            cuerpo = exc.read() or b""
        except Exception:  # noqa: BLE001 — cuerpo ilegible no tapa el código
            cuerpo = b""
        codigo = exc.code
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de transporte
        mensaje = _redact(f"{type(exc).__name__}: {exc}", clave)
        if err_path:
            with open(err_path, "w", encoding="utf-8") as fh:
                fh.write(mensaje + "\n")
        print("000")
        return "000"

    if out_path:
        with open(out_path, "wb") as fh:
            fh.write(cuerpo)
    print(str(codigo or 0).zfill(3))
    return str(codigo or 0).zfill(3)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="firms_http.py",
        description=(
            "Cliente HTTP de FIRMS sin exposición de la MAP_KEY: la clave se "
            "lee SOLO del entorno (FIRMS_MAP_KEY) y jamás viaja en argv."
        ),
    )
    parser.add_argument(
        "subcomando",
        choices=["probe", "mapkey-status", "data-availability"],
        help="endpoint a consultar",
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("FIRMS_BASE", DEFAULT_BASE),
        help=f"base del servicio (default {DEFAULT_BASE}; FIRMS_BASE del entorno)",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="segundos")
    parser.add_argument("--out", default=None, help="archivo para el cuerpo de la respuesta")
    parser.add_argument(
        "--err-out", default=None, help="archivo para el error de transporte (redactado)"
    )
    parser.add_argument(
        "--sensor",
        default="ALL",
        help="sensor para data-availability (default ALL)",
    )
    args, desconocidos = parser.parse_known_args(argv if argv is not None else None)

    # Defensa activa: si alguien intenta pasar la clave como argumento
    # (posicional u opción), se rechaza con mensaje explícito, sin procesar
    # nada y aunque argparse ya la hubiera rechazado como desconocida.
    argumentos = argv if argv is not None else sys.argv[1:]
    for sospechoso in argumentos:
        if sospechoso.startswith("MAP_KEY=") or sospechoso.startswith("--map-key"):
            print(
                "ERROR: la MAP_KEY no se pasa por argumento; usa la variable "
                "de entorno FIRMS_MAP_KEY (M011-C §1).",
                file=sys.stderr,
            )
            return EXIT_USO
    if desconocidos:
        print(f"ERROR: argumentos no reconocidos: {desconocidos}", file=sys.stderr)
        return EXIT_USO

    ok, motivo = _validar_base(args.base)
    if not ok:
        print(f"ERROR: {motivo}", file=sys.stderr)
        return EXIT_USO

    clave = os.environ.get("FIRMS_MAP_KEY") or None
    base = args.base.rstrip("/")

    if args.subcomando == "probe":
        # Sondeo de TRANSPORTE: sin clave en la URL (M011-C §4).
        url = f"{base}/api/area/"
    elif args.subcomando == "mapkey-status":
        if not clave:
            print("ERROR: FIRMS_MAP_KEY no está en el entorno.", file=sys.stderr)
            return EXIT_USO
        # La clave va en el query string, DENTRO del proceso: jamás en argv.
        query = urllib.parse.urlencode({"MAP_KEY": clave})
        url = f"{base}/mapserver/mapkey_status/?{query}"
    else:  # data-availability
        if not clave:
            print("ERROR: FIRMS_MAP_KEY no está en el entorno.", file=sys.stderr)
            return EXIT_USO
        sensor = urllib.parse.quote(args.sensor, safe="")
        url = f"{base}/api/data_availability/csv/{clave}/{sensor}"

    _get(
        url,
        timeout=args.timeout,
        out_path=args.out,
        err_path=args.err_out,
        clave=clave,
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
