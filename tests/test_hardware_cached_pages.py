from __future__ import annotations
import importlib
import json


def test_cached_inventory_never_probes_hardware(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import openscanstation.hardware as hardware
    hardware = importlib.reload(hardware)
    expected = {"devices": [{"id": "cached"}], "counts": {"scanner": 1}}
    hardware.CACHE_FILE.write_text(json.dumps(expected), encoding="utf-8")
    monkeypatch.setattr(hardware, "_scanner_devices", lambda: (_ for _ in ()).throw(AssertionError("live probe")))
    assert hardware.cached_inventory()["devices"][0]["id"] == "cached"
