from __future__ import annotations

import importlib


def test_kodak_standby_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import openscanstation.device_settings as module
    importlib.reload(module)

    saved = module.set_device_standby("kodak_i2600:test:device", 30)
    assert saved == {"standby_minutes": 30, "standby_enabled": True}
    assert module.get_device_setting("kodak_i2600:test:device") == saved


def test_kodak_standby_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import openscanstation.device_settings as module
    importlib.reload(module)

    for value in (-1, 241):
        try:
            module.set_device_standby("kodak_i2600:test:device", value)
        except ValueError:
            pass
        else:
            raise AssertionError("Ungültige Standby-Zeit wurde akzeptiert")
