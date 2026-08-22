"""Modulare Hardware-Seiten für OpenScanStation.

Jede Sektion importiert ihre Abhängigkeiten erst beim Aufruf. Dadurch legt ein
Fehler in einem optionalen Modul nicht mehr den gesamten Hardwaredienst lahm.
"""
from __future__ import annotations

import html
import json
import traceback
from datetime import date
from urllib.parse import quote

from openscanstation.cli import VERSION

STYLE = """
body{font-family:system-ui;margin:0;background:#f3f6f9;color:#17202a}main{max-width:1500px;margin:1.3rem auto;padding:0 1rem}.panel,.card{background:#fff;padding:1.15rem;border-radius:14px;box-shadow:0 2px 14px #0001;margin-bottom:1rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem}.metric{font-size:2rem;font-weight:800}.status{display:inline-block;padding:.25rem .6rem;border-radius:999px;font-weight:700}.ok{background:#d5f5e3;color:#196f3d}.bad{background:#fadbd8;color:#922b21}.warn{background:#fcf3cf;color:#7d6608}.muted{color:#687684}.actions{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}.hero{display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap}a.button,button{display:inline-block;background:#17202a;color:#fff;padding:.68rem .95rem;border:0;border-radius:8px;text-decoration:none;font-weight:700;cursor:pointer}a.secondary,button.secondary{background:#e9eef3;color:#17202a}button.danger{background:#922b21}input,select{box-sizing:border-box;padding:.65rem;border:1px solid #bcc5cc;border-radius:8px;width:100%}label{display:grid;gap:.25rem}form{display:grid;gap:.6rem}form.inline{display:inline-block}table{width:100%;border-collapse:collapse}th,td{padding:.65rem;border-bottom:1px solid #e1e5e8;text-align:left;vertical-align:top}pre{white-space:pre-wrap;overflow:auto;max-height:420px;background:#f6f7f8;padding:1rem;border-radius:8px}code{overflow-wrap:anywhere}.notice{padding:1rem;border-radius:9px;margin-bottom:1rem}.success{background:#d5f5e3}.error{background:#fadbd8}.due{border-left:5px solid #922b21}@media(max-width:700px){main{padding:.5rem}table{display:block;overflow-x:auto}}
"""

NAV = [
    ("/", "Übersicht"), ("/monitor", "Monitor"), ("/setup", "Assistent"),
    ("/scanners", "Scanner"), ("/profiles", "Scanprofile"),
    ("/printers", "Drucker"), ("/network", "Netzwerk"),
    ("/usb", "USB"), ("/brother", "Brother"),
    ("/maintenance", "Wartung"), ("/drivers", "Treiber"),
    ("/diagnostics", "Diagnose"), ("/support", "Support"),
]


def esc(value: object, attr: bool = False) -> str:
    return html.escape(str(value), quote=attr)


def badge(text: str, css: str) -> str:
    return f'<span class="status {css}">{esc(text)}</span>'


def layout(content: str, title: str = "Hardware", notice: str = "", error: bool = False) -> str:
    note = f'<div class="notice {"error" if error else "success"}">{esc(notice)}</div>' if notice else ""
    return f'<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{STYLE}</style></head><body><main>{note}{content}</main></body></html>'


def section_error(section: str, exc: Exception) -> str:
    detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    return layout(
        f'<section class="panel"><h2>{esc(section)} konnte nicht geladen werden</h2><p>Der übrige Hardware-Bereich bleibt verfügbar.</p><pre>{esc(detail)}</pre><a class="button" href="/diagnostics">Diagnose öffnen</a></section>',
        section,
        "Ein Hardware-Untermodul hat einen Fehler gemeldet.",
        True,
    )


def _device_cards(devices: list[dict]) -> str:
    cards = []
    for d in devices:
        state = badge("Online", "ok") if d.get("online") else badge("Offline", "bad")
        cards.append(f'<article class="card"><div class="actions">{state}</div><h2>{esc(d.get("name","Gerät"))}</h2><p>{esc(d.get("manufacturer",""))} {esc(d.get("model",""))}</p><p><code>{esc(d.get("connection","-"))}</code></p></article>')
    return "".join(cards) or '<article class="card"><h2>Keine Geräte gefunden</h2></article>'


