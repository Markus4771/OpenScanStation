"""Sichere Hardwareaktionen für die OpenScanStation-Weboberfläche."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from openscanstation.hardware import diagnostics, inventory, record_event

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
TEST_SCAN_DIR = DATA_DIR / "test-scans"
SUPPORT_DIR = DATA_DIR / "support"
TEST_HISTORY_FILE = TEST_SCAN_DIR / "history.json"
HARDWARE_STATUS_FILE = DATA_DIR / "hardware_status.json"
MAX_TEST_SCANS = 30


def _run(command: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-.")
    return cleaned[:80] or fallback


def _read_json(path: Path, fallback: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def _update_scanner_status(scanner_id: str, *, ok: bool, message: str, preview: str = "") -> None:
    state = _read_json(HARDWARE_STATUS_FILE, {})
    if not isinstance(state, dict):
        state = {}
    scanners = state.setdefault("scanners", {})
    scanners[scanner_id] = {
        "ok": bool(ok),
        "message": str(message)[:1000],
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "preview": preview,
    }
    _write_json(HARDWARE_STATUS_FILE, state)


def hardware_test_status() -> dict:
    state = _read_json(HARDWARE_STATUS_FILE, {})
    return state if isinstance(state, dict) else {}


def _append_test_history(entry: dict) -> None:
    history = _read_json(TEST_HISTORY_FILE, [])
    if not isinstance(history, list):
        history = []
    history.insert(0, entry)
    _write_json(TEST_HISTORY_FILE, history[:MAX_TEST_SCANS])


def _cleanup_test_scans() -> None:
    history = _read_json(TEST_HISTORY_FILE, [])
    if not isinstance(history, list):
        history = []
    keep = history[:MAX_TEST_SCANS]
    keep_names = {
        str(item.get(key, ""))
        for item in keep
        for key in ("file", "source_file")
        if item.get(key)
    }
    for path in TEST_SCAN_DIR.glob("testscan-*"):
        if path.is_file() and path.name not in keep_names:
            path.unlink(missing_ok=True)
    if history != keep:
        _write_json(TEST_HISTORY_FILE, keep)


def list_test_scans(limit: int = 20) -> list[dict]:
    history = _read_json(TEST_HISTORY_FILE, [])
    if not isinstance(history, list):
        return []
    return history[: max(1, min(100, int(limit)))]


def test_scan_history(limit: int = 20) -> list[dict]:
    """Kompatibilitätsname für ältere und neue Hardware-WebGUI-Stände."""
    return list_test_scans(limit)


def test_scan_file(filename: str) -> Path | None:
    safe = Path(filename).name
    if safe != filename or not safe.startswith("testscan-"):
        return None
    path = TEST_SCAN_DIR / safe
    return path if path.is_file() else None


def delete_test_scan(filename: str) -> dict:
    path = test_scan_file(filename)
    if path is None:
        raise ValueError("Testscan wurde nicht gefunden")
    history = _read_json(TEST_HISTORY_FILE, [])
    related = []
    if isinstance(history, list):
        for item in history:
            if item.get("file") == path.name or item.get("source_file") == path.name:
                related.extend([item.get("file", ""), item.get("source_file", "")])
        history = [item for item in history if item.get("file") != path.name and item.get("source_file") != path.name]
        _write_json(TEST_HISTORY_FILE, history)
    for name in set(filter(None, related + [path.name])):
        candidate = TEST_SCAN_DIR / Path(name).name
        candidate.unlink(missing_ok=True)
    record_event("scanner_test_scan_deleted", path.name, "Testscan gelöscht")
    return {"ok": True, "message": "Testscan wurde gelöscht."}


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
    source = TEST_SCAN_DIR / f"testscan-{timestamp}.pnm"
    preview = TEST_SCAN_DIR / f"testscan-{timestamp}.png"
    command = [
        "scanimage", "--device-name", connection,
        "--resolution", str(resolution), "--mode", mode,
        "--format", "pnm",
    ]
    try:
        with source.open("wb") as handle:
            result = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE, timeout=120)
    except FileNotFoundError as exc:
        _update_scanner_status(scanner_id, ok=False, message="scanimage ist nicht installiert")
        raise RuntimeError("scanimage ist nicht installiert") from exc
    except subprocess.TimeoutExpired as exc:
        source.unlink(missing_ok=True)
        _update_scanner_status(scanner_id, ok=False, message="Testscan hat das Zeitlimit überschritten")
        raise RuntimeError("Testscan hat das Zeitlimit überschritten") from exc
    message = result.stderr.decode("utf-8", errors="replace").strip()
    if result.returncode != 0 or not source.is_file() or source.stat().st_size == 0:
        source.unlink(missing_ok=True)
        failure = message or "Testscan fehlgeschlagen"
        _update_scanner_status(scanner_id, ok=False, message=failure)
        record_event("scanner_test_scan_failed", scanner_id, failure)
        raise RuntimeError(failure)

    preview_name = ""
    try:
        from PIL import Image
        with Image.open(source) as image:
            image.thumbnail((1600, 1600))
            image.save(preview, "PNG", optimize=True)
        preview_name = preview.name
    except Exception as exc:
        message = (message + f"\nVorschau konnte nicht erzeugt werden: {exc}").strip()

    created_at = datetime.now().isoformat(timespec="seconds")
    entry = {
        "created_at": created_at,
        "scanner_id": scanner_id,
        "scanner": scanner.get("name", scanner_id),
        "file": preview_name or source.name,
        "source_file": source.name,
        "size": (preview.stat().st_size if preview_name else source.stat().st_size),
        "resolution": resolution,
        "mode": mode,
        "message": message,
    }
    _append_test_history(entry)
    _cleanup_test_scans()
    _update_scanner_status(scanner_id, ok=True, message="Testscan erfolgreich", preview=entry["file"])
    record_event("scanner_test_scan", scanner_id, f"Testscan erstellt: {entry['file']}")
    return {
        "ok": True,
        "message": "Testscan wurde erfolgreich erstellt.",
        "file": entry["file"],
        "source_file": source.name,
        "path": str(TEST_SCAN_DIR / entry["file"]),
        "size": entry["size"],
        "resolution": resolution,
        "mode": mode,
        "scanner": entry["scanner"],
        "created_at": created_at,
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
            "hardware-test-status.json": json.dumps(hardware_test_status(), ensure_ascii=False, indent=2) + "\n",
            "test-scan-history.json": json.dumps(list_test_scans(100), ensure_ascii=False, indent=2) + "\n",
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
