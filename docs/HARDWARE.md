# OpenScanStation Hardware-Zentrale

Ab Version 0.8.0 werden Scanner und Drucker unter dem gemeinsamen Bereich **Hardware** verwaltet.

## Weboberfläche

- Hardware-Übersicht: `http://SERVER-IP:8107/`
- Scanner: `http://SERVER-IP:8107/scanners`
- Drucker: `http://SERVER-IP:8107/printers`
- Diagnose: `http://SERVER-IP:8107/diagnostics`
- Treiberstatus: `http://SERVER-IP:8107/drivers`

## REST-API

- `GET /api/hardware` – Scanner und Drucker
- `GET /api/diagnostics` – SANE, AirScan, USB und CUPS
- `GET /api/drivers` – installierte Basiskomponenten
- `GET /health` – Dienststatus

## Scanner

Scanner werden weiterhin über die Scanner-Plugins erkannt. Unterstützt sind aktuell insbesondere:

- Brother ADS-2600We und weitere Brother-ADS-Geräte über SANE/AirScan
- Kodak i2600 über den KDS-SANE-Treiber
- Samsung C48x über SANE-AirScan

Eigene Anzeigenamen, Deaktivierung und Standardscanner werden in `/var/lib/openscanstation/scanner_settings.json` gespeichert.

## Drucker

Drucker werden über CUPS erkannt. Die Hardware-Zentrale zeigt Status und erkannte Fähigkeiten wie Duplex, Farbe, Heften und Lochen an. Ein Standarddrucker kann für OpenScanStation gewählt und eine CUPS-Testseite gesendet werden.

Die Einstellungen liegen in `/var/lib/openscanstation/hardware_settings.json`.

## Diagnose

Die Diagnose bündelt die Ausgaben von:

```bash
scanimage -L
airscan-discover
lsusb
lpstat -p -d
lpinfo -v
```

## CLI

```bash
openscanstation hardware
openscanstation doctor
```

## Sicherheit

OpenScanStation installiert keine beliebigen Herstellertreiber ungeprüft aus dem Internet. Fehlende Komponenten werden angezeigt. Bevorzugt werden signierte Debian-Pakete und standardisierte Schnittstellen wie SANE, eSCL/AirScan, IPP und CUPS.
