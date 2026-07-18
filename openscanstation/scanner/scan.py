"""Gemeinsame Modelle für Scanaufträge und Ergebnisse."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScanJob:
    device: str
    output: Path
    dpi: int = 300
    mode: str = "color"
    source: str = "Automatic Document Feeder"


@dataclass(frozen=True)
class ScanResult:
    output: Path
    bytes_written: int
    backend: str
