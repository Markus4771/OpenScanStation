# OpenScanStation

**Version:** 0.1.0

OpenScanStation ist eine modulare, webbasierte Dokumentenscanner-Plattform für Linux und Raspberry Pi.

## Erste Scanner

- Kodak i2600: direkte USB-/libusb-Entwicklung
- Samsung AirScan: Anbindung über SANE/eSCL/AirScan

## Ziele

- Headless-Betrieb mit WebGUI
- Einheitliche Scanner-API
- Scanner-Plugins statt herstellerspezifischer Logik im Kern
- OCR, PDF/A, Barcode und QR-Code
- Workflows für SMB, Nextcloud, Paperless-ngx, Odoo und E-Mail
- REST-API
- Debian-Paket
- Backup und Updates

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

## Entwicklungsstand

Phase 0.1.0: Projektgrundlage und Scanner-Erkennung.

## Roadmap

### 0.1.x

- Projektstruktur und Dokumentation
- Scanner-Manager
- Kodak-USB-Erkennung
- Samsung-AirScan-Erkennung
- WebGUI-Grundgerüst

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

- Produktive Debian-Installation
- Backup, Update und Plugin-Verwaltung
