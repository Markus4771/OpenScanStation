"""Selbsttest und Cache-Steuerung für die OpenScanStation-Hardwaremodule."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
REPORT_FILE = DATA_DIR / "hardware_health_report.json"
CACHE_FILE = DATA_DIR / "hardware_inventory_cache.json"


@dataclass
class CheckResult:
    module: str
    ok: bool
    duration_ms: int
    message: str
    details: dict


def _run_check(name: str, callback: Callable[[], object]) -> CheckResult:
    started = time.monotonic()
    try:
        value = callback()
        details: dict
        if isinstance(value, dict):
            details = value
        elif isinstance(value, list):
            details = {"items": len(value)}
        else:
            details = {"result": str(value)[:500]}
        return CheckResult(
            module=name,
            ok=True,
            duration_ms=round((time.monotonic() - started) * 1000),
            message="OK",
            details=details,
        )
    except Exception as exc:  # Ein Modulfehler darf den Gesamttest nicht abbrechen.
        return CheckResult(
            module=name,
            ok=False,
            duration_ms=round((time.monotonic() - started) * 1000),
            message=f"{type(exc).__name__}: {exc}",
            details={},
        )


def run_hardware_checks() -> dict:
    """Prüft die zentralen Hardwaremodule getrennt und speichert einen Bericht."""
    from openscanstation.hardware import (
        brother_assistant,
        diagnostics,
        driver_status,
        inventory,
        network_discovery,
        usb_devices,
    )
    from openscanstation.hardware_management import (
        load_profiles,
        maintenance_items,
        manual_scanners,
        monitor_snapshot,
    )

    checks: list[tuple[str, Callable[[], object]]] = [
        ("inventory", inventory),
        ("monitor", monitor_snapshot),
        ("profiles", load_profiles),
        ("manual_scanners", manual_scanners),
        ("network", network_discovery),
        ("usb", usb_devices),
        ("brother", brother_assistant),
        ("maintenance", maintenance_items),
        ("drivers", driver_status),
        ("diagnostics", diagnostics),
    ]
    results = [_run_check(name, callback) for name, callback in checks]
    report = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "ok": all(result.ok for result in results),
        "summary": {
            "total": len(results),
            "passed": sum(1 for result in results if result.ok),
            "failed": sum(1 for result in results if not result.ok),
            "slow": sum(1 for result in results if result.duration_ms > 5000),
        },
        "results": [asdict(result) for result in results],
    }
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = REPORT_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, REPORT_FILE)
    return report


def load_last_report() -> dict:
    try:
        value = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def clear_hardware_cache() -> dict:
    removed = []
    for path in (CACHE_FILE,):
        if path.exists():
            path.unlink()
            removed.append(str(path))
    try:
        from openscanstation import hardware
        cache = getattr(hardware, "_INVENTORY_CACHE", None)
        if isinstance(cache, dict):
            cache.clear()
    except Exception:
        pass
    return {"ok": True, "removed": removed}
