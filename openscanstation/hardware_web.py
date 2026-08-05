"""Hardware-Zentrale für Scanner, Drucker, Diagnose, Treiber und Wartung."""
from __future__ import annotations

import argparse
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

from openscanstation.cli import VERSION
from openscanstation.hardware import (
    diagnostics,
    driver_status,
    hardware_events,
    inventory,
    load_settings,
    print_test_page,
    save_settings,
    update_printer,
)
from openscanstation.scanner_settings import (
    load_settings as load_scanner_settings,
    test_connection,
    update_scanner,
)

HOST = "0.0.0.0"
PORT = 8107


def _layout(content: str, title: str = "Hardware", notice: str = "", error: bool = False) -> str:
    note = f'<div class="notice {"error" if error else "success"}">{html.escape(notice)}</div>' if notice else ""
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>
body{{font-family:system-ui;margin:0;background:#f3f5f7;color:#17202a}}header{{background:#17202a;color:#fff;padding:1.2rem 2rem}}header a{{color:#fff;text-decoration:none;margin-right:1rem}}main{{max-width:1380px;margin:1.5rem auto;padding:0 1rem}}.panel,.card{{background:#fff;padding:1.2rem;border-radius:12px;box-shadow:0 2px 12px #0001;margin-bottom:1rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem}}.status{{display:inline-block;padding:.25rem .55rem;border-radius:999px;font-weight:700}}.ok{{background:#d5f5e3;color:#196f3d}}.bad{{background:#fadbd8;color:#922b21}}.muted{{color:#687684}}.metric{{font-size:2rem;font-weight:800}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.65rem;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}}button,input,select{{box-sizing:border-box;padding:.7rem;border:1px solid #bcc5cc;border-radius:8px;max-width:100%}}button{{background:#17202a;color:#fff;font-weight:700;cursor:pointer}}form{{display:grid;gap:.7rem}}.inline{{display:inline-block;margin-right:.4rem}}.button-row{{display:flex;gap:.5rem;flex-wrap:wrap}}.notice{{padding:1rem;border-radius:8px;margin-bottom:1rem}}.success{{background:#d5f5e3}}.error{{background:#fadbd8}}pre{{white-space:pre-wrap;max-height:420px;overflow:auto;background:#f7f7f7;padding:1rem;border-radius:8px}}code{{overflow-wrap:anywhere}}details summary{{cursor:pointer;font-weight:700}}</style></head><body><header><h1>OpenScanStation Hardware</h1><div>Version {VERSION}</div><nav><a href="/">Übersicht</a><a href="/scanners">Scanner</a><a href="/printers">Drucker</a><a href="/maintenance">Wartung</a><a href="/diagnostics">Diagnose</a><a href="/drivers">Treiber</a></nav></header><main>{note}{content}</main></body></html>'''


def _device_card(device: dict) -> str:
    caps = device.get("capabilities", {})
    positive = [name for name, value in caps.items() if value is True]
    details = ", ".join(positive) or "Keine zusätzlichen Fähigkeiten erkannt"
    detail_url = f'/{device["kind"]}/{quote(str(device["id"]), safe="")}'
    return f'''<article class="card"><div class="button-row"><span class="status {'ok' if device.get('online') else 'bad'}">{'Online' if device.get('online') else 'Offline'}</span>{'<span class="status ok">Standard</span>' if device.get('default') else ''}{'<span class="status bad">Deaktiviert</span>' if not device.get('enabled', True) else ''}</div><h2>{html.escape(device['name'])}</h2><p><b>Typ:</b> {html.escape(device['kind'].title())}</p><p><b>Backend:</b> {html.escape(str(device.get('backend','-')))}</p><p><b>Verbindung:</b> <code>{html.escape(str(device.get('connection','-')))}</code></p><p><b>Funktionen:</b> {html.escape(details)}</p><p><a href="{detail_url}">Details und Einstellungen öffnen</a></p></article>'''


def _overview(notice: str = "", error: bool = False) -> str:
    data = inventory()
    counts = data["counts"]
    events = hardware_events(10)
    event_rows = ''.join(f'<tr><td>{html.escape(e.get("timestamp",""))}</td><td>{html.escape(e.get("type",""))}</td><td>{html.escape(e.get("device_id",""))}</td><td>{html.escape(e.get("message",""))}</td></tr>' for e in events) or '<tr><td colspan="4">Noch keine Hardware-Ereignisse.</td></tr>'
    cards = ''.join(_device_card(device) for device in data["devices"]) or '<article class="card"><h2>Keine Hardware gefunden</h2><p>Öffne die Diagnose oder starte eine neue Suche.</p></article>'
    content = f'''<div class="grid"><article class="card"><h2>Scanner</h2><div class="metric">{counts['scanner']}</div></article><article class="card"><h2>Drucker</h2><div class="metric">{counts['printer']}</div></article><article class="card"><h2>Online</h2><div class="metric">{counts['online']}</div></article><article class="card"><h2>Druckaufträge</h2><div class="metric">{counts.get('print_jobs',0)}</div></article></div><section class="panel"><div class="button-row"><form method="post" action="/refresh"><button>Hardware neu suchen</button></form><a href="/diagnostics">Diagnose öffnen</a><a href="/drivers">Treiber prüfen</a></div><p class="muted">Letzte Aktualisierung: {html.escape(data['updated_at'])}</p></section><div class="grid">{cards}</div><section class="panel"><h2>Letzte Hardware-Ereignisse</h2><table><tr><th>Zeit</th><th>Typ</th><th>Gerät</th><th>Meldung</th></tr>{event_rows}</table></section>'''
    return _layout(content, notice=notice, error=error)


def _scanner_form(device: dict) -> str:
    settings = load_scanner_settings()
    alias = settings.get("aliases", {}).get(device["id"], "")
    return f'''<article class="card"><h2>{html.escape(device['name'])}</h2><p><b>Hersteller/Modell:</b> {html.escape(str(device.get('manufacturer','')))} {html.escape(str(device.get('model','')))}</p><p><b>Verbindung:</b> <code>{html.escape(str(device['connection']))}</code></p><p><b>ADF:</b> {'Ja' if device['capabilities'].get('adf') else 'Nein'} · <b>Duplex:</b> {'Ja' if device['capabilities'].get('duplex') else 'Nein'}</p><form method="post" action="/scanner/save"><input type="hidden" name="scanner_id" value="{html.escape(device['id'],quote=True)}"><label>Anzeigename<input name="alias" maxlength="80" value="{html.escape(alias,quote=True)}" placeholder="Eigener Scannername"></label><label>Aktiv<select name="enabled"><option value="1" {'selected' if device.get('enabled') else ''}>Ja</option><option value="0" {'selected' if not device.get('enabled') else ''}>Nein</option></select></label><label>Standardscanner<select name="make_default"><option value="0">Nein</option><option value="1" {'selected' if device.get('default') else ''}>Ja</option></select></label><button>Scanner speichern</button></form><form method="post" action="/scanner/test"><input type="hidden" name="scanner_id" value="{html.escape(device['id'],quote=True)}"><button>Verbindung testen</button></form></article>'''


def _scanners(notice: str = "", error: bool = False, test_result: dict | None = None) -> str:
    devices = [d for d in inventory()["devices"] if d["kind"] == "scanner"]
    result = f'<section class="panel"><h2>Testergebnis</h2><pre>{html.escape(json.dumps(test_result,ensure_ascii=False,indent=2))}</pre></section>' if test_result else ''
    content = f'''<section class="panel"><h2>Scanner verwalten</h2><p>Scanner benennen, aktivieren, als Standard festlegen und direkt testen.</p><form method="post" action="/refresh"><button>Scanner neu suchen</button></form></section>{result}<div class="grid">{''.join(_scanner_form(d) for d in devices) or '<article class="card"><h2>Keine Scanner gefunden</h2><p>Prüfe SANE, AirScan, USB und Netzwerk.</p></article>'}</div>'''
    return _layout(content, "Scanner", notice, error)


def _printer_form(device: dict) -> str:
    settings = load_settings()
    alias = settings.get("printer_aliases", {}).get(device["id"], "")
    caps = device.get("capabilities", {})
    jobs = ''.join(f'<li>{html.escape(j.get("raw",""))}</li>' for j in device.get("jobs", [])) or '<li>Keine offenen Aufträge</li>'
    return f'''<article class="card"><h2>{html.escape(device['name'])}</h2><p><span class="status {'ok' if device.get('online') else 'bad'}">{'Online' if device.get('online') else 'Offline'}</span></p><p><b>CUPS-Name:</b> <code>{html.escape(device['id'])}</code></p><p><b>Verbindung:</b> <code>{html.escape(str(device.get('connection','')))}</code></p><p><b>Duplex:</b> {'Ja' if caps.get('duplex') else 'Nein'} · <b>Farbe:</b> {'Ja' if caps.get('color') else 'Unbekannt'} · <b>Heften:</b> {'Ja' if caps.get('staple') else 'Nein'}</p><form method="post" action="/printer/save"><input type="hidden" name="printer" value="{html.escape(device['id'],quote=True)}"><label>Anzeigename<input name="alias" maxlength="80" value="{html.escape(alias,quote=True)}"></label><label>Aktiv<select name="enabled"><option value="1" {'selected' if device.get('enabled') else ''}>Ja</option><option value="0" {'selected' if not device.get('enabled') else ''}>Nein</option></select></label><label>Standarddrucker<select name="make_default"><option value="0">Nein</option><option value="1" {'selected' if device.get('default') else ''}>Ja</option></select></label><button>Drucker speichern</button></form><form method="post" action="/printer/test"><input type="hidden" name="printer" value="{html.escape(device['id'],quote=True)}"><button>Testseite drucken</button></form><details><summary>Offene Druckaufträge</summary><ul>{jobs}</ul></details></article>'''


def _printers(notice: str = "", error: bool = False) -> str:
    devices = [d for d in inventory()["devices"] if d["kind"] == "printer"]
    content = f'''<section class="panel"><h2>Drucker verwalten</h2><p>CUPS-Drucker benennen, aktivieren, als Standard setzen und testen.</p><p class="muted">Neue Drucker werden weiterhin über CUPS oder die Debian-Systemverwaltung hinzugefügt.</p></section><div class="grid">{''.join(_printer_form(d) for d in devices) or '<article class="card"><h2>Keine Drucker eingerichtet</h2><p>Richte zuerst einen CUPS-Drucker ein.</p></article>'}</div>'''
    return _layout(content, "Drucker", notice, error)


def _device_detail(kind: str, device_id: str) -> str:
    device = next((d for d in inventory()["devices"] if d["kind"] == kind and d["id"] == device_id), None)
    if not device:
        return _layout('<section class="panel"><h2>Gerät nicht gefunden</h2></section>', "Hardware", "Gerät wurde nicht gefunden.", True)
    caps = html.escape(json.dumps(device.get("capabilities", {}), ensure_ascii=False, indent=2))
    content = f'''<section class="panel"><h2>{html.escape(device['name'])}</h2><p><span class="status {'ok' if device.get('online') else 'bad'}">{'Online' if device.get('online') else 'Offline'}</span></p><table><tr><th>Typ</th><td>{html.escape(kind)}</td></tr><tr><th>Hersteller</th><td>{html.escape(str(device.get('manufacturer','-')))}</td></tr><tr><th>Modell</th><td>{html.escape(str(device.get('model','-')))}</td></tr><tr><th>Backend</th><td>{html.escape(str(device.get('backend','-')))}</td></tr><tr><th>Verbindung</th><td><code>{html.escape(str(device.get('connection','-')))}</code></td></tr><tr><th>Aktiv</th><td>{'Ja' if device.get('enabled') else 'Nein'}</td></tr><tr><th>Standard</th><td>{'Ja' if device.get('default') else 'Nein'}</td></tr></table></section><section class="panel"><h2>Fähigkeiten</h2><pre>{caps}</pre></section>'''
    return _layout(content, device["name"])


def _maintenance() -> str:
    data = inventory()
    rows = ''.join(f'<tr><td>{html.escape(d["name"])}</td><td>{html.escape(d["kind"])}</td><td>{"Online" if d.get("online") else "Offline"}</td><td>{"Gerät betriebsbereit" if d.get("online") else "Verbindung und Stromversorgung prüfen"}</td></tr>' for d in data["devices"]) or '<tr><td colspan="4">Keine Geräte gefunden.</td></tr>'
    content = f'''<section class="panel"><h2>Wartung</h2><p>Diese Übersicht bündelt Wartungs- und Funktionshinweise. Herstellerabhängige Seiten-, Rollen-, Toner- oder Trommelzähler werden ergänzt, sobald das jeweilige Plugin oder IPP sie liefert.</p></section><section class="panel"><table><tr><th>Gerät</th><th>Typ</th><th>Status</th><th>Empfehlung</th></tr>{rows}</table></section><div class="grid"><article class="card"><h2>Scanner</h2><p>Einzugsrollen reinigen, Papierpfad prüfen und bei Doppelblatteinzug die Ultraschallerkennung testen.</p></article><article class="card"><h2>Drucker</h2><p>CUPS-Warteschlange, Verbrauchsmaterial und Papierfächer prüfen. Gerätespezifische Werte hängen vom IPP-/SNMP-Support ab.</p></article></div>'''
    return _layout(content, "Wartung")


def _diagnostics() -> str:
    data = diagnostics()
    blocks = ''.join(f'<section class="panel"><h2>{html.escape(name)}</h2><span class="status {"ok" if result.get("ok", True) else "bad"}">{"OK" if result.get("ok", True) else "Fehler"}</span><pre>{html.escape(json.dumps(result,ensure_ascii=False,indent=2) if isinstance(result,dict) and "output" not in result else str(result.get("output","")))}</pre></section>' for name, result in data.items())
    return _layout(blocks, "Diagnose")


def _drivers() -> str:
    data = driver_status()
    labels = {"sane":"SANE Scannerbasis", "airscan":"AirScan/eSCL", "cups":"CUPS-Drucksystem", "brother":"Brother-SANE-Treiber", "barcode":"Barcode/QR", "ocr":"OCR"}
    rows = ''.join(f'<tr><td>{html.escape(labels.get(name,name))}</td><td><span class="status {"ok" if available else "bad"}">{"Installiert" if available else "Fehlt"}</span></td><td>{"Bereit" if available else "Debian-Paket oder Herstellertreiber prüfen"}</td></tr>' for name, available in data.items())
    return _layout(f'<section class="panel"><h2>Treiberstatus</h2><table><tr><th>Komponente</th><th>Status</th><th>Hinweis</th></tr>{rows}</table><p>OpenScanStation installiert keine ungeprüften Herstellerpakete automatisch. Bevorzugt werden signierte Debian-Pakete und standardisierte Protokolle wie AirScan und IPP.</p></section>', "Treiber")


class Handler(BaseHTTPRequestHandler):
    def _send(self, data, status=200, ctype="text/html; charset=utf-8"):
        body = data.encode() if isinstance(data, str) else data
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/": self._send(_overview())
        elif path == "/scanners": self._send(_scanners())
        elif path == "/printers": self._send(_printers())
        elif path == "/maintenance": self._send(_maintenance())
        elif path == "/diagnostics": self._send(_diagnostics())
        elif path == "/drivers": self._send(_drivers())
        elif path.startswith("/scanner/"): self._send(_device_detail("scanner", unquote(path[len('/scanner/'):])))
        elif path.startswith("/printer/"): self._send(_device_detail("printer", unquote(path[len('/printer/'):])))
        elif path == "/health": self._send(json.dumps({"status":"ok","service":"openscanstation-hardware","version":VERSION,"port":PORT}), ctype="application/json")
        elif path == "/api/hardware": self._send(json.dumps(inventory(),ensure_ascii=False), ctype="application/json")
        elif path == "/api/diagnostics": self._send(json.dumps(diagnostics(),ensure_ascii=False), ctype="application/json")
        elif path == "/api/drivers": self._send(json.dumps(driver_status(),ensure_ascii=False), ctype="application/json")
        elif path == "/api/events": self._send(json.dumps(hardware_events(),ensure_ascii=False), ctype="application/json")
        else: self._send(json.dumps({"error":"not_found"}),404,"application/json")

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
        try:
            if path == "/refresh": self._send(_overview("Hardware wurde neu eingelesen.")); return
            if path == "/scanner/save":
                update_scanner(form.get("scanner_id",[""])[0], alias=form.get("alias",[""])[0], enabled=form.get("enabled",["0"])[0] == "1", make_default=form.get("make_default",["0"])[0] == "1")
                self._send(_scanners("Scanner wurde gespeichert.")); return
            if path == "/scanner/test":
                scanners = [d for d in inventory()["devices"] if d["kind"] == "scanner"]
                result = test_connection(form.get("scanner_id",[""])[0], scanners)
                self._send(_scanners("Verbindungstest abgeschlossen.", not result.get("ok", False), result)); return
            if path == "/printer/save":
                update_printer(form.get("printer",[""])[0], alias=form.get("alias",[""])[0], enabled=form.get("enabled",["0"])[0] == "1", make_default=form.get("make_default",["0"])[0] == "1")
                self._send(_printers("Drucker wurde gespeichert.")); return
            if path == "/printer/default":
                settings = load_settings(); settings["default_printer"] = form.get("printer", [""])[0]; save_settings(settings); self._send(_printers("Standarddrucker wurde gespeichert.")); return
            if path == "/printer/test":
                result = print_test_page(form.get("printer", [""])[0]); self._send(_printers(result["message"])); return
            self._send(json.dumps({"error":"not_found"}),404,"application/json")
        except Exception as exc:
            page = _scanners(str(exc), True) if path.startswith("/scanner/") else _printers(str(exc), True)
            self._send(page, HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args):
        print(fmt % args)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host,args.port),Handler)
    print(f"Hardware-Zentrale auf {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
