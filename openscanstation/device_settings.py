"""Gerätebezogene Einstellungen für Scanner."""
from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
SETTINGS_FILE = DATA_DIR / "device_settings.json"

DEFAULT_SETTINGS = {"schema_version": 1, "devices": {}}


def _normalize(data: object) -> dict:
    result = deepcopy(DEFAULT_SETTINGS)
    if not isinstance(data, dict):
        return result
    devices = data.get("devices")
    if not isinstance(devices, dict):
        return result
    for device_id, raw in devices.items():
        if not isinstance(raw, dict):
            continue
        try:
            standby_minutes = int(raw.get("standby_minutes", 15))
        except (TypeError, ValueError):
            standby_minutes = 15
        standby_minutes = min(240, max(0, standby_minutes))
        result["devices"][str(device_id)[:512]] = {
            "standby_minutes": standby_minutes,
            "standby_enabled": bool(raw.get("standby_enabled", True)),
        }
    return result


def load_device_settings() -> dict:
    try:
        return _normalize(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return deepcopy(DEFAULT_SETTINGS)


def save_device_settings(data: dict) -> dict:
    normalized = _normalize(data)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="device-settings-", suffix=".json", dir=SETTINGS_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, SETTINGS_FILE)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return normalized


def get_device_setting(device_id: str) -> dict:
    data = load_device_settings()
    return deepcopy(data["devices"].get(device_id, {
        "standby_minutes": 15,
        "standby_enabled": True,
    }))


def set_device_standby(device_id: str, minutes: int, enabled: bool = True) -> dict:
    if not device_id:
        raise ValueError("Geräte-ID fehlt")
    minutes = int(minutes)
    if minutes < 0 or minutes > 240:
        raise ValueError("Standby-Zeit muss zwischen 0 und 240 Minuten liegen")
    data = load_device_settings()
    data["devices"][device_id] = {
        "standby_minutes": minutes,
        "standby_enabled": bool(enabled),
    }
    return save_device_settings(data)["devices"][device_id]
