"""Hardware-Zentrale für Scanner, Drucker, Netzwerk, USB und Wartung."""
from __future__ import annotations

import argparse
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from openscanstation.cli import VERSION
from openscanstation.hardware import (
    brother_assistant, cancel_print_job, diagnostics, driver_status,
    hardware_events, inventory, load_settings, network_discovery,
    print_test_page, tcp_probe, update_printer, usb_devices,
)
from openscanstation.hardware_actions import (
    add_ipp_printer, create_support_bundle, latest_support_bundle, test_scan,
)
from openscanstation.scanner_settings import (
    load_settings as load_scanner_settings, test_connection, update_scanner,
)

HOST = "127.0.0.1"
PORT = 8107
STYLE = """
body{font-family:system-ui;margin:0;background:#f3f6f9;color:#17202a}header{background:#17202a;color:#fff;padding:1.2rem 2rem}header a{color:#fff;text-decoration:none;margin-right:1rem}main{max-width:1450px;margin:1.4rem auto;padding:0 1rem}.panel,.card{background:#fff;padding:1.2rem;border-radius:14px;box-shadow:0 2px 14px #0001;margin-bottom:1rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1rem}.metric{font-size:2rem;font-weight:800}.status{display:inline-block;padding:.25rem .6rem;border-radius:999px;font-weight:700}.ok{background:#d5f5e3;color:#196f3d}.bad{background:#fadbd8;color:#922b21}.warn{background:#fcf3cf;color:#7d6608}.muted{color:#687684}.actions{display:flex;gap:.55rem;flex-wrap:wrap;align-items:center}a.button,button{display:inline-block;background:#17202a;color:#fff;padding:.7rem 1rem;border:0;border-radius:8px;text-decoration:none;font-weight:700;cursor:pointer}a.secondary,button.secondary{background:#e9eef3;color:#17202a}input,select{box-sizing:border-box;padding:.7rem;border:1px solid #bcc5cc;border-radius:8px;width:100%}form{display:grid;gap:.65rem}form.inline{display:inline-block}table{width:100%;border-collapse:collapse}th,td{padding:.7rem;border-bottom:1px solid #e1e5e8;text-align:left;vertical-align:top}pre{white-space:pre-wrap;overflow:auto;max-height:480px;background:#f6f7f8;padding:1rem;border-radius:8px}code{overflow-wrap:anywhere}.notice{padding:1rem;border-radius:9px;margin-bottom:1rem}.success{background:#d5f5e3}.error{background:#fadbd8}.step{border-left:4px solid #1769d2;padding-left:1rem}.hero{display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap}@media(max-width:700px){header{padding:1rem}main{padding:.5rem}table{display:block;overflow-x:auto}}
"""


def esc(value: object, attr: bool = False) -> str:
    return html.escape(str(value), quote=attr)


def layout(content: str, title: str = "Hardware", notice: str = "", error: bool = False) -> str:
    note = f'<div class="notice {"error" if error else "success"}">{esc(notice)}</div>' if notice else ""
    nav = '<a href="/">Übersicht</a><a href="/setup">Assistent</a><a href="/scanners">Scanner</a><a href="/printers">Drucker</a><a href="/network">Netzwerk</a><a href="/usb">USB</a><a href="/maintenance">Wartung</a><a href="/drivers">Treiber</a><a href="/diagnostics">Diagnose</a><a href="/support">Support</a>'
    return f'<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{STYLE}</style></head><body><header><h1>OpenScanStation Hardware</h1><div>Version {VERSION}</div><nav>{nav}</nav></header><main>{note}{content}</main></body></html>'


def badge(text: str, css: str) -> str:
    return f'<span class="status {css}">{esc(text)}</span>'


