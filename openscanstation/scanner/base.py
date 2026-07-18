"""Gemeinsame Scanner-Schnittstelle für OpenScanStation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScannerCapabilities:
    duplex: bool = False
    adf: bool = False
    panel_events: bool = False
    paper_sensor: bool = False
    network: bool = False
    usb: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScannerInfo:
    plugin_id: str
    name: str
    manufacturer: str
    model: str
    connection: str
    capabilities: ScannerCapabilities


class ScannerPlugin(ABC):
    """Minimale Schnittstelle, die jedes Scanner-Plugin implementiert."""

    plugin_id: str

    @abstractmethod
    def discover(self) -> list[ScannerInfo]:
        """Findet alle Geräte, die von diesem Plugin unterstützt werden."""

    @abstractmethod
    def get_status(self, device_name: str) -> dict[str, Any]:
        """Liefert einen normalisierten Gerätestatus."""

    def start_scan(self, device_name: str, options: dict[str, Any]) -> Any:
        raise NotImplementedError("Scannen wird von diesem Plugin noch nicht unterstützt.")
