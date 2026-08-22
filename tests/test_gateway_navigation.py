from pathlib import Path


def test_hardware_overview_is_only_active_on_exact_path():
    source = Path("openscanstation/unified_gateway.py").read_text(encoding="utf-8")
    assert "h==='/hardware'?p===h" in source
