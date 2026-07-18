"""Kommandozeilen-Diagnose für OpenScanStation."""

from __future__ import annotations

import argparse

from openscanstation.scanner.manager import ScannerManager

VERSION = "0.1.1"


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
            status = plugin.get_status(scanner.connection) if plugin else {}
            state = "verbunden" if status.get("connected") else "nicht verfügbar"

            print(f"\n{index}. {scanner.name}")
            print(f"   Hersteller: {scanner.manufacturer}")
            print(f"   Modell: {scanner.model}")
            print(f"   Verbindung: {scanner.connection}")
            print(f"   Plugin: {scanner.plugin_id}")
            print(f"   Status: {state}")

    if result.errors:
        print("\nPlugin-Fehler")
        print("-" * 40)
        for error in result.errors:
            print(f"{error.plugin_id}: {error.message}")

    print(f"\nScanner gefunden: {len(result.scanners)}")
    return 0 if not result.errors else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openscanstation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("scanners", help="Unterstützte Scanner erkennen")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scanners":
        return _print_scanners()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
