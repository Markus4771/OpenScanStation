"""Konfigurierbare Scanneraktionen für Kodak, Samsung und weitere Geräte."""
from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
ACTIONS_FILE = DATA_DIR / "scanner_actions.json"

DEFAULT_ACTIONS = {
    "schema_version": 1,
    "actions": [
        {
            "id": f"action-{slot}",
            "slot": slot,
            "enabled": slot <= 4,
            "label": ["Rechnung", "Lieferschein", "Archiv", "Freier Scan"][slot - 1] if slot <= 4 else f"Funktion {slot}",
            "profile": ["rechnung", "lieferschein", "archiv", "dokument"][slot - 1] if slot <= 4 else "dokument",
            "title": ["Rechnung", "Lieferschein", "Archivdokument", "Dokument"][slot - 1] if slot <= 4 else "Dokument",
            "tags": [],
            "destination": "local",
            "post_action": "none",
        }
        for slot in range(1, 10)
    ],
    "bindings": {},
}


def _normalize(data: object) -> dict:
    if not isinstance(data, dict):
        data = {}
    result = deepcopy(DEFAULT_ACTIONS)
    actions = data.get("actions")
    if isinstance(actions, list):
        by_slot = {item["slot"]: item for item in result["actions"]}
        for raw in actions:
            if not isinstance(raw, dict):
                continue
            try:
                slot = int(raw.get("slot", 0))
            except (TypeError, ValueError):
                continue
            if slot not in by_slot:
                continue
            item = by_slot[slot]
            item.update({
                "enabled": bool(raw.get("enabled", item["enabled"])),
                "label": str(raw.get("label", item["label"]))[:32].strip() or item["label"],
                "profile": str(raw.get("profile", item["profile"]))[:64],
                "title": str(raw.get("title", item["title"]))[:120].strip() or item["title"],
                "tags": [str(value).strip()[:64] for value in raw.get("tags", []) if str(value).strip()][:20],
                "destination": str(raw.get("destination", "local"))[:64],
                "post_action": str(raw.get("post_action", "none"))[:64],
            })
    bindings = data.get("bindings")
    if isinstance(bindings, dict):
        result["bindings"] = {
            str(scanner_id)[:512]: {
                str(key)[:64]: str(value)[:64]
                for key, value in mapping.items()
                if isinstance(mapping, dict)
            }
            for scanner_id, mapping in bindings.items()
        }
    return result


def load_actions() -> dict:
    try:
        return _normalize(json.loads(ACTIONS_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return deepcopy(DEFAULT_ACTIONS)


def save_actions(data: dict) -> dict:
    normalized = _normalize(data)
    ACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="scanner-actions-", suffix=".json", dir=ACTIONS_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, ACTIONS_FILE)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return normalized


def action_by_id(action_id: str) -> dict | None:
    return next((item for item in load_actions()["actions"] if item["id"] == action_id), None)


def action_for_event(scanner_id: str, event: str) -> dict | None:
    data = load_actions()
    mapping = data["bindings"].get(scanner_id, {})
    action_id = mapping.get(event)
    if not action_id and event.startswith("slot-"):
        action_id = f"action-{event.removeprefix('slot-')}"
    return next((item for item in data["actions"] if item["id"] == action_id and item["enabled"]), None)


def set_binding(scanner_id: str, event: str, action_id: str) -> dict:
    data = load_actions()
    data["bindings"].setdefault(scanner_id, {})[event] = action_id
    return save_actions(data)
