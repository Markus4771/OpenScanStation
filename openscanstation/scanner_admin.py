"""Vollständige Scannerverwaltung für OpenScanStation."""
from __future__ import annotations

import html
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from openscanstation.cli import VERSION
from openscanstation.hardware import inventory, record_event
from openscanstation.scanner_settings import load_settings, save_settings, update_scanner

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
MANUAL_SCANNERS_FILE = DATA_DIR / "manual_scanners.json"

STYLE = """
body{font-family:system-ui;margin:0;background:#f3f6f9;color:#17202a}main{max-width:1450px;margin:1.3rem auto;padding:0 1rem}.panel,.card{background:#fff;padding:1.15rem;border-radius:14px;box-shadow:0 2px 14px #0001;margin-bottom:1rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:1rem}.actions{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}.hero{display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap}.status{display:inline-block;padding:.25rem .6rem;border-radius:999px;font-weight:700}.ok{background:#d5f5e3;color:#196f3d}.warn{background:#fcf3cf;color:#7d6608}.bad{background:#fadbd8;color:#922b21}.muted{color:#687684}form{display:grid;gap:.65rem}form.inline{display:inline-block}label{display:grid;gap:.25rem}input,select{box-sizing:border-box;padding:.65rem;border:1px solid #bcc5cc;border-radius:8px;width:100%}button,a.button{display:inline-block;background:#17202a;color:#fff;padding:.68rem .95rem;border:0;border-radius:8px;text-decoration:none;font-weight:700;cursor:pointer}button.secondary,a.secondary{background:#e9eef3;color:#17202a}button.danger{background:#922b21}code{overflow-wrap:anywhere}.notice{padding:1rem;border-radius:9px;margin-bottom:1rem}.success{background:#d5f5e3}.error{background:#fadbd8}details{margin-top:.8rem}summary{cursor:pointer;font-weight:700}
"""


def esc(value: object, attr: bool = False) -> str:
    return html.escape(str(value), quote=attr)


