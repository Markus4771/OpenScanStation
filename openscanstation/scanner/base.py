"""Gemeinsame Scanner-Schnittstelle für OpenScanStation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ScannerState(str, Enum):
    READY = "bereit"
    OFFLINE = "offline"
    BUSY = "beschäftigt"
    ERROR = "fehler"
    UNKNOWN = "unbekannt"


@dataclass(frozen=True)
class ScannerCapabilities:
    duplex: bool = False
    adf: bool = False
    panel_events: bool = False
    paper_sensor: bool = False
    network: bool = False
    usb: bool = False
    resolutions_dpi: tuple[int, ...] = ()
    color_modes: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScannerInfo:
    plugin_id: str
    name: str
    manufacturer: str
    model: str
    connection: str
    capabilities: ScannerCapabilities


@dataclass(frozen=True)
class ScannerStatus:
    device: str
    state: ScannerState
    connected: bool
    backend: str
    scan_supported: bool
    paper_present: bool | None = None
    paper_jam: bool | None = None
    cover_open: bool | None = None
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class ScannerPlugin(ABC):
    """Schnittstelle, die jedes Scanner-Plugin implementiert."""

    plugin_id: str

    @abstractmethod
    def discover(self) -> list[ScannerInfo]:
        """Findet alle Geräte, die von diesem Plugin unterstützt werden."""

    @abstractmethod
    def get_status(self, device_name: str) -> ScannerStatus:
        """Liefert einen einheitlichen Gerätestatus."""

    def start_scan(self, device_name: str, options: dict[str, Any]) -> Any:
        raise NotImplementedError("Scannen wird von diesem Plugin noch nicht unterstützt.")