def overview() -> str:
    from openscanstation.hardware import cached_inventory
    from openscanstation.hardware_health import load_last_report
    from openscanstation.hardware_management import load_profiles
    data = cached_inventory(); counts = data.get("counts", {}); report = load_last_report(); driver_result = next((x for x in report.get("results", []) if x.get("module") == "drivers"), {}); driver_count = len(driver_result.get("details", {})) if driver_result.get("ok") else 0
    content = f'<section class="panel hero"><div><h2>Hardware-Dashboard</h2><p class="muted">Modulare Geräteverwaltung · Version {VERSION} · Cache: {esc(data.get("updated_at","-"))}</p></div><div class="actions"><a class="button" href="/setup">Hardware hinzufügen</a><a class="button secondary" href="/monitor">Monitor</a></div></section><div class="metrics"><article class="card"><b>Scanner</b><div class="metric">{counts.get("scanner",0)}</div></article><article class="card"><b>Drucker</b><div class="metric">{counts.get("printer",0)}</div></article><article class="card"><b>Online</b><div class="metric">{counts.get("online",0)}</div></article><article class="card"><b>Treiber-Prüfung</b><div class="metric">{driver_count}</div></article><article class="card"><b>Profile</b><div class="metric">{len(load_profiles())}</div></article></div><div class="grid">{_device_cards(data.get("devices", []))}</div>'
    return layout(content, "Hardware")


def monitor() -> str:
    from openscanstation.hardware_management import monitor_snapshot
    snap = monitor_snapshot()
    rows = "".join(f'<tr><td>{esc(d.get("name"))}</td><td>{esc(d.get("kind"))}</td><td>{badge("Online","ok") if d.get("online") else badge("Offline","bad")}</td><td>{esc(d.get("last_test") or "-")}</td></tr>' for d in snap.get("devices", [])) or '<tr><td colspan="4">Keine Geräte.</td></tr>'
    return layout(f'<section class="panel hero"><div><h2>Hardware-Monitor</h2><p class="muted">Stand: {esc(snap.get("updated_at",""))}</p></div><a class="button" href="/monitor">Aktualisieren</a></section><section class="panel"><table><tr><th>Gerät</th><th>Typ</th><th>Status</th><th>Letzter Test</th></tr>{rows}</table></section>', "Hardware-Monitor")


def setup() -> str:
    from openscanstation.hardware import cached_inventory
    data = cached_inventory(); brother_found = any("brother" in json.dumps(device).casefold() for device in data.get("devices", []))
    state = badge("Brother erkannt", "ok") if brother_found else badge("Brother nicht im Cache", "warn")
    return layout(f'<section class="panel"><h2>Hardware-Assistent</h2><p>{len(data.get("devices", []))} Geräte im letzten Erkennungsstand.</p></section><div class="grid"><article class="card"><h2>Brother ADS-2600We</h2>{state}<p class="muted">Die Seite verwendet den Hardwarecache und blockiert nicht auf schlafenden Geräten.</p><a class="button" href="/brother">Brother-Assistent</a></article><article class="card"><h2>Netzwerkscanner</h2><form method="post" action="/scanner/manual-add"><label>Name<input name="name" required></label><label>URI<input name="uri" required placeholder="http://192.168.0.25/eSCL"></label><label>Backend<select name="backend"><option value="airscan">AirScan</option><option value="escl">eSCL</option><option value="brother">Brother</option><option value="sane-net">SANE net</option></select></label><button>Scanner speichern</button></form></article><article class="card"><h2>IPP-Drucker</h2><form method="post" action="/printer/add"><label>Name<input name="name" required></label><label>URI<input name="uri" required placeholder="ipp://192.168.0.50/ipp/print"></label><button>Drucker einrichten</button></form></article></div>', "Hardware-Assistent")


