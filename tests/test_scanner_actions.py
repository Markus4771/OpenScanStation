from __future__ import annotations

import json

from openscanstation import scanner_actions


def test_defaults_have_nine_slots(monkeypatch, tmp_path):
    monkeypatch.setattr(scanner_actions, "ACTIONS_FILE", tmp_path / "scanner_actions.json")
    data = scanner_actions.load_actions()
    assert len(data["actions"]) == 9
    assert data["actions"][0]["label"] == "Rechnung"
    assert data["actions"][0]["enabled"] is True


def test_save_and_reload(monkeypatch, tmp_path):
    target = tmp_path / "scanner_actions.json"
    monkeypatch.setattr(scanner_actions, "ACTIONS_FILE", target)
    data = scanner_actions.load_actions()
    data["actions"][0]["label"] = "Eingangsrechnung"
    data["actions"][0]["tags"] = ["Buchhaltung", "Eingang"]
    scanner_actions.save_actions(data)
    loaded = scanner_actions.load_actions()
    assert loaded["actions"][0]["label"] == "Eingangsrechnung"
    assert loaded["actions"][0]["tags"] == ["Buchhaltung", "Eingang"]
    assert json.loads(target.read_text(encoding="utf-8"))["schema_version"] == 1


def test_default_slot_event_mapping(monkeypatch, tmp_path):
    monkeypatch.setattr(scanner_actions, "ACTIONS_FILE", tmp_path / "scanner_actions.json")
    action = scanner_actions.action_for_event("kodak:usb", "slot-2")
    assert action is not None
    assert action["id"] == "action-2"


def test_device_specific_binding(monkeypatch, tmp_path):
    monkeypatch.setattr(scanner_actions, "ACTIONS_FILE", tmp_path / "scanner_actions.json")
    scanner_actions.set_binding("samsung:airscan", "scan-button", "action-3")
    action = scanner_actions.action_for_event("samsung:airscan", "scan-button")
    assert action is not None
    assert action["id"] == "action-3"