def device_card(device: dict) -> str:
    state = badge("Online", "ok") if device.get("online") else badge("Offline", "bad")
    default = badge("Standard", "ok") if device.get("default") else ""
    disabled = badge("Deaktiviert", "warn") if not device.get("enabled", True) else ""
    flags = " ".join(badge(str(k), "ok") for k, value in device.get("capabilities", {}).items() if value is True)
    href = f'/{device["kind"]}/{quote(str(device["id"]), safe="")}'
    return f'<article class="card"><div class="actions">{state}{default}{disabled}</div><h2>{esc(device["name"])}</h2><p><b>{esc(device["kind"].title())}</b> · {esc(device.get("manufacturer",""))} {esc(device.get("model",""))}</p><p><code>{esc(device.get("connection","-"))}</code></p><p>{flags or "Keine erweiterten Fähigkeiten gemeldet"}</p><a class="button" href="{href}">Gerät öffnen</a></article>'


def overview(notice: str = "", error: bool = False) -> str:
    data = inventory(); counts = data["counts"]; drivers = driver_status(); events = hardware_events(8)
    cards = "".join(device_card(d) for d in data["devices"]) or '<article class="card"><h2>Keine Geräte gefunden</h2><a class="button" href="/setup">Assistent öffnen</a></article>'
    event_rows = "".join(f'<tr><td>{esc(e.get("timestamp",""))}</td><td>{esc(e.get("type",""))}</td><td>{esc(e.get("message",""))}</td></tr>' for e in events) or '<tr><td colspan="3">Noch keine Ereignisse.</td></tr>'
    content = f'<section class="panel hero"><div><h2>Hardware-Dashboard</h2><p class="muted">Scanner, Drucker und Schnittstellen zentral verwalten.</p></div><div class="actions"><a class="button" href="/setup">Hardware hinzufügen</a><form class="inline" method="post" action="/refresh"><button class="secondary">Neu suchen</button></form></div></section><div class="metrics"><article class="card"><b>Scanner</b><div class="metric">{counts["scanner"]}</div></article><article class="card"><b>Drucker</b><div class="metric">{counts["printer"]}</div></article><article class="card"><b>Online</b><div class="metric">{counts["online"]}</div></article><article class="card"><b>Druckaufträge</b><div class="metric">{counts.get("print_jobs",0)}</div></article><article class="card"><b>Treiber bereit</b><div class="metric">{sum(1 for v in drivers.values() if v)}/{len(drivers)}</div></article></div><div class="grid">{cards}</div><section class="panel"><h2>Letzte Ereignisse</h2><table><tr><th>Zeit</th><th>Typ</th><th>Meldung</th></tr>{event_rows}</table></section>'
    return layout(content, notice=notice, error=error)


def setup_page(notice: str = "", error: bool = False) -> str:
    brother = brother_assistant(); network = network_discovery(); usb = usb_devices(); inv = inventory()
    brother_state = badge("Brother-Scanner erkannt", "ok") if brother["scanner_found"] else badge("Noch kein Brother-Scanner erkannt", "warn")
    network_rows = "".join(f'<tr><td>{esc(d.get("name",""))}</td><td>{esc(d.get("protocol",""))}</td><td><code>{esc(d.get("uri",""))}</code></td></tr>' for d in network[:15]) or '<tr><td colspan="3">Keine Netzwerkgeräte gefunden.</td></tr>'
    content = f'<section class="panel"><h2>Hardware-Assistent</h2><p>Der Assistent prüft Scanner, Drucker, Treiber, Netzwerk und USB.</p></section><div class="grid"><article class="card step"><h2>1. Erkennung</h2><p>{len(inv["devices"])} eingerichtete Geräte, {len(network)} Netzwerkfunde, {len(usb)} USB-Geräte.</p><form method="post" action="/refresh"><button>Erkennung wiederholen</button></form></article><article class="card step"><h2>2. Brother ADS-2600We</h2>{brother_state}<p>SANE: {"bereit" if brother["sane"] else "fehlt"} · AirScan: {"bereit" if brother["airscan"] else "fehlt"} · Brother-Treiber: {"vorhanden" if brother["driver"] else "nicht erkannt"}</p><a class="button" href="/brother">Brother-Assistent</a></article><article class="card step"><h2>3. IPP-Drucker hinzufügen</h2><form method="post" action="/printer/add"><label>Name<input name="name" required placeholder="Bürodrucker"></label><label>Geräte-URI<input name="uri" required placeholder="ipp://192.168.0.50/ipp/print"></label><button>Drucker einrichten</button></form></article></div><section class="panel"><h2>Gefundene Netzwerkgeräte</h2><table><tr><th>Name</th><th>Protokoll</th><th>Adresse</th></tr>{network_rows}</table></section>'
    return layout(content, "Hardware-Assistent", notice, error)