def _read_manual() -> list[dict]:
    try:
        value = json.loads(MANUAL_SCANNERS_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _write_manual(items: list[dict]) -> None:
    MANUAL_SCANNERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="manual-scanners-", suffix=".json", dir=MANUAL_SCANNERS_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(items, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, MANUAL_SCANNERS_FILE)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


def manual_scanners() -> list[dict]:
    return _read_manual()


def save_manual_scanner(name: str, uri: str, backend: str, original_id: str = "") -> dict:
    uri = uri.strip()
    backend = backend if backend in {"airscan", "escl", "brother", "sane-net", "sane-device"} else "airscan"
    if backend == "sane-device":
        if not uri or "\x00" in uri or len(uri) > 512:
            raise ValueError("Ungültige SANE-Gerätekennung")
        host = ""
        scanner_id = "manual:sane:" + str(abs(hash(uri)))
    else:
        parsed = urlparse(uri)
        if parsed.scheme not in {"http", "https", "airscan", "escl"} or not parsed.hostname:
            raise ValueError("Bitte eine gültige HTTP-, HTTPS-, AirScan- oder eSCL-Adresse angeben")
        host = parsed.hostname
        scanner_id = f"manual:{host}:{parsed.port or 0}:{backend}"
    item = {
        "id": scanner_id,
        "name": name.strip()[:80] or host or "Manueller Scanner",
        "uri": uri[:512],
        "backend": backend,
        "host": host,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    existing = [x for x in _read_manual() if x.get("id") not in {scanner_id, original_id}]
    existing.append(item)
    _write_manual(existing)
    record_event("manual_scanner_saved", scanner_id, f"Scanner {item['name']} gespeichert")
    return item


def delete_manual_scanner(scanner_id: str) -> None:
    before = _read_manual()
    after = [x for x in before if x.get("id") != scanner_id]
    if len(after) == len(before):
        raise ValueError("Scanner wurde nicht gefunden")
    _write_manual(after)
    settings = load_settings()
    if settings.get("default_scanner") == scanner_id:
        settings["default_scanner"] = ""
        save_settings(settings)
    record_event("manual_scanner_deleted", scanner_id, "Manueller Scanner gelöscht")


def restore_all_hidden() -> None:
    settings = load_settings()
    settings["disabled"] = []
    save_settings(settings)
    record_event("scanner_restore_all", "", "Alle ausgeblendeten Scanner wiederhergestellt")


def render(notice: str = "", error: bool = False) -> str:
    data = inventory()
    automatic = [d for d in data.get("devices", []) if d.get("kind") == "scanner"]
    settings = load_settings()
    disabled = set(settings.get("disabled", []))
    aliases = settings.get("aliases", {})
    default_id = settings.get("default_scanner", "")

    auto_cards = []
    hidden_cards = []
    for scanner in automatic:
        sid = str(scanner.get("id", ""))
        enabled = sid not in disabled
        card = f'''<article class="card">
<div class="actions"><span class="status {'ok' if scanner.get('online') else 'bad'}">{'Online' if scanner.get('online') else 'Offline'}</span>{'<span class="status ok">Standard</span>' if sid == default_id else ''}{'<span class="status warn">Ausgeblendet</span>' if not enabled else ''}</div>
<h2>{esc(aliases.get(sid) or scanner.get('name') or 'Scanner')}</h2>
<p><b>Backend:</b> {esc(scanner.get('backend','-'))}<br><b>Verbindung:</b> <code>{esc(scanner.get('connection','-'))}</code></p>
<form method="post" action="/scanner/auto-save"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><label>Anzeigename<input name="alias" value="{esc(aliases.get(sid,''),True)}"></label><label>Aktiv<select name="enabled"><option value="1" {'selected' if enabled else ''}>Ja</option><option value="0" {'selected' if not enabled else ''}>Nein</option></select></label><label>Als Standard verwenden<select name="make_default"><option value="0">Nein</option><option value="1" {'selected' if sid == default_id else ''}>Ja</option></select></label><button>Änderungen speichern</button></form>
<div class="actions"><form class="inline" method="post" action="/scanner/test"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><button class="secondary">Verbindung testen</button></form><form class="inline" method="post" action="/scanner/auto-hide" onsubmit="return confirm('Scanner wirklich ausblenden? Er kann später wiederhergestellt werden.')"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><button class="danger">Scanner ausblenden</button></form></div>
</article>'''
        (auto_cards if enabled else hidden_cards).append(card)

    manual_cards = []
    for scanner in _read_manual():
        sid = str(scanner.get("id", ""))
        manual_cards.append(f'''<article class="card"><div class="actions"><span class="status warn">Manuell</span>{'<span class="status ok">Standard</span>' if sid == default_id else ''}</div><h2>{esc(scanner.get('name'))}</h2>
<form method="post" action="/scanner/manual-save"><input type="hidden" name="original_id" value="{esc(sid,True)}"><label>Name<input name="name" required value="{esc(scanner.get('name',''),True)}"></label><label>Adresse oder SANE-Gerätekennung<input name="uri" required value="{esc(scanner.get('uri',''),True)}"></label><label>Backend<select name="backend">{''.join(f'<option value="{x}" {"selected" if scanner.get("backend")==x else ""}>{x}</option>' for x in ['airscan','escl','brother','sane-net','sane-device'])}</select></label><label>Als Standard verwenden<select name="make_default"><option value="0">Nein</option><option value="1" {'selected' if sid == default_id else ''}>Ja</option></select></label><button>Scanner speichern</button></form>
<form method="post" action="/scanner/manual-delete" onsubmit="return confirm('Manuell angelegten Scanner endgültig löschen?')"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><input type="hidden" name="confirm" value="yes"><button class="danger">Scanner endgültig löschen</button></form></article>''')

    note = f'<div class="notice {"error" if error else "success"}">{esc(notice)}</div>' if notice else ""
    add_form = '''<section class="panel"><h2>Scanner hinzufügen</h2><form method="post" action="/scanner/manual-save"><label>Name<input name="name" required placeholder="Brother ADS-2600We"></label><label>Adresse oder SANE-Gerätekennung<input name="uri" required placeholder="http://192.168.0.25/eSCL oder airscan:e0:Brother..."></label><label>Backend<select name="backend"><option value="airscan">AirScan</option><option value="escl">eSCL</option><option value="brother">Brother</option><option value="sane-net">SANE-Netzwerk</option><option value="sane-device">SANE-Gerätekennung</option></select></label><label>Als Standard verwenden<select name="make_default"><option value="0">Nein</option><option value="1">Ja</option></select></label><button>Scanner hinzufügen</button></form></section>'''
    hidden = f'<details class="panel"><summary>Ausgeblendete Scanner ({len(hidden_cards)})</summary><div class="grid">{"".join(hidden_cards) or "<p>Keine ausgeblendeten Scanner.</p>"}</div><form method="post" action="/scanner/restore-all"><button class="secondary">Alle wiederherstellen</button></form></details>'
    content = f'''{note}<section class="panel hero"><div><h1>Scannerverwaltung</h1><p class="muted">OpenScanStation {VERSION} · Scanner hinzufügen, bearbeiten, ausblenden oder löschen.</p></div><a class="button secondary" href="/setup">Hardware-Assistent</a></section>{add_form}<section class="panel"><h2>Automatisch erkannte Scanner</h2><p>Automatisch erkannte Geräte werden beim Löschen ausgeblendet, weil SANE oder AirScan sie bei der nächsten Suche erneut erkennen kann.</p></section><div class="grid">{"".join(auto_cards) or "<article class='card'><h2>Kein aktiver Scanner erkannt</h2></article>"}</div>{hidden}<section class="panel"><h2>Manuell angelegte Scanner</h2></section><div class="grid">{"".join(manual_cards) or "<article class='card'><p>Keine manuellen Scanner angelegt.</p></article>"}</div>'''
    return f'<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Scannerverwaltung</title><style>{STYLE}</style></head><body><main>{content}</main></body></html>'