def scanners() -> str:
    from openscanstation.hardware import cached_inventory
    from openscanstation.hardware_management import manual_scanners
    data = [d for d in cached_inventory().get("devices", []) if d.get("kind") == "scanner"]
    cards = []
    for d in data:
        sid = str(d.get("id", ""))
        cards.append(f'<article class="card"><h2>{esc(d.get("name"))}</h2><p><code>{esc(d.get("connection",""))}</code></p><div class="actions"><form class="inline" method="post" action="/scanner/test"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><button class="secondary">Verbindung testen</button></form><form class="inline" method="post" action="/scanner/test-scan"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><select name="resolution"><option>100</option><option selected>300</option><option>600</option></select><select name="mode"><option>Gray</option><option>Color</option><option>Lineart</option></select><button>Testscan</button></form></div></article>')
    manual = "".join(f'<article class="card"><h2>{esc(d.get("name"))}</h2><p><code>{esc(d.get("uri"))}</code></p><form method="post" action="/scanner/manual-delete"><input type="hidden" name="scanner_id" value="{esc(d.get("id"),True)}"><button class="danger">Entfernen</button></form></article>' for d in manual_scanners())
    return layout(f'<section class="panel hero"><div><h2>Scanner</h2></div><a class="button" href="/profiles">Scanprofile</a></section><div class="grid">{"".join(cards) or "<article class=\"card\"><h2>Kein Scanner erkannt</h2></article>"}</div><section class="panel"><h2>Manuelle Scanner</h2></section><div class="grid">{manual or "<article class=\"card\"><p>Keine manuellen Scanner.</p></article>"}</div>', "Scanner")


def profiles() -> str:
    from openscanstation.hardware_management import load_profiles
    cards = "".join(f'<article class="card"><h2>{esc(p.get("name"))}</h2><p>{esc(p.get("resolution"))} dpi · {esc(p.get("mode"))} · {esc(p.get("format"))}</p><form method="post" action="/profile/delete"><input type="hidden" name="profile_id" value="{esc(p.get("id"),True)}"><button class="danger">Löschen</button></form></article>' for p in load_profiles())
    form = '<section class="panel"><h2>Scanprofil</h2><form method="post" action="/profile/save"><label>ID<input name="profile_id"></label><label>Name<input name="name" required></label><label>Auflösung<input type="number" name="resolution" value="300" min="75" max="1200"></label><label>Modus<select name="mode"><option>Gray</option><option>Color</option><option>Lineart</option></select></label><label>Format<select name="format"><option>pdf</option><option>pdfa</option><option>png</option><option>jpeg</option><option>tiff</option></select></label><label><input type="checkbox" name="duplex" value="1"> Duplex</label><label><input type="checkbox" name="ocr" value="1"> OCR</label><label><input type="checkbox" name="remove_blank" value="1"> Leerseiten entfernen</label><button>Speichern</button></form></section>'
    return layout(form + f'<div class="grid">{cards}</div>', "Scanprofile")


def printers() -> str:
    from openscanstation.hardware import cached_inventory
    devices = [d for d in cached_inventory().get("devices", []) if d.get("kind") == "printer"]
    cards = "".join(f'<article class="card"><h2>{esc(d.get("name"))}</h2>{badge("Online","ok") if d.get("online") else badge("Offline","bad")}<p><code>{esc(d.get("connection",""))}</code></p><form method="post" action="/printer/test"><input type="hidden" name="printer" value="{esc(d.get("id"),True)}"><button>Testseite</button></form></article>' for d in devices)
    return layout(f'<section class="panel hero"><h2>Drucker</h2><a class="button" href="/setup">Drucker hinzufügen</a></section><div class="grid">{cards or "<article class=\"card\"><h2>Kein Drucker eingerichtet</h2></article>"}</div>', "Drucker")


def network() -> str:
    from openscanstation.hardware import cached_inventory
    devices = [d for d in cached_inventory().get("devices", []) if str(d.get("connection", "")).startswith(("http", "airscan", "escl", "ipp"))]
    rows = "".join(f'<tr><td>{esc(d.get("name"))}</td><td>{esc(d.get("backend"))}</td><td><code>{esc(d.get("connection"))}</code></td></tr>' for d in devices) or '<tr><td colspan="3">Keine Netzwerkgeräte im Cache.</td></tr>'
    return layout(f'<section class="panel"><h2>Netzwerkgeräte</h2><form method="post" action="/network/probe"><label>IP oder Hostname<input name="host" required></label><button>Ports prüfen</button></form></section><section class="panel"><table><tr><th>Name</th><th>Protokoll</th><th>URI</th></tr>{rows}</table></section>', "Netzwerk")


