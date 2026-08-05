"""WebGUI und REST-API für Dokumenterkennung auf Port 8105."""
from __future__ import annotations

import argparse
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from openscanstation.barcode_decoder import decode_file, decoder_status
from openscanstation.classification import classify, delete_rule, load_rules, save_result, upsert_rule
from openscanstation.cli import VERSION
from openscanstation.documents import SCAN_DIR

HOST = "0.0.0.0"
PORT = 8105


def _csv(values: list[str]) -> str:
    return ", ".join(values)


def _rule_from_form(form: dict[str, list[str]]) -> dict:
    return {
        "id": form.get("id", [""])[0],
        "name": form.get("name", [""])[0],
        "document_type": form.get("document_type", [""])[0],
        "enabled": form.get("enabled", ["0"])[0] == "1",
        "priority": form.get("priority", ["0"])[0],
        "keywords_any": form.get("keywords_any", [""])[0],
        "keywords_all": form.get("keywords_all", [""])[0],
        "filename_contains": form.get("filename_contains", [""])[0],
        "tag_contains": form.get("tag_contains", [""])[0],
        "barcode_prefixes": form.get("barcode_prefixes", [""])[0],
    }


def _safe_scan_path(filename: str) -> Path:
    name = Path(filename).name
    if not name or name != filename:
        raise ValueError("Ungültiger Dateiname")
    target = SCAN_DIR / name
    if not target.is_file():
        raise FileNotFoundError(f"Scandatei nicht gefunden: {name}")
    return target


