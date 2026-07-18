# OpenScanStation 0.1.1 – Installationsanleitung

## Unterstützte Systeme

- Debian 12
- Raspberry Pi OS auf Debian-12-Basis
- Python 3
- Kodak i2600 über USB
- Samsung-AirScan-/eSCL-Scanner im lokalen Netzwerk

## Debian-Paket auf dem Entwicklungsrechner bauen

```bash
cd ~/OpenScanStation
git pull
chmod +x scripts/build_deb.sh
./scripts/build_deb.sh
```

Das fertige Paket liegt anschließend unter:

```text
dist/openscanstation_0.1.1_all.deb
```

## Installation

```bash
sudo apt update
sudo apt install -y ./dist/openscanstation_0.1.1_all.deb
```

`apt` installiert dabei automatisch die benötigten Pakete:

- `python3`
- `python3-usb`
- `sane-utils`
- `sane-airscan`

## Scanner prüfen

Nach der Installation:

```bash
openscanstation scanners
```

Erwartete Ausgabe bei angeschlossenem Kodak i2600 und erreichbarem Samsung-Scanner:

```text
OpenScanStation 0.1.1
Scanner-Erkennung
========================================

1. Kodak i2600
   Hersteller: Kodak
   Modell: i2600
   Verbindung: usb:1:6
   Plugin: kodak_i2600
   Status: verbunden

2. WSD Samsung C48x Series ...
   Hersteller: Samsung
   Verbindung: airscan:w0:Samsung C48x Series ...
   Plugin: samsung_airscan
   Status: verbunden

Scanner gefunden: 2
```

## Kodak i2600

Das Debian-Paket installiert die udev-Regel:

```text
/lib/udev/rules.d/60-openscanstation-kodak.rules
```

Nach der Installation den Kodak-Scanner einmal aus- und wieder einstecken. Falls er nicht erkannt wird:

```bash
lsusb | grep -i kodak
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Danach erneut:

```bash
openscanstation scanners
```

## Samsung AirScan

Zuerst prüfen, ob SANE den Scanner findet:

```bash
scanimage -L
```

Der Scanner und der OpenScanStation-Rechner müssen sich im selben erreichbaren Netzwerk befinden. Danach:

```bash
openscanstation scanners
```

## Update einer vorhandenen Installation

Ein neueres Paket wird mit demselben Befehl installiert:

```bash
sudo apt install -y ./openscanstation_NEUE_VERSION_all.deb
```

## Deinstallation

```bash
sudo apt remove openscanstation
```

Vollständige Entfernung einschließlich Paketkonfiguration:

```bash
sudo apt purge openscanstation
```

## Fehlerdiagnose

### Befehl nicht gefunden

```bash
dpkg -s openscanstation
ls -l /usr/bin/openscanstation
```

### Kein Scanner gefunden

```bash
lsusb
scanimage -L
openscanstation scanners
```

### Kodak nur mit sudo sichtbar

```bash
getent group scanner
ls -l /lib/udev/rules.d/60-openscanstation-kodak.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Anschließend den Scanner neu verbinden.
