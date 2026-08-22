from pathlib import Path


def test_brother_button_admin_routes_and_menu_exist():
    hardware = Path("openscanstation/hardware_web.py").read_text(encoding="utf-8")
    gateway = Path("openscanstation/unified_gateway.py").read_text(encoding="utf-8")
    assert 'path=="/brother-buttons"' in hardware
    assert 'path=="/brother-buttons/save"' in hardware
    assert 'path=="/brother-buttons/register"' in hardware
    assert '/hardware/brother-buttons' in gateway
