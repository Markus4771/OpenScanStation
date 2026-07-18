# OpenScanStation

**Version:** 0.1.1

OpenScanStation ist eine modulare Scannerplattform für Linux und Raspberry Pi.

## Aktueller Funktionsumfang

Version 0.1.1 ist die erste installierbare Testversion für die Scanner-Erkennung.

Unterstützt werden aktuell:

- Kodak i2600 über USB/PyUSB
- Samsung-AirScan-/eSCL-Geräte über SANE und `sane-airscan`
- gemeinsamer Scanner Manager
- CLI-Diagnose
- Debian-Paketstruktur
- Kodak-udev-Regel

Ein echter Dokumentenscan ist in Version 0.1.1 noch nicht enthalten.

## Scanner prüfen

Aus dem Repository:

```bash
python3 -m openscanstation scanners
```

Nach Installation des Debian-Pakets:

```bash
openscanstation scanners
```

## Debian-Paket bauen

```bash
chmod +x scripts/build_deb.sh
./scripts/build_deb.sh
```

Das Paket wird hier erzeugt:

```text
dist/openscanstation_0.1.1_all.deb
```

Installation:

```bash
sudo apt install -y ./dist/openscanstation_0.1.1_all.deb
```

Die vollständige Anleitung steht in [INSTALLATION.md](INSTALLATION.md).

## Architektur

```text
WebGUI / REST-API
        |
Scanner-Manager
        |
        +-- Kodak-i2600-Plugin
        +-- Samsung-AirScan-Plugin
        +-- weitere Scanner-Plugins
```

Scanner werden ausschließlich über Plugins angebunden. Herstellerspezifische Logik gehört nicht in den Core.

## Entwicklungsregel

Während einer laufenden Version werden keine zusätzlichen Produktfunktionen aufgenommen. Neue Ideen werden zunächst in `BACKLOG.md` dokumentiert und erst nach ausdrücklicher Freigabe einer Version zugeordnet.

## Roadmap

### 0.1.x

- Projektstruktur und Dokumentation
- Scanner Manager
- Kodak-USB-Erkennung
- Samsung-AirScan-Erkennung
- Diagnose und installierbares Testpaket

### 0.2.x

- Kodak-Protokollanalyse
- Samsung-Scanprofile und Status
- Papier- und Gerätestatus

### 0.3.x

- Erste Scans mit beiden Geräten
- Duplex und Mehrseitenscan
- Bildspeicherung

### 0.4.x

- OCR, PDF/A, Barcode und QR-Code

### 0.5.x

- Workflow-Engine und Speicherziele

### 1.0.0

- produktive Debian-Installation
- Backup, Update und Plugin-Verwaltung
