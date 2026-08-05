"""WebGUI für Papierkopien auf Port 8106."""
from __future__ import annotations

import argparse
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from openscanstation.cli import VERSION
from openscanstation.copy_service import create_copy, list_copy_jobs, list_printers
from openscanstation.scanner.manager import ScannerManager

HOST = "0.0.0.0"
PORT = 8106


def _layout(content: str, notice: str = "", error: bool = False) -> str:
    note = f'<div class="notice {"error" if error else "success"}">{html.escape(notice)}</div>' if notice else ""
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenScanStation Kopieren</title><style>
body{{font-family:system-ui;margin:0;background:#f3f5f7;color:#17202a}}header{{background:#17202a;color:#fff;padding:1.2rem 2rem}}main{{max-width:1100px;margin:1.5rem auto;padding:0 1rem}}.panel{{background:#fff;padding:1.2rem;border-radius:12px;box-shadow:0 2px 12px #0001;margin-bottom:1rem}}form{{display:grid;gap:.8rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.8rem}}label{{display:grid;gap:.3rem;font-weight:700}}input,select,button{{padding:.75rem;border:1px solid #bcc5cc;border-radius:8px}}button{{background:#17202a;color:#fff;font-weight:700;cursor:pointer}}.notice{{padding:1rem;border-radius:8px;margin-bottom:1rem}}.success{{background:#d5f5e3}}.error{{background:#fadbd8}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.6rem;border-bottom:1px solid #ddd;text-align:left}}.muted{{color:#65727e}}</style></head><body><header><h1>Kopieren</h1><div>OpenScanStation {VERSION} · Port {PORT}</div></header><main>{note}{content}</main></body></html>'''


def _page(notice: str = "", error: bool = False) -> str:
    scanners = ScannerManager().discover().scanners
    scanner_options = ''.join(
        f'<option value="{html.escape(f"{s.plugin_id}:{s.connection}", quote=True)}">{html.escape(s.name)}</option>'
        for s in scanners
    )
    printers = list_printers()
    printer_options = ''.join(
        f'<option value="{html.escape(p["name"], quote=True)}" {"selected" if p["default"] else ""}>{html.escape(p["name"])}</option>'
        for p in printers if p["enabled"]
    )
    unavailable = ""
    if not scanner_options:
        unavailable += '<p class="notice error">Kein Scanner verfügbar.</p>'
    if not printer_options:
        unavailable += '<p class="notice error">Kein aktiver CUPS-Drucker verfügbar.</p>'
    disabled = "disabled" if not scanner_options or not printer_options else ""
    form = f'''<section class="panel"><h2>Papierkopie starten</h2>{unavailable}<form method="post" action="/copy"><div class="grid">
<label>Scanner<select name="scanner_id">{scanner_options}</select></label>
<label>Drucker<select name="printer">{printer_options}</select></label>
<label>Anzahl Kopien<input type="number" min="1" max="99" name="copies" value="1"></label>
<label>Farbe<select name="color"><option value="1">Farbe</option><option value="0">Schwarzweiß</option></select></label>
<label>Scan-Seiten<select name="duplex_scan"><option value="0">Einseitig</option><option value="1">Duplex</option></select></label>
<label>Druck-Seiten<select name="duplex_print"><option value="0">Einseitig</option><option value="1">Duplex lange Kante</option></select></label>
<label>Papierformat<select name="media"><option>A4</option><option>A5</option><option>Letter</option></select></label>
<label>Skalierung %<input type="number" min="25" max="400" name="scale" value="100"></label>
<label>Seiten pro Blatt<select name="n_up"><option value="1">1</option><option value="2">2</option><option value="4">4</option></select></label>
<label>Helligkeit<input type="number" min="-100" max="100" name="brightness" value="0"></label>
<label>Kontrast<input type="number" min="-100" max="100" name="contrast" value="0"></label>
</div><button {disabled}>Kopie starten</button></form><p class="muted">Der Scanner erzeugt intern ein temporäres PDF. Dieses wird über CUPS gedruckt und anschließend gelöscht.</p></section>'''
    rows = ''.join(
        f'<tr><td>{html.escape(j.get("created_at", ""))}</td><td>{html.escape(j.get("scanner", ""))}</td><td>{html.escape(j.get("printer", ""))}</td><td>{j.get("copies", 1)}</td><td>{html.escape(j.get("status", ""))}</td></tr>'
        for j in list_copy_jobs(30)
    ) or '<tr><td colspan="5">Noch keine Kopieraufträge.</td></tr>'
    history = f'<section class="panel"><h2>Letzte Kopieraufträge</h2><table><tr><th>Zeit</th><th>Scanner</th><th>Drucker</th><th>Kopien</th><th>Status</th></tr>{rows}</table></section>'
    return _layout(form + history, notice, error)


class Handler(BaseHTTPRequestHandler):
    def _send(self, data, status=200, ctype="text/html; charset=utf-8"):
        body = data.encode() if isinstance(data, str) else data
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(_page())
        elif path == "/health":
            self._send(json.dumps({"status": "ok", "service": "openscanstation-copy", "version": VERSION, "port": PORT}), ctype="application/json")
        elif path == "/api/printers":
            self._send(json.dumps({"printers": list_printers()}, ensure_ascii=False), ctype="application/json")
        elif path == "/api/jobs":
            self._send(json.dumps({"jobs": list_copy_jobs()}, ensure_ascii=False), ctype="application/json")
        else:
            self._send(json.dumps({"error": "not_found"}), 404, "application/json")

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise ValueError("Ungültige Formulardaten")
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            if path == "/copy":
                job = create_copy(
                    form.get("scanner_id", [""])[0],
                    form.get("printer", [""])[0],
                    copies=int(form.get("copies", ["1"])[0]),
                    color=form.get("color", ["1"])[0] == "1",
                    duplex_scan=form.get("duplex_scan", ["0"])[0] == "1",
                    duplex_print=form.get("duplex_print", ["0"])[0] == "1",
                    media=form.get("media", ["A4"])[0],
                    scale=int(form.get("scale", ["100"])[0]),
                    n_up=int(form.get("n_up", ["1"])[0]),
                    brightness=int(form.get("brightness", ["0"])[0]),
                    contrast=int(form.get("contrast", ["0"])[0]),
                )
                self._send(_page(f"Kopierauftrag an {job['printer']} übergeben."))
                return
            self._send(json.dumps({"error": "not_found"}), 404, "application/json")
        except Exception as exc:
            self._send(_page(str(exc), True), HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args):
        print(fmt % args)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Kopier-WebGUI auf {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
