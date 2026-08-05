"""Brother ADS-Scanner über SANE/AirScan oder Brother brscan5.

Unterstützt insbesondere den Brother ADS-2600We. Das Plugin verwendet die
vorhandene SANE-Geräteliste und funktioniert damit sowohl mit sane-airscan als
auch mit dem Brother-Backend, sofern dieses installiert und konfiguriert ist.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

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
_MODE_MAP = {"color": "Color", "gray": "Gray", "lineart": "Black & White"}
_ALLOWED_DPI = (100, 150, 200, 300, 400, 600)


class BrotherADSPlugin(ScannerPlugin):
    plugin_id = "brother_ads"

    @staticmethod
    def _device_lines() -> list[tuple[str, str]]:
        try:
            result = subprocess.run(
                ["scanimage", "-L"], check=True, capture_output=True,
                text=True, timeout=45,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("scanimage ist nicht installiert") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Brother-Erkennung hat nach 45 Sekunden nicht geantwortet") from exc
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or "unbekannter SANE-Fehler").strip()
            raise RuntimeError(f"Brother-Erkennung fehlgeschlagen: {message}") from exc
        devices = []
        for line in result.stdout.splitlines():
            match = _DEVICE_PATTERN.search(line.strip())
            if match:
                devices.append((match.group("device"), match.group("label")))
        return devices

    def discover(self) -> list[ScannerInfo]:
        scanners = []
        for device, label in self._device_lines():
            searchable = f"{device} {label}".casefold()
            if "brother" not in searchable or "ads" not in searchable:
                continue
            model = "ADS-2600We" if "2600" in searchable else label
            scanners.append(ScannerInfo(
                plugin_id=self.plugin_id,
                name=f"Brother {model}",
                manufacturer="Brother",
                model=model,
                connection=device,
                capabilities=ScannerCapabilities(
                    duplex=True,
                    adf=True,
                    panel_events=False,
                    paper_sensor=True,
                    network=device.startswith(("airscan:", "escl:", "net:")),
                    usb=not device.startswith(("airscan:", "escl:", "net:")),
                    resolutions_dpi=_ALLOWED_DPI,
                    color_modes=("Farbe", "Graustufen", "Schwarz/Weiß"),
                    extra={
                        "blank_page_removal": True,
                        "auto_crop": True,
                        "auto_rotate": True,
                        "multifeed_detection": True,
                        "preferred_source": "Automatic Document Feeder(centrally aligned,Duplex)",
                    },
                ),
            ))
        return scanners

    def get_status(self, device_name: str) -> ScannerStatus:
        backend = "sane-airscan" if device_name.startswith(("airscan:", "escl:")) else "brother-sane"
        return ScannerStatus(
            device=device_name,
            state=ScannerState.READY,
            connected=True,
            backend=backend,
            scan_supported=True,
            message="Brother ADS ist über SANE erreichbar.",
            details={"recommended_driver": "sane-airscan oder Brother brscan5"},
        )

    def start_scan(self, device_name: str, options: dict) -> ScanResult:
        output = Path(options["output"]).expanduser().resolve()
        dpi = int(options.get("dpi", 300))
        mode = str(options.get("mode", "color"))
        duplex = bool(options.get("duplex", False))
        if dpi not in _ALLOWED_DPI:
            raise ValueError("Nicht unterstützte Brother-Auflösung")
        if mode not in _MODE_MAP:
            raise ValueError("Ungültiger Farbmodus")
        output.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="openscanstation-brother-") as temp_dir:
            temp = Path(temp_dir)
            batch_pattern = str(temp / "page-%04d.png")
            command = [
                "scanimage", "--device-name", device_name,
                "--resolution", str(dpi), "--mode", _MODE_MAP[mode],
                "--format=png", "--batch=" + batch_pattern,
                "--batch-start=1", "--batch-increment=1",
            ]
            source = options.get("source")
            if source:
                command += ["--source", str(source)]
            elif duplex:
                command += ["--source", "Automatic Document Feeder(centrally aligned,Duplex)"]
            else:
                command += ["--source", "Automatic Document Feeder(centrally aligned,Simplex)"]
            if options.get("brightness") not in (None, ""):
                command += ["--brightness", str(options["brightness"])]
            if options.get("contrast") not in (None, ""):
                command += ["--contrast", str(options["contrast"])]

            try:
                subprocess.run(command, check=True, capture_output=True, timeout=900)
            except subprocess.CalledProcessError as exc:
                message = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else str(exc.stderr or exc.stdout or "")
                raise RuntimeError(f"Brother-Scan fehlgeschlagen: {message.strip()}") from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Brother-Scan wurde nach 15 Minuten abgebrochen") from exc

            pages = sorted(temp.glob("page-*.png"))
            if not pages:
                raise RuntimeError("Der Brother-Scanner hat keine Seiten geliefert")
            images = [Image.open(page).convert("RGB") for page in pages]
            try:
                suffix = output.suffix.lower()
                if suffix == ".pdf":
                    images[0].save(output, "PDF", save_all=True, append_images=images[1:], resolution=dpi)
                elif suffix in {".jpg", ".jpeg"}:
                    images[0].save(output, "JPEG", quality=92)
                elif suffix == ".png":
                    images[0].save(output, "PNG")
                else:
                    raise ValueError("Ausgabeformat muss PDF, PNG oder JPG sein")
            finally:
                for image in images:
                    image.close()
        return ScanResult(output=output, bytes_written=output.stat().st_size, backend="brother-sane")
