"""Samsung-AirScan-Plugin über die vorhandene scanimage-/SANE-Anbindung."""

from __future__ import annotations

import re
import subprocess
from typing import Any

from openscanstation.scanner.base import ScannerCapabilities, ScannerInfo, ScannerPlugin


_DEVICE_PATTERN = re.compile(r"device `(?P<device>[^']+)' is a (?P<label>.+)")


class SamsungAirScanPlugin(ScannerPlugin):
    plugin_id = "samsung_airscan"

    def discover(self) -> list[ScannerInfo]:
        try:
            result = subprocess.run(
                ["scanimage", "-L"],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return []

        scanners: list[ScannerInfo] = []
        for line in result.stdout.splitlines():
            match = _DEVICE_PATTERN.search(line.strip())
            if not match:
                continue

            device_name = match.group("device")
            label = match.group("label")
            if "samsung" not in label.lower() and "samsung" not in device_name.lower():
                continue

            scanners.append(
                ScannerInfo(
                    plugin_id=self.plugin_id,
                    name=label,
                    manufacturer="Samsung",
                    model=label,
                    connection=device_name,
                    capabilities=ScannerCapabilities(
                        duplex=True,
                        adf=True,
                        network=True,
                    ),
                )
            )

        return scanners

    def get_status(self, device_name: str) -> dict[str, Any]:
        devices = {scanner.connection for scanner in self.discover()}
        return {
            "device": device_name,
            "connected": device_name in devices,
            "backend": "sane-airscan",
            "scan_supported": True,
        }
