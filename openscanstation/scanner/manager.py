"""Zentrale Scanner-Erkennung für OpenScanStation."""

from __future__ import annotations

from dataclasses import dataclass

from openscanstation.scanner.base import ScannerInfo, ScannerPlugin
from plugins.kodak_i2600.plugin import KodakI2600Plugin
from plugins.samsung_airscan.plugin import SamsungAirScanPlugin


@dataclass(frozen=True)
class PluginError:
    """Fehler eines Plugins, ohne die gesamte Erkennung abzubrechen."""

    plugin_id: str
    message: str


@dataclass(frozen=True)
class DiscoveryResult:
    scanners: list[ScannerInfo]
    errors: list[PluginError]


class ScannerManager:
    """Lädt Scanner-Plugins und führt deren Erkennung gemeinsam aus."""

    def __init__(self, plugins: list[ScannerPlugin] | None = None) -> None:
        self.plugins = plugins or [KodakI2600Plugin(), SamsungAirScanPlugin()]

    def discover(self) -> DiscoveryResult:
        scanners: list[ScannerInfo] = []
        errors: list[PluginError] = []
        seen: set[tuple[str, str]] = set()

        for plugin in self.plugins:
            try:
                discovered = plugin.discover()
            except Exception as exc:  # Ein defektes Plugin darf andere nicht blockieren.
                errors.append(PluginError(plugin.plugin_id, str(exc)))
                continue

            for scanner in discovered:
                key = (scanner.plugin_id, scanner.connection)
                if key in seen:
                    continue
                seen.add(key)
                scanners.append(scanner)

        return DiscoveryResult(scanners=scanners, errors=errors)

    def get_plugin(self, plugin_id: str) -> ScannerPlugin | None:
        for plugin in self.plugins:
            if plugin.plugin_id == plugin_id:
                return plugin
        return None
