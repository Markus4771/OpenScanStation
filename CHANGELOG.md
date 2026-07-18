# Changelog

## 0.4.2

- Vollständige Sicherung aller produktiven Daten unter `/var/lib/openscanstation` ergänzt.
- Sicherungen enthalten Scans, Dokumentendatenbank und Scanprofile.
- SHA256-Prüfsummen für Sicherungsarchive ergänzt.
- Sichere Wiederherstellung mit Archivprüfung gegen absolute Pfade und Pfadnavigation ergänzt.
- Vor jeder Wiederherstellung wird automatisch eine Rückfallsicherung erzeugt.
- Neues Konsolenwerkzeug `openscanstation-backup` mit `create`, `list`, `restore` und `help` ergänzt.
- Release-Build erweitert, sodass das Sicherungswerkzeug Bestandteil des DEB-Pakets ist.
- GitHub Actions prüft Shell-Skripte und kontrolliert den Paketinhalt auf das Sicherungswerkzeug.

## 0.4.1

- Konsolen-Installer `install.sh` ergänzt.
- Einheitliche Befehle `install`, `update`, `status` und `uninstall` ergänzt.
- Neueste DEB-Datei wird bevorzugt direkt aus dem aktuellen GitHub Release geladen.
- Falls noch kein Release-Paket vorhanden ist, wird automatisch aus dem aktuellen `main`-Stand gebaut.
- Optionaler Zugriff auf private Releases über die Umgebungsvariable `GITHUB_TOKEN` ergänzt.
- Dienst wird nach Installation oder Update automatisch aktiviert und gestartet.
- Automatischer Health-Check auf Port 8101 ergänzt.
- Fehlerausgabe verweist direkt auf den passenden `journalctl`-Diagnosebefehl.
- Versions- und Installationsdokumentation aktualisiert.

## 0.4.0

- Dokumentenkatalog auf Basis von SQLite ergänzt.
- Volltextsuche über Titel, Dateiname, Scanner, Tags und OCR-Text ergänzt.
- OCR mit Tesseract und deutscher Sprache integriert.
- PDF-Seiten werden für OCR automatisch über `pdftoppm` aufbereitet.
- Konfigurierbare Scanprofile für Rechnung, Lieferschein, Dokument, Foto und Archiv ergänzt.
- WebGUI um die Bereiche Dashboard, Dokumente und Scanprofile erweitert.
- Dokumentvorschau und Download im Browser ergänzt.
- OCR kann automatisch beim Scan oder nachträglich gestartet werden.
- Samsung-AirScan und Kodak-SANE bleiben gemeinsam auswählbar.
- Diagnose prüft jetzt zusätzlich Tesseract und Poppler.
- Debian-Paket enthält alle OCR-Abhängigkeiten.

## 0.3.1

- WebGUI auf Port 8101 um Scanformular erweitert.
- Samsung-AirScan- und Kodak-SANE-Geräte sind direkt auswählbar.
- Auflösung, Farbmodus und Ausgabeformat können in der WebGUI gewählt werden.
- Scans werden dauerhaft unter `/var/lib/openscanstation/scans` gespeichert.
- Download und Übersicht der letzten Scans ergänzt.
- REST-Endpunkt `/api/scans` ergänzt.
- Gleichzeitige Scanaufträge werden durch eine Sperre verhindert.
- Debian-Paket und systemd-Härtung für den persistenten Scanordner angepasst.
- GitHub Actions baut bei jedem Push automatisch eine DEB-Datei.
- Bei Versions-Tags `v*` wird die DEB-Datei an den GitHub Release angehängt.

## 0.3.0

- WebGUI und REST-API auf Port 8101 ergänzt.
- Health-, Versions- und Scanner-Endpunkte ergänzt.
- systemd-Dienst und Integration in die IT-Projektzentrale ergänzt.
- Diagnosebefehl `openscanstation doctor` für Intel-Proxmox-VM, USB und SANE ergänzt.
- Kodak i2600 kann über ein installiertes x86_64-SANE-Backend scannen.

## 0.2.0

- Einheitliches Datenmodell `ScannerStatus` eingeführt.
- Kodak-i2600- und Samsung-AirScan-Plugin auf den normalisierten Status umgestellt.
- Scannerfähigkeiten, Statusausgabe und CLI-Diagnose erweitert.

## 0.1.1

- Zentralen Scanner Manager hinzugefügt.
- Kodak-i2600- und Samsung-AirScan-Plugin gemeinsam registriert.
- Debian-Paketstruktur, udev-Regel und Diagnose ergänzt.

## 0.1.0

- Projekt OpenScanStation initialisiert.
- Modulare Scanner-Architektur festgelegt.
