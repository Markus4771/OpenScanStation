# Changelog

## 0.5.1

- Gerätebezogene Energieeinstellungen unter `/var/lib/openscanstation/device_settings.json` ergänzt.
- Konfigurierbare Standby-Zeit für Kodak i2600 von 0 bis 240 Minuten ergänzt.
- Kodak-Plugin erkennt automatisch SANE-Optionen wie `sleep-timer`, `standby-time`, `power-save` oder `energy-star`.
- Die konfigurierte Standby-Zeit wird bei Kodak-Scans an den Treiber übergeben, sofern dieser eine passende Option anbietet.
- Scannerstatus zeigt, ob der installierte Kodak-Treiber die Standby-Steuerung unterstützt.
- Neues Werkzeug `openscanstation-kodak-standby` zur Konfiguration ergänzt.
- Release-Paket enthält das neue Kodak-Standby-Werkzeug.

## 0.5.0

- Herstellerunabhängiges Modell für konfigurierbare Scanneraktionen ergänzt.
- Neun Funktionsplätze mit Aktivierung, Displayname, Dokumenttitel, Scanprofil, Tags, Ablageziel und Nachbearbeitung ergänzt.
- Sichere Speicherung unter `/var/lib/openscanstation/scanner_actions.json` ergänzt.
- Neue WebGUI-Seite `Scanneraktionen` zum Bearbeiten aller neun Funktionsplätze ergänzt.
- Aktive Scanneraktionen werden als Schnellaktionen direkt auf dem Dashboard angezeigt.
- Scanneraktionen können bereits über die WebGUI gestartet werden.
- REST-Endpunkt `/api/scanner-actions` ergänzt.
- Geräte- und Ereignisbindungen für Kodak-, Samsung- und weitere Scanner vorbereitet.
- Physische Tasten- und Displayanbindung bleibt modell- und treiberabhängig und wird über Geräteadapter ergänzt.

## 0.4.5

- Langsame Scannererkennung aus den HTTP-Anfragen entfernt.
- Threadsicheren Scanner-Cache mit automatischer Aktualisierung alle 10 Sekunden ergänzt.
- Dashboard und Scanner-API lesen den Scannerstatus jetzt ohne blockierende SANE-/AirScan-Abfragen.
- Button „Scanner neu suchen“ ergänzt; die Erkennung läuft im Hintergrund.
- Cache-Zeitpunkt und Ladezustand werden im Dashboard und über `/api/scanners` angezeigt.
- Eine echte Hardwareerkennung erfolgt weiterhin unmittelbar vor einem Scan, damit keine veraltete Geräteverbindung verwendet wird.

## 0.4.4

- systemd-Watchdog und Timer für den Health-Endpunkt ergänzt.
- Der Dienst kann bei einem fehlgeschlagenen Health-Check automatisch neu gestartet werden.

## 0.4.3

- Neue lesende Systemseite in der WebGUI ergänzt.
- Anzeige von Version, Dokumentanzahl, Datenbestand und freiem Speicher ergänzt.
- Übersicht der zuletzt gefundenen Sicherungen mit Größe und Prüfsummenstatus ergänzt.
- Neue REST-Schnittstelle `/api/system` ergänzt.
- Sicherheits-Header `X-Content-Type-Options`, `X-Frame-Options` und Content-Security-Policy ergänzt.
- Administrative Aktionen bleiben bewusst auf der Konsole, solange keine Benutzeranmeldung vorhanden ist.

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
