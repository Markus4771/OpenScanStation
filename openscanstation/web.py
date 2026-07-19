"""OpenScanStation-WebGUI und REST-API auf Port 8101."""
from __future__ import annotations

import argparse
import html
import json
import re
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

from openscanstation.cli import VERSION
from openscanstation.documents import SCAN_DIR, add_document, list_documents, run_ocr
from openscanstation.profiles import (
    ALLOWED_DPI,
    ALLOWED_FORMATS,
    ALLOWED_MODES,
    delete_profile,
    load_profiles,
    upsert_profile,
)
from openscanstation.scanner.manager import ScannerManager
from openscanstation.scanner_actions import action_by_id, load_actions, save_actions
from openscanstation.scanner_cache import ScannerCache
from openscanstation.system_info import system_payload

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8101
_SCAN_LOCK = threading.Lock()
_SAFE_FILE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _discover_scanners() -> dict:
    manager = ScannerManager()
    result = manager.discover()
    scanners = []
    for scanner in result.scanners:
        plugin = manager.get_plugin(scanner.plugin_id)
        status = plugin.get_status(scanner.connection) if plugin else None
        scanners.append({
            "id": f"{scanner.plugin_id}:{scanner.connection}",
            "name": scanner.name,
            "manufacturer": scanner.manufacturer,
            "model": scanner.model,
            "connection": scanner.connection,
            "plugin_id": scanner.plugin_id,
            "state": status.state.value if status else "unknown",
            "connected": status.connected if status else False,
            "backend": status.backend if status else None,
            "scan_supported": status.scan_supported if status else False,
            "message": status.message if status else "Plugin nicht verfügbar",
            "capabilities": {
                "duplex": scanner.capabilities.duplex,
                "adf": scanner.capabilities.adf,
                "resolutions_dpi": list(scanner.capabilities.resolutions_dpi),
                "color_modes": list(scanner.capabilities.color_modes),
            },
        })
    return {
        "version": VERSION,
        "scanners": scanners,
        "errors": [{"plugin_id": e.plugin_id, "message": e.message} for e in result.errors],
    }


_SCANNER_CACHE = ScannerCache(_discover_scanners, interval_seconds=10)


def _scanner_payload() -> dict:
    return {"version": VERSION, **_SCANNER_CACHE.snapshot()}


def _find_scanner(scanner_id: str):
    manager = ScannerManager()
    for scanner in manager.discover().scanners:
        if f"{scanner.plugin_id}:{scanner.connection}" == scanner_id:
            return scanner, manager.get_plugin(scanner.plugin_id)
    return None, None


def _perform_scan(form: dict[str, list[str]]) -> dict:
    scanner_id = form.get("scanner_id", [""])[0]
    requested_profile_id = form.get("profile", ["dokument"])[0]
    profiles = load_profiles()
    default_profile_id = "dokument" if "dokument" in profiles else next(iter(profiles))
    profile_id = requested_profile_id if requested_profile_id in profiles else default_profile_id
    profile = profiles[profile_id]
    dpi = int(form.get("dpi", [str(profile.get("dpi", 300))])[0])
    mode = form.get("mode", [str(profile.get("mode", "color"))])[0]
    output_format = form.get("format", [str(profile.get("format", "pdf"))])[0].lower()
    title = form.get("title", [profile.get("label", "Dokument")])[0].strip() or "Dokument"
    tags = [x.strip() for x in form.get("tags", [""])[0].split(",") if x.strip()]
    do_ocr = form.get("ocr", ["0"])[0] == "1" or bool(profile.get("ocr"))
    if output_format not in ALLOWED_FORMATS:
        raise ValueError("Ungültiges Ausgabeformat")
    scanner, plugin = _find_scanner(scanner_id)
    if scanner is None or plugin is None:
        raise RuntimeError("Scanner nicht gefunden")
    status = plugin.get_status(scanner.connection)
    if not status.scan_supported:
        raise RuntimeError(status.message or "Scanner nicht scanfähig")
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"scan-{stamp}-{scanner.plugin_id}.{output_format}"
    target = SCAN_DIR / filename
    with _SCAN_LOCK:
        result = plugin.start_scan(scanner.connection, {
            "output": str(target),
            "dpi": dpi,
            "mode": mode,
            "duplex": bool(profile.get("duplex")),
        })
    add_document(filename, title, scanner.name, profile_id, output_format, 1, tags)
    ocr_error = ""
    if do_ocr:
        try:
            run_ocr(filename)
        except Exception as exc:
            ocr_error = str(exc)
    _SCANNER_CACHE.request_refresh()
    return {
        "ok": True,
        "filename": filename,
        "bytes": result.bytes_written,
        "download_url": f"/scans/{quote(filename)}",
        "ocr_error": ocr_error,
    }


