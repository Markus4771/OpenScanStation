"""Kommandozeile für OpenScanStation."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
from pathlib import Path

from openscanstation.scanner.manager import ScannerManager

VERSION = "0.3.0"


def _format_optional(value: bool | None) -> str:
    if value is None:
        return "nicht verfügbar"
    return "ja" if value else "nein"


def _print_scanners() -> int:
    manager = ScannerManager()
    result = manager.discover()
    print(f"OpenScanStation {VERSION}")
    print("Scanner-Erkennung")
    print("=" * 40)
    if not result.scanners:
        print("Keine unterstützten Scanner gefunden.")
    else:
        for index, scanner in enumerate(result.scanners, start=1):
            plugin = manager.get_plugin(scanner.plugin_id)
            status = plugin.get_status(scanner.connection) if plugin else None
            print(f"\n{index}. {scanner.name}")
            print(f"   Hersteller: {scanner.manufacturer}")
            print(f"   Modell: {scanner.model}")
            print(f"   Verbindung: {scanner.connection}")
            print(f"   Plugin: {scanner.plugin_id}")
            print(f"   Status: {status.state.value if status else 'unbekannt'}")
    if result.errors:
        print("\nPlugin-Fehler")
        print("-" * 40)
        for error in result.errors:
            print(f"{error.plugin_id}: {error.message}")
    print(f"\nScanner gefunden: {len(result.scanners)}")
    return 0 if not result.errors else 1


def _print_status() -> int:
    manager = ScannerManager()
    result = manager.discover()
    print(f"OpenScanStation {VERSION}")
    print("Scanner-Status")
    print("=" * 40)
    if not result.scanners:
        print("Keine unterstützten Scanner gefunden.")
        return 1
    for index, scanner in enumerate(result.scanners, start=1):
        plugin = manager.get_plugin(scanner.plugin_id)
        if plugin is None:
            continue
        status = plugin.get_status(scanner.connection)
        print(f"\n{index}. {scanner.name}")
        print(f"   Zustand: {status.state.value}")
        print(f"   Verbunden: {'ja' if status.connected else 'nein'}")
        print(f"   Backend: {status.backend}")
        print(f"   Scan-Unterstützung: {'ja' if status.scan_supported else 'noch nicht'}")
        print(f"   Papier vorhanden: {_format_optional(status.paper_present)}")
        print(f"   Papierstau: {_format_optional(status.paper_jam)}")
        print(f"   Abdeckung offen: {_format_optional(status.cover_open)}")
        print(f"   Duplex: {'ja' if scanner.capabilities.duplex else 'nein'}")
        print(f"   ADF: {'ja' if scanner.capabilities.adf else 'nein'}")
        if scanner.capabilities.resolutions_dpi:
            values = ", ".join(str(value) for value in scanner.capabilities.resolutions_dpi)
            print(f"   Auflösungen: {values} dpi")
        if scanner.capabilities.color_modes:
            print(f"   Farbmodi: {', '.join(scanner.capabilities.color_modes)}")
        if status.message:
            print(f"   Hinweis: {status.message}")
    return 0 if not result.errors else 1


def _command_output(command: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, "Befehl nicht installiert"
    except subprocess.TimeoutExpired:
        return 124, "Zeitüberschreitung"
    text = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return result.returncode, text


def _doctor() -> int:
    """Prüft Proxmox-Passthrough, Architektur und SANE-Treiberstatus."""
    print(f"OpenScanStation {VERSION}")
    print("Kodak-i2600-VM-Diagnose")
    print("=" * 40)

    architecture = platform.machine()
    architecture_ok = architecture in {"x86_64", "amd64"}
    print(f"Architektur: {architecture} ({'geeignet' if architecture_ok else 'nicht für den x86_64-Kodak-Treiber geeignet'})")
    print(f"scanimage installiert: {'ja' if shutil.which('scanimage') else 'nein'}")

    usb_code, usb_text = _command_output(["lsusb"])
    usb_found = "040a:601d" in usb_text.lower()
    print(f"Kodak USB 040a:601d: {'gefunden' if usb_found else 'nicht gefunden'}")

    sane_code, sane_text = _command_output(["scanimage", "-L"], timeout=30)
    sane_found = "kodak" in sane_text.lower() or "i2600" in sane_text.lower()
    print(f"Kodak als SANE-Gerät: {'gefunden' if sane_found else 'nicht gefunden'}")

    print("\nBewertung")
    print("-" * 40)
    if not architecture_ok:
        print("Die VM benötigt x86_64. Auf ARM64 kann der offizielle Kodak-Treiber nicht verwendet werden.")
        return 1
    if not usb_found:
        print("Der Scanner ist nicht in der VM sichtbar. Prüfe das Proxmox-USB-Passthrough für 040a:601d.")
        return 2
    if sane_code == 127:
        print("Installiere zuerst sane-utils: sudo apt install sane-utils")
        return 3
    if not sane_found:
        print("USB-Passthrough funktioniert, aber der Kodak-Treiber fehlt oder ist nicht geladen.")
        print("Nach der Treiberinstallation muss 'scanimage -L' den Kodak i2600 anzeigen.")
        if sane_text:
            print(f"\nscanimage-Ausgabe:\n{sane_text}")
        return 4

    print("Die VM und der Kodak-Treiber sind bereit. Ein Testscan kann gestartet werden:")
    print("openscanstation scan --scanner kodak --dpi 300 --mode color --output /tmp/kodak-test.pdf")
    return 0


def _scan(args: argparse.Namespace) -> int:
    manager = ScannerManager()
    result = manager.discover()
    candidates = []
    for scanner in result.scanners:
        plugin = manager.get_plugin(scanner.plugin_id)
        if plugin is None:
            continue
        status = plugin.get_status(scanner.connection)
        if status.scan_supported:
            candidates.append(scanner)

    if not candidates:
        print("Kein scanfähiger Scanner gefunden.")
        if result.scanners:
            print("Erkannte Geräte:")
            for item in result.scanners:
                plugin = manager.get_plugin(item.plugin_id)
                status = plugin.get_status(item.connection) if plugin else None
                note = status.message if status else "Plugin nicht verfügbar"
                print(f"- {item.name}: {note}")
        print("Hinweis: 'openscanstation doctor' zeigt den Kodak-Treiberstatus.")
        return 1

    scanner = candidates[0]
    if args.scanner:
        needle = args.scanner.lower()
        matches = [
            item
            for item in candidates
            if needle in item.name.lower()
            or needle in item.connection.lower()
            or needle in item.plugin_id.lower()
            or needle in item.manufacturer.lower()
            or needle in item.model.lower()
        ]
        if not matches:
            print(f"Scanner '{args.scanner}' wurde nicht als scanfähig gefunden.")
            print("Scanfähige Scanner:")
            for item in candidates:
                print(f"- {item.name} ({item.plugin_id})")
            return 1
        scanner = matches[0]

    plugin = manager.get_plugin(scanner.plugin_id)
    if plugin is None:
        print("Scanner-Plugin ist nicht verfügbar.")
        return 1
    try:
        scan_result = plugin.start_scan(
            scanner.connection,
            {
                "output": str(Path(args.output)),
                "dpi": args.dpi,
                "mode": args.mode,
            },
        )
    except Exception as exc:
        print(f"Scan fehlgeschlagen: {exc}")
        return 1
    print(f"Scan erfolgreich: {scan_result.output}")
    print(f"Dateigröße: {scan_result.bytes_written} Bytes")
    print(f"Backend: {scan_result.backend}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openscanstation")
    parser.add_argument("--version", action="version", version=f"OpenScanStation {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("scanners", help="Unterstützte Scanner erkennen")
    subparsers.add_parser("status", help="Detaillierten Scannerstatus anzeigen")
    subparsers.add_parser("doctor", help="Proxmox-VM, USB-Passthrough und Kodak-Treiber prüfen")
    scan_parser = subparsers.add_parser("scan", help="Eine Seite mit einem scanfähigen Scanner scannen")
    scan_parser.add_argument("--scanner", help="Name, Modell, Hersteller, Plugin oder Gerätekennung")
    scan_parser.add_argument("--dpi", type=int, default=300, choices=(75, 100, 150, 200, 240, 300, 400, 600))
    scan_parser.add_argument("--mode", default="color", choices=("color", "gray", "lineart"))
    scan_parser.add_argument("--output", default="scan.pdf", help="Zieldatei: .pdf, .png, .jpg oder .jpeg")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scanners":
        return _print_scanners()
    if args.command == "status":
        return _print_status()
    if args.command == "doctor":
        return _doctor()
    if args.command == "scan":
        return _scan(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
