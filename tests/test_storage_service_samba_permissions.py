from pathlib import Path


def test_storage_service_can_update_samba_state():
    unit = Path("packaging/openscanstation-storage-settings.service").read_text(encoding="utf-8")
    assert "/var/lib/samba" in unit
    assert "/etc/samba" in unit
