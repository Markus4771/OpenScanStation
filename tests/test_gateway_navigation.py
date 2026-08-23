from pathlib import Path


def test_hardware_overview_is_only_active_on_exact_path():
    source = Path("openscanstation/unified_gateway.py").read_text(encoding="utf-8")
    assert "h==='/hardware'?p===h" in source


def test_navigation_is_grouped_and_mobile_friendly():
    source = Path("openscanstation/unified_gateway.py").read_text(encoding="utf-8")
    assert 'data-menu="scan"' in source
    assert 'data-menu="processing"' in source
    assert 'data-menu="hardware-tools"' in source
    assert 'class="oss-menu-toggle"' in source
    assert '/storage/#brother-network' in source


def test_administration_is_only_rendered_for_admins():
    source = Path("openscanstation/unified_gateway.py").read_text(encoding="utf-8")
    assert "def sidebar(is_admin: bool = True)" in source
    assert "if is_admin else ''" in source
