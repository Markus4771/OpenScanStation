"""Umfassende Hardware-Zentrale für OpenScanStation."""
from __future__ import annotations

import argparse
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

from openscanstation.cli import VERSION
from openscanstation.hardware import (
    brother_assistant, cancel_print_job, diagnostics, driver_status,
    inventory, load_settings, network_discovery, print_test_page,
    tcp_probe, update_printer, usb_devices,
)
from openscanstation.hardware_actions import (
    add_ipp_printer, create_support_bundle, latest_support_bundle,
    test_scan, test_scan_history,
)
from openscanstation.hardware_management import (
    add_manual_scanner, complete_maintenance, delete_manual_scanner,
    delete_profile, load_profiles, maintenance_items, manual_scanners,
    monitor_snapshot, save_maintenance, save_profile,
)
from openscanstation.scanner_settings import (
    load_settings as load_scanner_settings, test_connection, update_scanner,
)

HOST = "127.0.0.1"
PORT = 8107
STYLE = """
body{font-family:system-ui;margin:0;background:#f3f6f9;color:#17202a}header{background:#17202a;color:#fff;padding:1.1rem 1.5rem}header h1{margin:.1rem 0}.topnav{display:flex;gap:.45rem;flex-wrap:wrap;margin-top:.8rem}.topnav a{color:#fff;text-decoration:none;padding:.45rem .65rem;border-radius:7px}.topnav a:hover{background:#ffffff22}main{max-width:1500px;margin:1.3rem auto;padding:0 1rem}.panel,.card{background:#fff;padding:1.15rem;border-radius:14px;box-shadow:0 2px 14px #0001;margin-bottom:1rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem}.metric{font-size:2rem;font-weight:800}.status{display:inline-block;padding:.25rem .6rem;border-radius:999px;font-weight:700}.ok{background:#d5f5e3;color:#196f3d}.bad{background:#fadbd8;color:#922b21}.warn{background:#fcf3cf;color:#7d6608}.muted{color:#687684}.actions{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}.hero{display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap}a.button,button{display:inline-block;background:#17202a;color:#fff;padding:.68rem .95rem;border:0;border-radius:8px;text-decoration:none;font-weight:700;cursor:pointer}a.secondary,button.secondary{background:#e9eef3;color:#17202a}button.danger{background:#922b21}input,select{box-sizing:border-box;padding:.65rem;border:1px solid #bcc5cc;border-radius:8px;width:100%}label{display:grid;gap:.25rem}form{display:grid;gap:.6rem}form.inline{display:inline-block}table{width:100%;border-collapse:collapse}th,td{padding:.65rem;border-bottom:1px solid #e1e5e8;text-align:left;vertical-align:top}pre{white-space:pre-wrap;overflow:auto;max-height:420px;background:#f6f7f8;padding:1rem;border-radius:8px}code{overflow-wrap:anywhere}.notice{padding:1rem;border-radius:9px;margin-bottom:1rem}.success{background:#d5f5e3}.error{background:#fadbd8}.preview{max-width:320px;max-height:240px;border:1px solid #ddd;border-radius:8px}.due{border-left:5px solid #922b21}.soon{border-left:5px solid #b7950b}@media(max-width:700px){header{padding:1rem}main{padding:.5rem}table{display:block;overflow-x:auto}}
"""


def esc(value: object, attr: bool = False) -> str:
    return html.escape(str(value), quote=attr)


def badge(text: str, css: str) -> str:
    return f'<span class="status {css}">{esc(text)}</span>'


def layout(content: str, title: str = "Hardware", notice: str = "", error: bool = False) -> str:
    note = f'<div class="notice {"error" if error else "success"}">{esc(notice)}</div>' if notice else ""
    nav = "".join(f'<a href="{href}">{label}</a>' for href, label in [
        ("/", "Übersicht"), ("/monitor", "Monitor"), ("/setup", "Assistent"),
        ("/scanners", "Scanner"), ("/profiles", "Scanprofile"), ("/printers", "Drucker"),
        ("/network", "Netzwerk"), ("/usb", "USB"), ("/brother", "Brother"),
        ("/maintenance", "Wartung"), ("/drivers", "Treiber"),
        ("/diagnostics", "Diagnose"), ("/support", "Support"),
    ])
    return f'<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{STYLE}</style></head><body><header><h1>OpenScanStation Hardware</h1><div>Version {VERSION}</div><nav class="topnav">{nav}</nav></header><main>{note}{content}</main></body></html>'