def scanners(notice: str = "", error: bool = False, result: dict | None = None) -> str:
    devices = [d for d in inventory()["devices"] if d["kind"] == "scanner"]; settings = load_scanner_settings(); blocks = []
    for d in devices:
        sid = d["id"]; alias = settings.get("aliases", {}).get(sid, ""); caps = d.get("capabilities", {})
        active_yes = "selected" if d.get("enabled") else ""; active_no = "selected" if not d.get("enabled") else ""; default_yes = "selected" if d.get("default") else ""
        blocks.append(f'<article class="card"><h2>{esc(d["name"])}</h2><p>{esc(d.get("manufacturer",""))} {esc(d.get("model",""))}</p><p><code>{esc(d.get("connection",""))}</code></p><p>ADF: {"Ja" if caps.get("adf") else "Nein"} · Duplex: {"Ja" if caps.get("duplex") else "Nein"}</p><form method="post" action="/scanner/save"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><label>Anzeigename<input name="alias" value="{esc(alias,True)}"></label><label>Aktiv<select name="enabled"><option value="1" {active_yes}>Ja</option><option value="0" {active_no}>Nein</option></select></label><label>Standard<select name="make_default"><option value="0">Nein</option><option value="1" {default_yes}>Ja</option></select></label><button>Speichern</button></form><div class="actions"><form class="inline" method="post" action="/scanner/test"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><button class="secondary">Verbindung testen</button></form><form class="inline" method="post" action="/scanner/test-scan"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><input type="hidden" name="resolution" value="100"><input type="hidden" name="mode" value="Gray"><button>Testscan</button></form><a class="button secondary" href="/scanner/{quote(sid,safe="")}">Details</a></div></article>')
    result_box = f'<section class="panel"><h2>Testergebnis</h2><pre>{esc(json.dumps(result,ensure_ascii=False,indent=2))}</pre></section>' if result else ""
    empty = '<article class="card"><h2>Kein Scanner gefunden</h2><a class="button" href="/setup">Assistent öffnen</a></article>'
    return layout(f'<section class="panel hero"><div><h2>Scanner</h2><p class="muted">Erkennen, benennen, testen und als Standard festlegen.</p></div><a class="button" href="/brother">Brother-Assistent</a></section>{result_box}<div class="grid">{"".join(blocks) or empty}</div>', "Scanner", notice, error)


