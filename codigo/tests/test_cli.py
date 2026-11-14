"""Pruebas de la CLI (subprocesos reales, sin red)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def _run(*args, data_dir=None):
    env = os.environ.copy()
    cmd = [sys.executable, "-m", "hotspots.cli.app", *args]
    if data_dir:
        cmd += ["--data-dir", str(data_dir)]
    return subprocess.run(
        cmd, cwd=str(PROJECT_ROOT), env=env, capture_output=True, text=True, timeout=120
    )


def test_help():
    p = _run("--help")
    assert p.returncode == 0
    for cmd in ("validate", "manifest", "ingest", "status", "test"):
        assert cmd in p.stdout


def test_validate_fixture_valida(tmp_path):
    p = _run("validate", str(FIXTURES / "synthetic_modis_nrt.csv"), data_dir=tmp_path)
    assert p.returncode == 0
    assert "válidas           : 12" in p.stdout
    assert "cuarentena     : 0" in p.stdout


def test_validate_fixture_con_invalidas(tmp_path):
    p = _run("validate", str(FIXTURES / "synthetic_invalid_rows.csv"), data_dir=tmp_path)
    assert p.returncode == 1
    assert "cuarentena     : 7" in p.stdout


def test_validate_archivo_inexistente(tmp_path):
    p = _run("validate", "/no/existe.csv", data_dir=tmp_path)
    assert p.returncode == 1


def test_ingest_fixture_y_status(tmp_path):
    data = tmp_path / "cli_data"
    p = _run(
        "ingest",
        "--fixture",
        str(FIXTURES / "synthetic_viirs_noaa20_nrt.csv"),
        "--product",
        "VIIRS_NOAA20_NRT",
        data_dir=data,
    )
    assert p.returncode == 0
    assert '"state": "success_with_detections"' in p.stdout

    p2 = _run("status", data_dir=data)
    assert p2.returncode == 0
    assert "VIIRS_NOAA20_NRT" in p2.stdout
    assert "8" in p2.stdout

    # manifiesto listado
    p3 = _run("manifest", "list", data_dir=data)
    assert p3.returncode == 0
    assert "success_with_detections" in p3.stdout


def test_ingest_dry_run_no_escribe(tmp_path):
    data = tmp_path / "dry"
    p = _run(
        "ingest",
        "--source",
        "firms-api",
        "--product",
        "VIIRS_NOAA21_NRT",
        "--date",
        "2026-09-15",
        "--dry-run",
        data_dir=data,
    )
    assert p.returncode == 0
    assert "DRY-RUN" in p.stdout
    assert "{MAP_KEY}" in p.stdout
    if data.exists():
        assert not any(data.rglob("*.parquet")) and not any(data.rglob("*.csv"))


def test_ingest_real_bloqueada(tmp_path):
    p = _run(
        "ingest",
        "--source",
        "firms-api",
        "--product",
        "VIIRS_NOAA21_NRT",
        data_dir=tmp_path,
    )
    assert p.returncode == 1
    assert "BLOQUEADO" in p.stdout
    assert "allow-network" in p.stdout


def test_ingest_idempotente_por_cli(tmp_path):
    data = tmp_path / "idem"
    p1 = _run(
        "ingest",
        "--fixture",
        str(FIXTURES / "synthetic_modis_nrt.csv"),
        "--product",
        "MODIS_NRT",
        data_dir=data,
    )
    p2 = _run(
        "ingest",
        "--fixture",
        str(FIXTURES / "synthetic_modis_nrt.csv"),
        "--product",
        "MODIS_NRT",
        data_dir=data,
    )
    assert p1.returncode == 0 and p2.returncode == 0
    assert '"state": "skipped_already_ingested"' in p2.stdout


def test_status_vacio(tmp_path):
    p = _run("status", data_dir=tmp_path / "vacio")
    assert p.returncode == 0
    assert "sin ingesta todavía" in p.stdout
    # nunca imprime valores de credenciales
    assert "FIRMS_MAP_KEY: UNSET" in p.stdout or "FIRMS_MAP_KEY: SET" in p.stdout


# ------------------------------------------------------------------ verify superseded (Misión 005)

def test_verify_maniesto_superseded(tmp_path, monkeypatch, capsys):
    """Artefacto regenerado + manifiesto nuevo => SUPERSEDED, no inconsistencia."""
    from hotspots.cli.app import main as cli_main
    from hotspots.provenance.manifests import Artifact, Manifest, ManifestStore
    from hotspots.storage.raw import sha256_bytes

    monkeypatch.delenv("HOTSPOTS_DATA_DIR", raising=False)
    data = tmp_path / "data"
    (data / "manifests").mkdir(parents=True)

    art_path = data / "cosa.bin"
    art_path.write_bytes(b"version 1")
    mstore = ManifestStore(data / "manifests")
    m1 = Manifest(
        provider="test", source="test", product="test", request_key="k1",
        result_state="success_with_detections", sensor="-", satellite_scope=[],
        acquisition_period={"from": "", "to": ""}, counts={},
        artifacts=[Artifact(path=str(art_path), sha256=sha256_bytes(art_path.read_bytes()),
                            size=art_path.stat().st_size, role="processed")],
        notes=[], created_at_utc="2026-01-01T00:00:00Z",
    ).finalize()
    mstore.write(m1)

    # el artefacto se regenera y un manifiesto NUEVO lo describe
    art_path.write_bytes(b"version 2 con mas contenido")
    m2 = Manifest(
        provider="test", source="test", product="test", request_key="k2",
        result_state="success_with_detections", sensor="-", satellite_scope=[],
        acquisition_period={"from": "", "to": ""}, counts={},
        artifacts=[Artifact(path=str(art_path), sha256=sha256_bytes(art_path.read_bytes()),
                            size=art_path.stat().st_size, role="processed")],
        notes=[], created_at_utc="2026-01-02T00:00:00Z",
    ).finalize()
    mstore.write(m2)

    rc = cli_main(["verify", "--data-dir", str(data)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "SUPERSEDED" in out
    assert "INCONSISTENCIAS" not in out


def test_verify_tamper_sin_supersede_falla(tmp_path, monkeypatch, capsys):
    """Archivo alterado SIN manifiesto que lo respalde => inconsistencia."""
    from hotspots.cli.app import main as cli_main
    from hotspots.provenance.manifests import Artifact, Manifest, ManifestStore
    from hotspots.storage.raw import sha256_bytes

    monkeypatch.delenv("HOTSPOTS_DATA_DIR", raising=False)
    data = tmp_path / "data"
    (data / "manifests").mkdir(parents=True)
    art_path = data / "cosa.bin"
    art_path.write_bytes(b"honesto")
    m = Manifest(
        provider="test", source="test", product="test", request_key="k1",
        result_state="success_with_detections", sensor="-", satellite_scope=[],
        acquisition_period={"from": "", "to": ""}, counts={},
        artifacts=[Artifact(path=str(art_path), sha256=sha256_bytes(art_path.read_bytes()),
                            size=art_path.stat().st_size, role="processed")],
        notes=[], created_at_utc="2026-01-01T00:00:00Z",
    ).finalize()
    ManifestStore(data / "manifests").write(m)

    art_path.write_bytes(b"manipulado")  # alterado sin re-registrar
    rc = cli_main(["verify", "--data-dir", str(data)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "INCONSISTENCIAS" in out