def device_card(device: dict) -> str:
    state = badge("Online", "ok") if device.get("online") else badge("Offline", "bad")
    default = badge("Standard", "ok") if device.get("default") else ""
    disabled = badge("Deaktiviert", "warn") if not device.get("enabled", True) else ""
    href = f'/{device["kind"]}/{quote(str(device["id"]), safe="")}'
    return f'<article class="card"><div class="actions">{state}{default}{disabled}</div><h2>{esc(device["name"])}</h2><p>{esc(device.get("manufacturer",""))} {esc(device.get("model",""))}</p><p><code>{esc(device.get("connection","-"))}</code></p><a class="button" href="{href}">Gerät öffnen</a></article>'


def overview(notice: str = "", error: bool = False) -> str:
    data = inventory(); counts = data["counts"]; drivers = driver_status()
    cards = "".join(device_card(d) for d in data["devices"]) or '<article class="card"><h2>Keine Geräte gefunden</h2><a class="button" href="/setup">Assistent öffnen</a></article>'
    content = f'<section class="panel hero"><div><h2>Hardware-Dashboard</h2><p class="muted">Zentrale Geräteverwaltung und Betriebsübersicht.</p></div><div class="actions"><a class="button" href="/setup">Hardware hinzufügen</a><a class="button secondary" href="/monitor">Live-Monitor</a></div></section><div class="metrics"><article class="card"><b>Scanner</b><div class="metric">{counts["scanner"]}</div></article><article class="card"><b>Drucker</b><div class="metric">{counts["printer"]}</div></article><article class="card"><b>Online</b><div class="metric">{counts["online"]}</div></article><article class="card"><b>Druckaufträge</b><div class="metric">{counts.get("print_jobs",0)}</div></article><article class="card"><b>Treiber</b><div class="metric">{sum(1 for v in drivers.values() if v)}/{len(drivers)}</div></article><article class="card"><b>Profile</b><div class="metric">{len(load_profiles())}</div></article></div><div class="grid">{cards}</div>'
    return layout(content, notice=notice, error=error)


def monitor_page() -> str:
    snap = monitor_snapshot()
    rows = "".join(f'<tr><td>{esc(d.get("name"))}</td><td>{esc(d.get("kind"))}</td><td>{badge("Online","ok") if d.get("online") else badge("Offline","bad")}</td><td>{esc(d.get("last_test") or "-")}</td><td>{badge("OK","ok") if d.get("last_test_ok") is True else badge("Fehler","bad") if d.get("last_test_ok") is False else badge("Nicht getestet","warn")}</td></tr>' for d in snap["devices"]) or '<tr><td colspan="5">Keine Geräte.</td></tr>'
    manual = "".join(f'<tr><td>{esc(d.get("name"))}</td><td><code>{esc(d.get("uri"))}</code></td><td>{badge("Erreichbar","ok") if d.get("online") else badge("Nicht erreichbar","bad")}</td></tr>' for d in snap["manual_scanners"]) or '<tr><td colspan="3">Keine manuellen Scanner.</td></tr>'
    history = "".join(f'<tr><td>{esc(x.get("created_at",""))}</td><td>{esc(x.get("scanner",""))}</td><td>{esc(x.get("resolution",""))} dpi</td><td>{esc(x.get("mode",""))}</td></tr>' for x in snap["recent_tests"]) or '<tr><td colspan="4">Noch keine Testscans.</td></tr>'
    return layout(f'<section class="panel hero"><div><h2>Hardware-Monitor</h2><p class="muted">Stand: {esc(snap["updated_at"])}</p></div><a class="button" href="/monitor">Aktualisieren</a></section><section class="panel"><h2>Gerätestatus</h2><table><tr><th>Gerät</th><th>Typ</th><th>Status</th><th>Letzter Test</th><th>Ergebnis</th></tr>{rows}</table></section><section class="panel"><h2>Manuelle Netzwerkscanner</h2><table><tr><th>Name</th><th>URI</th><th>Status</th></tr>{manual}</table></section><section class="panel"><h2>Letzte Testscans</h2><table><tr><th>Zeit</th><th>Scanner</th><th>Auflösung</th><th>Modus</th></tr>{history}</table></section>', "Hardware-Monitor")


