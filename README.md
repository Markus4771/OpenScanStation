# OpenScanStation

**Version:** 0.4.1

OpenScanStation ist eine modulare Scannerplattform für Linux und Debian-VMs. Die Weboberfläche läuft standardmäßig auf Port **8101**.

## Aktueller Funktionsumfang

- Samsung-AirScan-/eSCL-Geräte über SANE und `sane-airscan`
- Kodak i2600 über ein installiertes x86_64-SANE-Backend
- gemeinsamer Scanner-Manager und Plugin-System
- WebGUI und REST-API
- PDF-, JPG- und PNG-Scans
- Duplex- und Mehrseitenscans, sofern das Scanner-Backend dies unterstützt
- persistenter Scanordner `/var/lib/openscanstation/scans`
- Dokumentenkatalog mit SQLite
- OCR mit Tesseract und deutscher Sprache
- Volltextsuche über Dokumentdaten, Tags und OCR-Text
- Scanprofile für Rechnung, Lieferschein, Dokument, Foto und Archiv
- Dokumentvorschau und Download
- Diagnosebefehl für Scanner, SANE, OCR und Systemabhängigkeiten
- Debian-Paket und systemd-Dienst
- Integration in die IT-Projektzentrale
- automatischer GitHub-Actions-Build
- Konsolen-Installer und Updater

## Installation auf Debian

Direkt auf dem Zielrechner:

```bash
curl -fsSL https://raw.githubusercontent.com/Markus4771/OpenScanStation/main/install.sh -o /tmp/openscanstation-install.sh
sudo bash /tmp/openscanstation-install.sh install
```

Der Installer lädt bevorzugt das neueste Debian-Paket aus einem GitHub Release. Falls noch kein Release-Paket vorhanden ist, klont er das Repository nach `/opt/OpenScanStation`, baut das Paket lokal und installiert es anschließend.

## Update auf der Konsole

```bash
curl -fsSL https://raw.githubusercontent.com/Markus4771/OpenScanStation/main/install.sh -o /tmp/openscanstation-install.sh
sudo bash /tmp/openscanstation-install.sh update
```

Status prüfen:

```bash
sudo bash /tmp/openscanstation-install.sh status
```

Deinstallieren:

```bash
sudo bash /tmp/openscanstation-install.sh uninstall
```

Die Scandaten unter `/var/lib/openscanstation` bleiben bei der normalen Deinstallation erhalten.

## Privates GitHub-Repository

Falls Releases nur mit Token erreichbar sind:

```bash
export GITHUB_TOKEN='DEIN_TOKEN'
sudo --preserve-env=GITHUB_TOKEN bash /tmp/openscanstation-install.sh update
```

## WebGUI

Nach erfolgreicher Installation:

```text
http://IP-DER-VM:8101
```

Prüfung auf dem Server:

```bash
curl http://127.0.0.1:8101/health
sudo systemctl status openscanstation.service --no-pager
```

## Scanner prüfen

```bash
openscanstation scanners
openscanstation doctor
scanimage -L
```

## Debian-Paket manuell bauen

```bash
git clone https://github.com/Markus4771/OpenScanStation.git
cd OpenScanStation
bash scripts/build_deb.sh
sudo apt install -y ./dist/openscanstation_*.deb
```

## Architektur

```text
WebGUI / REST-API
        |
Dokumentenkatalog / OCR / Scanprofile
        |
Scanner-Manager
        |
        +-- Kodak-i2600-Plugin
        +-- Samsung-AirScan-Plugin
        +-- weitere Scanner-Plugins
```

Scanner werden ausschließlich über Plugins angebunden. Herstellerspezifische Logik gehört nicht in den Core.

## Roadmap

### 0.4.x

- OCR, PDF/A, Barcode und QR-Code
- Dokumentenkatalog und Volltextsuche
- Installations- und Update-Automatisierung

### 0.5.x

- Workflow-Engine
- konfigurierbare Speicherziele
- erweiterte Barcode- und QR-Workflows

### 1.0.0

- produktive Debian-Installation
- Backup- und Wiederherstellungsfunktionen
- Update- und Plugin-Verwaltung über die WebGUI
