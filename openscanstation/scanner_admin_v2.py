"""Scannerverwaltung Version 2 für OpenScanStation."""
from __future__ import annotations

import html
import json
import os
import socket
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from openscanstation.cli import VERSION
from openscanstation.hardware import cached_inventory, record_event
from openscanstation.scanner_settings import load_settings, save_settings, update_scanner

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
MANUAL_FILE = DATA_DIR / "manual_scanners.json"

STYLE = """
body{font-family:system-ui;margin:0;background:#f3f6f9;color:#17202a}main{max-width:1450px;margin:1.3rem auto;padding:0 1rem}.panel,.card{background:#fff;padding:1.15rem;border-radius:14px;box-shadow:0 2px 14px #0001;margin-bottom:1rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:1rem}.actions{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}.hero{display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap}.status{display:inline-block;padding:.25rem .6rem;border-radius:999px;font-weight:700}.ok{background:#d5f5e3;color:#196f3d}.warn{background:#fcf3cf;color:#7d6608}.bad{background:#fadbd8;color:#922b21}.muted{color:#687684}form{display:grid;gap:.65rem}form.inline{display:inline-block}label{display:grid;gap:.25rem}input,select,textarea{box-sizing:border-box;padding:.65rem;border:1px solid #bcc5cc;border-radius:8px;width:100%}textarea{min-height:180px;font-family:monospace}button,a.button{display:inline-block;background:#17202a;color:#fff;padding:.68rem .95rem;border:0;border-radius:8px;text-decoration:none;font-weight:700;cursor:pointer}button.secondary,a.secondary{background:#e9eef3;color:#17202a}button.danger{background:#922b21}code{overflow-wrap:anywhere}.notice{padding:1rem;border-radius:9px;margin-bottom:1rem}.success{background:#d5f5e3}.error{background:#fadbd8}details{margin-top:.8rem}summary{cursor:pointer;font-weight:700}
"""


def esc(value: object, attr: bool = False) -> str:
    return html.escape(str(value), quote=attr)


def _read_json(path: Path, fallback):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.stem + "-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


def manual_scanners() -> list[dict]:
    value = _read_json(MANUAL_FILE, [])
    return value if isinstance(value, list) else []


def save_manual(name: str, uri: str, backend: str, original_id: str = "") -> dict:
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
            raise ValueError("Ungültige Scanneradresse")
        host = parsed.hostname
        scanner_id = f"manual:{host}:{parsed.port or 0}:{backend}"
    item = {"id": scanner_id, "name": name.strip()[:80] or host or "Scanner", "uri": uri[:512], "backend": backend, "host": host, "updated_at": datetime.now().isoformat(timespec="seconds")}
    items = [x for x in manual_scanners() if x.get("id") not in {scanner_id, original_id}]
    items.append(item)
    _write_json(MANUAL_FILE, items)
    record_event("manual_scanner_saved", scanner_id, f"Scanner {item['name']} gespeichert")
    return item


def delete_manual(scanner_id: str) -> None:
    items = manual_scanners()
    remaining = [x for x in items if x.get("id") != scanner_id]
    if len(remaining) == len(items):
        raise ValueError("Scanner nicht gefunden")
    _write_json(MANUAL_FILE, remaining)
    settings = load_settings()
    if settings.get("default_scanner") == scanner_id:
        settings["default_scanner"] = ""
        save_settings(settings)
    record_event("manual_scanner_deleted", scanner_id, "Manueller Scanner gelöscht")


def restore(scanner_id: str) -> None:
    settings = load_settings()
    disabled = set(settings.get("disabled", []))
    disabled.discard(scanner_id)
    settings["disabled"] = sorted(disabled)
    save_settings(settings)
    record_event("scanner_restored", scanner_id, "Scanner wiederhergestellt")


def restore_all() -> None:
    settings = load_settings()
    settings["disabled"] = []
    save_settings(settings)
    record_event("scanner_restore_all", "", "Alle Scanner wiederhergestellt")


def configuration() -> dict:
    return {"format": "openscanstation-scanners-v1", "exported_at": datetime.now().isoformat(timespec="seconds"), "settings": load_settings(), "manual_scanners": manual_scanners()}


