from __future__ import annotations

import importlib


def module(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import openscanstation.brother_buttons as brother_buttons
    return importlib.reload(brother_buttons)


def sample():
    return {
        "scanner_ip": "192.168.1.20",
        "server_ip": "192.168.1.10",
        "scanner_id": "brother:brother4:net1;dev0",
        "display_name": "OpenScan",
        "actions": {"FILE": "action-1", "OCR": "action-3"},
    }


def test_config_roundtrip(tmp_path, monkeypatch):
    buttons = module(tmp_path, monkeypatch)
    saved = buttons.save_config(sample())
    assert saved["listen_port"] == 54925
    assert buttons.load_config()["actions"]["OCR"] == "action-3"


def test_registration_commands_are_scoped(tmp_path, monkeypatch):
    buttons = module(tmp_path, monkeypatch)
    config = buttons.normalize_config(sample())
    commands = buttons.registration_commands(config)
    assert len(commands) == 2
    assert all(command[:5] == ["snmpset", "-v1", "-c", "internal", "192.168.1.20"] for command in commands)
    assert any("FUNC=FILE" in command[-1] and "HOST=192.168.1.10:54925" in command[-1] for command in commands)


def test_register_collects_results(tmp_path, monkeypatch):
    buttons = module(tmp_path, monkeypatch)

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return Result()

    result = buttons.register(buttons.normalize_config(sample()), runner=runner)
    assert result["registered"] is True
    assert len(calls) == 2
    assert buttons.STATUS_FILE.exists()


def test_parse_button_event(tmp_path, monkeypatch):
    buttons = module(tmp_path, monkeypatch)
    assert buttons.parse_event(b"TYPE=BR;BUTTON=SCAN;FUNC=OCR;") == "OCR"
    assert buttons.parse_event(b"TYPE=BR;BUTTON=OTHER;FUNC=OCR;") is None


def test_invalid_address_rejected(tmp_path, monkeypatch):
    buttons = module(tmp_path, monkeypatch)
    data = sample()
    data["scanner_ip"] = "scanner.local"
    try:
        buttons.normalize_config(data)
    except ValueError as exc:
        assert "ip-adresse" in str(exc).lower()
    else:
        raise AssertionError("invalid scanner address accepted")