def setup_page(notice: str = "", error: bool = False) -> str:
    brother = brother_assistant(); network = network_discovery(); inv = inventory()
    state = badge("Brother erkannt", "ok") if brother["scanner_found"] else badge("Brother noch nicht erkannt", "warn")
    return layout(f'<section class="panel"><h2>Hardware-Assistent</h2><p>{len(inv["devices"])} eingerichtete Geräte und {len(network)} Netzwerkfunde.</p></section><div class="grid"><article class="card"><h2>Brother ADS-2600We</h2>{state}<p>SANE: {"bereit" if brother["sane"] else "fehlt"} · AirScan: {"bereit" if brother["airscan"] else "fehlt"}</p><a class="button" href="/brother">Assistent öffnen</a></article><article class="card"><h2>Netzwerkscanner manuell</h2><form method="post" action="/scanner/manual-add"><label>Name<input name="name" required placeholder="Brother ADS-2600We"></label><label>Scanner-URI<input name="uri" required placeholder="http://192.168.0.25/eSCL"></label><label>Backend<select name="backend"><option value="airscan">AirScan</option><option value="escl">eSCL</option><option value="brother">Brother</option><option value="sane-net">SANE net</option></select></label><button>Scanner speichern</button></form></article><article class="card"><h2>IPP-Drucker</h2><form method="post" action="/printer/add"><label>Name<input name="name" required></label><label>Geräte-URI<input name="uri" required placeholder="ipp://192.168.0.50/ipp/print"></label><button>Drucker einrichten</button></form></article></div>', "Hardware-Assistent", notice, error)


def scanners(notice: str = "", error: bool = False, result: dict | None = None) -> str:
    devices = [d for d in inventory()["devices"] if d["kind"] == "scanner"]
    settings = load_scanner_settings(); blocks = []
    for d in devices:
        sid = d["id"]; alias = settings.get("aliases", {}).get(sid, "")
        blocks.append(f'<article class="card"><h2>{esc(d["name"])}</h2><p><code>{esc(d.get("connection",""))}</code></p><form method="post" action="/scanner/save"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><label>Anzeigename<input name="alias" value="{esc(alias,True)}"></label><label>Aktiv<select name="enabled"><option value="1" {"selected" if d.get("enabled") else ""}>Ja</option><option value="0" {"selected" if not d.get("enabled") else ""}>Nein</option></select></label><label>Standard<select name="make_default"><option value="0">Nein</option><option value="1" {"selected" if d.get("default") else ""}>Ja</option></select></label><button>Speichern</button></form><div class="actions"><form class="inline" method="post" action="/scanner/test"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><button class="secondary">Verbindung testen</button></form><form class="inline" method="post" action="/scanner/test-scan"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><select name="resolution"><option>100</option><option selected>300</option><option>600</option></select><select name="mode"><option>Gray</option><option>Color</option><option>Lineart</option></select><button>Testscan</button></form><a class="button secondary" href="/scanner/{quote(sid,safe="")}">Details</a></div></article>')
    manual = "".join(f'<article class="card"><h2>{esc(d.get("name"))}</h2><p><code>{esc(d.get("uri"))}</code></p><form method="post" action="/scanner/manual-delete"><input type="hidden" name="scanner_id" value="{esc(d.get("id"),True)}"><button class="danger">Entfernen</button></form></article>' for d in manual_scanners())
    result_box = f'<section class="panel"><h2>Ergebnis</h2><pre>{esc(json.dumps(result,ensure_ascii=False,indent=2))}</pre></section>' if result else ""
    return layout(f'<section class="panel hero"><div><h2>Scanner</h2><p class="muted">Scanner konfigurieren, prüfen und testen.</p></div><a class="button" href="/profiles">Scanprofile</a></section>{result_box}<div class="grid">{"".join(blocks) or "<article class=\"card\"><h2>Kein automatisch erkannter Scanner</h2></article>"}</div><section class="panel"><h2>Manuelle Scanner</h2></section><div class="grid">{manual or "<article class=\"card\"><p>Keine manuellen Scanner.</p></article>"}</div>', "Scanner", notice, error)


