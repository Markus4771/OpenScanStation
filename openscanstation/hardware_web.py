"""Hardware-Zentrale für Scanner, Drucker, Diagnose und Treiberstatus."""
from __future__ import annotations

import argparse
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from openscanstation.cli import VERSION
from openscanstation.hardware import diagnostics, driver_status, inventory, load_settings, print_test_page, save_settings

HOST = "0.0.0.0"
PORT = 8107


def _layout(content: str, title: str = "Hardware", notice: str = "", error: bool = False) -> str:
    note = f'<div class="notice {"error" if error else "success"}">{html.escape(notice)}</div>' if notice else ""
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>
body{{font-family:system-ui;margin:0;background:#f3f5f7;color:#17202a}}header{{background:#17202a;color:#fff;padding:1.2rem 2rem}}header a{{color:#fff;text-decoration:none;margin-right:1rem}}main{{max-width:1280px;margin:1.5rem auto;padding:0 1rem}}.panel,.card{{background:#fff;padding:1.2rem;border-radius:12px;box-shadow:0 2px 12px #0001;margin-bottom:1rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem}}.status{{padding:.25rem .55rem;border-radius:999px;font-weight:700}}.ok{{background:#d5f5e3;color:#196f3d}}.bad{{background:#fadbd8;color:#922b21}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.65rem;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}}button,input,select{{padding:.7rem;border:1px solid #bcc5cc;border-radius:8px}}button{{background:#17202a;color:#fff;font-weight:700;cursor:pointer}}form{{display:grid;gap:.7rem}}.inline{{display:inline-block;margin-right:.4rem}}.notice{{padding:1rem;border-radius:8px;margin-bottom:1rem}}.success{{background:#d5f5e3}}.error{{background:#fadbd8}}pre{{white-space:pre-wrap;max-height:420px;overflow:auto;background:#f7f7f7;padding:1rem;border-radius:8px}}code{{overflow-wrap:anywhere}}</style></head><body><header><h1>OpenScanStation Hardware</h1><div>Version {VERSION} · Port {PORT}</div><nav><a href="/">Übersicht</a><a href="/scanners">Scanner</a><a href="/printers">Drucker</a><a href="/diagnostics">Diagnose</a><a href="/drivers">Treiber</a><a href="http://localhost:8101">Hauptanwendung</a></nav></header><main>{note}{content}</main></body></html>'''


def _overview(notice: str = "", error: bool = False) -> str:
    data = inventory()
    cards = []
    for device in data["devices"]:
        caps = ", ".join(k for k, v in device.get("capabilities", {}).items() if v is True) or "–"
        cards.append(f'''<article class="card"><h2>{html.escape(device['name'])}</h2><p><span class="status {'ok' if device.get('online') else 'bad'}">{'Online' if device.get('online') else 'Offline'}</span></p><p><b>Typ:</b> {html.escape(device['kind'])}</p><p><b>Backend:</b> {html.escape(str(device.get('backend','-')))}</p><p><b>Verbindung:</b> <code>{html.escape(str(device.get('connection','-')))}</code></p><p><b>Funktionen:</b> {html.escape(caps)}</p></article>''')
    counts = data["counts"]
    content = f'''<div class="grid"><article class="card"><h2>Scanner</h2><div>{counts['scanner']}</div></article><article class="card"><h2>Drucker</h2><div>{counts['printer']}</div></article><article class="card"><h2>Online</h2><div>{counts['online']}</div></article><article class="card"><h2>Deaktiviert</h2><div>{counts['disabled']}</div></article></div><section class="panel"><form method="post" action="/refresh"><button>Hardware neu suchen</button></form></section><div class="grid">{''.join(cards) or '<p>Keine Hardware gefunden.</p>'}</div>'''
    return _layout(content, notice=notice, error=error)


def _scanners() -> str:
    devices = [d for d in inventory()["devices"] if d["kind"] == "scanner"]
    rows = ''.join(f"<tr><td>{html.escape(d['name'])}</td><td>{html.escape(d.get('manufacturer',''))}</td><td><code>{html.escape(d['connection'])}</code></td><td>{'Ja' if d['capabilities'].get('adf') else 'Nein'}</td><td>{'Ja' if d['capabilities'].get('duplex') else 'Nein'}</td><td>{'Ja' if d.get('default') else 'Nein'}</td></tr>" for d in devices) or '<tr><td colspan="6">Keine Scanner gefunden.</td></tr>'
    return _layout(f'<section class="panel"><h2>Scanner</h2><p>Scanner-Namen, Aktivierung und Standardgerät werden weiterhin in der Hauptanwendung verwaltet.</p><p><a href="http://localhost:8101/scanners">Scanner einrichten</a></p><table><tr><th>Name</th><th>Hersteller</th><th>Verbindung</th><th>ADF</th><th>Duplex</th><th>Standard</th></tr>{rows}</table></section>', "Scanner")


def _printers(notice: str = "", error: bool = False) -> str:
    devices = [d for d in inventory()["devices"] if d["kind"] == "printer"]
    settings = load_settings()
    options = ''.join(f'<option value="{html.escape(d["id"],quote=True)}" {"selected" if d.get("default") else ""}>{html.escape(d["name"])}</option>' for d in devices)
    rows = ''.join(f'''<tr><td>{html.escape(d['name'])}</td><td>{'Online' if d.get('online') else 'Offline'}</td><td>{'Ja' if d.get('default') else 'Nein'}</td><td>{'Ja' if d['capabilities'].get('duplex') else 'Nein'}</td><td>{'Ja' if d['capabilities'].get('color') else 'Unbekannt'}</td><td><form class="inline" method="post" action="/printer/test"><input type="hidden" name="printer" value="{html.escape(d['id'],quote=True)}"><button>Testseite</button></form></td></tr>''' for d in devices) or '<tr><td colspan="6">Keine CUPS-Drucker eingerichtet.</td></tr>'
    content = f'''<section class="panel"><h2>Drucker verwalten</h2><form method="post" action="/printer/default"><label>Standarddrucker<select name="printer"><option value="">CUPS-Standard verwenden</option>{options}</select></label><button>Speichern</button></form><p>CUPS-Verwaltung: <code>http://SERVER-IP:631</code></p></section><section class="panel"><table><tr><th>Name</th><th>Status</th><th>Standard</th><th>Duplex</th><th>Farbe</th><th>Aktion</th></tr>{rows}</table></section>'''
    return _layout(content, "Drucker", notice, error)


def _diagnostics() -> str:
    data = diagnostics()
    blocks = ''.join(f'<section class="panel"><h2>{html.escape(name)}</h2><span class="status {"ok" if result.get("ok", True) else "bad"}">{"OK" if result.get("ok", True) else "Fehler"}</span><pre>{html.escape(json.dumps(result,ensure_ascii=False,indent=2) if isinstance(result,dict) and "output" not in result else str(result.get("output","")))}</pre></section>' for name, result in data.items())
    return _layout(blocks, "Diagnose")


def _drivers() -> str:
    data = driver_status()
    rows = ''.join(f'<tr><td>{html.escape(name)}</td><td><span class="status {"ok" if available else "bad"}">{"Installiert" if available else "Fehlt"}</span></td></tr>' for name, available in data.items())
    return _layout(f'<section class="panel"><h2>Treiberstatus</h2><table><tr><th>Komponente</th><th>Status</th></tr>{rows}</table><p>Herstellertreiber werden aus Sicherheitsgründen nicht ungeprüft automatisch aus dem Internet installiert. OpenScanStation zeigt fehlende Komponenten an und nutzt bevorzugt Debian-Pakete.</p></section>', "Treiber")


class Handler(BaseHTTPRequestHandler):
    def _send(self, data, status=200, ctype="text/html; charset=utf-8"):
        body = data.encode() if isinstance(data, str) else data
        self.send_response(status); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.send_header("X-Frame-Options", "DENY"); self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/": self._send(_overview())
        elif path == "/scanners": self._send(_scanners())
        elif path == "/printers": self._send(_printers())
        elif path == "/diagnostics": self._send(_diagnostics())
        elif path == "/drivers": self._send(_drivers())
        elif path == "/health": self._send(json.dumps({"status":"ok","service":"openscanstation-hardware","version":VERSION,"port":PORT}), ctype="application/json")
        elif path == "/api/hardware": self._send(json.dumps(inventory(),ensure_ascii=False), ctype="application/json")
        elif path == "/api/diagnostics": self._send(json.dumps(diagnostics(),ensure_ascii=False), ctype="application/json")
        elif path == "/api/drivers": self._send(json.dumps(driver_status(),ensure_ascii=False), ctype="application/json")
        else: self._send(json.dumps({"error":"not_found"}),404,"application/json")

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0")); form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            if path == "/refresh": self._send(_overview("Hardware wurde neu eingelesen.")); return
            if path == "/printer/default":
                settings = load_settings(); settings["default_printer"] = form.get("printer", [""])[0]; save_settings(settings); self._send(_printers("Standarddrucker wurde gespeichert.")); return
            if path == "/printer/test":
                result = print_test_page(form.get("printer", [""])[0]); self._send(_printers(result["message"])); return
            self._send(json.dumps({"error":"not_found"}),404,"application/json")
        except Exception as exc:
            self._send(_printers(str(exc), True), HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args): print(fmt % args)


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--host", default=HOST); parser.add_argument("--port", type=int, default=PORT); args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host,args.port),Handler); print(f"Hardware-Zentrale auf {args.host}:{args.port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0


if __name__ == "__main__": raise SystemExit(main())
