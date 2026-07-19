from __future__ import annotations

import subprocess

import pytest

from plugins.samsung_airscan import plugin as samsung_plugin


def test_discovers_wsd_samsung(monkeypatch):
    output = (
        "device `airscan:w0:Samsung C48x Series (SEC30CDA7AE3870)' "
        "is a WSD Samsung C48x Series (SEC30CDA7AE3870) ip=192.168.0.3\n"
    )

    def fake_run(*_args, **kwargs):
        assert kwargs["timeout"] == 45
        return subprocess.CompletedProcess(["scanimage", "-L"], 0, output, "")

    monkeypatch.setattr(samsung_plugin.subprocess, "run", fake_run)
    scanners = samsung_plugin.SamsungAirScanPlugin().discover()

    assert len(scanners) == 1
    assert scanners[0].plugin_id == "samsung_airscan"
    assert scanners[0].connection.startswith("airscan:w0:Samsung C48x")
    assert scanners[0].manufacturer == "Samsung"


def test_discovery_timeout_is_reported(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["scanimage", "-L"], 45)

    monkeypatch.setattr(samsung_plugin.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="45 Sekunden"):
        samsung_plugin.SamsungAirScanPlugin().discover()