def profiles_page(notice: str = "", error: bool = False) -> str:
    cards = "".join(f'<article class="card"><h2>{esc(p.get("name"))}</h2><p>{esc(p.get("resolution"))} dpi · {esc(p.get("mode"))} · {esc(p.get("format"))}</p><p>Duplex: {"Ja" if p.get("duplex") else "Nein"} · OCR: {"Ja" if p.get("ocr") else "Nein"} · Leerseiten: {"entfernen" if p.get("remove_blank") else "behalten"}</p><form method="post" action="/profile/delete"><input type="hidden" name="profile_id" value="{esc(p.get("id"),True)}"><button class="danger">Profil löschen</button></form></article>' for p in load_profiles())
    form = '<section class="panel"><h2>Scanprofil anlegen oder aktualisieren</h2><form method="post" action="/profile/save"><label>ID<input name="profile_id" placeholder="rechnung"></label><label>Name<input name="name" required placeholder="Rechnung"></label><label>Auflösung<input type="number" min="75" max="1200" name="resolution" value="300"></label><label>Farbmodus<select name="mode"><option>Gray</option><option>Color</option><option>Lineart</option></select></label><label>Ausgabe<select name="format"><option value="pdf">PDF</option><option value="pdfa">PDF/A</option><option value="png">PNG</option><option value="jpeg">JPEG</option><option value="tiff">TIFF</option></select></label><label><input type="checkbox" name="duplex" value="1" checked> Duplex</label><label><input type="checkbox" name="ocr" value="1" checked> OCR</label><label><input type="checkbox" name="remove_blank" value="1" checked> Leerseiten entfernen</label><button>Profil speichern</button></form></section>'
    return layout(f'{form}<div class="grid">{cards}</div>', "Scanprofile", notice, error)


def printers(notice: str = "", error: bool = False) -> str:
    devices = [d for d in inventory()["devices"] if d["kind"] == "printer"]
    settings = load_settings(); blocks = []
    for d in devices:
        pid = d["id"]; alias = settings.get("printer_aliases", {}).get(pid, "")
        jobs = "".join(f'<li>{esc(j.get("raw",""))} <form class="inline" method="post" action="/printer/cancel"><input type="hidden" name="job" value="{esc(j.get("id"),True)}"><button class="secondary">Abbrechen</button></form></li>' for j in d.get("jobs", [])) or '<li>Keine offenen Aufträge</li>'
        blocks.append(f'<article class="card"><h2>{esc(d["name"])}</h2>{badge("Online","ok") if d.get("online") else badge("Offline","bad")}<p><code>{esc(d.get("connection",""))}</code></p><form method="post" action="/printer/save"><input type="hidden" name="printer" value="{esc(pid,True)}"><label>Anzeigename<input name="alias" value="{esc(alias,True)}"></label><label>Standard<select name="make_default"><option value="0">Nein</option><option value="1" {"selected" if d.get("default") else ""}>Ja</option></select></label><input type="hidden" name="enabled" value="1"><button>Speichern</button></form><div class="actions"><form class="inline" method="post" action="/printer/test"><input type="hidden" name="printer" value="{esc(pid,True)}"><button>Testseite</button></form><a class="button secondary" href="/printer/{quote(pid,safe="")}">Details</a></div><details><summary>Druckaufträge</summary><ul>{jobs}</ul></details></article>')
    return layout(f'<section class="panel hero"><div><h2>Drucker</h2></div><a class="button" href="/setup">Drucker hinzufügen</a></section><div class="grid">{"".join(blocks) or "<article class=\"card\"><h2>Kein Drucker eingerichtet</h2></article>"}</div>', "Drucker", notice, error)


def detail(kind: str, device_id: str) -> str:
    device = next((x for x in inventory()["devices"] if x["kind"] == kind and x["id"] == device_id), None)
    if not device:
        return layout('<section class="panel"><h2>Gerät nicht gefunden</h2></section>', "Hardware", "Gerät nicht gefunden", True)
    rows = "".join(f'<tr><th>{esc(k)}</th><td><pre>{esc(json.dumps(v,ensure_ascii=False,indent=2) if isinstance(v,(dict,list)) else v)}</pre></td></tr>' for k, v in device.items())
    return layout(f'<section class="panel"><h2>{esc(device["name"])}</h2><table>{rows}</table></section>', device["name"])


