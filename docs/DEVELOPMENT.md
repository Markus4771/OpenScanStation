# Entwicklung

## Projektstruktur

| Ordner | Inhalt |
|---|---|
| `openscanstation/` | Anwendung, Webdienste und gemeinsame Fachlogik |
| `openscanstation/scanner/` | Herstellerunabhängiger Scanner-Core |
| `plugins/` | Herstellerspezifische Scanneradapter |
| `packaging/` | systemd-Units, Programmstarter und udev-Regeln |
| `scripts/` | Paketbau, Backup und Systemtests |
| `tests/` | Automatisierte Tests |
| `docs/` | Betriebs-, Hardware- und Entwicklungsdokumentation |
| `integration/` | Metadaten für externe Projektzentralen |

Produktive Daten gehören nicht in das Repository. Sie liegen auf Debian unter
`/var/lib/openscanstation`.

## Architekturregeln

- Herstellerprotokolle bleiben in Plugins oder klar benannten Brother-Modulen.
- Der Scanner-Core bleibt herstellerunabhängig.
- Extern wird nur der Gateway-Port `8101` veröffentlicht.
- Interne Webdienste hören auf `127.0.0.1`.
- Zentrale Scanprofile werden ausschließlich über
  `/var/lib/openscanstation/profiles.json` verwaltet.
- Änderungen an Paketinhalt oder Diensten müssen im Debian-Paket geprüft werden.

## Lokale Prüfung

```bash
python3 -m pytest -q
python3 -m compileall -q openscanstation plugins
```

## Debian-Paket bauen

Das Basispaket wird mit folgendem Befehl erzeugt:

```bash
bash scripts/build_deb.sh
```

Für das vollständige Release-Paket einschließlich aller Zusatzdienste:

```bash
bash scripts/build_release.sh
```

Die erzeugten Verzeichnisse `build/` und `dist/` sind lokale Artefakte und
werden nicht in Git aufgenommen.

