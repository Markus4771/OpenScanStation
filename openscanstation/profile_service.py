"""Hilfsfunktionen für die zentrale Profilverwaltung."""
from __future__ import annotations
from openscanstation.profiles import upsert_profile, delete_profile
from openscanstation.scanner_actions import load_actions, save_actions

def values(get):
    return {
        "label": get("label"),
        "dpi": int(get("dpi", "300")),
        "mode": get("mode", "color"),
        "format": get("format", "pdf"),
        "ocr": get("ocr") == "1",
        "duplex": get("duplex") == "1",
        "owner": get("owner"),
        "visibility": get("visibility", "all"),
        "users": [x.strip() for x in get("users").split(",") if x.strip()],
        "destination": get("destination", "local"),
        "show_on_device": get("show_on_device") == "1",
        "device_order": int(get("device_order", "10")),
    }

def save_profile(get, create_only=False):
    return upsert_profile(get("profile_id"), values(get), create_only=create_only)

def remove_profile(profile_id):
    actions = load_actions()
    changed = False
    for action in actions.get("actions", []):
        if action.get("profile") == profile_id:
            action["enabled"] = False
            action["profile"] = ""
            changed = True
    if changed:
        save_actions(actions)
    return delete_profile(profile_id)
