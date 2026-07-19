"""Konfigurierbare und sicher gespeicherte Scanprofile."""
from __future__ import annotations

import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path

PROFILE_PATH = Path(os.environ.get("OPENSCANSTATION_PROFILE_PATH", "/var/lib/openscanstation/profiles.json"))
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
ALLOWED_DPI = (75, 100, 150, 200, 240, 300, 400, 600)
ALLOWED_MODES = ("color", "gray", "lineart")
ALLOWED_FORMATS = ("pdf", "png", "jpg")

DEFAULT_PROFILES = {
    "rechnung": {"label": "Rechnung", "dpi": 300, "mode": "gray", "format": "pdf", "ocr": True, "duplex": True},
    "lieferschein": {"label": "Lieferschein", "dpi": 300, "mode": "gray", "format": "pdf", "ocr": True, "duplex": True},
    "dokument": {"label": "Dokument", "dpi": 300, "mode": "color", "format": "pdf", "ocr": True, "duplex": False},
    "foto": {"label": "Foto", "dpi": 600, "mode": "color", "format": "jpg", "ocr": False, "duplex": False},
    "archiv": {"label": "Archiv PDF/A", "dpi": 300, "mode": "gray", "format": "pdf", "ocr": True, "duplex": True},
}


def normalize_profile(profile_id: str, raw: object) -> dict:
    if not PROFILE_ID_PATTERN.fullmatch(profile_id):
        raise ValueError("Profil-ID darf nur Kleinbuchstaben, Zahlen, Bindestrich und Unterstrich enthalten")
    if not isinstance(raw, dict):
        raise ValueError("Ungültige Profildaten")

    label = str(raw.get("label", "")).strip()
    if not label:
        raise ValueError("Profilname darf nicht leer sein")
    if len(label) > 80:
        raise ValueError("Profilname darf höchstens 80 Zeichen enthalten")

    try:
        dpi = int(raw.get("dpi", 300))
    except (TypeError, ValueError) as exc:
        raise ValueError("DPI muss eine Zahl sein") from exc
    if dpi not in ALLOWED_DPI:
        raise ValueError(f"DPI muss einer dieser Werte sein: {', '.join(map(str, ALLOWED_DPI))}")

    mode = str(raw.get("mode", "color")).lower()
    if mode not in ALLOWED_MODES:
        raise ValueError("Ungültiger Farbmodus")

    output_format = str(raw.get("format", "pdf")).lower()
    if output_format not in ALLOWED_FORMATS:
        raise ValueError("Ungültiges Ausgabeformat")

    return {
        "label": label,
        "dpi": dpi,
        "mode": mode,
        "format": output_format,
        "ocr": bool(raw.get("ocr", False)),
        "duplex": bool(raw.get("duplex", False)),
    }


def normalize_profiles(data: object) -> dict:
    if not isinstance(data, dict):
        return deepcopy(DEFAULT_PROFILES)
    normalized: dict[str, dict] = {}
    for raw_id, raw_profile in data.items():
        profile_id = str(raw_id).strip().lower()
        try:
            normalized[profile_id] = normalize_profile(profile_id, raw_profile)
        except ValueError:
            continue
    return normalized or deepcopy(DEFAULT_PROFILES)


def load_profiles() -> dict:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not PROFILE_PATH.exists():
        save_profiles(deepcopy(DEFAULT_PROFILES))
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_PROFILES)
    return normalize_profiles(data)


def save_profiles(profiles: dict) -> dict:
    normalized = normalize_profiles(profiles)
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="profiles-", suffix=".json", dir=PROFILE_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, PROFILE_PATH)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return normalized


def upsert_profile(profile_id: str, profile: dict, *, create_only: bool = False) -> dict:
    profile_id = profile_id.strip().lower()
    normalized_profile = normalize_profile(profile_id, profile)
    profiles = load_profiles()
    if create_only and profile_id in profiles:
        raise ValueError("Diese Profil-ID ist bereits vorhanden")
    profiles[profile_id] = normalized_profile
    return save_profiles(profiles)


def delete_profile(profile_id: str) -> dict:
    profiles = load_profiles()
    if profile_id not in profiles:
        raise ValueError("Scanprofil wurde nicht gefunden")
    if len(profiles) <= 1:
        raise ValueError("Das letzte Scanprofil kann nicht gelöscht werden")
    del profiles[profile_id]
    return save_profiles(profiles)