def printers(notice: str = "", error: bool = False) -> str:
    devices = [d for d in inventory()["devices"] if d["kind"] == "printer"]; settings = load_settings(); blocks = []
    for d in devices:
        pid = d["id"]; alias = settings.get("printer_aliases", {}).get(pid, "")
        jobs = "".join(f'<li>{esc(j.get("raw",""))} <form class="inline" method="post" action="/printer/cancel"><input type="hidden" name="job" value="{esc(j.get("id",""),True)}"><button class="secondary">Abbrechen</button></form></li>' for j in d.get("jobs", [])) or '<li>Keine offenen Aufträge</li>'
        state = badge("Online", "ok") if d.get("online") else badge("Offline", "bad")
        active_yes = "selected" if d.get("enabled") else ""; active_no = "selected" if not d.get("enabled") else ""; default_yes = "selected" if d.get("default") else ""
        blocks.append(f'<article class="card"><h2>{esc(d["name"])}</h2>{state}<p><code>{esc(d.get("connection",""))}</code></p><form method="post" action="/printer/save"><input type="hidden" name="printer" value="{esc(pid,True)}"><label>Anzeigename<input name="alias" value="{esc(alias,True)}"></label><label>Aktiv<select name="enabled"><option value="1" {active_yes}>Ja</option><option value="0" {active_no}>Nein</option></select></label><label>Standard<select name="make_default"><option value="0">Nein</option><option value="1" {default_yes}>Ja</option></select></label><button>Speichern</button></form><div class="actions"><form class="inline" method="post" action="/printer/test"><input type="hidden" name="printer" value="{esc(pid,True)}"><button class="secondary">Testseite</button></form><a class="button secondary" href="/printer/{quote(pid,safe="")}">Details</a></div><details><summary>Druckaufträge</summary><ul>{jobs}</ul></details></article>')
    empty = '<article class="card"><h2>Kein Drucker eingerichtet</h2><p>Nutze den Hardware-Assistenten für einen IPP-Drucker.</p><a class="button" href="/setup">Assistent öffnen</a></article>'
    return layout(f'<section class="panel hero"><div><h2>Drucker</h2><p class="muted">CUPS-Drucker verwalten, testen und Warteschlangen bearbeiten.</p></div><a class="button" href="/setup">Drucker hinzufügen</a></section><div class="grid">{"".join(blocks) or empty}</div>', "Drucker", notice, error)


def detail(kind: str, device_id: str) -> str:
    device = next((x for x in inventory()["devices"] if x["kind"] == kind and x["id"] == device_id), None)
    if not device: return layout('<section class="panel"><h2>Gerät nicht gefunden</h2></section>', "Hardware", "Gerät nicht gefunden", True)
    rows = "".join(f'<tr><th>{esc(k)}</th><td><pre>{esc(json.dumps(v,ensure_ascii=False,indent=2) if isinstance(v,(dict,list)) else v)}</pre></td></tr>' for k, v in device.items())
    return layout(f'<section class="panel"><h2>{esc(device["name"])}</h2><table>{rows}</table></section>', device["name"])


def network_page(result: dict | None = None) -> str:
    devices = network_discovery(); rows = "".join(f'<tr><td>{esc(d.get("name",""))}</td><td>{esc(d.get("protocol",""))}</td><td><code>{esc(d.get("uri",""))}</code></td><td>{esc(d.get("model",""))}</td></tr>' for d in devices) or '<tr><td colspan="4">Keine Geräte gefunden.</td></tr>'
    probe = f'<section class="panel"><h2>Verbindungstest</h2><pre>{esc(json.dumps(result,ensure_ascii=False,indent=2))}</pre></section>' if result else ""
    return layout(f'<section class="panel"><h2>Netzwerkgeräte</h2><p>AirScan/eSCL, IPP, JetDirect, LPD und DNS-SD werden geprüft.</p><form method="post" action="/network/probe"><label>IP-Adresse oder Hostname<input name="host" required placeholder="192.168.0.25"></label><button>Ports prüfen</button></form></section>{probe}<section class="panel"><table><tr><th>Name</th><th>Typ</th><th>Adresse</th><th>Modell</th></tr>{rows}</table></section>', "Netzwerkgeräte")


def usb_page() -> str:
    rows = "".join(f'<tr><td>{esc(d["bus"])}</td><td>{esc(d["device"])}</td><td><code>{esc(d["id"])}</code></td><td>{esc(d["description"])}</td></tr>' for d in usb_devices()) or '<tr><td colspan="4">Keine USB-Geräte erkannt.</td></tr>'
    return layout(f'<section class="panel"><h2>USB-Geräte</h2><table><tr><th>Bus</th><th>Gerät</th><th>USB-ID</th><th>Beschreibung</th></tr>{rows}</table></section>', "USB-Geräte")


