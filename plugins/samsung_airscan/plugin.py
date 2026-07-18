"""Samsung-AirScan-Plugin über die vorhandene scanimage-/SANE-Anbindung."""

from __future__ import annotations

import re
import subprocess

from openscanstation.scanner.base import (
    ScannerCapabilities,
    ScannerInfo,
    ScannerPlugin,
    ScannerState,
    ScannerStatus,
)

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
                        resolutions_dpi=(75, 100, 150, 200, 300, 600),
                        color_modes=("Farbe", "Graustufen", "Schwarz/Weiß"),
                    ),
                )
            )

        return scanners

    def get_status(self, device_name: str) -> ScannerStatus:
        devices = {scanner.connection for scanner in self.discover()}
        connected = device_name in devices
        return ScannerStatus(
            device=device_name,
            state=ScannerState.READY if connected else ScannerState.OFFLINE,
            connected=connected,
            backend="sane-airscan",
            scan_supported=True,
            message=(
                "Scanner ist über SANE/AirScan erreichbar."
                if connected
                else "Scanner ist über SANE/AirScan nicht erreichbar."
            ),
        )