from __future__ import annotations


def test_brother_profile_routes_are_registered():
    source = open("openscanstation/hardware_web.py", encoding="utf-8").read()
    assert 'path=="/brother-profiles"' in source
    assert 'path=="/api/brother-device-profiles"' in source
