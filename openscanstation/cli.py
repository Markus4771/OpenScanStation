"""Kommandozeile für OpenScanStation."""

from __future__ import annotations
import argparse
import json
import platform
import shutil
import subprocess
from pathlib import Path
from openscanstation.scanner.manager import ScannerManager

VERSION = "0.12.3"

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

def command_hardware(_args: argparse.Namespace) -> int:
    from openscanstation.hardware import inventory_fallback
    print(json.dumps(inventory_fallback(), ensure_ascii=False, indent=2))
    return 0

def command_hardware_check(args: argparse.Namespace) -> int:
    from openscanstation.hardware_health import load_last_report, run_hardware_checks
    report = load_last_report() if args.last else run_hardware_checks()
    if not report:
        print("Noch kein Hardware-Prüfbericht vorhanden.")
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = report.get("summary", {})
        print(f"Hardwareprüfung: {summary.get('passed', 0)}/{summary.get('total', 0)} Module OK")
        for result in report.get("results", []):
            state = "OK" if result.get("ok") else "FEHLER"
            duration = result.get("duration_ms", 0)
            print(f"{state:<7} {result.get('module',''):<18} {duration:>6} ms  {result.get('message','')}")
    return 0 if report.get("ok") else 1

def command_hardware_refresh(_args: argparse.Namespace) -> int:
    from openscanstation.hardware_health import clear_hardware_cache
    from openscanstation.hardware import inventory_fallback
    result = clear_hardware_cache()
    inventory = inventory_fallback()
    print(json.dumps({"cache": result, "inventory": inventory}, ensure_ascii=False, indent=2))
    return 0

def command_doctor(_args: argparse.Namespace) -> int:
    print(f"OpenScanStation {VERSION}")
    print(f"System: {platform.platform()}")
    print(f"Architektur: {platform.machine()}")
    checks = ["scanimage", "airscan-discover", "tesseract", "pdftoppm", "zbarimg", "lp", "lpstat", "lpoptions"]
    failed = False
    for command in checks:
        path = shutil.which(command)
        print(f"{command}: {path or 'nicht gefunden'}")
        failed = failed or path is None
    sane_config = Path("/etc/sane.d")
    print(f"SANE-Konfiguration: {'vorhanden' if sane_config.is_dir() else 'fehlt'}")
    if shutil.which("scanimage"):
        code, output = _run_text(["scanimage", "-L"], 8)
        print("Scannererkennung:")
        print(output or "Keine Ausgabe")
        failed = failed or code != 0
    if shutil.which("lpstat"):
        code, output = _run_text(["lpstat", "-p", "-d"], 5)
        print("CUPS-Drucker:")
        print(output or "Keine Drucker eingerichtet")
        failed = failed or code not in {0, 1}
    return 1 if failed else 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openscanstation")
    sub = parser.add_subparsers(dest="command")
    version = sub.add_parser("version", help="Version anzeigen")
    version.set_defaults(func=command_version)
    scanners = sub.add_parser("scanners", help="Scanner erkennen")
    scanners.set_defaults(func=command_scanners)
    hardware = sub.add_parser("hardware", help="Scanner und Drucker als JSON anzeigen")
    hardware.set_defaults(func=command_hardware)
    hardware_check = sub.add_parser("hardware-check", help="Alle Hardwaremodule getrennt prüfen")
    hardware_check.add_argument("--json", action="store_true", help="Vollständigen Bericht als JSON ausgeben")
    hardware_check.add_argument("--last", action="store_true", help="Zuletzt gespeicherten Bericht anzeigen")
    hardware_check.set_defaults(func=command_hardware_check)
    hardware_refresh = sub.add_parser("hardware-refresh", help="Hardwarecache löschen und Geräte neu erfassen")
    hardware_refresh.set_defaults(func=command_hardware_refresh)
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
