from pathlib import Path

import openscanstation.scanner_settings as settings


def test_scanner_settings_default_alias_and_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "scanner_settings.json")
    scanners = [
        {"id": "brother_ads:airscan:w0", "name": "Brother ADS", "model": "ADS-2600We"},
        {"id": "kodak_i2600:kds:usb", "name": "Kodak i2600", "model": "i2600"},
    ]
    settings.update_scanner(scanners[0]["id"], alias="Büro-Scanner", enabled=True, make_default=True)
    assert settings.default_scanner_id(scanners) == scanners[0]["id"]
    assert settings.scanner_name(scanners[0]) == "Büro-Scanner"

    settings.update_scanner(scanners[0]["id"], alias="Büro-Scanner", enabled=False, make_default=False)
    assert settings.visible_scanners(scanners) == [scanners[1]]
    assert settings.default_scanner_id(settings.visible_scanners(scanners)) == scanners[1]["id"]
