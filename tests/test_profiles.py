from __future__ import annotations

import json

import pytest

from openscanstation import profiles


def _use_temp_profile_file(monkeypatch, tmp_path):
    target = tmp_path / "profiles.json"
    monkeypatch.setattr(profiles, "PROFILE_PATH", target)
    return target


def test_defaults_are_created(monkeypatch, tmp_path):
    target = _use_temp_profile_file(monkeypatch, tmp_path)
    data = profiles.load_profiles()
    assert "dokument" in data
    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8"))["dokument"]["dpi"] == 300


def test_create_and_edit_profile(monkeypatch, tmp_path):
    _use_temp_profile_file(monkeypatch, tmp_path)
    profiles.load_profiles()
    profiles.upsert_profile(
        "buchhaltung",
        {
            "label": "Buchhaltung",
            "dpi": 300,
            "mode": "gray",
            "format": "pdf",
            "ocr": True,
            "duplex": True,
        },
        create_only=True,
    )
    assert profiles.load_profiles()["buchhaltung"]["label"] == "Buchhaltung"

    profiles.upsert_profile(
        "buchhaltung",
        {
            "label": "Buchhaltung Eingang",
            "dpi": 400,
            "mode": "color",
            "format": "pdf",
            "ocr": True,
            "duplex": False,
        },
    )
    edited = profiles.load_profiles()["buchhaltung"]
    assert edited["label"] == "Buchhaltung Eingang"
    assert edited["dpi"] == 400
    assert edited["duplex"] is False


def test_duplicate_create_is_rejected(monkeypatch, tmp_path):
    _use_temp_profile_file(monkeypatch, tmp_path)
    profiles.load_profiles()
    with pytest.raises(ValueError, match="bereits vorhanden"):
        profiles.upsert_profile(
            "dokument",
            {
                "label": "Noch ein Dokument",
                "dpi": 300,
                "mode": "color",
                "format": "pdf",
            },
            create_only=True,
        )


def test_invalid_values_are_rejected(monkeypatch, tmp_path):
    _use_temp_profile_file(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="Profil-ID"):
        profiles.upsert_profile("Ungültig!", {"label": "Test", "dpi": 300, "mode": "color", "format": "pdf"})
    with pytest.raises(ValueError, match="DPI"):
        profiles.upsert_profile("test", {"label": "Test", "dpi": 123, "mode": "color", "format": "pdf"})
    with pytest.raises(ValueError, match="Farbmodus"):
        profiles.upsert_profile("test", {"label": "Test", "dpi": 300, "mode": "sepia", "format": "pdf"})


def test_delete_profile_but_not_last(monkeypatch, tmp_path):
    _use_temp_profile_file(monkeypatch, tmp_path)
    profiles.save_profiles({
        "eins": {"label": "Eins", "dpi": 300, "mode": "color", "format": "pdf", "ocr": False, "duplex": False},
        "zwei": {"label": "Zwei", "dpi": 300, "mode": "gray", "format": "pdf", "ocr": True, "duplex": True},
    })
    profiles.delete_profile("zwei")
    assert list(profiles.load_profiles()) == ["eins"]
    with pytest.raises(ValueError, match="letzte Scanprofil"):
        profiles.delete_profile("eins")
