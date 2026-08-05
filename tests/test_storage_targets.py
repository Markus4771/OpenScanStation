import importlib
import json
from pathlib import Path

import pytest


def load_module(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import openscanstation.storage_targets as storage_targets
    return importlib.reload(storage_targets)


def test_default_local_target(tmp_path, monkeypatch):
    module = load_module(tmp_path, monkeypatch)
    data = module.load_targets()
    assert data["targets"][0]["id"] == "local"
    assert data["targets"][0]["default"] is True


def test_create_and_redact_webdav_target(tmp_path, monkeypatch):
    module = load_module(tmp_path, monkeypatch)
    module.upsert_target({
        "id": "nextcloud",
        "name": "Nextcloud",
        "type": "webdav",
        "enabled": True,
        "default": True,
        "config": {
            "url": "https://cloud.example/remote.php/dav/files/user/Scans",
            "username": "scanner",
            "password": "secret",
        },
    }, create_only=True)
    public = module.load_targets(public=True)
    target = next(item for item in public["targets"] if item["id"] == "nextcloud")
    assert target["config"]["password"] == "********"
    assert target["default"] is True


def test_only_one_default_target(tmp_path, monkeypatch):
    module = load_module(tmp_path, monkeypatch)
    module.upsert_target({
        "id": "archive",
        "name": "Archiv",
        "type": "local",
        "enabled": True,
        "default": True,
        "config": {"path": str(tmp_path / "archive")},
    }, create_only=True)
    defaults = [item for item in module.load_targets()["targets"] if item["default"]]
    assert [item["id"] for item in defaults] == ["archive"]


def test_atomic_file_permissions(tmp_path, monkeypatch):
    module = load_module(tmp_path, monkeypatch)
    module.save_targets(module.DEFAULT_TARGETS)
    assert module.TARGETS_FILE.exists()
    assert module.TARGETS_FILE.stat().st_mode & 0o777 == 0o600
    json.loads(module.TARGETS_FILE.read_text(encoding="utf-8"))


def test_invalid_target_rejected(tmp_path, monkeypatch):
    module = load_module(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        module.upsert_target({
            "id": "INVALID ID",
            "name": "Fehler",
            "type": "local",
            "config": {"path": "/tmp"},
        })


def test_used_target_cannot_be_deleted(tmp_path, monkeypatch):
    module = load_module(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="verwendet"):
        module.delete_target("local", used_by=["Rechnung"])


def test_local_connection_test(tmp_path, monkeypatch):
    module = load_module(tmp_path, monkeypatch)
    result = module.test_target("local")
    assert result["ok"] is True
    assert Path(tmp_path / "scans").is_dir()