def _layout(content: str, notice: str = "", error: bool = False) -> str:
    note = f'<div class="notice {"error" if error else "success"}">{html.escape(notice)}</div>' if notice else ""
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenScanStation Dokumenterkennung</title><style>
body{{font-family:system-ui;margin:0;background:#f3f5f7;color:#17202a}}header{{background:#17202a;color:#fff;padding:1.2rem 2rem}}main{{max-width:1250px;margin:1.5rem auto;padding:0 1rem}}.panel,.card{{background:#fff;padding:1.2rem;border-radius:12px;box-shadow:0 2px 12px #0001;margin-bottom:1rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:1rem}}form{{display:grid;gap:.7rem}}label{{display:grid;gap:.3rem;font-weight:700}}input,textarea,select,button{{padding:.7rem;border:1px solid #bcc5cc;border-radius:8px}}input[type=checkbox]{{width:auto}}textarea{{min-height:90px}}button{{background:#17202a;color:#fff;font-weight:700;cursor:pointer}}.danger{{background:#922b21}}.notice{{padding:1rem;border-radius:8px;margin-bottom:1rem}}.success{{background:#d5f5e3}}.error{{background:#fadbd8}}.muted{{color:#65727e}}pre{{white-space:pre-wrap;background:#f7f7f7;padding:1rem;border-radius:8px}}</style></head><body><header><h1>Dokumenterkennung</h1><div>OpenScanStation {VERSION} · Port {PORT}</div></header><main>{note}{content}</main></body></html>'''


def _fields(rule: dict, include_id: bool) -> str:
    rid = html.escape(rule.get("id", ""), quote=True)
    id_field = f'<label>Regel-ID<input name="id" pattern="[a-z0-9_-]+" value="{rid}" required></label>' if include_id else f'<input type="hidden" name="id" value="{rid}"><p><b>ID:</b> <code>{rid}</code></p>'
    enabled = "selected" if rule.get("enabled", True) else ""
    disabled = "selected" if not rule.get("enabled", True) else ""
    return f'''{id_field}<label>Name<input name="name" value="{html.escape(rule.get('name',''),quote=True)}" required></label><label>Dokumenttyp<input name="document_type" value="{html.escape(rule.get('document_type',''),quote=True)}" required></label><label>Priorität<input type="number" name="priority" min="0" max="1000" value="{int(rule.get('priority',0))}"></label><label>Aktiv<select name="enabled"><option value="1" {enabled}>Ja</option><option value="0" {disabled}>Nein</option></select></label><label>Mindestens eines dieser OCR-Wörter<textarea name="keywords_any">{html.escape(_csv(rule.get('keywords_any',[])))}</textarea></label><label>Alle diese OCR-Wörter<textarea name="keywords_all">{html.escape(_csv(rule.get('keywords_all',[])))}</textarea></label><label>Dateiname enthält<textarea name="filename_contains">{html.escape(_csv(rule.get('filename_contains',[])))}</textarea></label><label>Tag enthält<textarea name="tag_contains">{html.escape(_csv(rule.get('tag_contains',[])))}</textarea></label><label>Barcode-/QR-Präfixe<textarea name="barcode_prefixes">{html.escape(_csv(rule.get('barcode_prefixes',[])))}</textarea></label>'''


def _page(notice: str = "", error: bool = False, result: dict | None = None) -> str:
    cards = []
    for rule in load_rules()["rules"]:
        cards.append(f'''<article class="card"><h2>{html.escape(rule['name'])}</h2><form method="post" action="/save">{_fields(rule,False)}<button>Regel speichern</button></form><form method="post" action="/delete"><input type="hidden" name="id" value="{html.escape(rule['id'],quote=True)}"><button class="danger">Regel löschen</button></form></article>''')
    defaults = {"id":"","name":"Neue Regel","document_type":"dokument","enabled":True,"priority":50,"keywords_any":[],"keywords_all":[],"filename_contains":[],"tag_contains":[],"barcode_prefixes":[]}
    result_box = f'<section class="panel"><h2>Testergebnis</h2><pre>{html.escape(json.dumps(result,ensure_ascii=False,indent=2))}</pre></section>' if result else ""
    status = decoder_status()
    decoder_text = "bereit" if status["available"] else "nicht installiert"
    test = f'''<section class="panel"><h2>Erkennung testen</h2><form method="post" action="/classify"><label>Dateiname im Scanordner<input name="filename" value="test.pdf"></label><label>OCR-Text<textarea name="text" placeholder="Optional OCR-Text einfügen"></textarea></label><label>Tags<input name="tags" placeholder="Eingang, Kunde"></label><label>Zusätzliche Barcode-/QR-Inhalte<input name="barcodes" placeholder="INV:12345, https://..."></label><label><span>Codes automatisch aus der Datei lesen</span><input type="checkbox" name="auto_decode" value="1" checked></label><button>Dokument klassifizieren</button></form><p class="muted">Decoder: {html.escape(decoder_text)} · zbarimg: <code>{html.escape(str(status.get('zbarimg') or '-'))}</code></p></section>'''
    create = f'<section class="panel"><h2>Neue Regel</h2><form method="post" action="/create">{_fields(defaults,True)}<button>Regel anlegen</button></form></section>'
    info = '<section class="panel"><h2>Phase 3</h2><p>Die Klassifizierung nutzt OCR-Text, Dateiname, Tags sowie automatisch ausgelesene Barcodes und QR-Codes. PDF-Dateien werden dafür seitenweise verarbeitet.</p><p class="muted">Regeln: /var/lib/openscanstation/classification_rules.json · Ergebnisse: /var/lib/openscanstation/classification_results.json</p></section>'
    return _layout(info + test + result_box + create + '<div class="grid">' + ''.join(cards) + '</div>', notice, error)


class Handler(BaseHTTPRequestHandler):
    def _send(self, data, status=200, ctype="text/html; charset=utf-8"):
        body = data.encode() if isinstance(data, str) else data
        self.send_response(status); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("X-Frame-Options", "DENY"); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/": self._send(_page())
        elif path == "/health": self._send(json.dumps({"status":"ok","service":"openscanstation-classification","version":VERSION,"port":PORT,"decoder":decoder_status()}), ctype="application/json")
        elif path == "/api/rules": self._send(json.dumps(load_rules(), ensure_ascii=False), ctype="application/json")
        elif path == "/api/decoder": self._send(json.dumps(decoder_status(), ensure_ascii=False), ctype="application/json")
        else: self._send(json.dumps({"error":"not_found"}), 404, "application/json")

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 262144: raise ValueError("Ungültige Formulardaten")
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            if path in {"/create", "/save"}:
                upsert_rule(_rule_from_form(form), create_only=path == "/create")
                self._send(_page("Regel gespeichert.")); return
            if path == "/delete":
                delete_rule(form.get("id", [""])[0]); self._send(_page("Regel gelöscht.")); return
            if path == "/api/decode":
                target = _safe_scan_path(form.get("filename", [""])[0])
                decoded = decode_file(target)
                self._send(json.dumps(decoded, ensure_ascii=False), ctype="application/json"); return
            if path in {"/classify", "/api/classify"}:
                filename = form.get("filename", [""])[0]
                barcodes = [x.strip() for x in form.get("barcodes", [""])[0].split(",") if x.strip()]
                decoded = None
                if filename and form.get("auto_decode", ["1"])[0] == "1":
                    decoded = decode_file(_safe_scan_path(filename))
                    barcodes = list(dict.fromkeys(barcodes + decoded["values"]))
                result = classify(text=form.get("text", [""])[0], filename=filename,
                                  tags=[x.strip() for x in form.get("tags", [""])[0].split(",") if x.strip()],
                                  barcodes=barcodes)
                if decoded is not None:
                    result["decoder"] = decoded
                if filename: save_result(filename, result)
                if path.startswith("/api/"): self._send(json.dumps(result, ensure_ascii=False), ctype="application/json")
                else: self._send(_page("Klassifizierung abgeschlossen.", result=result))
                return
            self._send(json.dumps({"error":"not_found"}), 404, "application/json")
        except Exception as exc:
            if path.startswith("/api/"):
                self._send(json.dumps({"error": str(exc)}, ensure_ascii=False), HTTPStatus.BAD_REQUEST, "application/json")
            else:
                self._send(_page(str(exc), True), HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args): print(fmt % args)


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--host", default=HOST); parser.add_argument("--port", type=int, default=PORT); args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler); print(f"Dokumenterkennung auf {args.host}:{args.port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0


if __name__ == "__main__": raise SystemExit(main())
