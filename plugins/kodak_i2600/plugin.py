"""Kodak-i2600-Plugin: zunächst sichere USB-Erkennung und Diagnose."""

from __future__ import annotations

from typing import Any

import usb.core

from openscanstation.scanner.base import ScannerCapabilities, ScannerInfo, ScannerPlugin


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
                ),
            )
        ]

    def get_status(self, device_name: str) -> dict[str, Any]:
        device = usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)
        return {
            "device": device_name,
            "connected": device is not None,
            "protocol_state": "analysis",
            "scan_supported": False,
        }
