"""Einheitliche Hardware-Erkennung für Scanner und CUPS-Drucker."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
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
        "disabled_printers": sorted({str(v)[:256] for v in data.get("disabled_printers", [])}),
        "manual_devices": [dict(v) for v in data.get("manual_devices", []) if isinstance(v, dict)][:100],
    }
    _atomic_write(SETTINGS_FILE, normalized)
    return normalized


def update_printer(printer_id: str, *, alias: str, enabled: bool, make_default: bool) -> dict:
    if not printer_id or "/" in printer_id or "\\" in printer_id:
        raise ValueError("Ungültiger Druckername")
    settings = load_settings()
    aliases = settings.setdefault("printer_aliases", {})
    disabled = set(settings.setdefault("disabled_printers", []))
    if alias.strip(): aliases[printer_id] = alias.strip()[:80]
    else: aliases.pop(printer_id, None)
    if enabled: disabled.discard(printer_id)
    else:
        disabled.add(printer_id)
        if settings.get("default_printer") == printer_id: settings["default_printer"] = ""
    if make_default and enabled: settings["default_printer"] = printer_id
    settings["disabled_printers"] = sorted(disabled)
    saved = save_settings(settings)
    record_event("printer_settings", printer_id, "Druckereinstellungen geändert")
    return saved


def record_event(event_type: str, device_id: str, message: str) -> None:
    try:
        events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        if not isinstance(events, list): events = []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        events = []
    events.insert(0, {"timestamp": datetime.now().isoformat(timespec="seconds"), "type": str(event_type)[:60], "device_id": str(device_id)[:512], "message": str(message)[:500]})
    _atomic_write(EVENTS_FILE, events[:200])


def hardware_events(limit: int = 30) -> list[dict]:
    try:
        events = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        return events[:limit] if isinstance(events, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError): return []


def _scanner_devices() -> list[dict]:
    settings = load_scanner_settings(); aliases = settings.get("aliases", {}); disabled = set(settings.get("disabled", [])); default_id = settings.get("default_scanner", "")
    result = ScannerManager().discover(); devices = []
    for item in result.scanners:
        scanner_id = f"{item.plugin_id}:{item.connection}"
        devices.append({"id": scanner_id, "kind": "scanner", "name": aliases.get(scanner_id) or item.name, "original_name": item.name, "manufacturer": item.manufacturer, "model": item.model, "connection": item.connection, "backend": item.plugin_id, "enabled": scanner_id not in disabled, "default": scanner_id == default_id, "online": True, "capabilities": {"adf": item.capabilities.adf, "duplex": item.capabilities.duplex, "network": item.capabilities.network, "usb": item.capabilities.usb, "resolutions_dpi": list(item.capabilities.resolutions_dpi), "color_modes": list(item.capabilities.color_modes)}})
    return devices


def printer_uri(name: str) -> str:
    code, output = _run(["lpstat", "-v", name], 10)
    return output.split(":", 1)[1].strip() if code == 0 and ":" in output else name


def printer_jobs(name: str = "") -> list[dict]:
    command = ["lpstat", "-o"] + ([name] if name else []); code, output = _run(command, 10)
    if code != 0: return []
    jobs = []
    for line in output.splitlines():
        parts = line.split()
        if parts: jobs.append({"id": parts[0], "owner": parts[1] if len(parts) > 1 else "", "raw": line})
    return jobs


def printer_capabilities(name: str) -> dict:
    code, output = _run(["lpoptions", "-p", name, "-l"], 15); text = output.casefold() if code == 0 else ""
    return {"duplex": "duplex" in text or "sides" in text, "color": "colormodel" in text or "print-color-mode" in text, "media": "pagesize" in text or "media" in text, "staple": "staple" in text, "punch": "punch" in text}


def _printer_devices() -> list[dict]:
    settings = load_settings(); aliases = settings.get("printer_aliases", {}); disabled = set(settings.get("disabled_printers", [])); configured_default = settings.get("default_printer", "")
    code, output = _run(["lpstat", "-p", "-d"], 15); printers = []; system_default = ""
    for line in output.splitlines():
        if line.startswith("system default destination:"): system_default = line.split(":", 1)[1].strip()
        elif line.startswith("printer "):
            name = line.split()[1]; online = "disabled" not in line.lower()
            printers.append({"id": name, "kind": "printer", "name": aliases.get(name) or name, "original_name": name, "manufacturer": "", "model": "CUPS-Drucker", "connection": printer_uri(name), "backend": "cups", "enabled": name not in disabled, "default": name == (configured_default or system_default), "online": online, "state": line, "capabilities": printer_capabilities(name), "jobs": printer_jobs(name)})
    return [] if code != 0 and not shutil.which("lpstat") else printers


def inventory() -> dict:
    scanners = _scanner_devices(); printers = _printer_devices(); devices = scanners + printers
    return {"updated_at": datetime.now().isoformat(timespec="seconds"), "devices": devices, "counts": {"scanner": len(scanners), "printer": len(printers), "online": sum(1 for d in devices if d.get("online")), "disabled": sum(1 for d in devices if not d.get("enabled", True)), "print_jobs": sum(len(d.get("jobs", [])) for d in printers)}}


def network_discovery() -> list[dict]:
    devices: list[dict] = []
    if shutil.which("airscan-discover"):
        _, output = _run(["airscan-discover"], 35)
        current: dict = {}
        for line in output.splitlines():
            text = line.strip()
            if not text: continue
            if text.startswith("[") and text.endswith("]"):
                if current: devices.append(current)
                current = {"name": text.strip("[]"), "protocol": "AirScan/eSCL", "uri": "", "model": ""}
            elif "=" in text and current:
                key, value = [p.strip() for p in text.split("=", 1)]
                if key in {"uri", "model", "type"}: current[key] = value
        if current: devices.append(current)
    if shutil.which("lpinfo"):
        _, output = _run(["lpinfo", "-v"], 20)
        for line in output.splitlines():
            if any(proto in line for proto in ("ipp://", "ipps://", "dnssd://", "socket://", "lpd://")):
                parts = line.split(maxsplit=1); uri = parts[-1]
                devices.append({"name": uri, "protocol": "Drucker", "uri": uri, "model": "Netzwerkdrucker"})
    seen = set(); unique = []
    for item in devices:
        key = item.get("uri") or item.get("name")
        if key and key not in seen: seen.add(key); unique.append(item)
    return unique


def usb_devices() -> list[dict]:
    if not shutil.which("lsusb"): return []
    _, output = _run(["lsusb"], 15); result = []
    for line in output.splitlines():
        match = re.match(r"Bus (\d+) Device (\d+): ID ([0-9a-fA-F:]+) (.*)", line)
        if match: result.append({"bus": match.group(1), "device": match.group(2), "id": match.group(3), "description": match.group(4), "raw": line})
    return result


def tcp_probe(host: str, ports: list[int] | None = None) -> dict:
    host = host.strip()
    if not host or len(host) > 255: raise ValueError("Ungültiger Host")
    ports = ports or [80, 443, 631, 9100]
    result = {"host": host, "resolved": "", "ports": {}}
    try: result["resolved"] = socket.gethostbyname(host)
    except OSError as exc: result["error"] = str(exc); return result
    for port in ports:
        sock = socket.socket(); sock.settimeout(1.2)
        try: result["ports"][str(port)] = sock.connect_ex((result["resolved"], port)) == 0
        finally: sock.close()
    return result


def brother_assistant() -> dict:
    inv = inventory(); candidates = [d for d in inv["devices"] if d["kind"] == "scanner" and ("brother" in (d.get("manufacturer", "") + d.get("model", "") + d.get("name", "")).casefold())]
    drivers = driver_status(); airscan = network_discovery()
    return {"scanner_found": bool(candidates), "scanners": candidates, "airscan_devices": [d for d in airscan if "brother" in json.dumps(d).casefold()], "driver": drivers.get("brother", False), "sane": drivers.get("sane", False), "airscan": drivers.get("airscan", False), "recommendations": ["AirScan/eSCL bevorzugen, wenn der Scanner im Netzwerk erkannt wird.", "Bei fehlender Erkennung IP-Adresse und Weboberfläche des ADS-2600We prüfen.", "Anschließend Verbindungstest und Standardscanner festlegen."]}


def diagnostics() -> dict:
    commands = {"sane": ["scanimage", "-L"], "airscan": ["airscan-discover"], "usb": ["lsusb"], "cups": ["lpstat", "-p", "-d"], "drucker-verbindungen": ["lpstat", "-v"], "druckaufträge": ["lpstat", "-o"]}; checks = {}
    for key, command in commands.items():
        if not shutil.which(command[0]): checks[key] = {"ok": False, "output": f"{command[0]} ist nicht installiert"}; continue
        code, output = _run(command, 45 if key in {"sane", "airscan"} else 20); checks[key] = {"ok": code == 0, "output": output[:20000]}
    checks["drivers"] = driver_status(); return checks


def driver_status() -> dict:
    return {"sane": bool(shutil.which("scanimage")), "airscan": bool(shutil.which("airscan-discover")), "cups": bool(shutil.which("lp") and shutil.which("lpstat")), "brother": any(Path(path).exists() for path in ("/usr/lib/sane/libsane-brother4.so", "/usr/lib64/sane/libsane-brother4.so", "/usr/lib/x86_64-linux-gnu/sane/libsane-brother4.so")), "barcode": bool(shutil.which("zbarimg")), "ocr": bool(shutil.which("tesseract")), "usb": bool(shutil.which("lsusb")), "ipp": bool(shutil.which("lpinfo"))}


def print_test_page(printer: str) -> dict:
    if not printer or "/" in printer or "\\" in printer: raise ValueError("Ungültiger Druckername")
    test_file = Path("/usr/share/cups/data/testprint"); command = ["lp", "-d", printer]
    command.append(str(test_file)) if test_file.is_file() else command.extend(["-t", "OpenScanStation Testseite", "/etc/hostname"])
    code, output = _run(command, 30)
    if code != 0: raise RuntimeError(output or "Testseite konnte nicht gesendet werden")
    record_event("printer_test", printer, output or "Testseite wurde gesendet"); return {"ok": True, "message": output or "Testseite wurde gesendet"}


def cancel_print_job(job_id: str) -> dict:
    if not job_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", job_id): raise ValueError("Ungültige Auftrags-ID")
    code, output = _run(["cancel", job_id], 15)
    if code != 0: raise RuntimeError(output or "Druckauftrag konnte nicht abgebrochen werden")
    record_event("print_job_cancelled", job_id, "Druckauftrag abgebrochen"); return {"ok": True, "message": output or "Druckauftrag wurde abgebrochen"}
