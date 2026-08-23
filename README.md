# OpenScanStation

**Version:** 0.19.0

OpenScanStation ist eine modulare Dokumentenscanner-Plattform für Linux und Debian. Die zentrale Weboberfläche läuft standardmäßig auf Port **8101** und verbindet Scanner, OCR, Dokumenterkennung, Workflows und Speicherziele.

Entwicklung, Projektstruktur und Paketbau sind in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) beschrieben. Hardware- und Brother-Hinweise befinden sich gesammelt unter [docs/](docs/).

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
- konfigurierbare Speicherziele einschließlich Paperless-ngx
- Workflows und Dokumentklassifizierung
- Kopiermodul
- Backup, Wiederherstellung, Diagnose und Supportpaket
- Debian-Paket, systemd-Dienste und GitHub-basierter Updater
- lokale Konten mit Administrator- und Benutzerrolle
- private oder gemeinsam freigegebene Speicherziele
- aktive Ausgabe in SMB-/NAS-Ordner

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

Beim ersten Aufruf erscheint die Ersteinrichtung für das erste lokale Administratorkonto. Danach ist der zentrale Zugang durch Anmeldung geschützt. Administratoren verwalten Konten unter **Benutzer**. Jeder Benutzer wählt unter **Meine Scanner** seine Geräte und verwaltet eigene Scanprofile und Speicherziele.

## Lokale Ordner und NAS-Ausgabe

Unter **Verarbeitung → Speicherziele** können lokale Ordner und SMB-/NAS-Ziele angelegt werden. Ein Ziel kann privat bleiben oder mit anderen Benutzern geteilt werden. Der Verbindungstest prüft bei SMB nicht nur Port 445, sondern Anmeldung, Freigabe und Unterordner. Ein Workflow mit Speicherschritt überträgt die Datei anschließend mit `smbclient` zum NAS.

Der Administrator kann auf derselben Seite den lokalen Samba-Eingang `OpenScan` für native Brother-Profile konfigurieren. Ordner werden dort vorhandenen Scanneraktionen zugeordnet, beispielsweise `rechnung=action-1`.

Alternativ kann das erste Konto auf der Konsole angelegt werden:

```bash
sudo openscanstation-users create admin --role admin --display-name Administrator
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
- SMB, Nextcloud/WebDAV, SFTP, E-Mail und Paperless-ngx produktiv testen
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

## Paperless-ngx

Paperless-ngx kann unter **Speicherziele** als eigener Zieltyp angelegt werden. Benötigt werden die Basis-URL der Paperless-Instanz und ein API-Token. Optional können Korrespondent, Dokumenttyp, Speicherpfad und Tags als numerische Paperless-IDs vorbelegt werden. Ein Workflow mit einem Speicherschritt überträgt das gescannte Dokument anschließend an `/api/documents/post_document/`.

## Brother-Tasten automatisch programmieren

OpenScanStation kann sich experimentell per SNMP als Scan-to-PC-Ziel am Brother registrieren und Tastenereignisse über UDP-Port 54925 empfangen. Dafür müssen Scanner-IP, Server-IP, die interne Scanner-ID und vorhandene Scanneraktionen zugeordnet werden:

```bash
sudo openscanstation-brother-buttons configure \
  --scanner-ip 192.168.1.20 \
  --server-ip 192.168.1.10 \
  --scanner-id 'brother:brother4:net1;dev0' \
  --display-name OpenScan \
  --file-action action-1 \
  --ocr-action action-3

sudo openscanstation-brother-buttons register
sudo systemctl enable --now openscanstation-brother-buttons.service
sudo openscanstation-brother-buttons status
```

Die Firewall muss UDP-Port 54925 ausschließlich aus dem Scanner-Netz zulassen. Die Registrierung verwendet ein herstellerspezifisches, nicht als stabile öffentliche API dokumentiertes Brother-Protokoll und muss deshalb mit dem konkreten Modell und Firmwarestand geprüft werden.

## Brother „Scan to Network“

Native Brother-Netzwerkprofile koennen Dateien direkt in eine SMB-Freigabe von OpenScanStation schreiben. Jeder Unterordner wird einer vorhandenen Scanneraktion zugeordnet; deren Workflow verarbeitet die bereits vom Brother erzeugte Datei, ohne einen zweiten Scan zu starten.

```bash
sudo openscanstation-brother-network configure \
  --profile rechnung=action-1 \
  --profile archiv=action-3

sudo openscanstation-brother-network setup-samba \
  --username openscanstation

sudo systemctl enable --now openscanstation-brother-network.service
```

Das SMB-Passwort wird dabei verdeckt abgefragt. Im Brother-Webinterface wird pro Profil `Network` gewaehlt. Server ist die IP von OpenScanStation, Freigabe `OpenScan`, Speicherordner beispielsweise `rechnung` oder `archiv` und Benutzer `openscanstation`. Der Status des letzten Imports ist mit `sudo openscanstation-brother-network status` abrufbar.
