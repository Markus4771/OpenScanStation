"""Schnelle und fehlertolerante Hardware-Erkennung für OpenScanStation."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from openscanstation.scanner.manager import ScannerManager
from openscanstation.scanner_settings import load_settings as load_scanner_settings

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
SETTINGS_FILE = DATA_DIR / "hardware_settings.json"
EVENTS_FILE = DATA_DIR / "hardware_events.json"
CACHE_FILE = DATA_DIR / "hardware_inventory_cache.json"
CACHE_TTL = 30

_cache_lock = threading.Lock()
_memory_cache: dict = {"timestamp": 0.0, "inventory": None, "network": None}


def _run(command: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return 127, f"{command[0]} ist nicht installiert"
    except subprocess.TimeoutExpired:
        return 124, f"Zeitüberschreitung nach {timeout} Sekunden: {' '.join(command)}"
    except OSError as exc:
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
        "disabled_printers": sorted({str(v)[:256] for v in data.get("disabled_printers", [])}),
        "manual_devices": [dict(v) for v in data.get("manual_devices", []) if isinstance(v, dict)][:100],
    }
    _atomic_write(SETTINGS_FILE, normalized)
    invalidate_cache()
    return normalized


def invalidate_cache() -> None:
    with _cache_lock:
        _memory_cache["timestamp"] = 0.0
        _memory_cache["inventory"] = None
        _memory_cache["network"] = None


def update_printer(printer_id: str, *, alias: str, enabled: bool, make_default: bool) -> dict:
    if not printer_id or "/" in printer_id or "\\" in printer_id:
        raise ValueError("Ungültiger Druckername")
    settings = load_settings()
    aliases = settings.setdefault("printer_aliases", {})
    disabled = set(settings.setdefault("disabled_printers", []))
    if alias.strip():
        aliases[printer_id] = alias.strip()[:80]
    else:
        aliases.pop(printer_id, None)
    if enabled:
        disabled.discard(printer_id)
    else:
        disabled.add(printer_id)
        if settings.get("default_printer") == printer_id:
            settings["default_printer"] = ""
    if make_default and enabled:
        settings["default_printer"] = printer_id
    settings["disabled_printers"] = sorted(disabled)
    saved = save_settings(settings)
    record_event("printer_settings", printer_id, "Druckereinstellungen geändert")
    return saved


def record_event(event_type: str, device_id: str, message: str) -> None:
    try:
        events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        if not isinstance(events, list):
            events = []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        events = []
    events.insert(0, {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "type": str(event_type)[:60],
        "device_id": str(device_id)[:512],
        "message": str(message)[:500],
    })
    _atomic_write(EVENTS_FILE, events[:200])


def hardware_events(limit: int = 30) -> list[dict]:
    try:
        events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        return events[:limit] if isinstance(events, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _scanner_devices() -> tuple[list[dict], list[str]]:
    settings = load_scanner_settings()
    aliases = settings.get("aliases", {})
    disabled = set(settings.get("disabled", []))
    default_id = settings.get("default_scanner", "")
    devices: list[dict] = []
    errors: list[str] = []
    try:
        result = ScannerManager().discover()
        errors.extend(str(getattr(error, "message", error)) for error in getattr(result, "errors", []))
        for item in result.scanners:
            scanner_id = f"{item.plugin_id}:{item.connection}"
            devices.append({
                "id": scanner_id,
                "kind": "scanner",
                "name": aliases.get(scanner_id) or item.name,
                "original_name": item.name,
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
    except Exception as exc:
        errors.append(f"Scannererkennung: {exc}")
    return devices, errors


def printer_uri(name: str) -> str:
    code, output = _run(["lpstat", "-v", name], 4)
    return output.split(":", 1)[1].strip() if code == 0 and ":" in output else name


def printer_jobs(name: str = "") -> list[dict]:
    command = ["lpstat", "-o"] + ([name] if name else [])
    code, output = _run(command, 4)
    if code != 0:
        return []
    jobs = []
    for line in output.splitlines():
        parts = line.split()
        if parts:
            jobs.append({"id": parts[0], "owner": parts[1] if len(parts) > 1 else "", "raw": line})
    return jobs


def printer_capabilities(name: str) -> dict:
    code, output = _run(["lpoptions", "-p", name, "-l"], 5)
    text = output.casefold() if code == 0 else ""
    return {
        "duplex": "duplex" in text or "sides" in text,
        "color": "colormodel" in text or "print-color-mode" in text,
        "media": "pagesize" in text or "media" in text,
        "staple": "staple" in text,
        "punch": "punch" in text,
    }


def _printer_devices() -> tuple[list[dict], list[str]]:
    if not shutil.which("lpstat"):
        return [], ["lpstat ist nicht installiert"]
    settings = load_settings()
    aliases = settings.get("printer_aliases", {})
    disabled = set(settings.get("disabled_printers", []))
    configured_default = settings.get("default_printer", "")
    code, output = _run(["lpstat", "-p", "-d"], 5)
    if code not in {0, 1}:
        return [], [output]
    printers: list[dict] = []
    system_default = ""
    jobs = printer_jobs()
    jobs_by_printer: dict[str, list[dict]] = {}
    for job in jobs:
        printer = str(job.get("id", "")).rsplit("-", 1)[0]
        jobs_by_printer.setdefault(printer, []).append(job)
    for line in output.splitlines():
        if line.startswith("system default destination:"):
            system_default = line.split(":", 1)[1].strip()
        elif line.startswith("printer "):
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[1]
            online = "disabled" not in line.lower()
            printers.append({
                "id": name,
                "kind": "printer",
                "name": aliases.get(name) or name,
                "original_name": name,
                "manufacturer": "",
                "model": "CUPS-Drucker",
                "connection": printer_uri(name),
                "backend": "cups",
                "enabled": name not in disabled,
                "default": name == (configured_default or system_default),
                "online": online,
                "state": line,
                "capabilities": printer_capabilities(name),
                "jobs": jobs_by_printer.get(name, []),
            })
    return printers, []


def _load_disk_cache() -> dict | None:
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return None


def cached_inventory() -> dict:
    """Liefert garantiert ohne Hardwarezugriff den letzten bekannten Stand."""
    with _cache_lock:
        cached = _memory_cache.get("inventory")
        if isinstance(cached, dict):
            return cached
    cached = _load_disk_cache()
    if isinstance(cached, dict):
        cached["cached"] = True
        return cached
    return {
        "updated_at": "noch nicht ermittelt",
        "cached": True,
        "devices": [],
        "errors": [],
        "counts": {"scanner": 0, "printer": 0, "online": 0, "disabled": 0, "print_jobs": 0},
    }


def inventory(force: bool = False) -> dict:
    now = time.monotonic()
    with _cache_lock:
        cached = _memory_cache.get("inventory")
        age = now - float(_memory_cache.get("timestamp", 0.0))
        if not force and isinstance(cached, dict) and age < CACHE_TTL:
            return cached
    scanners, scanner_errors = _scanner_devices()
    printers, printer_errors = _printer_devices()
    devices = scanners + printers
    result = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "cached": False,
        "devices": devices,
        "errors": scanner_errors + printer_errors,
        "counts": {
            "scanner": len(scanners),
            "printer": len(printers),
            "online": sum(1 for d in devices if d.get("online")),
            "disabled": sum(1 for d in devices if not d.get("enabled", True)),
            "print_jobs": sum(len(d.get("jobs", [])) for d in printers),
        },
    }
    try:
        _atomic_write(CACHE_FILE, result)
    except OSError:
        pass
    with _cache_lock:
        _memory_cache["timestamp"] = now
        _memory_cache["inventory"] = result
    return result


def inventory_fallback() -> dict:
    """Liefert bei Erkennungsfehlern den letzten bekannten Stand."""
    try:
        return inventory()
    except Exception as exc:
        cached = _load_disk_cache() or {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "devices": [],
            "counts": {"scanner": 0, "printer": 0, "online": 0, "disabled": 0, "print_jobs": 0},
        }
        cached["cached"] = True
        cached.setdefault("errors", []).append(str(exc))
        return cached


def network_discovery(force: bool = False) -> list[dict]:
    now = time.monotonic()
    with _cache_lock:
        cached = _memory_cache.get("network")
        age = now - float(_memory_cache.get("timestamp", 0.0))
        if not force and isinstance(cached, list) and age < CACHE_TTL:
            return cached
    devices: list[dict] = []
    if shutil.which("airscan-discover"):
        _, output = _run(["airscan-discover"], 7)
        current: dict = {}
        for line in output.splitlines():
            text = line.strip()
            if not text:
                continue
            if text.startswith("[") and text.endswith("]"):
                if current:
                    devices.append(current)
                current = {"name": text.strip("[]"), "protocol": "AirScan/eSCL", "uri": "", "model": ""}
            elif "=" in text and current:
                key, value = [part.strip() for part in text.split("=", 1)]
                if key in {"uri", "model", "type"}:
                    current[key] = value
        if current:
            devices.append(current)
    if shutil.which("lpinfo"):
        _, output = _run(["lpinfo", "-v"], 6)
        for line in output.splitlines():
            if any(proto in line for proto in ("ipp://", "ipps://", "dnssd://", "socket://", "lpd://")):
                uri = line.split(maxsplit=1)[-1]
                devices.append({"name": uri, "protocol": "Drucker", "uri": uri, "model": "Netzwerkdrucker"})
    seen: set[str] = set()
    unique: list[dict] = []
    for item in devices:
        key = str(item.get("uri") or item.get("name") or "")
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    with _cache_lock:
        _memory_cache["network"] = unique
    return unique


def usb_devices() -> list[dict]:
    if not shutil.which("lsusb"):
        return []
    _, output = _run(["lsusb"], 5)
    result = []
    for line in output.splitlines():
        match = re.match(r"Bus (\d+) Device (\d+): ID ([0-9a-fA-F:]+) (.*)", line)
        if match:
            result.append({"bus": match.group(1), "device": match.group(2), "id": match.group(3), "description": match.group(4), "raw": line})
    return result


def tcp_probe(host: str, ports: list[int] | None = None) -> dict:
    host = host.strip()
    if not host or len(host) > 255:
        raise ValueError("Ungültiger Host")
    ports = ports or [80, 443, 631, 9100]
    result = {"host": host, "resolved": "", "ports": {}}
    try:
        result["resolved"] = socket.gethostbyname(host)
    except OSError as exc:
        result["error"] = str(exc)
        return result
    for port in ports:
        sock = socket.socket()
        sock.settimeout(0.8)
        try:
            result["ports"][str(port)] = sock.connect_ex((result["resolved"], port)) == 0
        finally:
            sock.close()
    return result


def brother_assistant() -> dict:
    inv = inventory_fallback()
    candidates = [
        d for d in inv.get("devices", [])
        if d.get("kind") == "scanner" and "brother" in (
            str(d.get("manufacturer", "")) + str(d.get("model", "")) + str(d.get("name", ""))
        ).casefold()
    ]
    drivers = driver_status()
    try:
        airscan = network_discovery()
    except Exception:
        airscan = []
    return {
        "scanner_found": bool(candidates),
        "scanners": candidates,
        "airscan_devices": [d for d in airscan if "brother" in json.dumps(d).casefold()],
        "driver": drivers.get("brother", False),
        "sane": drivers.get("sane", False),
        "airscan": drivers.get("airscan", False),
        "recommendations": [
            "AirScan/eSCL bevorzugen, wenn der Scanner im Netzwerk erkannt wird.",
            "Bei fehlender Erkennung IP-Adresse und Weboberfläche des ADS-2600We prüfen.",
            "Anschließend Verbindungstest und Standardscanner festlegen.",
        ],
        "errors": inv.get("errors", []),
    }


def diagnostics() -> dict:
    commands = {
        "sane": (["scanimage", "-L"], 8),
        "airscan": (["airscan-discover"], 8),
        "usb": (["lsusb"], 5),
        "cups": (["lpstat", "-p", "-d"], 5),
        "drucker-verbindungen": (["lpstat", "-v"], 5),
        "druckaufträge": (["lpstat", "-o"], 5),
    }
    checks: dict = {}
    for key, (command, timeout) in commands.items():
        if not shutil.which(command[0]):
            checks[key] = {"ok": False, "output": f"{command[0]} ist nicht installiert"}
            continue
        code, output = _run(command, timeout)
        checks[key] = {"ok": code == 0, "returncode": code, "output": output[:20000]}
    checks["drivers"] = driver_status()
    checks["inventory"] = inventory_fallback()
    return checks


def driver_status() -> dict:
    return {
        "sane": bool(shutil.which("scanimage")),
        "airscan": bool(shutil.which("airscan-discover")),
        "cups": bool(shutil.which("lp") and shutil.which("lpstat")),
        "brother": any(Path(path).exists() for path in (
            "/usr/lib/sane/libsane-brother4.so",
            "/usr/lib64/sane/libsane-brother4.so",
            "/usr/lib/x86_64-linux-gnu/sane/libsane-brother4.so",
        )),
        "barcode": bool(shutil.which("zbarimg")),
        "ocr": bool(shutil.which("tesseract")),
        "usb": bool(shutil.which("lsusb")),
        "ipp": bool(shutil.which("lpinfo")),
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
    code, output = _run(command, 15)
    if code != 0:
        raise RuntimeError(output or "Testseite konnte nicht gesendet werden")
    record_event("printer_test", printer, output or "Testseite wurde gesendet")
    return {"ok": True, "message": output or "Testseite wurde gesendet"}


def cancel_print_job(job_id: str) -> dict:
    if not job_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", job_id):
        raise ValueError("Ungültige Auftrags-ID")
    code, output = _run(["cancel", job_id], 8)
    if code != 0:
        raise RuntimeError(output or "Druckauftrag konnte nicht abgebrochen werden")
    record_event("print_job_cancelled", job_id, "Druckauftrag abgebrochen")
    return {"ok": True, "message": output or "Druckauftrag wurde abgebrochen"}
