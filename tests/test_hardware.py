from __future__ import annotations

import importlib


def test_hardware_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENSCANSTATION_DATA_DIR", str(tmp_path))
    import openscanstation.hardware as hardware
    importlib.reload(hardware)
    saved = hardware.save_settings({
        "default_printer": "Office",
        "printer_aliases": {"Office": "Bürodrucker"},
        "disabled_printers": ["Alt"],
    })
    assert saved["default_printer"] == "Office"
    assert hardware.load_settings()["printer_aliases"]["Office"] == "Bürodrucker"


def test_invalid_test_printer_name():
    import openscanstation.hardware as hardware
    try:
        hardware.print_test_page("../printer")
    except ValueError:
        pass
    else:
        raise AssertionError("Pfadartige Druckernamen müssen abgelehnt werden")
