"""Laufzeitadapter für den proprietären Kodak-KDS-i2000-Treiber.

Der alte Treiber reagiert auf mehrere unmittelbar aufeinanderfolgende
sane_open-Aufrufe teilweise mit ``Invalid argument``. Dieser Adapter führt
vor einem Scan daher keine zusätzliche Options- oder Statusöffnung aus.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from openscanstation.scanner.base import ScannerState, ScannerStatus
from openscanstation.scanner.scan import ScanJob, ScanResult
from plugins.kodak_i2600.plugin import KodakI2600Plugin as BaseKodakI2600Plugin


_MODE_MAP = {
    "color": "Color",
    "gray": "Gray",
    "lineart": "Lineart",
}


class KodakI2600Plugin(BaseKodakI2600Plugin):
    """Kodak-i2600-Adapter mit genau einer Geräteöffnung je Scanauftrag."""

    def get_status(self, device_name: str) -> ScannerStatus:
        if device_name.startswith("usb:"):
            return super().get_status(device_name)

        return ScannerStatus(
            device=device_name,
            state=ScannerState.READY,
            connected=True,
            backend=device_name.split(":", 1)[0] or "kds_i2000",
            scan_supported=True,
            message=(
                "Kodak i2600 wurde vom KDS-SANE-Treiber erkannt. "
                "Die Geräteöffnung erfolgt erst beim Scan."
            ),
            details={
                "driver_ready": True,
                "single_open_mode": True,
                "profile_mapping": True,
            },
        )

    def start_scan(self, device_name: str, options: dict) -> ScanResult:
        if device_name.startswith("usb:"):
            raise RuntimeError(
                "USB ist durchgereicht, aber der Scanner besitzt noch kein SANE-Gerät."
            )

        output = Path(options["output"]).expanduser().resolve()
        job = ScanJob(
            device=device_name,
            output=output,
            dpi=int(options.get("dpi", 300)),
            mode=str(options.get("mode", "color")),
            source="ADF Duplex" if bool(options.get("duplex", False)) else "",
        )
        if job.mode not in _MODE_MAP:
            raise ValueError("Ungültiger Farbmodus. Erlaubt: color, gray, lineart")
        if job.dpi not in (100, 150, 200, 240, 300, 400, 600):
            raise ValueError("Nicht unterstützte Kodak-Auflösung")

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="openscanstation-kodak-") as temp_dir:
            temp_png = Path(temp_dir) / "scan.png"
            command = [
                "scanimage",
                "--device-name",
                job.device,
                "--resolution",
                str(job.dpi),
                "--mode",
                _MODE_MAP[job.mode],
            ]
            if job.source:
                command.extend(["--source", job.source])
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
                if "open of device" in message and "Invalid argument" in message:
                    raise RuntimeError(
                        "Der Kodak-KDS-Treiber konnte das Gerät nicht öffnen. "
                        "Bitte OpenScanStation neu starten und prüfen, dass kein anderes "
                        "Scanprogramm den Kodak verwendet. Technische Meldung: " + message
                    ) from exc
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

        return ScanResult(
            output=output,
            bytes_written=output.stat().st_size,
            backend="kds_i2000",
        )
