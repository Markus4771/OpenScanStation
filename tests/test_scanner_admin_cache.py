from pathlib import Path


def test_scanner_admin_uses_nonblocking_inventory_cache():
    source = Path("openscanstation/scanner_admin_v2.py").read_text(encoding="utf-8")
    assert "cached_inventory().get" in source
    assert "inventory().get" not in source
