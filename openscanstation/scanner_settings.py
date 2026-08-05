"""Scannerverwaltung für die Haupt-Weboberfläche von OpenScanStation."""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
SETTINGS_FILE = DATA_DIR / "scanner_settings.json"


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_settings(data: dict) -> dict:
    normalized = {
        "default_scanner": str(data.get("default_scanner", ""))[:512],
        "aliases": {str(k)[:512]: str(v).strip()[:80] for k, v in dict(data.get("aliases", {})).items()},
        "disabled": [str(value)[:512] for value in data.get("disabled", [])],
    }
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="scanner-settings-", suffix=".json", dir=SETTINGS_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, SETTINGS_FILE)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return normalized


def update_scanner(scanner_id: str, *, alias: str, enabled: bool, make_default: bool) -> dict:
    settings = load_settings()
    aliases = settings.setdefault("aliases", {})
    disabled = set(settings.setdefault("disabled", []))
    if alias.strip():
        aliases[scanner_id] = alias.strip()[:80]
    else:
        aliases.pop(scanner_id, None)
    if enabled:
        disabled.discard(scanner_id)
    else:
        disabled.add(scanner_id)
        if settings.get("default_scanner") == scanner_id:
            settings["default_scanner"] = ""
    if make_default and enabled:
        settings["default_scanner"] = scanner_id
    settings["disabled"] = sorted(disabled)
    return save_settings(settings)


def scanner_name(scanner: dict) -> str:
    settings = load_settings()
    return settings.get("aliases", {}).get(scanner.get("id"), scanner.get("name") or scanner.get("model") or "Scanner")


def visible_scanners(scanners: list[dict]) -> list[dict]:
    disabled = set(load_settings().get("disabled", []))
    return [scanner for scanner in scanners if scanner.get("id") not in disabled]


def default_scanner_id(scanners: list[dict]) -> str:
    settings = load_settings()
    configured = settings.get("default_scanner", "")
    ids = {str(scanner.get("id")) for scanner in scanners}
    if configured in ids:
        return configured
    return str(scanners[0].get("id")) if scanners else ""


def _run(command: list[str], timeout: int = 30) -> dict:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return {
            "command": " ".join(command),
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip()[:20000],
        }
    except FileNotFoundError:
        return {"command": " ".join(command), "ok": False, "returncode": 127, "output": "Programm nicht installiert"}
    except subprocess.TimeoutExpired:
        return {"command": " ".join(command), "ok": False, "returncode": 124, "output": "Zeitüberschreitung"}


def diagnostics() -> list[dict]:
    checks = [_run(["scanimage", "-L"], 60)]
    if shutil.which("airscan-discover"):
        checks.append(_run(["airscan-discover"], 30))
    checks.append(_run(["lsusb"], 15))
    return checks


def test_connection(scanner_id: str, scanners: list[dict]) -> dict:
    scanner = next((item for item in scanners if item.get("id") == scanner_id), None)
    if not scanner:
        raise ValueError("Scanner nicht gefunden")
    connection = str(scanner.get("connection", ""))
    result = _run(["scanimage", "--device-name", connection, "--help"], 30)
    result["scanner_id"] = scanner_id
    result["scanner"] = scanner_name(scanner)
    return result


def render_page(scanners: list[dict], *, notice: str = "", error: bool = False, test_result: dict | None = None) -> str:
    settings = load_settings()
    disabled = set(settings.get("disabled", []))
    default_id = default_scanner_id(scanners)
    cards = []
    for scanner in scanners:
        sid = str(scanner.get("id", ""))
        ready = bool(scanner.get("connected") and scanner.get("scan_supported"))
        enabled = sid not in disabled
        alias = settings.get("aliases", {}).get(sid, "")
        capabilities = scanner.get("capabilities", {})
        cards.append(f'''<article class="card"><div class="headline"><h2>{html.escape(scanner_name(scanner))}</h2><span class="{'ready' if ready else 'warning'}">{'Bereit' if ready else 'Prüfen'}</span></div>
<p><b>Hersteller/Modell:</b> {html.escape(str(scanner.get('manufacturer','-')))} {html.escape(str(scanner.get('model','-')))}</p>
<p><b>Backend:</b> {html.escape(str(scanner.get('backend','-')))}</p><p><b>Verbindung:</b> <code>{html.escape(str(scanner.get('connection','-')))}</code></p>
<p><b>ADF:</b> {'Ja' if capabilities.get('adf') else 'Nein'} · <b>Duplex:</b> {'Ja' if capabilities.get('duplex') else 'Nein'}</p>
<form method="post" action="/scanners/save"><input type="hidden" name="scanner_id" value="{html.escape(sid, quote=True)}"><label>Anzeigename<input name="alias" value="{html.escape(alias, quote=True)}" placeholder="Eigener Scannername"></label><label>Aktiv<select name="enabled"><option value="1" {'selected' if enabled else ''}>Ja</option><option value="0" {'selected' if not enabled else ''}>Nein</option></select></label><label>Standardscanner<select name="make_default"><option value="0">Nein</option><option value="1" {'selected' if sid == default_id else ''}>Ja</option></select></label><button>Scanner speichern</button></form>
<form method="post" action="/scanners/test"><input type="hidden" name="scanner_id" value="{html.escape(sid, quote=True)}"><button>Verbindung testen</button></form></article>''')
    if not cards:
        cards.append('<article class="card"><h2>Kein Scanner gefunden</h2><p>Starte eine neue Suche oder öffne die Diagnose.</p></article>')
    result_box = ""
    if test_result:
        result_box = f'<section class="panel"><h2>Testergebnis</h2><pre>{html.escape(json.dumps(test_result, ensure_ascii=False, indent=2))}</pre></section>'
    diagnostic_rows = "".join(
        f'<article class="card"><h3>{html.escape(check["command"])}</h3><p><span class="{"ready" if check["ok"] else "warning"}">{"OK" if check["ok"] else "Fehler"}</span></p><pre>{html.escape(check["output"] or "Keine Ausgabe")}</pre></article>'
        for check in diagnostics()
    )
    content = f'''<section class="panel"><div class="headline"><div><h2>Scanner einrichten</h2><p>Scanner suchen, benennen, aktivieren, als Standard festlegen und testen.</p></div><form class="inline-form" method="post" action="/scanners/refresh"><button>Scanner neu suchen</button></form></div><p class="muted">Konfiguration: <code>{html.escape(str(SETTINGS_FILE))}</code></p></section>{result_box}<div class="grid">{''.join(cards)}</div><section class="panel"><h2>Diagnose</h2><p>Die Diagnose zeigt SANE-, AirScan- und USB-Erkennung.</p></section><div class="grid">{diagnostic_rows}</div>'''
    note = f'<div class="notice {"error" if error else "success"}">{html.escape(notice)}</div>' if notice else ""
    return note + content
