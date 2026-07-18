"""Kodak-i2600-Plugin: sichere USB-Erkennung und Diagnose."""

from __future__ import annotations

import usb.core

from openscanstation.scanner.base import (
    ScannerCapabilities,
    ScannerInfo,
    ScannerPlugin,
    ScannerState,
    ScannerStatus,
)


class KodakI2600Plugin(ScannerPlugin):
    plugin_id = "kodak_i2600"
    vendor_id = 0x040A
    product_id = 0x601D

    def discover(self) -> list[ScannerInfo]:
        device = usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)
        if device is None:
            return []

        return [
            ScannerInfo(
                plugin_id=self.plugin_id,
                name="Kodak i2600",
                manufacturer="Kodak",
                model="i2600",
                connection=f"usb:{device.bus}:{device.address}",
                capabilities=ScannerCapabilities(
                    duplex=True,
                    adf=True,
                    panel_events=True,
                    paper_sensor=True,
                    usb=True,
                    resolutions_dpi=(100, 150, 200, 240, 300, 400, 600),
                    color_modes=("Farbe", "Graustufen", "Schwarz/Weiß"),
                ),
            )
        ]

    def get_status(self, device_name: str) -> ScannerStatus:
        device = usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)
        connected = device is not None
        return ScannerStatus(
            device=device_name,
            state=ScannerState.READY if connected else ScannerState.OFFLINE,
            connected=connected,
            backend="libusb/pyusb",
            scan_supported=False,
            message=(
                "USB-Verbindung verfügbar; Protokollanalyse für Detailstatus läuft."
                if connected
                else "Kodak i2600 wurde nicht am USB-Bus gefunden."
            ),
            details={"protocol_state": "analysis"},
        )