def network_page(result: dict | None = None) -> str:
    rows = "".join(f'<tr><td>{esc(d.get("name"))}</td><td>{esc(d.get("protocol"))}</td><td><code>{esc(d.get("uri"))}</code></td></tr>' for d in network_discovery()) or '<tr><td colspan="3">Keine Netzwerkgeräte gefunden.</td></tr>'
    probe = f'<section class="panel"><pre>{esc(json.dumps(result,ensure_ascii=False,indent=2))}</pre></section>' if result else ""
    return layout(f'<section class="panel"><h2>Netzwerkgeräte</h2><form method="post" action="/network/probe"><label>IP oder Hostname<input name="host" required></label><button>Ports prüfen</button></form></section>{probe}<section class="panel"><table><tr><th>Name</th><th>Protokoll</th><th>URI</th></tr>{rows}</table></section>', "Netzwerk")


def usb_page() -> str:
    rows = "".join(f'<tr><td>{esc(d["bus"])}</td><td>{esc(d["device"])}</td><td><code>{esc(d["id"])}</code></td><td>{esc(d["description"])}</td></tr>' for d in usb_devices()) or '<tr><td colspan="4">Keine USB-Geräte.</td></tr>'
    return layout(f'<section class="panel"><h2>USB-Geräte</h2><table><tr><th>Bus</th><th>Gerät</th><th>ID</th><th>Beschreibung</th></tr>{rows}</table></section>', "USB")


def brother_page() -> str:
    data = brother_assistant(); recommendations = "".join(f'<li>{esc(x)}</li>' for x in data["recommendations"])
    return layout(f'<section class="panel"><h2>Brother ADS-2600We</h2><div class="actions">{badge("SANE","ok" if data["sane"] else "bad")}{badge("AirScan","ok" if data["airscan"] else "bad")}{badge("Brother-Treiber","ok" if data["driver"] else "warn")}</div><ol>{recommendations}</ol><a class="button" href="/setup">Manuell hinzufügen</a></section>', "Brother-Assistent")


def maintenance_page(notice: str = "", error: bool = False) -> str:
    today = __import__("datetime").date.today().isoformat()
    cards = []
    for item in maintenance_items():
        css = "due" if item.get("next_due", "9999") <= today else ""
        cards.append(f'<article class="card {css}"><h2>{esc(item.get("task"))}</h2><p>Gerät: <code>{esc(item.get("device_id"))}</code></p><p>Letzte Wartung: {esc(item.get("last_done"))}<br>Nächster Termin: {esc(item.get("next_due"))}</p><form method="post" action="/maintenance/complete"><input type="hidden" name="item_id" value="{esc(item.get("id"),True)}"><button>Als erledigt markieren</button></form></article>')
    form = '<section class="panel"><h2>Wartung planen</h2><form method="post" action="/maintenance/save"><label>Geräte-ID<input name="device_id" required></label><label>Aufgabe<input name="task" required placeholder="Einzugsrollen reinigen"></label><label>Intervall in Tagen<input type="number" name="interval_days" min="1" max="3650" value="90"></label><label>Zuletzt erledigt<input type="date" name="last_done"></label><button>Wartung speichern</button></form></section>'
    return layout(f'{form}<div class="grid">{"".join(cards) or "<article class=\"card\"><p>Noch keine Wartung geplant.</p></article>"}</div>', "Wartung", notice, error)


def drivers_page() -> str:
    rows = "".join(f'<tr><td>{esc(k)}</td><td>{badge("Bereit","ok") if v else badge("Fehlt","bad")}</td></tr>' for k, v in driver_status().items())
    return layout(f'<section class="panel"><h2>Treiber</h2><table>{rows}</table></section>', "Treiber")


def diagnostics_page() -> str:
    blocks = "".join(f'<section class="panel"><h2>{esc(k)}</h2><pre>{esc(json.dumps(v,ensure_ascii=False,indent=2))}</pre></section>' for k, v in diagnostics().items())
    return layout(blocks, "Diagnose")


def support_page(notice: str = "", error: bool = False) -> str:
    latest = latest_support_bundle()
    download = f'<a class="button secondary" href="/support/download">Herunterladen</a><p>{esc(latest.name)}</p>' if latest else '<p>Noch kein Paket.</p>'
    return layout(f'<section class="panel"><h2>Supportpaket</h2><form method="post" action="/support/create"><button>Supportpaket erstellen</button></form>{download}</section>', "Support", notice, error)


