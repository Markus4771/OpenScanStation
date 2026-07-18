# OpenScanStation – Projektkontext

## Aktuelle Version

0.1.0

## Ziel

OpenScanStation ist eine modulare Dokumentenscanner-Plattform für Raspberry Pi und Linux mit WebGUI, REST-API, OCR, PDF/A und automatisierten Ablage-Workflows.

## Architekturgrundsätze

- Scanner werden als austauschbare Plugins umgesetzt.
- Der Scanner-Core enthält keine herstellerspezifische Protokolllogik.
- Frontend, Scanner-Manager, Workflows und Speicherziele bleiben getrennt.
- Erweiterungen sollen möglichst durch Konfiguration und Plugins erfolgen.
- Zielplattformen sind Raspberry Pi OS 64 Bit und Debian.
- Primäres Installationsformat ist ein Debian-Paket.

## Erste Scanner

### Kodak i2600

- USB-ID: `040a:601d`
- Eine herstellerspezifische USB-Schnittstelle
- Endpunkte: Interrupt IN `0x81` und `0x88`, Bulk OUT `0x02`, Bulk IN `0x82` und `0x86`
- Standard-SANE erkennt das Gerät nicht als nutzbaren Scanner.
- Entwicklung erfolgt schrittweise über PyUSB/libusb und Protokollanalyse.
- Bis zur Protokollklärung werden nur sichere Lese- und Diagnosetests durchgeführt.

### Samsung AirScan

- Wurde bereits von `scanimage -L` über `airscan` im Netzwerk gefunden.
- Erste Integration erfolgt über SANE/eSCL/AirScan.
- Exaktes Modell und vollständiger Gerätename müssen aus der aktuellen `scanimage -L`-Ausgabe übernommen werden.

## Einheitliche Scanner-API

Scanner-Plugins sollen mindestens folgende Fähigkeiten abbilden:

- erkennen
- verbinden und trennen
- Informationen und Status liefern
- Papierstatus liefern, soweit unterstützt
- Scanoptionen melden
- Scan starten und abbrechen
- Bild- beziehungsweise Dokumentdaten liefern
- Bedienfeldereignisse melden, soweit unterstützt

Nicht jedes Gerät muss jede Fähigkeit unterstützen. Fähigkeiten werden über Capability-Flags gemeldet.

## Roadmap

### 0.1.x

- Projektgrundlage
- Scanner-Plugin-Schnittstelle
- Kodak- und Samsung-Erkennung
- Diagnosewerkzeuge
- erste WebGUI

### 0.2.x

- Samsung-Scannen über SANE/eSCL
- Kodak-Protokollanalyse und Status
- Profile und Gerätefähigkeiten

### 0.3.x

- stabiler Mehrseitenscan
- Duplex
- Jobverwaltung

### 0.4.x

- OCR
- PDF/A
- Barcode und QR-Code

### 0.5.x

- SMB, Nextcloud, Paperless-ngx, Odoo und E-Mail

### 1.0.0

- Debian-Paket
- Backup und Update
- produktive WebGUI
- Pluginverwaltung

## Arbeitsweise

Bei einem neuen Chat zuerst `NEUER_CHAT.md`, danach diese Datei, `version.txt`, `README.md` und `CHANGELOG.md` lesen. Anschließend immer den tatsächlichen Quellcode prüfen und nur auf dem aktuellen Repository-Stand weiterarbeiten.
