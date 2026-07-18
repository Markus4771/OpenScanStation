"""Kommandozeilen-Diagnose für OpenScanStation."""

from __future__ import annotations

import argparse

from openscanstation.scanner.manager import ScannerManager

VERSION = "0.2.0"


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openscanstation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("scanners", help="Unterstützte Scanner erkennen")
    subparsers.add_parser("status", help="Detaillierten Scannerstatus anzeigen")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scanners":
        return _print_scanners()
    if args.command == "status":
        return _print_status()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())