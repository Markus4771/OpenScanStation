"""Einheitliche Hardware-Erkennung für Scanner und CUPS-Drucker."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from openscanstation.scanner.manager import ScannerManager
from openscanstation.scanner_settings import load_settings as load_scanner_settings

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
SETTINGS_FILE = DATA_DIR / "hardware_settings.json"
EVENTS_FILE = DATA_DIR / "hardware_events.json"


def _run(command: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _atomic_write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.stem + "-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_settings(data: dict) -> dict:
    normalized = {
        "default_printer": str(data.get("default_printer", ""))[:256],
        "printer_aliases": {str(k)[:256]: str(v).strip()[:80] for k, v in dict(data.get("printer_aliases", {})).items()},
        "disabled_printers": [str(v)[:256] for v in data.get("disabled_printers", [])],
    }
    _atomic_write(SETTINGS_FILE, normalized)
    return normalized


def _scanner_devices() -> list[dict]:
    settings = load_scanner_settings()
    aliases = settings.get("aliases", {})
    disabled = set(settings.get("disabled", []))
    default_id = settings.get("default_scanner", "")
    result = ScannerManager().discover()
    devices = []
    for item in result.scanners:
        scanner_id = f"{item.plugin_id}:{item.connection}"
        devices.append({
            "id": scanner_id,
            "kind": "scanner",
            "name": aliases.get(scanner_id) or item.name,
            "manufacturer": item.manufacturer,
            "model": item.model,
            "connection": item.connection,
            "backend": item.plugin_id,
            "enabled": scanner_id not in disabled,
            "default": scanner_id == default_id,
            "online": True,
            "capabilities": {
                "adf": item.capabilities.adf,
                "duplex": item.capabilities.duplex,
                "network": item.capabilities.network,
                "usb": item.capabilities.usb,
                "resolutions_dpi": list(item.capabilities.resolutions_dpi),
                "color_modes": list(item.capabilities.color_modes),
            },
        })
    return devices


def _printer_devices() -> list[dict]:
    settings = load_settings()
    aliases = settings.get("printer_aliases", {})
    disabled = set(settings.get("disabled_printers", []))
    configured_default = settings.get("default_printer", "")
    code, output = _run(["lpstat", "-p", "-d"], 15)
    printers: list[dict] = []
    system_default = ""
    for line in output.splitlines():
        if line.startswith("system default destination:"):
            system_default = line.split(":", 1)[1].strip()
        elif line.startswith("printer "):
            name = line.split()[1]
            online = "disabled" not in line.lower()
            printers.append({
                "id": name,
                "kind": "printer",
                "name": aliases.get(name) or name,
                "manufacturer": "",
                "model": "CUPS-Drucker",
                "connection": name,
                "backend": "cups",
                "enabled": name not in disabled,
                "default": name == (configured_default or system_default),
                "online": online,
                "state": line,
                "capabilities": printer_capabilities(name),
            })
    if code != 0 and not shutil.which("lpstat"):
        return []
    return printers


def printer_capabilities(name: str) -> dict:
    code, output = _run(["lpoptions", "-p", name, "-l"], 15)
    text = output.casefold() if code == 0 else ""
    return {
        "duplex": "duplex" in text or "sides" in text,
        "color": "colormodel" in text or "print-color-mode" in text,
        "media": "pagesize" in text or "media" in text,
        "staple": "staple" in text,
        "punch": "punch" in text,
    }


def inventory() -> dict:
    scanners = _scanner_devices()
    printers = _printer_devices()
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "devices": scanners + printers,
        "counts": {
            "scanner": len(scanners),
            "printer": len(printers),
            "online": sum(1 for d in scanners + printers if d.get("online")),
            "disabled": sum(1 for d in scanners + printers if not d.get("enabled", True)),
        },
    }


def diagnostics() -> dict:
    checks = {}
    commands = {
        "sane": ["scanimage", "-L"],
        "airscan": ["airscan-discover"],
        "usb": ["lsusb"],
        "cups": ["lpstat", "-p", "-d"],
        "printers": ["lpinfo", "-v"],
    }
    for key, command in commands.items():
        if not shutil.which(command[0]):
            checks[key] = {"ok": False, "output": f"{command[0]} ist nicht installiert"}
            continue
        code, output = _run(command, 45 if key in {"sane", "airscan"} else 20)
        checks[key] = {"ok": code == 0, "output": output[:20000]}
    checks["drivers"] = driver_status()
    return checks


def driver_status() -> dict:
    return {
        "sane": bool(shutil.which("scanimage")),
        "airscan": bool(shutil.which("airscan-discover")),
        "cups": bool(shutil.which("lp") and shutil.which("lpstat")),
        "brother": any(Path(path).exists() for path in ("/usr/lib/sane/libsane-brother4.so", "/usr/lib64/sane/libsane-brother4.so")),
        "barcode": bool(shutil.which("zbarimg")),
        "ocr": bool(shutil.which("tesseract")),
    }


def print_test_page(printer: str) -> dict:
    if not printer or "/" in printer or "\\" in printer:
        raise ValueError("Ungültiger Druckername")
    test_file = Path("/usr/share/cups/data/testprint")
    command = ["lp", "-d", printer]
    if test_file.is_file():
        command.append(str(test_file))
    else:
        command.extend(["-t", "OpenScanStation Testseite", "/etc/hostname"])
    code, output = _run(command, 30)
    if code != 0:
        raise RuntimeError(output or "Testseite konnte nicht gesendet werden")
    return {"ok": True, "message": output or "Testseite wurde gesendet"}
