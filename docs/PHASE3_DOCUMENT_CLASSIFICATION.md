# Phase 3 – Dokumenterkennung

OpenScanStation 0.6.2 ergänzt eine nachvollziehbare, regelbasierte Dokumentklassifizierung.

## Unterstützte Eingangsdaten

- OCR-Text
- Dateiname
- Dokument-Tags
- bereits erkannte Barcode- und QR-Code-Inhalte

## Vordefinierte Dokumenttypen

- Rechnung
- Lieferschein
- Vertrag
- Brief
- Foto
- Fallback: Dokument

## WebGUI und API

Die Verwaltung läuft auf Port 8105.

- `GET /` – Regelverwaltung und Testmaske
- `GET /health` – Dienststatus
- `GET /api/rules` – Regeln lesen
- `POST /api/classify` – Inhalt klassifizieren

Beispiel:

```bash
curl -X POST http://127.0.0.1:8105/api/classify \
  -d 'filename=eingang.pdf' \
  -d 'text=Rechnung Rechnungsnummer 4711 Gesamtbetrag 99 Euro' \
  -d 'tags=Eingang' \
  -d 'barcodes=INV:4711'
```

## Speicherung

- Regeln: `/var/lib/openscanstation/classification_rules.json`
- Ergebnisse: `/var/lib/openscanstation/classification_results.json`

## Barcode und QR-Code

Die Klassifizierungs-Engine verarbeitet Barcode-/QR-Inhalte bereits. Das automatische Auslesen aus Bild- und PDF-Dateien benötigt anschließend einen Decoder-Adapter, beispielsweise auf Basis von `zbarimg` oder ZXing. Dieser Adapter wird getrennt vom Core gehalten.

## Erweiterbarkeit

Die regelbasierte Engine bleibt der deterministische Standard. Ein späterer KI-Klassifizierer kann als zusätzliches Plugin Ergebnisse vorschlagen, ohne die vorhandenen Regeln und deren Nachvollziehbarkeit zu ersetzen.
