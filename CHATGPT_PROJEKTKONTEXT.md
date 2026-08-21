# OpenScanStation – Projektkontext

## Aktuelle Version

0.16.0

## Ziel

OpenScanStation ist eine modulare Dokumentenscanner-Plattform für Linux und Debian mit zentraler WebGUI, REST-APIs, OCR, Dokumenterkennung, Workflows und automatisierten Speicherzielen. Die Weboberfläche ist standardmäßig über Port 8101 erreichbar.

## Architekturgrundsätze

- Scanner und herstellerspezifische Funktionen bleiben modular.
- Der Scanner-Core enthält möglichst keine herstellerspezifische Protokolllogik.
- WebGUI, Gateway, Hardware, Scanner-Manager, Profile, Workflows und Speicherziele bleiben klar getrennt.
- Produktive Daten liegen standardmäßig unter `/var/lib/openscanstation`.
- Primäres Installationsformat ist ein Debian-Paket.
- Dokumentation, `version.txt` und Changelog müssen bei Änderungen synchron bleiben.

## Aktueller Ist-Stand

- zentrale Weboberfläche und REST-APIs
- SANE- und AirScan/eSCL-basierte Scannererkennung
- funktionsfähiges Scannen mit dem Brother ADS-2600We
- Kodak-i2600- und Samsung-AirScan-Unterstützung
- Dokumentenkatalog, Vorschau, Download und Volltextsuche
- OCR-Grundfunktionen
- zentrale Scanprofile
- Benutzer-, Scanner- und Speicherzielzuordnung im Profilmodell
- Scanneraktionen und Schnellaktionen
- Hardware-Zentrale mit Scanner-, Drucker-, Netzwerk- und USB-Bereichen
- Hardware-Monitor, Wartung, Treiber, Diagnose und Supportpaket
- Brother-Assistent und vorbereitete Geräteprofile
- Speicherziele, Workflows und Dokumentklassifizierung
- Kopiermodul
- Backup und Wiederherstellung
- Debian-Paket, Installer und GitHub-basierter Updater

## Zentrale Scanprofile

Es gibt nur noch ein produktives Profilmodell. Die Profile werden in

```text
/var/lib/openscanstation/profiles.json
```

gespeichert.

Die frühere Hardware-Datei

```text
/var/lib/openscanstation/hardware_scan_profiles.json
```

wird einmalig migriert und anschließend nicht mehr als eigene Profilverwaltung verwendet. Im Hardware-Bereich erfolgt nur noch die Profilzuordnung zu Scannern, Benutzern und Geräteanzeige.

## Ziel bis Version 1.0

Die vorhandenen Module müssen zu einer stabilen Ende-zu-Ende-Verarbeitung verbunden werden:

```text
Benutzer → Scanprofil → Scanner → Scan → OCR
→ Dokumenterkennung → Workflow → Speicherziel
```

Offene Schwerpunkte:

1. Benutzerverwaltung vollständig integrieren.
2. Profil-, Benutzer-, Scanner- und Speicherzielzuordnung durchgängig machen.
3. Profile bei unterstützten Geräten zuverlässig bereitstellen.
4. SMB, Nextcloud/WebDAV, SFTP und E-Mail produktiv testen.
5. Workflows automatisch nach erfolgreichen Scans ausführen.
6. Dokumenterkennung mit der Workflow-Auswahl verbinden.
7. Hardware-Unterseiten auf Geschwindigkeit und Fehlerfreiheit prüfen.
8. Integrations-, Installations- und Upgrade-Tests ausbauen.

## Arbeitsweise in einem neuen Chat

1. `NEUER_CHAT.md` lesen.
2. Danach `CHATGPT_PROJEKTKONTEXT.md`, `version.txt`, `README.md` und `CHANGELOG.md` lesen.
3. Den tatsächlichen Quellcode und die Tests prüfen.
4. Version, Ist-Stand und offene Aufgaben bestätigen.
5. Ausschließlich auf Basis des aktuellen Repository-Stands weiterarbeiten.
6. Die modulare Scannerarchitektur bewahren.
7. Änderungen angemessen testen und Dokumentation synchron halten.
