# OpenScanStation

**Version:** 0.16.0

OpenScanStation ist eine modulare Dokumentenscanner-Plattform für Linux und Debian. Die zentrale Weboberfläche läuft standardmäßig auf Port **8101** und verbindet Scanner, OCR, Dokumenterkennung, Workflows und Speicherziele.

## Aktueller Funktionsumfang

- zentrale Weboberfläche und REST-APIs
- Scannererkennung und Scannen über SANE und AirScan/eSCL
- Unterstützung für Brother ADS-2600We, Kodak i2600 und Samsung-AirScan-Geräte
- PDF-, JPG- und PNG-Ausgabe sowie Mehrseiten- und Duplexscan, sofern vom Backend unterstützt
- Dokumentenkatalog mit SQLite, Vorschau, Download und Volltextsuche
- OCR mit Tesseract
- zentrale Scanprofile mit Auflösung, Farbmodus, Ausgabeformat, OCR und Duplex
- Profilzuordnung zu Benutzern, Scannern und Speicherzielen
- Scanneraktionen und Schnellaktionen
- Hardware-Zentrale mit Scanner-, Drucker-, Netzwerk- und USB-Verwaltung
- Geräteerkennung, Verbindungstest, Testscan, Monitoring, Wartung und Diagnose
- Brother-Assistent und vorbereitete Brother-Geräteprofile
- konfigurierbare Speicherziele
- Workflows und Dokumentklassifizierung
- Kopiermodul
- Backup, Wiederherstellung, Diagnose und Supportpaket
- Debian-Paket, systemd-Dienste und GitHub-basierter Updater

## Architektur

```text
WebGUI / Gateway (Port 8101)
        |
        +-- Scan- und Dokumentendienst
        +-- Hardwaredienst
        +-- Speicherziele
        +-- Workflows und Klassifizierung
        +-- Kopierdienst
        |
Scanner-Manager / SANE / AirScan
        |
        +-- geräte- und herstellerspezifische Adapter
```

Scanneranbindung und herstellerspezifische Funktionen bleiben modular. Zentrale Profile werden in `/var/lib/openscanstation/profiles.json` gespeichert. Die frühere getrennte Hardware-Profilverwaltung wird beim ersten Laden migriert.

## Installation auf Debian

```bash
curl -fsSL https://raw.githubusercontent.com/Markus4771/OpenScanStation/main/install.sh -o /tmp/openscanstation-install.sh
sudo bash /tmp/openscanstation-install.sh install
```

## Update

```bash
curl -fsSL https://raw.githubusercontent.com/Markus4771/OpenScanStation/main/install.sh -o /tmp/openscanstation-install.sh
sudo bash /tmp/openscanstation-install.sh update
```

Für private Releases kann ein GitHub-Token übergeben werden:

```bash
export GITHUB_TOKEN='DEIN_TOKEN'
sudo --preserve-env=GITHUB_TOKEN bash /tmp/openscanstation-install.sh update
```

## Betrieb und Diagnose

```bash
openscanstation version
openscanstation scanners
openscanstation doctor
sudo systemctl status openscanstation.service --no-pager
curl http://127.0.0.1:8101/health
```

Weboberfläche:

```text
http://IP-DES-SERVERS:8101
```

Die produktiven Daten liegen standardmäßig unter `/var/lib/openscanstation`.

## Entwicklungsstand Richtung 1.0

Die Grundarchitektur und die wesentlichen Module sind vorhanden. Der Schwerpunkt bis Version 1.0 liegt auf dem durchgängigen Zusammenschalten und Stabilisieren dieser Verarbeitungskette:

```text
Benutzer → Scanprofil → Scanner → Scan → OCR
→ Dokumenterkennung → Workflow → Speicherziel
```

Besonders wichtig sind noch:

- Benutzerverwaltung vollständig integrieren
- Profil-, Benutzer-, Scanner- und Speicherzielzuordnung durchgängig testen
- unterstützte Scannerprofile zuverlässig an Geräte übertragen
- SMB, Nextcloud/WebDAV, SFTP und E-Mail produktiv testen
- Workflows nach einem Scan automatisch ausführen
- Dokumenterkennung mit Workflows verbinden
- Hardware-Unterseiten auf Geschwindigkeit und Fehlerfreiheit prüfen
- Integrations-, Installations- und Upgrade-Tests ausbauen

## Debian-Paket manuell bauen

```bash
git clone https://github.com/Markus4771/OpenScanStation.git
cd OpenScanStation
bash scripts/build_deb.sh
sudo apt install -y ./dist/openscanstation_*.deb
```
