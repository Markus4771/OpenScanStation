#!/usr/bin/env python3
"""Standby-Zeit eines Kodak-Scanners konfigurieren."""
from __future__ import annotations

import argparse
import json

from openscanstation.device_settings import set_device_standby


def main() -> int:
    parser = argparse.ArgumentParser(prog="openscanstation-kodak-standby")
    parser.add_argument("device", help="SANE-Gerätename aus 'scanimage -L'")
    parser.add_argument("minutes", type=int, help="0 bis 240 Minuten")
    parser.add_argument(
        "--disable",
        action="store_true",
        help="Standby-Übergabe an den Treiber deaktivieren",
    )
    args = parser.parse_args()
    device_id = f"kodak_i2600:{args.device}"
    setting = set_device_standby(device_id, args.minutes, enabled=not args.disable)
    print(json.dumps({"device_id": device_id, **setting}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