def brother_page() -> str:
    data = brother_assistant(); scanner_cards = "".join(device_card(d) for d in data["scanners"]) or '<p>Kein Brother-Scanner in SANE erkannt.</p>'
    air = "".join(f'<li>{esc(d.get("name",""))}: <code>{esc(d.get("uri",""))}</code></li>' for d in data["airscan_devices"]) or '<li>Kein Brother-AirScan-Gerät gefunden.</li>'
    recommendations = "".join(f'<li>{esc(x)}</li>' for x in data["recommendations"])
    states = badge("SANE", "ok" if data["sane"] else "bad") + badge("AirScan", "ok" if data["airscan"] else "bad") + badge("Brother-Treiber", "ok" if data["driver"] else "warn")
    return layout(f'<section class="panel"><h2>Brother ADS-2600We Assistent</h2><div class="actions">{states}</div><ol>{recommendations}</ol></section><div class="grid">{scanner_cards}</div><section class="panel"><h2>AirScan-Funde</h2><ul>{air}</ul><p>Beim ADS-2600We ist die treiberlose Netzwerkverbindung über AirScan/eSCL normalerweise die bevorzugte Variante.</p></section>', "Brother-Assistent")


def maintenance() -> str:
    rows = "".join(f'<tr><td>{esc(d["name"])}</td><td>{esc(d["kind"])}</td><td>{"Online" if d.get("online") else "Offline"}</td><td>{"Test durchführen und Zähler am Gerät prüfen" if d.get("online") else "Stromversorgung, Netzwerk und Treiber prüfen"}</td></tr>' for d in inventory()["devices"]) or '<tr><td colspan="4">Keine Geräte.</td></tr>'
    return layout(f'<section class="panel"><h2>Wartung</h2><p>Herstellerabhängige Rollen-, Seiten-, Toner- und Trommelzähler werden angezeigt, sobald das Geräteprotokoll sie bereitstellt.</p><table><tr><th>Gerät</th><th>Typ</th><th>Status</th><th>Empfehlung</th></tr>{rows}</table></section><div class="grid"><article class="card"><h2>Scannerpflege</h2><p>Einzugsrollen und Glas reinigen, Papierpfad kontrollieren und Doppelblatteinzug testen.</p></article><article class="card"><h2>Druckerpflege</h2><p>Papier, Toner, Trommel und CUPS-Warteschlange kontrollieren.</p></article></div>', "Wartung")


def drivers_page() -> str:
    rows = "".join(f'<tr><td>{esc(k)}</td><td>{badge("Bereit","ok") if v else badge("Fehlt","bad")}</td></tr>' for k, v in driver_status().items())
    return layout(f'<section class="panel"><h2>Treiber und Werkzeuge</h2><table><tr><th>Komponente</th><th>Status</th></tr>{rows}</table></section>', "Treiber")


def diagnostics_page() -> str:
    blocks = "".join(f'<section class="panel"><h2>{esc(k)}</h2>{badge("OK","ok") if v.get("ok",True) else badge("Fehler","bad")}<pre>{esc(json.dumps(v,ensure_ascii=False,indent=2))}</pre></section>' for k, v in diagnostics().items())
    return layout(blocks, "Diagnose")


def support_page(notice: str = "", error: bool = False) -> str:
    latest = latest_support_bundle()
    download = f'<a class="button secondary" href="/support/download">Letztes Supportpaket herunterladen</a><p class="muted">{esc(latest.name)} · {latest.stat().st_size} Byte</p>' if latest else '<p>Noch kein Supportpaket vorhanden.</p>'
    content = f'<section class="panel"><h2>Support und Diagnoseexport</h2><p>Das Paket enthält Hardwareinventar, Diagnoseausgaben, CUPS-/SANE-Status und relevante Dienstprotokolle. Es enthält keine Dokumente oder Scanbilder.</p><form method="post" action="/support/create"><button>Supportpaket erstellen</button></form>{download}</section>'
    return layout(content, "Support", notice, error)


