# Brother ADS-2600We mit OpenScanStation

## Empfohlene Anbindung

Der Scanner sollte bevorzugt per LAN mit fester IP-Adresse betrieben werden.
OpenScanStation unterstützt zwei SANE-Wege:

1. `sane-airscan`, wenn der Scanner über eSCL/AirScan erkannt wird.
2. Brother `brscan5`, falls AirScan nicht angeboten oder nicht stabil erkannt wird.

## Debian-Abhängigkeiten

```bash
sudo apt update
sudo apt install -y sane-utils sane-airscan cups cups-client printer-driver-all
```

Danach prüfen:

```bash
scanimage -L
openscanstation scanners
openscanstation doctor
```

Die Ausgabe muss ein Brother-ADS-Gerät enthalten. Das Plugin erkennt sowohl
AirScan-Gerätenamen als auch Brother-SANE-Gerätenamen.

## Feste IP-Adresse

Für einen zuverlässigen Dauerbetrieb sollte der ADS-2600We im DHCP-Server eine
Reservierung erhalten. Bei Verwendung von `brscan5` wird der Scanner mit dem
Brother-Werkzeug anhand seiner IP-Adresse registriert.

## Kopieren

Die Kopieroberfläche läuft auf Port 8106:

```text
http://SERVER-IP:8106
```

CUPS-Drucker prüfen:

```bash
lpstat -p -d
```

Unterstützt werden:

- 1 bis 99 Kopien
- Farbe oder Graustufen
- Simplex- oder Duplex-Scan
- Simplex- oder Duplex-Druck
- A4, A5 und Letter
- Skalierung von 25 bis 400 Prozent
- 1, 2 oder 4 Seiten pro Blatt
- Helligkeit und Kontrast, sofern das SANE-Backend die Optionen unterstützt

Druckerspezifische Funktionen wie Heften, Lochen oder Broschürendruck können
später als CUPS-Optionen ergänzt werden. Ihre Verfügbarkeit hängt von der
PPD-/IPP-Beschreibung des jeweiligen Druckers ab.
