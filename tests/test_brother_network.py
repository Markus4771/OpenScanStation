from __future__ import annotations

import importlib
import time


def module(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import openscanstation.brother_network as network
    network = importlib.reload(network)
    network.INBOX_ROOT = tmp_path / "network-inbox"
    network.CONFIG_FILE = tmp_path / "brother_network.json"
    network.STATUS_FILE = tmp_path / "brother_network_status.json"
    return network


def test_config_creates_profile_directories(tmp_path, monkeypatch):
    network = module(tmp_path, monkeypatch)
    config = network.save_config({"profiles": {"rechnung": "action-1", "archiv": "action-3"}})
    assert config["profiles"]["archiv"] == "action-3"
    assert (network.INBOX_ROOT / "rechnung").is_dir()


def test_profile_argument(tmp_path, monkeypatch):
    network = module(tmp_path, monkeypatch)
    assert network.parse_profile("rechnung=action-1") == ("rechnung", "action-1")


def test_web_profile_management_preserves_other_profiles(tmp_path, monkeypatch):
    network = module(tmp_path, monkeypatch)
    network.save_config({"profiles": {"rechnung": "action-1", "archiv": "action-3"}})
    network.upsert_profile("rechnung", "action-2")
    assert network.load_config()["profiles"] == {"rechnung": "action-2", "archiv": "action-3"}
    network.delete_profile("archiv")
    assert network.load_config()["profiles"] == {"rechnung": "action-2"}


def test_last_web_profile_cannot_be_deleted(tmp_path, monkeypatch):
    network = module(tmp_path, monkeypatch)
    network.save_config({"profiles": {"rechnung": "action-1"}})
    try:
        network.delete_profile("rechnung")
    except ValueError as exc:
        assert "Mindestens ein" in str(exc)
    else:
        raise AssertionError("last profile deletion must fail")


def test_scan_waits_until_file_is_stable(tmp_path, monkeypatch):
    network = module(tmp_path, monkeypatch)
    config = network.save_config({"profiles": {"rechnung": "action-1"}, "settle_seconds": 1})
    source = network.INBOX_ROOT / "rechnung" / "scan.pdf"
    source.write_bytes(b"PDF")
    state = {}
    assert network.scan_once(config, state) == []
    key = str(source)
    state[key] = (3, time.monotonic() - 2)
    monkeypatch.setattr(network, "process_file", lambda path, profile, action: {"ok": True, "filename": path.name})
    result = network.scan_once(config, state)
    assert result[0]["last_import_ok"] is True


def test_unsupported_file_is_reported(tmp_path, monkeypatch):
    network = module(tmp_path, monkeypatch)
    config = network.save_config({"profiles": {"rechnung": "action-1"}, "settle_seconds": 1})
    source = network.INBOX_ROOT / "rechnung" / "scan.exe"
    source.write_bytes(b"no")
    state = {str(source): (2, time.monotonic() - 2)}
    result = network.scan_once(config, state)
    assert result[0]["last_import_ok"] is False
    assert "Dateityp" in result[0]["error"]
