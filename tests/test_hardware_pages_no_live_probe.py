from pathlib import Path


def test_get_pages_do_not_call_expensive_probes():
    source = Path("openscanstation/hardware_sections.py").read_text(encoding="utf-8")
    for call in ("brother_assistant()", "diagnostics()", "network_discovery()", "usb_devices()", "driver_status()"):
        assert call not in source
