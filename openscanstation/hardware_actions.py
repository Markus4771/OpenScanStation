"""Sichere Hardwareaktionen für die OpenScanStation-Weboberfläche."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from openscanstation.hardware import diagnostics, inventory, record_event

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
TEST_SCAN_DIR = DATA_DIR / "test-scans"
SUPPORT_DIR = DATA_DIR / "support"


def _run(command: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-.")
    return cleaned[:80] or fallback


def test_scan(scanner_id: str, *, resolution: int = 100, mode: str = "Gray") -> dict:
    devices = [d for d in inventory()["devices"] if d.get("kind") == "scanner"]
    scanner = next((d for d in devices if d.get("id") == scanner_id), None)
    if not scanner:
        raise ValueError("Scanner nicht gefunden")
    connection = str(scanner.get("connection", ""))
    if not connection or "\x00" in connection:
        raise ValueError("Ungültige Scannerverbindung")
    resolution = min(600, max(75, int(resolution)))
    mode = mode if mode in {"Color", "Gray", "Lineart"} else "Gray"
    TEST_SCAN_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = TEST_SCAN_DIR / f"testscan-{timestamp}.pnm"
    command = [
        "scanimage", "--device-name", connection,
        "--resolution", str(resolution), "--mode", mode,
        "--format", "pnm",
    ]
    try:
        with output.open("wb") as handle:
            result = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE, timeout=120)
    except FileNotFoundError as exc:
        raise RuntimeError("scanimage ist nicht installiert") from exc
    except subprocess.TimeoutExpired as exc:
        output.unlink(missing_ok=True)
        raise RuntimeError("Testscan hat das Zeitlimit überschritten") from exc
    message = result.stderr.decode("utf-8", errors="replace").strip()
    if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
        raise RuntimeError(message or "Testscan fehlgeschlagen")
    record_event("scanner_test_scan", scanner_id, f"Testscan erstellt: {output.name}")
    return {
        "ok": True,
        "message": "Testscan wurde erfolgreich erstellt.",
        "file": output.name,
        "path": str(output),
        "size": output.stat().st_size,
        "resolution": resolution,
        "mode": mode,
        "scanner": scanner.get("name", scanner_id),
        "stderr": message,
    }


def add_ipp_printer(name: str, uri: str) -> dict:
    printer = _safe_name(name, "OpenScanStation-Printer")
    parsed = urlparse(uri.strip())
    if parsed.scheme not in {"ipp", "ipps", "socket", "lpd"} or not parsed.hostname:
        raise ValueError("Erlaubt sind IPP, IPPS, JetDirect/socket oder LPD mit gültigem Hostnamen")
    if not shutil.which("lpadmin"):
        raise RuntimeError("lpadmin ist nicht installiert")
    command = ["lpadmin", "-p", printer, "-E", "-v", uri.strip()]
    if parsed.scheme in {"ipp", "ipps"}:
        command += ["-m", "everywhere"]
    else:
        command += ["-m", "drv:///sample.drv/generic.ppd"]
    code, output = _run(command, 90)
    if code != 0:
        raise RuntimeError(output or "Drucker konnte nicht eingerichtet werden")
    record_event("printer_added", printer, f"Drucker über {parsed.scheme} eingerichtet")
    return {"ok": True, "message": f"Drucker {printer} wurde eingerichtet.", "printer": printer, "uri": uri.strip()}


def create_support_bundle() -> dict:
    SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = SUPPORT_DIR / f"openscanstation-support-{timestamp}.tar.gz"
    command_outputs: dict[str, str] = {}
    commands = {
        "scanimage-L.txt": ["scanimage", "-L"],
        "airscan-discover.txt": ["airscan-discover"],
        "lsusb.txt": ["lsusb"],
        "lpstat.txt": ["lpstat", "-t"],
        "systemctl-failed.txt": ["systemctl", "--failed", "--no-pager"],
        "journal-hardware.txt": ["journalctl", "-u", "openscanstation-hardware.service", "-n", "300", "--no-pager"],
        "journal-gateway.txt": ["journalctl", "-u", "openscanstation-gateway.service", "-n", "300", "--no-pager"],
    }
    for filename, command in commands.items():
        if not shutil.which(command[0]):
            command_outputs[filename] = f"{command[0]} ist nicht installiert\n"
            continue
        _, output = _run(command, 45)
        command_outputs[filename] = output[:100000] + "\n"
    with tarfile.open(archive, "w:gz") as tar:
        payloads = {
            "inventory.json": json.dumps(inventory(), ensure_ascii=False, indent=2) + "\n",
            "diagnostics.json": json.dumps(diagnostics(), ensure_ascii=False, indent=2) + "\n",
            **command_outputs,
        }
        for name, text in payloads.items():
            data = text.encode("utf-8", errors="replace")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
    os.chmod(archive, 0o600)
    record_event("support_bundle", archive.name, "Supportpaket erstellt")
    return {"ok": True, "message": "Supportpaket wurde erstellt.", "file": archive.name, "path": str(archive), "size": archive.stat().st_size}


def latest_support_bundle() -> Path | None:
    bundles = sorted(SUPPORT_DIR.glob("openscanstation-support-*.tar.gz"), reverse=True)
    return bundles[0] if bundles else None
