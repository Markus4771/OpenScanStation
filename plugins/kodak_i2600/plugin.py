"""Kodak-i2600-Plugin mit produktivem SANE-Pfad und USB-Diagnose-Fallback."""

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
_MODE_CANDIDATES = {
    "color": ("Color", "24bit Color", "Colour"),
    "gray": ("Gray", "Grayscale", "8bit Gray"),
    "lineart": ("Lineart", "Black & White", "Binary"),
}
_SOURCE_CANDIDATES = (
    "Automatic Document Feeder",
    "ADF Duplex",
    "ADF Front",
    "ADF",
)


class KodakI2600Plugin(ScannerPlugin):
    plugin_id = "kodak_i2600"
    vendor_id = 0x040A
    product_id = 0x601D

    @staticmethod
    def _run(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _discover_sane(self) -> list[ScannerInfo]:
        try:
            result = self._run(["scanimage", "-L"], timeout=20)
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

    def _device_options(self, device_name: str) -> str:
        try:
            result = self._run(
                ["scanimage", "--device-name", device_name, "--help"], timeout=30
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return ""
        return f"{result.stdout}\n{result.stderr}"

    @staticmethod
    def _pick_supported(options_text: str, candidates: tuple[str, ...]) -> str | None:
        lowered = options_text.lower()
        for candidate in candidates:
            if candidate.lower() in lowered:
                return candidate
        return None

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
                name="Kodak i2600 (USB erkannt, Treiber fehlt)",
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
            connected = any(
                scanner.connection == device_name for scanner in self._discover_sane()
            )
            options = self._device_options(device_name) if connected else ""
            return ScannerStatus(
                device=device_name,
                state=ScannerState.READY if connected else ScannerState.OFFLINE,
                connected=connected,
                backend="sane",
                scan_supported=connected,
                message=(
                    "Kodak i2600 ist über den installierten SANE/Kodak-Treiber scanfähig."
                    if connected
                    else "Kodak i2600 ist über SANE nicht erreichbar."
                ),
                details={
                    "driver_ready": connected,
                    "duplex_option_detected": "duplex" in options.lower(),
                    "adf_option_detected": "adf" in options.lower(),
                },
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
                "USB-Passthrough funktioniert. Installiere jetzt den x86_64-Kodak/SANE-Treiber in der VM; danach muss 'scanimage -L' den i2600 anzeigen."
                if connected
                else "Kodak i2600 wurde nicht am USB-Bus der VM gefunden. Prüfe das Proxmox-USB-Passthrough."
            ),
            details={"protocol_state": "driver_required", "usb_id": "040a:601d"},
        )

    def start_scan(self, device_name: str, options: dict) -> ScanResult:
        if device_name.startswith("usb:"):
            raise RuntimeError(
                "USB ist durchgereicht, aber der Scanner besitzt noch kein SANE-Gerät. Installiere den Kodak-x86_64-Treiber und prüfe 'scanimage -L'."
            )

        output = Path(options["output"]).expanduser().resolve()
        job = ScanJob(
            device=device_name,
            output=output,
            dpi=int(options.get("dpi", 300)),
            mode=str(options.get("mode", "color")),
            source=str(options.get("source", "auto")),
        )
        if job.mode not in _MODE_CANDIDATES:
            raise ValueError("Ungültiger Farbmodus. Erlaubt: color, gray, lineart")
        if job.dpi not in (100, 150, 200, 240, 300, 400, 600):
            raise ValueError("Nicht unterstützte Kodak-Auflösung")

        options_text = self._device_options(job.device)
        selected_mode = self._pick_supported(options_text, _MODE_CANDIDATES[job.mode])
        selected_source = self._pick_supported(options_text, _SOURCE_CANDIDATES)

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="openscanstation-kodak-") as temp_dir:
            temp_png = Path(temp_dir) / "scan.png"
            command = [
                "scanimage",
                "--device-name",
                job.device,
                "--resolution",
                str(job.dpi),
            ]
            if selected_mode:
                command.extend(["--mode", selected_mode])
            if selected_source:
                command.extend(["--source", selected_source])
            command.append("--format=png")

            try:
                with temp_png.open("wb") as handle:
                    subprocess.run(
                        command,
                        check=True,
                        stdout=handle,
                        stderr=subprocess.PIPE,
                        timeout=600,
                    )
            except FileNotFoundError as exc:
                raise RuntimeError("scanimage ist nicht installiert") from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Kodak-Scan wurde nach 10 Minuten abgebrochen") from exc
            except subprocess.CalledProcessError as exc:
                message = exc.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(
                    f"Kodak-Scan fehlgeschlagen: {message or 'unbekannter SANE-Fehler'}"
                ) from exc

            if not temp_png.exists() or temp_png.stat().st_size == 0:
                raise RuntimeError("Der Kodak-Treiber hat keine Bilddaten geliefert")

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
