"""Erweiterte Hardwareverwaltung für OpenScanStation."""
from __future__ import annotations

import json
import os
import socket
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from openscanstation.hardware import driver_status, hardware_events, inventory, record_event
from openscanstation.hardware_actions import hardware_test_status, test_scan_history

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
PROFILES_FILE = DATA_DIR / "hardware_scan_profiles.json"
MANUAL_SCANNERS_FILE = DATA_DIR / "manual_scanners.json"
MAINTENANCE_FILE = DATA_DIR / "hardware_maintenance.json"

DEFAULT_PROFILES = [
    {"id": "document", "name": "Dokument", "resolution": 300, "mode": "Gray", "duplex": True, "format": "pdf", "ocr": True, "remove_blank": True},
    {"id": "color", "name": "Farbe", "resolution": 300, "mode": "Color", "duplex": True, "format": "pdf", "ocr": True, "remove_blank": False},
    {"id": "archive", "name": "Archiv PDF/A", "resolution": 300, "mode": "Gray", "duplex": True, "format": "pdfa", "ocr": True, "remove_blank": True},
    {"id": "photo", "name": "Foto", "resolution": 600, "mode": "Color", "duplex": False, "format": "png", "ocr": False, "remove_blank": False},
]


def _read(path: Path, fallback):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.stem + "-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_profiles() -> list[dict]:
    profiles = _read(PROFILES_FILE, [])
    return profiles if isinstance(profiles, list) and profiles else [dict(item) for item in DEFAULT_PROFILES]


def save_profile(profile_id: str, *, name: str, resolution: int, mode: str, duplex: bool, output_format: str, ocr: bool, remove_blank: bool) -> dict:
    safe_id = "".join(ch for ch in profile_id.lower().strip() if ch.isalnum() or ch in "-_")[:50]
    if not safe_id:
        safe_id = "profile-" + datetime.now().strftime("%Y%m%d%H%M%S")
    if mode not in {"Color", "Gray", "Lineart"}:
        raise ValueError("Ungültiger Farbmodus")
    if output_format not in {"pdf", "pdfa", "png", "jpeg", "tiff"}:
        raise ValueError("Ungültiges Ausgabeformat")
    item = {
        "id": safe_id,
        "name": name.strip()[:80] or safe_id,
        "resolution": min(1200, max(75, int(resolution))),
        "mode": mode,
        "duplex": bool(duplex),
        "format": output_format,
        "ocr": bool(ocr),
        "remove_blank": bool(remove_blank),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    profiles = [profile for profile in load_profiles() if profile.get("id") != safe_id]
    profiles.append(item)
    _write(PROFILES_FILE, profiles)
    record_event("scan_profile", safe_id, f"Scanprofil {item['name']} gespeichert")
    return item


def delete_profile(profile_id: str) -> None:
    profiles = [profile for profile in load_profiles() if profile.get("id") != profile_id]
    _write(PROFILES_FILE, profiles)
    record_event("scan_profile_deleted", profile_id, "Scanprofil gelöscht")


def manual_scanners() -> list[dict]:
    value = _read(MANUAL_SCANNERS_FILE, [])
    return value if isinstance(value, list) else []


def add_manual_scanner(name: str, uri: str, backend: str = "airscan") -> dict:
    parsed = urlparse(uri.strip())
    if parsed.scheme not in {"http", "https", "airscan", "escl"} or not parsed.hostname:
        raise ValueError("Scanner-URI muss HTTP, HTTPS, AirScan oder eSCL verwenden")
    backend = backend if backend in {"airscan", "escl", "brother", "sane-net"} else "airscan"
    scanner_id = f"manual:{parsed.hostname}:{parsed.port or 0}:{backend}"
    item = {
        "id": scanner_id,
        "name": name.strip()[:80] or parsed.hostname,
        "uri": uri.strip()[:512],
        "backend": backend,
        "host": parsed.hostname,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    scanners = [scanner for scanner in manual_scanners() if scanner.get("id") != scanner_id]
    scanners.append(item)
    _write(MANUAL_SCANNERS_FILE, scanners)
    record_event("manual_scanner", scanner_id, f"Manueller Scanner {item['name']} gespeichert")
    return item


def delete_manual_scanner(scanner_id: str) -> None:
    _write(MANUAL_SCANNERS_FILE, [scanner for scanner in manual_scanners() if scanner.get("id") != scanner_id])
    record_event("manual_scanner_deleted", scanner_id, "Manueller Scanner gelöscht")


def _port_open(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def monitor_snapshot() -> dict:
    from openscanstation.hardware import cached_inventory
    data = cached_inventory()
    tests = hardware_test_status()
    drivers = driver_status()
    manual = []
    for scanner in manual_scanners():
        host = scanner.get("host", "")
        manual.append({**scanner, "online": bool(host and any(_port_open(host, port) for port in (80, 443, 6566, 8080)))} )
    devices = []
    for device in data.get("devices", []):
        state = tests.get(device.get("id", ""), {}) if isinstance(tests, dict) else {}
        devices.append({
            "id": device.get("id"), "name": device.get("name"), "kind": device.get("kind"),
            "online": bool(device.get("online")), "enabled": bool(device.get("enabled", True)),
            "last_test": state.get("timestamp", ""), "last_test_ok": state.get("ok"),
            "connection": device.get("connection", ""),
        })
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "counts": data.get("counts", {}), "devices": devices, "manual_scanners": manual,
        "drivers": drivers, "recent_tests": test_scan_history(10), "events": hardware_events(12),
    }


def maintenance_items() -> list[dict]:
    value = _read(MAINTENANCE_FILE, [])
    return value if isinstance(value, list) else []


def save_maintenance(device_id: str, *, task: str, interval_days: int, last_done: str = "") -> dict:
    interval_days = min(3650, max(1, int(interval_days)))
    try:
        last = datetime.fromisoformat(last_done).date() if last_done else datetime.now().date()
    except ValueError:
        last = datetime.now().date()
    item_id = f"{device_id}:{task.strip().lower()[:50]}"
    item = {
        "id": item_id, "device_id": device_id[:512], "task": task.strip()[:120] or "Wartung",
        "interval_days": interval_days, "last_done": last.isoformat(),
        "next_due": (last + timedelta(days=interval_days)).isoformat(),
    }
    items = [entry for entry in maintenance_items() if entry.get("id") != item_id]
    items.append(item)
    _write(MAINTENANCE_FILE, items)
    record_event("maintenance", device_id, f"Wartung geplant: {item['task']}")
    return item


def complete_maintenance(item_id: str) -> dict:
    items = maintenance_items()
    item = next((entry for entry in items if entry.get("id") == item_id), None)
    if not item:
        raise ValueError("Wartungseintrag nicht gefunden")
    today = datetime.now().date()
    item["last_done"] = today.isoformat()
    item["next_due"] = (today + timedelta(days=int(item.get("interval_days", 30)))).isoformat()
    _write(MAINTENANCE_FILE, items)
    record_event("maintenance_done", item.get("device_id", ""), f"Wartung erledigt: {item.get('task', '')}")
    return item
