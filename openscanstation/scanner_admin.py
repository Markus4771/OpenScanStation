"""Kompatibilitätsschicht für die Scannerverwaltung Version 2."""
from openscanstation.scanner_admin_v2 import (
    configuration,
    delete_manual as delete_manual_scanner,
    import_configuration,
    manual_scanners,
    render,
    restore,
    restore_all as restore_all_hidden,
    save_manual as save_manual_scanner,
)

__all__ = [
    "configuration",
    "delete_manual_scanner",
    "import_configuration",
    "manual_scanners",
    "render",
    "restore",
    "restore_all_hidden",
    "save_manual_scanner",
]
