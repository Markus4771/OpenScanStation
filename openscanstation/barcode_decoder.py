"""Barcode- und QR-Code-Erkennung für Bild- und PDF-Dateien.

Primäres Backend ist ``zbarimg``. PDF-Dateien werden seitenweise mit
``pdftoppm`` in PNG-Dateien umgewandelt. Die Verarbeitung läuft in einem
abgeschotteten temporären Verzeichnis und akzeptiert nur reguläre Dateien.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED_DOCUMENTS = SUPPORTED_IMAGES | {".pdf"}


def decoder_status() -> dict:
    return {
        "zbarimg": shutil.which("zbarimg"),
        "pdftoppm": shutil.which("pdftoppm"),
        "available": bool(shutil.which("zbarimg")),
        "pdf_available": bool(shutil.which("zbarimg") and shutil.which("pdftoppm")),
    }


def _run(command: list[str], *, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Barcode-Erkennung hat das Zeitlimit überschritten") from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc


def _decode_image(path: Path) -> list[dict]:
    zbarimg = shutil.which("zbarimg")
    if not zbarimg:
        raise RuntimeError("zbarimg ist nicht installiert")
    result = _run([zbarimg, "--quiet", "--raw", str(path)])
    # zbarimg liefert bei keinem Treffer üblicherweise Status 4.
    if result.returncode not in {0, 4}:
        message = (result.stderr or result.stdout).strip()
        raise RuntimeError(message or f"zbarimg wurde mit Status {result.returncode} beendet")
    values = []
    seen = set()
    for line in result.stdout.splitlines():
        value = line.strip()
        if value and value not in seen:
            seen.add(value)
            values.append({"value": value, "source": path.name})
    return values


def decode_file(path: str | Path, *, max_pdf_pages: int = 25) -> dict:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_DOCUMENTS:
        raise ValueError("Nicht unterstütztes Dateiformat für Barcode-Erkennung")

    detections: list[dict] = []
    if suffix in SUPPORTED_IMAGES:
        detections = _decode_image(source)
    else:
        pdftoppm = shutil.which("pdftoppm")
        if not pdftoppm:
            raise RuntimeError("pdftoppm ist nicht installiert")
        with tempfile.TemporaryDirectory(prefix="openscanstation-barcode-") as temp_dir:
            prefix = Path(temp_dir) / "page"
            result = _run([
                pdftoppm,
                "-png",
                "-r", "200",
                "-f", "1",
                "-l", str(max(1, min(100, int(max_pdf_pages)))),
                str(source),
                str(prefix),
            ], timeout=120)
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout).strip() or "PDF-Konvertierung fehlgeschlagen")
            for page in sorted(Path(temp_dir).glob("page-*.png")):
                detections.extend(_decode_image(page))

    values = []
    seen_values = set()
    for item in detections:
        value = item["value"]
        if value not in seen_values:
            seen_values.add(value)
            values.append(value)
    return {
        "filename": source.name,
        "count": len(values),
        "values": values,
        "detections": detections,
        "backend": "zbarimg",
    }