def _perform_action(scanner_id: str, action_id: str) -> dict:
    action = action_by_id(action_id)
    if not action or not action.get("enabled"):
        raise ValueError("Scanneraktion ist nicht aktiviert")
    form = {
        "scanner_id": [scanner_id],
        "profile": [action.get("profile", "dokument")],
        "title": [action.get("title", action.get("label", "Dokument"))],
        "tags": [", ".join(action.get("tags", []))],
    }
    return _perform_scan(form)


def _layout(content: str, title: str = "OpenScanStation", notice: str = "", error: bool = False) -> str:
    note = f'<div class="notice {"error" if error else "success"}">{html.escape(notice)}</div>' if notice else ""
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f3f5f7;color:#17202a}}header{{background:#17202a;color:#fff;padding:1.25rem 2rem}}header h1{{margin:0}}nav{{margin-top:.8rem}}nav a{{color:#fff;margin-right:1rem;text-decoration:none}}main{{max-width:1200px;margin:1.5rem auto;padding:0 1rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}}.card,.panel{{background:#fff;border-radius:12px;padding:1.2rem;box-shadow:0 2px 12px #0001;margin-bottom:1rem}}.ready,.warning{{padding:.25rem .55rem;border-radius:999px;font-weight:700;font-size:.85rem}}.ready{{background:#d5f5e3;color:#196f3d}}.warning{{background:#fdebd0;color:#935116}}.headline{{display:flex;justify-content:space-between;gap:1rem;align-items:center}}form{{display:grid;gap:.8rem}}.form-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.8rem}}label{{display:grid;gap:.3rem;font-weight:700}}input,select,button{{padding:.7rem;border:1px solid #bcc5cc;border-radius:8px;background:#fff}}input[type=checkbox]{{width:auto}}button{{background:#17202a;color:#fff;font-weight:700;cursor:pointer}}button.danger{{background:#922b21}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.65rem;border-bottom:1px solid #e5e8eb;text-align:left;vertical-align:top}}.notice{{padding:1rem;border-radius:8px;margin-bottom:1rem}}.success{{background:#d5f5e3}}.error{{background:#fadbd8}}code{{overflow-wrap:anywhere}}.muted{{color:#65727e;font-size:.9rem}}.metric{{font-size:1.6rem;font-weight:800;margin:.2rem 0}}progress{{width:100%;height:1.1rem}}.inline-form{{display:inline-block;margin:0}}.action-card{{border-left:5px solid #65727e}}.profile-card{{border-left:5px solid #2e86c1}}.button-row{{display:flex;gap:.7rem;flex-wrap:wrap;align-items:center}}.button-row form{{display:inline-block;margin:0}}
</style></head><body><header><h1>OpenScanStation</h1><div>Version {VERSION} · Port {DEFAULT_PORT}</div><nav><a href="/">Dashboard</a><a href="/documents">Dokumente</a><a href="/profiles">Scanprofile</a><a href="/scanner-actions">Scanneraktionen</a><a href="/system">System</a><a href="/api/scanners">API</a></nav></header><main>{note}{content}</main></body></html>'''


def _dashboard(message: str = "", error: bool = False) -> str:
    payload = _scanner_payload()
    profiles = load_profiles()
    actions = [a for a in load_actions()["actions"] if a.get("enabled")]
    cards, options, dpis = [], [], set()
    for scanner in payload["scanners"]:
        ready = scanner["connected"] and scanner["scan_supported"]
        cards.append(f'''<article class="card"><div class="headline"><h2>{html.escape(scanner['name'])}</h2><span class="{'ready' if ready else 'warning'}">{'Bereit' if ready else 'Prüfen'}</span></div><p><b>Backend:</b> {html.escape(scanner['backend'] or '-')}</p><p><b>Verbindung:</b> <code>{html.escape(scanner['connection'])}</code></p><p>{html.escape(scanner['message'])}</p></article>''')
        if ready:
            options.append(f'<option value="{html.escape(scanner["id"], quote=True)}">{html.escape(scanner["name"])}</option>')
            dpis.update(scanner["capabilities"]["resolutions_dpi"])
    if not cards:
        text = "Scannerstatus wird im Hintergrund geladen." if not payload.get("cache_ready") else "Kein Scanner gefunden. USB-Passthrough, Netzwerk und Treiber prüfen."
        cards = [f"<article class='card'><h2>Scanner</h2><p>{html.escape(text)}</p></article>"]
    profile_options = ''.join(f'<option value="{html.escape(k)}">{html.escape(v.get("label", k))}</option>' for k, v in profiles.items())
    dpi_options = ''.join(f'<option value="{d}" {"selected" if d == 300 else ""}>{d} dpi</option>' for d in sorted(dpis or set(ALLOWED_DPI)))
    form = "<p>Kein scanfähiger Scanner verfügbar.</p>"
    action_buttons = ""
    if options:
        form = f'''<form method="post" action="/scan"><div class="form-grid"><label>Titel<input name="title" value="Dokument"></label><label>Scanner<select name="scanner_id">{''.join(options)}</select></label><label>Profil<select name="profile">{profile_options}</select></label><label>Auflösung<select name="dpi">{dpi_options}</select></label><label>Farbmodus<select name="mode"><option value="color">Farbe</option><option value="gray">Graustufen</option><option value="lineart">Schwarz/Weiß</option></select></label><label>Format<select name="format"><option value="pdf">PDF</option><option value="png">PNG</option><option value="jpg">JPEG</option></select></label><label>Tags<input name="tags" placeholder="Rechnung, Kunde"></label><label>OCR<select name="ocr"><option value="1">Aktiv</option><option value="0">Aus</option></select></label></div><button type="submit">Scan starten</button></form>'''
        action_buttons = ''.join(f'''<article class="card action-card"><h3>{a['slot']}: {html.escape(a['label'])}</h3><p>{html.escape(a['title'])} · Profil {html.escape(a['profile'])}</p><form method="post" action="/run-action"><label>Scanner<select name="scanner_id">{''.join(options)}</select></label><input type="hidden" name="action_id" value="{html.escape(a['id'], quote=True)}"><button>Aktion starten</button></form></article>''' for a in actions)
    docs = list_documents(limit=10)
    rows = ''.join(f'<tr><td><a href="/scans/{quote(d["filename"])}">{html.escape(d["title"])}</a></td><td>{html.escape(d["scanner"])}</td><td>{html.escape(d["created_at"])}</td><td>{html.escape(d["ocr_status"])}</td></tr>' for d in docs) or '<tr><td colspan="4">Noch keine Dokumente.</td></tr>'
    updated = html.escape(payload.get("updated_at") or "noch nicht abgeschlossen")
    content = f'<section class="panel"><h2>Schnellaktionen</h2><div class="grid">{action_buttons or "<p>Keine aktiven Scanneraktionen oder kein Scanner verfügbar.</p>"}</div></section><section class="panel"><h2>Freier Scan</h2>{form}</section><div class="headline"><h2>Scanner</h2><form class="inline-form" method="post" action="/refresh-scanners"><button>Scanner neu suchen</button></form></div><p class="muted">Scannerstatus: {updated} · automatische Aktualisierung alle 10 Sekunden</p><div class="grid">{"".join(cards)}</div><section class="panel"><h2>Letzte Dokumente</h2><table><tr><th>Titel</th><th>Scanner</th><th>Zeit</th><th>OCR</th></tr>{rows}</table></section>'
    return _layout(content, notice=message, error=error)


def _scanner_actions_page(message: str = "", error: bool = False) -> str:
    data = load_actions()
    profiles = load_profiles()
    def profile_options(selected: str) -> str:
        return ''.join(f'<option value="{html.escape(pid)}" {"selected" if pid == selected else ""}>{html.escape(p.get("label", pid))}</option>' for pid, p in profiles.items())
    cards = []
    for action in data["actions"]:
        checked = "checked" if action.get("enabled") else ""
        cards.append(f'''<article class="card action-card"><h2>Funktion {action['slot']}</h2><form method="post" action="/scanner-actions/save"><input type="hidden" name="slot" value="{action['slot']}"><label><span>Aktiv</span><input type="checkbox" name="enabled" value="1" {checked}></label><label>Display-/Tastenname<input name="label" maxlength="32" value="{html.escape(action['label'], quote=True)}"></label><label>Dokumenttitel<input name="title" maxlength="120" value="{html.escape(action['title'], quote=True)}"></label><label>Scanprofil<select name="profile">{profile_options(action['profile'])}</select></label><label>Tags<input name="tags" value="{html.escape(', '.join(action.get('tags', [])), quote=True)}" placeholder="Rechnung, Eingang"></label><label>Ablageziel<input name="destination" value="{html.escape(action.get('destination', 'local'), quote=True)}"></label><label>Nachbearbeitung<input name="post_action" value="{html.escape(action.get('post_action', 'none'), quote=True)}"></label><button>Funktion speichern</button></form></article>''')
    info = '''<section class="panel"><h2>Kodak und Samsung</h2><p>Die Aktionen sind herstellerunabhängig. Kodak-Funktionsplätze und unterstützte Samsung-Tasten können später auf diese Aktionen gelegt werden.</p><p class="muted">Die physische Tasten- und Displayanbindung hängt vom jeweiligen Treiber und Modell ab. Web-Schnellaktionen funktionieren bereits ohne Hardwaretasten.</p></section>'''
    return _layout(info + '<div class="grid">' + ''.join(cards) + '</div>', "Scanneraktionen", message, error)


def _save_action(form: dict[str, list[str]]) -> dict:
    slot = int(form.get("slot", ["0"])[0])
    if slot < 1 or slot > 9:
        raise ValueError("Ungültiger Funktionsplatz")
    data = load_actions()
    action = next(item for item in data["actions"] if item["slot"] == slot)
    selected_profile = form.get("profile", [action["profile"]])[0]
    if selected_profile not in load_profiles():
        raise ValueError("Das gewählte Scanprofil existiert nicht")
    action.update({
        "enabled": form.get("enabled", ["0"])[0] == "1",
        "label": form.get("label", [action["label"]])[0],
        "title": form.get("title", [action["title"]])[0],
        "profile": selected_profile,
        "tags": [x.strip() for x in form.get("tags", [""])[0].split(",") if x.strip()],
        "destination": form.get("destination", ["local"])[0],
        "post_action": form.get("post_action", ["none"])[0],
    })
    return save_actions(data)


def _profile_values(form: dict[str, list[str]]) -> dict:
    return {
        "label": form.get("label", [""])[0],
        "dpi": form.get("dpi", ["300"])[0],
        "mode": form.get("mode", ["color"])[0],
        "format": form.get("format", ["pdf"])[0],
        "ocr": form.get("ocr", ["0"])[0] == "1",
        "duplex": form.get("duplex", ["0"])[0] == "1",
    }


def _profile_form_fields(profile_id: str, profile: dict, *, include_id: bool) -> str:
    id_field = f'<label>Profil-ID<input name="profile_id" maxlength="32" pattern="[a-z0-9][a-z0-9_-]*" value="{html.escape(profile_id, quote=True)}" required><span class="muted">z. B. buchhaltung oder foto_hoch</span></label>' if include_id else f'<input type="hidden" name="profile_id" value="{html.escape(profile_id, quote=True)}"><p><b>Profil-ID:</b> <code>{html.escape(profile_id)}</code></p>'
    dpi_options = ''.join(f'<option value="{dpi}" {"selected" if dpi == int(profile.get("dpi", 300)) else ""}>{dpi} dpi</option>' for dpi in ALLOWED_DPI)
    mode_labels = {"color": "Farbe", "gray": "Graustufen", "lineart": "Schwarz/Weiß"}
    mode_options = ''.join(f'<option value="{mode}" {"selected" if mode == profile.get("mode") else ""}>{mode_labels[mode]}</option>' for mode in ALLOWED_MODES)
    format_labels = {"pdf": "PDF", "png": "PNG", "jpg": "JPEG"}
    format_options = ''.join(f'<option value="{fmt}" {"selected" if fmt == profile.get("format") else ""}>{format_labels[fmt]}</option>' for fmt in ALLOWED_FORMATS)
    ocr_checked = "checked" if profile.get("ocr") else ""
    duplex_checked = "checked" if profile.get("duplex") else ""
    return f'''{id_field}<label>Anzeigename<input name="label" maxlength="80" value="{html.escape(str(profile.get('label', '')), quote=True)}" required></label><div class="form-grid"><label>Auflösung<select name="dpi">{dpi_options}</select></label><label>Farbmodus<select name="mode">{mode_options}</select></label><label>Ausgabeformat<select name="format">{format_options}</select></label><label><span>OCR aktivieren</span><input type="checkbox" name="ocr" value="1" {ocr_checked}></label><label><span>Duplex verwenden</span><input type="checkbox" name="duplex" value="1" {duplex_checked}></label></div>'''


def _profiles_page(message: str = "", error: bool = False) -> str:
    profiles = load_profiles()
    actions = load_actions()["actions"]
    cards = []
    for profile_id, profile in profiles.items():
        used_by = [str(a.get("label") or f"Funktion {a.get('slot')}") for a in actions if a.get("profile") == profile_id]
        usage = f'<p class="muted">Verwendet von: {html.escape(", ".join(used_by))}</p>' if used_by else '<p class="muted">Aktuell keiner Scanneraktion zugeordnet.</p>'
        delete_area = '<p class="muted">Zum Löschen zuerst die zugeordneten Scanneraktionen auf ein anderes Profil umstellen.</p>' if used_by else f'''<form method="post" action="/profiles/delete"><input type="hidden" name="profile_id" value="{html.escape(profile_id, quote=True)}"><button class="danger" type="submit">Profil löschen</button></form>'''
        cards.append(f'''<article class="card profile-card"><h2>{html.escape(profile.get('label', profile_id))}</h2>{usage}<form method="post" action="/profiles/save">{_profile_form_fields(profile_id, profile, include_id=False)}<button type="submit">Änderungen speichern</button></form><div class="button-row">{delete_area}</div></article>''')
    new_defaults = {"label": "Neues Profil", "dpi": 300, "mode": "color", "format": "pdf", "ocr": True, "duplex": False}
    create = f'''<section class="panel"><h2>Neues Scanprofil hinzufügen</h2><form method="post" action="/profiles/create">{_profile_form_fields('', new_defaults, include_id=True)}<button type="submit">Profil hinzufügen</button></form></section>'''
    info = '<section class="panel"><h2>Scanprofile verwalten</h2><p>Profile bestimmen Auflösung, Farbmodus, Dateiformat, OCR und Duplex. Änderungen stehen sofort im Dashboard und bei den Scanneraktionen zur Verfügung.</p><p class="muted">Speicherort: <code>/var/lib/openscanstation/profiles.json</code></p></section>'
    return _layout(info + create + '<div class="grid">' + ''.join(cards) + '</div>', "Scanprofile", message, error)


def _save_profile_from_form(form: dict[str, list[str]], *, create_only: bool) -> dict:
    profile_id = form.get("profile_id", [""])[0]
    return upsert_profile(profile_id, _profile_values(form), create_only=create_only)


def _delete_profile_from_form(form: dict[str, list[str]]) -> dict:
    profile_id = form.get("profile_id", [""])[0]
    used_by = [a for a in load_actions()["actions"] if a.get("profile") == profile_id]
    if used_by:
        raise ValueError("Das Profil wird noch von einer Scanneraktion verwendet")
    return delete_profile(profile_id)


def _documents_page(query: str = "", message: str = "", error: bool = False) -> str:
    docs = list_documents(query=query)
    rows = ''.join(f'''<tr><td><a href="/scans/{quote(d['filename'])}">{html.escape(d['title'])}</a><div class="muted">{html.escape(d['filename'])}</div></td><td>{html.escape(d['scanner'])}</td><td>{html.escape(', '.join(d['tags']))}</td><td>{html.escape(d['ocr_status'])}</td><td><form method="post" action="/ocr"><input type="hidden" name="filename" value="{html.escape(d['filename'], quote=True)}"><button>OCR starten</button></form></td></tr>''' for d in docs) or '<tr><td colspan="5">Keine Treffer.</td></tr>'
    content = f'''<section class="panel"><h2>Dokumentensuche</h2><form method="get" action="/documents"><div class="form-grid"><label>Suchbegriff<input name="q" value="{html.escape(query, quote=True)}" placeholder="Titel, Tag oder OCR-Text"></label></div><button>Suchen</button></form></section><section class="panel"><table><tr><th>Dokument</th><th>Scanner</th><th>Tags</th><th>OCR</th><th>Aktion</th></tr>{rows}</table></section>'''
    return _layout(content, "Dokumente", message, error)


def _system_page() -> str:
    data = system_payload()
    backup_rows = ''.join(f'<tr><td>{html.escape(item["name"])}</td><td>{html.escape(item["size_human"])}</td><td>{"Ja" if item["checksum"] else "Nein"}</td></tr>' for item in data["backups"]) or '<tr><td colspan="3">Noch keine Sicherungen gefunden.</td></tr>'
    content = f'''<div class="grid"><article class="card"><h2>Version</h2><div class="metric">{VERSION}</div><p>WebGUI auf Port {DEFAULT_PORT}</p></article><article class="card"><h2>Dokumente</h2><div class="metric">{data["document_count"]}</div><p>Datenbestand: {html.escape(data["data_size_human"])}</p></article><article class="card"><h2>Freier Speicher</h2><div class="metric">{html.escape(data["disk_free_human"])}</div><progress max="100" value="{data["disk_percent"]}"></progress><p>{data["disk_percent"]}% belegt</p></article></div><section class="panel"><h2>Pfade</h2><table><tr><th>Bereich</th><th>Pfad</th></tr><tr><td>Daten</td><td><code>{html.escape(data["data_dir"])}</code></td></tr><tr><td>Scans</td><td><code>{html.escape(data["scan_dir"])}</code></td></tr><tr><td>Sicherungen</td><td><code>{html.escape(data["backup_dir"])}</code></td></tr></table></section><section class="panel"><h2>Letzte Sicherungen</h2><p class="muted">Sicherungen werden über <code>sudo openscanstation-backup create</code> erstellt.</p><table><tr><th>Datei</th><th>Größe</th><th>Prüfsumme</th></tr>{backup_rows}</table></section><section class="panel"><h2>Diagnose</h2><code>openscanstation doctor</code></section>'''
    return _layout(content, "System")


class Handler(BaseHTTPRequestHandler):
    server_version = f"OpenScanStation/{VERSION}"

    def _send(self, body: bytes, ctype: str, status: HTTPStatus = HTTPStatus.OK, disposition: str | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status=HTTPStatus.OK):
        self._send(json.dumps(data, ensure_ascii=False, indent=2).encode(), "application/json; charset=utf-8", status)

    def _html(self, data, status=HTTPStatus.OK):
        self._send(data.encode(), "text/html; charset=utf-8", status)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._html(_dashboard())
        elif path == "/documents":
            self._html(_documents_page(parse_qs(parsed.query).get("q", [""])[0]))
        elif path == "/profiles":
            self._html(_profiles_page())
        elif path == "/scanner-actions":
            self._html(_scanner_actions_page())
        elif path == "/system":
            self._html(_system_page())
        elif path == "/health":
            self._json({"status": "ok", "service": "openscanstation", "version": VERSION, "port": DEFAULT_PORT})
        elif path == "/version":
            self._json({"version": VERSION})
        elif path == "/api/scanners":
            self._json(_scanner_payload())
        elif path == "/api/scanner-actions":
            self._json(load_actions())
        elif path == "/api/profiles":
            self._json({"profiles": load_profiles()})
        elif path == "/api/documents":
            self._json({"documents": list_documents(parse_qs(parsed.query).get("q", [""])[0])})
        elif path == "/api/system":
            self._json({"version": VERSION, **system_payload()})
        elif path.startswith("/scans/"):
            name = unquote(path.removeprefix("/scans/"))
            if not _SAFE_FILE.fullmatch(name):
                return self._json({"error": "invalid_filename"}, HTTPStatus.BAD_REQUEST)
            target = SCAN_DIR / name
            if not target.is_file():
                return self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            types = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
            self._send(target.read_bytes(), types.get(target.suffix.lower(), "application/octet-stream"), disposition=f'inline; filename="{target.name}"')
        else:
            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/refresh-scanners":
                _SCANNER_CACHE.request_refresh()
                self._html(_dashboard("Scanneraktualisierung wurde im Hintergrund gestartet."))
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise ValueError("Ungültige Formulardaten")
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            if path == "/scan":
                result = _perform_scan(form)
                msg = f"Scan erfolgreich: {result['filename']}" + (f"; OCR-Hinweis: {result['ocr_error']}" if result["ocr_error"] else "")
                self._html(_dashboard(msg))
                return
            if path == "/run-action":
                result = _perform_action(form.get("scanner_id", [""])[0], form.get("action_id", [""])[0])
                self._html(_dashboard(f"Scanneraktion erfolgreich: {result['filename']}"))
                return
            if path == "/scanner-actions/save":
                _save_action(form)
                self._html(_scanner_actions_page("Scanneraktion wurde gespeichert."))
                return
            if path == "/profiles/create":
                _save_profile_from_form(form, create_only=True)
                self._html(_profiles_page("Scanprofil wurde hinzugefügt."))
                return
            if path == "/profiles/save":
                _save_profile_from_form(form, create_only=False)
                self._html(_profiles_page("Scanprofil wurde gespeichert."))
                return
            if path == "/profiles/delete":
                _delete_profile_from_form(form)
                self._html(_profiles_page("Scanprofil wurde gelöscht."))
                return
            if path == "/ocr":
                filename = form.get("filename", [""])[0]
                if not _SAFE_FILE.fullmatch(filename):
                    raise ValueError("Ungültiger Dateiname")
                run_ocr(filename)
                self._html(_documents_page(message=f"OCR abgeschlossen: {filename}"))
                return
            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            if path.startswith("/profiles"):
                page = _profiles_page(str(exc), True)
            elif path.startswith("/scanner-actions"):
                page = _scanner_actions_page(str(exc), True)
            elif path == "/ocr":
                page = _documents_page(message=str(exc), error=True)
            else:
                page = _dashboard(str(exc), True)
            self._html(page, HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openscanstation-web")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    _SCANNER_CACHE.start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"OpenScanStation WebGUI {VERSION} läuft auf {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _SCANNER_CACHE.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