def usb() -> str:
    from openscanstation.hardware import cached_inventory
    devices = [d for d in cached_inventory().get("devices", []) if "usb" in str(d.get("connection", "")).lower()]
    rows = "".join(f'<tr><td>-</td><td>-</td><td><code>{esc(d.get("id"))}</code></td><td>{esc(d.get("name"))}</td></tr>' for d in devices) or '<tr><td colspan="4">Keine USB-Geräte im Cache.</td></tr>'
    return layout(f'<section class="panel"><h2>USB-Geräte</h2><table><tr><th>Bus</th><th>Gerät</th><th>ID</th><th>Beschreibung</th></tr>{rows}</table></section>', "USB")


def brother() -> str:
    from openscanstation.hardware import cached_inventory
    devices = [d for d in cached_inventory().get("devices", []) if "brother" in json.dumps(d).casefold()]
    cards = _device_cards(devices)
    return layout(f'<section class="panel"><h2>Brother ADS-2600We</h2><p class="muted">Anzeige aus dem Hardwarecache; beim Öffnen wird kein Scannerzugriff gestartet.</p></section><div class="grid">{cards}</div>', "Brother")


def maintenance() -> str:
    from openscanstation.hardware_management import maintenance_items
    today = date.today().isoformat(); cards = []
    for item in maintenance_items():
        css = "due" if item.get("next_due", "9999") <= today else ""
        cards.append(f'<article class="card {css}"><h2>{esc(item.get("task"))}</h2><p>Gerät: <code>{esc(item.get("device_id"))}</code></p><p>Nächster Termin: {esc(item.get("next_due"))}</p><form method="post" action="/maintenance/complete"><input type="hidden" name="item_id" value="{esc(item.get("id"),True)}"><button>Erledigt</button></form></article>')
    form = '<section class="panel"><h2>Wartung planen</h2><form method="post" action="/maintenance/save"><label>Geräte-ID<input name="device_id" required></label><label>Aufgabe<input name="task" required></label><label>Intervall Tage<input type="number" name="interval_days" value="90"></label><label>Zuletzt erledigt<input type="date" name="last_done"></label><button>Speichern</button></form></section>'
    return layout(form + f'<div class="grid">{"".join(cards) or "<article class=\"card\"><p>Keine Wartung geplant.</p></article>"}</div>', "Wartung")


def drivers() -> str:
    from openscanstation.hardware_health import load_last_report
    result = next((x for x in load_last_report().get("results", []) if x.get("module") == "drivers"), {})
    rows = f'<tr><td>Letzte Prüfung</td><td>{badge("Bereit","ok") if result.get("ok") else badge("Nicht geprüft","warn")}</td></tr>'
    return layout(f'<section class="panel"><h2>Treiber</h2><table>{rows}</table></section>', "Treiber")


def diagnostics() -> str:
    from openscanstation.hardware import cached_inventory
    from openscanstation.hardware_health import load_last_report
    values = {"hardware_cache": cached_inventory(), "last_health_report": load_last_report()}
    blocks = "".join(f'<section class="panel"><h2>{esc(k)}</h2><pre>{esc(json.dumps(v,ensure_ascii=False,indent=2))}</pre></section>' for k, v in values.items())
    return layout(blocks, "Diagnose")


def support() -> str:
    from openscanstation.hardware_actions import latest_support_bundle
    latest = latest_support_bundle()
    download = f'<a class="button secondary" href="/support/download">Herunterladen</a><p>{esc(latest.name)}</p>' if latest else '<p>Noch kein Supportpaket.</p>'
    return layout(f'<section class="panel"><h2>Supportpaket</h2><form method="post" action="/support/create"><button>Supportpaket erstellen</button></form>{download}</section>', "Support")


SECTIONS = {
    "/": overview, "/monitor": monitor, "/setup": setup,
    "/scanners": scanners, "/profiles": profiles, "/printers": printers,
    "/network": network, "/usb": usb, "/brother": brother,
    "/maintenance": maintenance, "/drivers": drivers,
    "/diagnostics": diagnostics, "/support": support,
}


def render(path: str) -> str | None:
    handler = SECTIONS.get(path)
    if handler is None:
        return None
    try:
        return handler()
    except Exception as exc:
        return section_error(path.strip("/") or "Hardware", exc)
