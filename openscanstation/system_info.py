"""Read-only system information for the OpenScanStation WebGUI."""
from __future__ import annotations

import shutil
from pathlib import Path

from openscanstation.documents import SCAN_DIR, list_documents

DATA_DIR = Path("/var/lib/openscanstation")
BACKUP_DIR = Path("/var/backups/openscanstation")


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def system_payload() -> dict:
    usage = shutil.disk_usage(DATA_DIR if DATA_DIR.exists() else Path("/"))
    backups = []
    if BACKUP_DIR.exists():
        for item in sorted(BACKUP_DIR.glob("openscanstation-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
            try:
                stat = item.stat()
                backups.append({
                    "name": item.name,
                    "size": stat.st_size,
                    "size_human": _format_bytes(stat.st_size),
                    "modified": stat.st_mtime,
                    "checksum": item.with_suffix(item.suffix + ".sha256").exists(),
                })
            except OSError:
                continue

    documents = list_documents()
    return {
        "data_dir": str(DATA_DIR),
        "backup_dir": str(BACKUP_DIR),
        "scan_dir": str(SCAN_DIR),
        "document_count": len(documents),
        "data_size": _directory_size(DATA_DIR),
        "data_size_human": _format_bytes(_directory_size(DATA_DIR)),
        "disk_total": usage.total,
        "disk_used": usage.used,
        "disk_free": usage.free,
        "disk_total_human": _format_bytes(usage.total),
        "disk_used_human": _format_bytes(usage.used),
        "disk_free_human": _format_bytes(usage.free),
        "disk_percent": round((usage.used / usage.total) * 100, 1) if usage.total else 0,
        "backups": backups,
    }
