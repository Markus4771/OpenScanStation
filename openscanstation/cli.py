"""Kommandozeile für OpenScanStation."""

from __future__ import annotations
import argparse
import platform
import shutil
import subprocess
from pathlib import Path
from openscanstation.scanner.manager import ScannerManager

VERSION = "0.5.1"

def _format_optional(value: bool | None) -> str:
    if value is None:
        return "nicht verfügbar"
    return "ja" if value else "nein"

def _run_text(command: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)

def command_version(_args: argparse.Namespace) -> int:
    print(VERSION)
    return 0

def command_scanners(_args: argparse.Namespace) -> int:
    result = ScannerManager().discover()
    if not result.scanners:
        print("Keine Scanner gefunden.")
    for scanner in result.scanners:
        print(f"{scanner.name} [{scanner.plugin_id}]")
        print(f"  Hersteller: {scanner.manufacturer}")
        print(f"  Modell: {scanner.model}")
        print(f"  Verbindung: {scanner.connection}")
        print(f"  Duplex: {_format_optional(scanner.capabilities.duplex)}")
        print(f"  ADF: {_format_optional(scanner.capabilities.adf)}")
    for error in result.errors:
        print(f"Fehler [{error.plugin_id}]: {error.message}")
    return 0 if result.scanners else 1

def command_doctor(_args: argparse.Namespace) -> int:
    print(f"OpenScanStation {VERSION}")
    print(f"System: {platform.platform()}")
    print(f"Architektur: {platform.machine()}")
    checks = ["scanimage", "tesseract", "pdftoppm"]
    failed = False
    for command in checks:
        path = shutil.which(command)
        print(f"{command}: {path or 'nicht gefunden'}")
        failed = failed or path is None
    sane_config = Path("/etc/sane.d")
    print(f"SANE-Konfiguration: {'vorhanden' if sane_config.is_dir() else 'fehlt'}")
    if shutil.which("scanimage"):
        code, output = _run_text(["scanimage", "-L"])
        print("Scannererkennung:")
        print(output or "Keine Ausgabe")
        failed = failed or code != 0
    return 1 if failed else 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openscanstation")
    sub = parser.add_subparsers(dest="command")
    version = sub.add_parser("version", help="Version anzeigen")
    version.set_defaults(func=command_version)
    scanners = sub.add_parser("scanners", help="Scanner erkennen")
    scanners.set_defaults(func=command_scanners)
    doctor = sub.add_parser("doctor", help="Systemdiagnose ausführen")
    doctor.set_defaults(func=command_doctor)
    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
