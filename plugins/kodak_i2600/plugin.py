"""Kodak-i2600-Plugin mit SANE-Scan und USB-Diagnose-Fallback."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import usb.core
from PIL import Image

from openscanstation.scanner.base import (
    ScannerCapabilities,
    ScannerInfo,
    ScannerPlugin,
    ScannerState,
    ScannerStatus,
)
from openscanstation.scanner.scan import ScanJob, ScanResult

_DEVICE_PATTERN = re.compile(r"device `(?P<device>[^']+)' is a (?P<label>.+)")
_MODE_MAP = {"color": "Color", "gray": "Gray", "lineart": "Lineart"}


class KodakI2600Plugin(ScannerPlugin):
    plugin_id = "kodak_i2600"
    vendor_id = 0x040A
    product_id = 0x601D

    def _discover_sane(self) -> list[ScannerInfo]:
        try:
            result = subprocess.run(
                ["scanimage", "-L"], check=True, capture_output=True, text=True, timeout=15
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
            searchable = f"{device_name} {label}".lower()
            if "kodak" not in searchable and "i2600" not in searchable:
                continue
            scanners.append(
                ScannerInfo(
                    plugin_id=self.plugin_id,
                    name=label,
                    manufacturer="Kodak",
                    model="i2600",
                    connection=device_name,
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
            )
        return scanners

    def discover(self) -> list[ScannerInfo]:
        sane_scanners = self._discover_sane()
        if sane_scanners:
            return sane_scanners

        device = usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)
        if device is None:
            return []
        return [
            ScannerInfo(
                plugin_id=self.plugin_id,
                name="Kodak i2600 (USB-Diagnose)",
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
        if not device_name.startswith("usb:"):
            connected = any(scanner.connection == device_name for scanner in self._discover_sane())
            return ScannerStatus(
                device=device_name,
                state=ScannerState.READY if connected else ScannerState.OFFLINE,
                connected=connected,
                backend="sane",
                scan_supported=connected,
                message=(
                    "Kodak i2600 ist über SANE scanfähig."
                    if connected
                    else "Kodak i2600 ist über SANE nicht erreichbar."
                ),
            )

        device = usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)
        connected = device is not None
        return ScannerStatus(
            device=device_name,
            state=ScannerState.READY if connected else ScannerState.OFFLINE,
            connected=connected,
            backend="libusb/pyusb",
            scan_supported=False,
            message=(
                "USB-Verbindung erkannt, aber kein SANE-Gerät verfügbar. Scannen ist damit noch nicht möglich."
                if connected
                else "Kodak i2600 wurde nicht am USB-Bus gefunden."
            ),
            details={"protocol_state": "diagnostic_only"},
        )

    def start_scan(self, device_name: str, options: dict) -> ScanResult:
        if device_name.startswith("usb:"):
            raise RuntimeError(
                "Der Kodak wurde nur per USB-Diagnose erkannt. Prüfe mit 'scanimage -L', ob ein SANE-Treiber verfügbar ist."
            )

        output = Path(options["output"]).expanduser().resolve()
        job = ScanJob(
            device=device_name,
            output=output,
            dpi=int(options.get("dpi", 300)),
            mode=str(options.get("mode", "color")),
            source=str(options.get("source", "Automatic Document Feeder")),
        )
        if job.mode not in _MODE_MAP:
            raise ValueError("Ungültiger Farbmodus. Erlaubt: color, gray, lineart")
        if job.dpi not in (100, 150, 200, 240, 300, 400, 600):
            raise ValueError("Nicht unterstützte Kodak-Auflösung")

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="openscanstation-kodak-") as temp_dir:
            temp_png = Path(temp_dir) / "scan.png"
            command = [
                "scanimage", "--device-name", job.device,
                "--resolution", str(job.dpi),
                "--mode", _MODE_MAP[job.mode],
                "--format=png",
            ]
            try:
                with temp_png.open("wb") as handle:
                    subprocess.run(command, check=True, stdout=handle, stderr=subprocess.PIPE, timeout=300)
            except FileNotFoundError as exc:
                raise RuntimeError("scanimage ist nicht installiert") from exc
            except subprocess.CalledProcessError as exc:
                message = exc.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"Kodak-Scan fehlgeschlagen: {message}") from exc

            suffix = output.suffix.lower()
            if suffix == ".png":
                output.write_bytes(temp_png.read_bytes())
            elif suffix in (".jpg", ".jpeg"):
                with Image.open(temp_png) as image:
                    image.convert("RGB").save(output, "JPEG", quality=92)
            elif suffix == ".pdf":
                with Image.open(temp_png) as image:
                    image.convert("RGB").save(output, "PDF", resolution=job.dpi)
            else:
                raise ValueError("Ausgabeformat muss PNG, JPG/JPEG oder PDF sein")

        return ScanResult(output=output, bytes_written=output.stat().st_size, backend="sane")