class Handler(BaseHTTPRequestHandler):
    def send(self, data: str | bytes, status: int = 200, ctype: str = "text/html; charset=utf-8", disposition: str = "") -> None:
        body = data.encode() if isinstance(data, str) else data
        self.send_response(status); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.send_header("X-Content-Type-Options", "nosniff")
        if disposition: self.send_header("Content-Disposition", disposition)
        self.end_headers(); self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        routes = {"/": overview, "/setup": setup_page, "/scanners": scanners, "/printers": printers, "/network": network_page, "/usb": usb_page, "/brother": brother_page, "/maintenance": maintenance, "/drivers": drivers_page, "/diagnostics": diagnostics_page, "/support": support_page}
        if path in routes: self.send(routes[path]())
        elif path == "/support/download":
            bundle = latest_support_bundle()
            if not bundle: self.send(support_page("Noch kein Supportpaket vorhanden.", True), 404); return
            self.send(bundle.read_bytes(), ctype="application/gzip", disposition=f'attachment; filename="{bundle.name}"')
        elif path.startswith("/scanner/"): self.send(detail("scanner", unquote(path.split("/", 2)[2])))
        elif path.startswith("/printer/"): self.send(detail("printer", unquote(path.split("/", 2)[2])))
        elif path == "/health": self.send(json.dumps({"status":"ok","service":"openscanstation-hardware","version":VERSION}), ctype="application/json")
        elif path == "/api/hardware": self.send(json.dumps(inventory(), ensure_ascii=False), ctype="application/json")
        elif path == "/api/network": self.send(json.dumps(network_discovery(), ensure_ascii=False), ctype="application/json")
        elif path == "/api/usb": self.send(json.dumps(usb_devices(), ensure_ascii=False), ctype="application/json")
        elif path == "/api/drivers": self.send(json.dumps(driver_status(), ensure_ascii=False), ctype="application/json")
        else: self.send(json.dumps({"error":"not_found"}), 404, "application/json")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0")); form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
            if path == "/refresh": self.send(overview("Hardware wurde neu eingelesen.")); return
            if path == "/scanner/save":
                update_scanner(form.get("scanner_id", [""])[0], alias=form.get("alias", [""])[0], enabled=form.get("enabled", ["0"])[0] == "1", make_default=form.get("make_default", ["0"])[0] == "1"); self.send(scanners("Scanner gespeichert.")); return
            if path == "/scanner/test":
                data = inventory(); result = test_connection(form.get("scanner_id", [""])[0], [d for d in data["devices"] if d["kind"] == "scanner"]); self.send(scanners("Verbindungstest abgeschlossen.", not result.get("ok", False), result)); return
            if path == "/scanner/test-scan":
                result = test_scan(form.get("scanner_id", [""])[0], resolution=int(form.get("resolution", ["100"])[0]), mode=form.get("mode", ["Gray"])[0]); self.send(scanners(result["message"], False, result)); return
            if path == "/printer/add":
                result = add_ipp_printer(form.get("name", [""])[0], form.get("uri", [""])[0]); self.send(setup_page(result["message"])); return
            if path == "/printer/save":
                update_printer(form.get("printer", [""])[0], alias=form.get("alias", [""])[0], enabled=form.get("enabled", ["0"])[0] == "1", make_default=form.get("make_default", ["0"])[0] == "1"); self.send(printers("Drucker gespeichert.")); return
            if path == "/printer/test": self.send(printers(print_test_page(form.get("printer", [""])[0])["message"])); return
            if path == "/printer/cancel": self.send(printers(cancel_print_job(form.get("job", [""])[0])["message"])); return
            if path == "/network/probe": self.send(network_page(tcp_probe(form.get("host", [""])[0]))); return
            if path == "/support/create":
                result = create_support_bundle(); self.send(support_page(result["message"])); return
            self.send(json.dumps({"error":"not_found"}), 404, "application/json")
        except Exception as exc:
            self.send(layout('<section class="panel"><h2>Aktion fehlgeschlagen</h2></section>', "Hardware", str(exc), True), HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args) -> None:
        print(fmt % args)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--host", default=HOST); parser.add_argument("--port", type=int, default=PORT); args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host,args.port),Handler); print(f"Hardware-Zentrale auf {args.host}:{args.port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0


if __name__ == "__main__": raise SystemExit(main())
