"""Konfigurierbare Standard-Scanprofile."""
from __future__ import annotations

import json
from pathlib import Path

PROFILE_PATH = Path("/var/lib/openscanstation/profiles.json")
DEFAULT_PROFILES = {
    "rechnung": {"label": "Rechnung", "dpi": 300, "mode": "gray", "format": "pdf", "ocr": True, "duplex": True},
    "lieferschein": {"label": "Lieferschein", "dpi": 300, "mode": "gray", "format": "pdf", "ocr": True, "duplex": True},
    "dokument": {"label": "Dokument", "dpi": 300, "mode": "color", "format": "pdf", "ocr": True, "duplex": False},
    "foto": {"label": "Foto", "dpi": 600, "mode": "color", "format": "jpg", "ocr": False, "duplex": False},
    "archiv": {"label": "Archiv PDF/A", "dpi": 300, "mode": "gray", "format": "pdf", "ocr": True, "duplex": True},
}


def load_profiles() -> dict:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not PROFILE_PATH.exists():
        PROFILE_PATH.write_text(json.dumps(DEFAULT_PROFILES, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = DEFAULT_PROFILES
    return data if isinstance(data, dict) else DEFAULT_PROFILES


def save_profiles(profiles: dict) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
