"""Papierkopien: Scanner -> temporäres PDF -> CUPS-Druckauftrag."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from openscanstation.scanner.manager import ScannerManager

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
HISTORY_FILE = DATA_DIR / "copy_jobs.json"


def list_printers() -> list[dict]:
    if not shutil.which("lpstat"):
        return []
    result = subprocess.run(["lpstat", "-p", "-d"], capture_output=True, text=True, timeout=15)
    printers = []
    default = ""
    for line in result.stdout.splitlines():
        if line.startswith("printer "):
            name = line.split()[1]
            printers.append({"name": name, "enabled": "disabled" not in line.lower(), "default": False})
        elif line.startswith("system default destination:"):
            default = line.split(":", 1)[1].strip()
    for printer in printers:
        printer["default"] = printer["name"] == default
    return printers


def _record(job: dict) -> None:
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(([job] + data)[:200], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_copy_jobs(limit: int = 50) -> list[dict]:
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data[:limit] if isinstance(data, list) else []
    except Exception:
        return []


def create_copy(scanner_id: str, printer: str, *, copies: int = 1,
                color: bool = True, duplex_scan: bool = False,
                duplex_print: bool = False, media: str = "A4",
                scale: int = 100, n_up: int = 1,
                brightness: int = 0, contrast: int = 0) -> dict:
    if not shutil.which("lp"):
        raise RuntimeError("CUPS-Befehl lp ist nicht installiert")
    copies = max(1, min(99, int(copies)))
    scale = max(25, min(400, int(scale)))
    n_up = int(n_up) if int(n_up) in {1, 2, 4} else 1

    manager = ScannerManager()
    scanner = None
    plugin = None
    for item in manager.discover().scanners:
        if f"{item.plugin_id}:{item.connection}" == scanner_id:
            scanner = item
            plugin = manager.get_plugin(item.plugin_id)
            break
    if scanner is None or plugin is None:
        raise ValueError("Scanner nicht gefunden")

    with tempfile.TemporaryDirectory(prefix="openscanstation-copy-") as temp_dir:
        pdf = Path(temp_dir) / "copy.pdf"
        plugin.start_scan(scanner.connection, {
            "output": str(pdf),
            "dpi": 300,
            "mode": "color" if color else "gray",
            "duplex": duplex_scan,
            "brightness": brightness,
            "contrast": contrast,
        })
        command = ["lp", "-d", printer, "-n", str(copies), "-o", f"media={media}"]
        command += ["-o", f"scaling={scale}"]
        if duplex_print:
            command += ["-o", "sides=two-sided-long-edge"]
        else:
            command += ["-o", "sides=one-sided"]
        if n_up > 1:
            command += ["-o", f"number-up={n_up}"]
        command.append(str(pdf))
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "CUPS-Druckauftrag fehlgeschlagen").strip())

    job = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scanner": scanner.name,
        "printer": printer,
        "copies": copies,
        "color": color,
        "duplex_scan": duplex_scan,
        "duplex_print": duplex_print,
        "media": media,
        "scale": scale,
        "n_up": n_up,
        "cups_response": result.stdout.strip(),
        "status": "submitted",
    }
    _record(job)
    return job
