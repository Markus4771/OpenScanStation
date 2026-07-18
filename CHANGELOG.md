# Changelog

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
- Zustände `bereit`, `offline`, `beschäftigt`, `fehler` und `unbekannt` definiert.
- Kodak-i2600-Plugin auf den normalisierten Status umgestellt.
- Samsung-AirScan-Plugin auf den normalisierten Status umgestellt.
- Scannerfähigkeiten um Auflösungen und Farbmodi erweitert.
- CLI-Befehl `openscanstation status` ergänzt.
- Detaillierte Ausgabe für Backend, Verbindung, Scan-Unterstützung, ADF, Duplex und verfügbare Modi ergänzt.
- Noch nicht auslesbare Sensorwerte werden ausdrücklich als `nicht verfügbar` angezeigt.

## 0.1.1

- Zentralen Scanner Manager hinzugefügt.
- Kodak-i2600- und Samsung-AirScan-Plugin gemeinsam registriert.
- Pluginfehler werden isoliert und blockieren die übrige Erkennung nicht.
- Doppelte Scannerergebnisse werden gefiltert.
- Diagnosebefehl `python3 -m openscanstation scanners` hinzugefügt.
- Scanner-Erkennung mit echtem Kodak i2600 und Samsung C48x erfolgreich getestet.
- Debian-Paket-Build für `openscanstation_0.1.1_all.deb` ergänzt.
- Globalen Befehl `openscanstation` ergänzt.
- Abhängigkeiten für PyUSB, SANE und AirScan im Paket definiert.
- udev-Regel für den Kodak i2600 ergänzt.
- Installations-, Update-, Deinstallations- und Fehlerdiagnose-Anleitung ergänzt.

## 0.1.0

- Projekt OpenScanStation initialisiert.
- Modulare Scanner-Architektur festgelegt.
- Kodak i2600 als direktes USB-/libusb-Plugin vorgesehen.
- Samsung AirScan als SANE-/eSCL-Plugin vorgesehen.
- README und Versionsverwaltung angelegt.
