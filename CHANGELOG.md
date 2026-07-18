# Changelog

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
