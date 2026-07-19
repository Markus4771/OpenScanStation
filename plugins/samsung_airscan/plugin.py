"""Samsung-AirScan-Plugin über die vorhandene scanimage-/SANE-Anbindung."""

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
_MODE_MAP = {"color": "Color", "gray": "Gray", "lineart": "Lineart"}
_DISCOVERY_TIMEOUT_SECONDS = 45


class SamsungAirScanPlugin(ScannerPlugin):
    plugin_id = "samsung_airscan"

    @staticmethod
    def _discover_output() -> str:
        """Liefert die SANE-Geräteliste mit ausreichend Zeit für WSD/AirScan."""
        try:
            result = subprocess.run(
                ["scanimage", "-L"],
                check=True,
                capture_output=True,
                text=True,
                timeout=_DISCOVERY_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("scanimage ist nicht installiert") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Samsung-AirScan-Erkennung hat nach 45 Sekunden nicht geantwortet"
            ) from exc
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or "unbekannter SANE-Fehler").strip()
            raise RuntimeError(f"Samsung-AirScan-Erkennung fehlgeschlagen: {message}") from exc
        return result.stdout

    def discover(self) -> list[ScannerInfo]:
        scanners: list[ScannerInfo] = []
        for line in self._discover_output().splitlines():
            match = _DEVICE_PATTERN.search(line.strip())
            if not match:
                continue
            device_name = match.group("device")
            label = match.group("label")
            searchable = f"{device_name} {label}".lower()
            if "samsung" not in searchable:
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
        # Diese Methode wird nur für Geräte aufgerufen, die discover() bereits
        # erfolgreich geliefert hat. Ein zweiter Aufruf von `scanimage -L`
        # kann bei Netzwerk-Scannern blockieren und ist daher absichtlich
        # nicht erforderlich.
        return ScannerStatus(
            device=device_name,
            state=ScannerState.READY,
            connected=True,
            backend="sane-airscan",
            scan_supported=True,
            message="Scanner ist über SANE/AirScan erreichbar.",
        )

    def start_scan(self, device_name: str, options: dict) -> ScanResult:
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
        if job.dpi not in (75, 100, 150, 200, 300, 600):
            raise ValueError("Nicht unterstützte Auflösung")

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="openscanstation-") as temp_dir:
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
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Der Scan wurde nach 300 Sekunden abgebrochen") from exc
            except subprocess.CalledProcessError as exc:
                message = exc.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"Scan fehlgeschlagen: {message}") from exc

            if not temp_png.exists() or temp_png.stat().st_size == 0:
                raise RuntimeError("Der Samsung-Scanner hat keine Bilddaten geliefert")

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

        return ScanResult(output=output, bytes_written=output.stat().st_size, backend="sane-airscan")