def import_configuration(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ungültiges JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("format") != "openscanstation-scanners-v1":
        raise ValueError("Unbekanntes Konfigurationsformat")
    settings = payload.get("settings", {})
    manual = payload.get("manual_scanners", [])
    if not isinstance(settings, dict) or not isinstance(manual, list):
        raise ValueError("Scannerkonfiguration ist unvollständig")
    save_settings(settings)
    cleaned = []
    for item in manual[:200]:
        if not isinstance(item, dict):
            continue
        name, uri, backend = str(item.get("name", "")), str(item.get("uri", "")), str(item.get("backend", "airscan"))
        cleaned.append(save_manual(name, uri, backend))
    record_event("scanner_config_import", "", f"{len(cleaned)} manuelle Scanner importiert")
    return {"imported": len(cleaned)}


def _manual_online(scanner: dict) -> bool | None:
    backend = scanner.get("backend")
    if backend == "sane-device":
        return None
    host = scanner.get("host")
    if not host:
        return False
    for port in (80, 443, 6566, 8080):
        try:
            with socket.create_connection((host, port), timeout=0.45):
                return True
        except OSError:
            continue
    return False


def _status_badge(value: bool | None) -> str:
    if value is True:
        return '<span class="status ok">Erreichbar</span>'
    if value is False:
        return '<span class="status bad">Nicht erreichbar</span>'
    return '<span class="status warn">Nicht geprüft</span>'


def render(notice: str = "", error: bool = False) -> str:
    devices = [d for d in cached_inventory().get("devices", []) if d.get("kind") == "scanner"]
    settings = load_settings()
    disabled = set(settings.get("disabled", []))
    aliases = settings.get("aliases", {})
    default_id = settings.get("default_scanner", "")
    active_cards, hidden_cards = [], []
    for scanner in devices:
        sid = str(scanner.get("id", "")); enabled = sid not in disabled
        controls = f'''<form method="post" action="/scanner/auto-save"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><label>Anzeigename<input name="alias" value="{esc(aliases.get(sid,''),True)}"></label><label>Aktiv<select name="enabled"><option value="1" {'selected' if enabled else ''}>Ja</option><option value="0" {'selected' if not enabled else ''}>Nein</option></select></label><label>Standard<select name="make_default"><option value="0">Nein</option><option value="1" {'selected' if sid==default_id else ''}>Ja</option></select></label><button>Speichern</button></form>'''
        action = f'''<form class="inline" method="post" action="/scanner/auto-hide" onsubmit="return confirm('Scanner ausblenden?')"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><button class="danger">Ausblenden</button></form>''' if enabled else f'''<form class="inline" method="post" action="/scanner/restore"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><button>Wiederherstellen</button></form>'''
        card = f'''<article class="card"><div class="actions">{_status_badge(bool(scanner.get('online')))}{'<span class="status ok">Standard</span>' if sid==default_id else ''}{'<span class="status warn">Ausgeblendet</span>' if not enabled else ''}</div><h2>{esc(aliases.get(sid) or scanner.get('name') or 'Scanner')}</h2><p><b>Backend:</b> {esc(scanner.get('backend','-'))}<br><b>Verbindung:</b> <code>{esc(scanner.get('connection','-'))}</code></p>{controls}<div class="actions"><form class="inline" method="post" action="/scanner/test"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><button class="secondary">Verbindung testen</button></form>{action}</div></article>'''
        (active_cards if enabled else hidden_cards).append(card)

    manual_cards = []
    for scanner in manual_scanners():
        sid = str(scanner.get("id", "")); online = _manual_online(scanner)
        options = ''.join(f'<option value="{x}" {"selected" if scanner.get("backend")==x else ""}>{x}</option>' for x in ["airscan","escl","brother","sane-net","sane-device"])
        manual_cards.append(f'''<article class="card"><div class="actions">{_status_badge(online)}<span class="status warn">Manuell</span>{'<span class="status ok">Standard</span>' if sid==default_id else ''}</div><h2>{esc(scanner.get('name'))}</h2><form method="post" action="/scanner/manual-save"><input type="hidden" name="original_id" value="{esc(sid,True)}"><label>Name<input name="name" required value="{esc(scanner.get('name',''),True)}"></label><label>Adresse oder Gerätekennung<input name="uri" required value="{esc(scanner.get('uri',''),True)}"></label><label>Backend<select name="backend">{options}</select></label><label>Standard<select name="make_default"><option value="0">Nein</option><option value="1" {'selected' if sid==default_id else ''}>Ja</option></select></label><button>Änderungen speichern</button></form><form method="post" action="/scanner/manual-delete" onsubmit="return confirm('Scanner endgültig löschen?')"><input type="hidden" name="scanner_id" value="{esc(sid,True)}"><input type="hidden" name="confirm" value="yes"><button class="danger">Endgültig löschen</button></form></article>''')

    note = f'<div class="notice {"error" if error else "success"}">{esc(notice)}</div>' if notice else ""
    add = '''<section class="panel"><h2>Scanner hinzufügen</h2><form method="post" action="/scanner/manual-save"><label>Name<input name="name" required></label><label>Adresse oder SANE-Gerätekennung<input name="uri" required placeholder="http://192.168.0.25/eSCL"></label><label>Backend<select name="backend"><option value="airscan">AirScan</option><option value="escl">eSCL</option><option value="brother">Brother</option><option value="sane-net">SANE-Netzwerk</option><option value="sane-device">SANE-Gerätekennung</option></select></label><label>Standard<select name="make_default"><option value="0">Nein</option><option value="1">Ja</option></select></label><button>Scanner hinzufügen</button></form></section>'''
    transfer = '''<details class="panel"><summary>Konfiguration sichern oder wiederherstellen</summary><div class="actions"><a class="button secondary" href="/scanner/config-export">Konfiguration herunterladen</a></div><form method="post" action="/scanner/config-import"><label>Exportierte JSON-Konfiguration<textarea name="configuration" required></textarea></label><button>Konfiguration importieren</button></form></details>'''
    hidden = f'<details class="panel"><summary>Ausgeblendete Scanner ({len(hidden_cards)})</summary><div class="grid">{"".join(hidden_cards) or "<p>Keine ausgeblendeten Scanner.</p>"}</div><form method="post" action="/scanner/restore-all"><button class="secondary">Alle wiederherstellen</button></form></details>'
    body = f'''{note}<section class="panel hero"><div><h1>Scannerverwaltung</h1><p class="muted">OpenScanStation {VERSION}</p></div><a class="button secondary" href="/setup">Hardware-Assistent</a></section>{add}<section class="panel"><h2>Automatisch erkannte Scanner</h2></section><div class="grid">{"".join(active_cards) or "<article class='card'><h2>Kein aktiver Scanner erkannt</h2></article>"}</div>{hidden}<section class="panel"><h2>Manuell angelegte Scanner</h2></section><div class="grid">{"".join(manual_cards) or "<article class='card'><p>Keine manuellen Scanner.</p></article>"}</div>{transfer}'''
    return f'<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Scannerverwaltung</title><style>{STYLE}</style></head><body><main>{body}</main></body></html>'
