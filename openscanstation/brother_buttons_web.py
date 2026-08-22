"""Webverwaltung fuer Brother-Scan-to-PC-Tasten."""
from __future__ import annotations

import html
import json

from openscanstation.brother_buttons import CONFIG_FILE, STATUS_FILE, load_config, register, save_config
from openscanstation.scanner_actions import load_actions


def esc(value: object, attr: bool = False) -> str:
    return html.escape(str(value), quote=attr)


def _config() -> dict:
    try:
        return load_config()
    except ValueError:
        return {"scanner_ip": "", "server_ip": "", "scanner_id": "", "display_name": "OpenScan", "listen_port": 54925, "actions": {}}


def _status() -> dict:
    try:
        value = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def render(message: str = "", error: bool = False) -> str:
    config, status = _config(), _status()
    actions = [item for item in load_actions()["actions"] if item.get("enabled")]
    def options(function: str) -> str:
        selected = config.get("actions", {}).get(function, "")
        values = ['<option value="">Nicht zugeordnet</option>']
        values.extend(f'<option value="{esc(item["id"], True)}" {"selected" if item["id"] == selected else ""}>{esc(item["id"])} · {esc(item.get("label", ""))}</option>' for item in actions)
        return "".join(values)
    notice = f'<div class="notice {"bad" if error else "ok"}">{esc(message)}</div>' if message else ""
    status_text = esc(json.dumps(status, ensure_ascii=False, indent=2)) if status else "Noch kein Ereignis oder Registrierungsergebnis."
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Brother-Tasten</title><style>
body{{font-family:system-ui;background:#f3f6f9;color:#17202a;margin:0}}main{{max-width:1050px;margin:auto;padding:1rem}}.panel{{background:white;padding:1.2rem;border-radius:12px;box-shadow:0 2px 12px #0001;margin-bottom:1rem}}form,label{{display:grid;gap:.4rem;margin-bottom:.7rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:1rem}}input,select,button{{padding:.7rem;border:1px solid #b8c1ca;border-radius:8px}}button{{background:#17202a;color:white;font-weight:700;cursor:pointer}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f7f8;padding:1rem}}.notice{{padding:1rem;border-radius:8px}}.ok{{background:#d5f5e3}}.bad{{background:#fadbd8}}
</style></head><body><main>{notice}<section class="panel"><h1>Brother-Tasten</h1><p>Direkte Brother-Funktionen mit vorhandenen OpenScanStation-Scanneraktionen verbinden.</p><form method="post" action="/brother-buttons/save"><div class="grid"><label>Scanner-IP<input name="scanner_ip" value="{esc(config.get("scanner_ip", ""), True)}" required></label><label>OpenScanStation-IP<input name="server_ip" value="{esc(config.get("server_ip", ""), True)}" required></label><label>Scanner-ID<input name="scanner_id" value="{esc(config.get("scanner_id", ""), True)}" required></label><label>Anzeigename<input name="display_name" maxlength="15" value="{esc(config.get("display_name", "OpenScan"), True)}"></label><label>UDP-Port<input name="listen_port" type="number" value="{esc(config.get("listen_port", 54925), True)}"></label><label>FILE<select name="file_action">{options("FILE")}</select></label><label>OCR<select name="ocr_action">{options("OCR")}</select></label><label>IMAGE<select name="image_action">{options("IMAGE")}</select></label><label>EMAIL<select name="email_action">{options("EMAIL")}</select></label></div><button>Konfiguration speichern</button></form></section><section class="panel"><h2>Scannerregistrierung</h2><p>Nach Änderungen die Zuordnung per SNMP am Brother registrieren.</p><form method="post" action="/brother-buttons/register"><button>Jetzt am Scanner registrieren</button></form></section><section class="panel"><h2>Status</h2><pre>{status_text}</pre></section></main></body></html>'''


def save_from_form(get) -> dict:
    actions = {"FILE": get("file_action"), "OCR": get("ocr_action"), "IMAGE": get("image_action"), "EMAIL": get("email_action")}
    return save_config({"scanner_ip": get("scanner_ip"), "server_ip": get("server_ip"), "scanner_id": get("scanner_id"), "display_name": get("display_name", "OpenScan"), "listen_port": int(get("listen_port", "54925")), "actions": actions})


def register_now() -> dict:
    return register(load_config())