class Handler(BaseHTTPRequestHandler):
    def send(self, data: str | bytes, status: int = 200, ctype: str = "text/html; charset=utf-8", disposition: str = "") -> None:
        body = data.encode() if isinstance(data, str) else data
        self.send_response(status); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.send_header("X-Content-Type-Options", "nosniff")
        if disposition: self.send_header("Content-Disposition", disposition)
        self.end_headers(); self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        routes = {"/": overview, "/monitor": monitor_page, "/setup": setup_page, "/scanners": scanners, "/profiles": profiles_page, "/printers": printers, "/network": network_page, "/usb": usb_page, "/brother": brother_page, "/maintenance": maintenance_page, "/drivers": drivers_page, "/diagnostics": diagnostics_page, "/support": support_page}
        if path in routes: self.send(routes[path]()); return
        if path == "/support/download":
            bundle = latest_support_bundle()
            if not bundle: self.send(support_page("Noch kein Supportpaket.", True), 404); return
            self.send(bundle.read_bytes(), ctype="application/gzip", disposition=f'attachment; filename="{bundle.name}"'); return
        if path.startswith("/scanner/"): self.send(detail("scanner", unquote(path.split("/", 2)[2]))); return
        if path.startswith("/printer/"): self.send(detail("printer", unquote(path.split("/", 2)[2]))); return
        if path == "/health": self.send(json.dumps({"status":"ok","service":"openscanstation-hardware","version":VERSION}), ctype="application/json"); return
        if path == "/api/hardware": self.send(json.dumps(inventory(), ensure_ascii=False), ctype="application/json"); return
        if path == "/api/monitor": self.send(json.dumps(monitor_snapshot(), ensure_ascii=False), ctype="application/json"); return
        if path == "/api/profiles": self.send(json.dumps(load_profiles(), ensure_ascii=False), ctype="application/json"); return
        self.send(json.dumps({"error":"not_found"}), 404, "application/json")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0")); form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
            get = lambda key, default="": form.get(key, [default])[0]
            if path == "/scanner/save": update_scanner(get("scanner_id"), alias=get("alias"), enabled=get("enabled") == "1", make_default=get("make_default") == "1"); self.send(scanners("Scanner gespeichert.")); return
            if path == "/scanner/test":
                result = test_connection(get("scanner_id"), [d for d in inventory()["devices"] if d["kind"] == "scanner"]); self.send(scanners("Test abgeschlossen.", not result.get("ok", False), result)); return
            if path == "/scanner/test-scan":
                result = test_scan(get("scanner_id"), resolution=int(get("resolution", "300")), mode=get("mode", "Gray")); self.send(scanners(result["message"], False, result)); return
            if path == "/scanner/manual-add": add_manual_scanner(get("name"), get("uri"), get("backend")); self.send(setup_page("Netzwerkscanner gespeichert.")); return
            if path == "/scanner/manual-delete": delete_manual_scanner(get("scanner_id")); self.send(scanners("Manueller Scanner entfernt.")); return
            if path == "/profile/save": save_profile(get("profile_id"), name=get("name"), resolution=int(get("resolution", "300")), mode=get("mode"), duplex=get("duplex") == "1", output_format=get("format"), ocr=get("ocr") == "1", remove_blank=get("remove_blank") == "1"); self.send(profiles_page("Profil gespeichert.")); return
            if path == "/profile/delete": delete_profile(get("profile_id")); self.send(profiles_page("Profil gelöscht.")); return
            if path == "/printer/add": result = add_ipp_printer(get("name"), get("uri")); self.send(setup_page(result["message"])); return
            if path == "/printer/save": update_printer(get("printer"), alias=get("alias"), enabled=get("enabled") == "1", make_default=get("make_default") == "1"); self.send(printers("Drucker gespeichert.")); return
            if path == "/printer/test": self.send(printers(print_test_page(get("printer"))["message"])); return
            if path == "/printer/cancel": self.send(printers(cancel_print_job(get("job"))["message"])); return
            if path == "/network/probe": self.send(network_page(tcp_probe(get("host")))); return
            if path == "/maintenance/save": save_maintenance(get("device_id"), task=get("task"), interval_days=int(get("interval_days", "90")), last_done=get("last_done")); self.send(maintenance_page("Wartung gespeichert.")); return
            if path == "/maintenance/complete": complete_maintenance(get("item_id")); self.send(maintenance_page("Wartung erledigt.")); return
            if path == "/support/create": result = create_support_bundle(); self.send(support_page(result["message"])); return
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
