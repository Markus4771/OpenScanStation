"""Produktiver Webstart mit scannerfreundlicher Erkennung und Scannerverwaltung."""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from datetime import datetime
from http import HTTPStatus
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, urlparse

import usb.core

from openscanstation import web
from openscanstation.documents import SCAN_DIR, add_document, list_documents, run_ocr
from openscanstation.profiles import ALLOWED_FORMATS, load_profiles
from openscanstation.scanner.manager import ScannerManager
from openscanstation.scanner_cache import ScannerCache
from openscanstation.scanner_actions import load_actions
from openscanstation.scanner_settings import (
    default_scanner_id,
    load_settings,
    render_page,
    scanner_name,
    test_connection,
    update_scanner,
    visible_scanners,
)

_DEVICE_PATTERN = re.compile(r"device `(?P<device>[^']+)' is a (?P<label>.+)")
_KODAK_VENDOR_ID = 0x040A
_KODAK_PRODUCT_ID = 0x601D


def _short_name(scanner: dict) -> str:
    if scanner.get("plugin_id") == "kodak_i2600":
        return "Kodak i2600"
    if scanner.get("plugin_id") == "samsung_airscan":
        return "Samsung C48x"
    if scanner.get("plugin_id") == "brother_ads":
        return "Brother ADS-2600We" if "2600" in str(scanner.get("model", "")) else str(scanner.get("model") or "Brother ADS")
    return str(scanner.get("model") or scanner.get("name") or "Scanner")


def _single_discovery() -> dict:
    """Fragt SANE nur einmal ab und vermeidet parallele Treiberzugriffe."""
    if web._SCAN_LOCK.locked():
        current = web._SCANNER_CACHE.snapshot()
        return {"version": web.VERSION, "scanners": current.get("scanners", []), "errors": current.get("errors", [])}

    scanners: list[dict] = []
    errors: list[dict] = []
    try:
        result = subprocess.run(["scanimage", "-L"], check=True, capture_output=True, text=True, timeout=60)
        output = result.stdout
    except FileNotFoundError:
        output = ""
        errors.append({"plugin_id": "sane", "message": "scanimage ist nicht installiert"})
    except subprocess.TimeoutExpired:
        output = ""
        errors.append({"plugin_id": "sane", "message": "Scannererkennung hat nach 60 Sekunden nicht geantwortet"})
    except subprocess.CalledProcessError as exc:
        output = exc.stdout or ""
        errors.append({"plugin_id": "sane", "message": (exc.stderr or "SANE-Erkennung fehlgeschlagen").strip()})

    kodak_found = False
    for line in output.splitlines():
        match = _DEVICE_PATTERN.search(line.strip())
        if not match:
            continue
        connection = match.group("device")
        label = match.group("label")
        searchable = f"{connection} {label}".lower()
        common = {
            "connection": connection,
            "state": "bereit",
            "connected": True,
            "scan_supported": True,
        }
        if "kds_i2000" in searchable or "kodak" in searchable or "i2600" in searchable:
            kodak_found = True
            scanners.append({
                **common, "id": f"kodak_i2600:{connection}", "name": "Kodak i2600", "manufacturer": "Kodak",
                "model": "i2600", "plugin_id": "kodak_i2600", "backend": connection.split(":", 1)[0],
                "message": "Kodak i2600 ist über den KDS-SANE-Treiber bereit.",
                "capabilities": {"duplex": True, "adf": True, "resolutions_dpi": [100,150,200,240,300,400,600], "color_modes": ["Farbe","Graustufen","Schwarz/Weiß"]},
            })
        elif "brother" in searchable and ("ads" in searchable or "2600" in searchable):
            model = "ADS-2600We" if "2600" in searchable else label
            scanners.append({
                **common, "id": f"brother_ads:{connection}", "name": f"Brother {model}", "manufacturer": "Brother",
                "model": model, "plugin_id": "brother_ads", "backend": connection.split(":", 1)[0],
                "message": "Brother ADS ist über SANE/AirScan erreichbar.",
                "capabilities": {"duplex": True, "adf": True, "resolutions_dpi": [100,150,200,300,400,600], "color_modes": ["Farbe","Graustufen","Schwarz/Weiß"]},
            })
        elif "samsung" in searchable:
            scanners.append({
                **common, "id": f"samsung_airscan:{connection}", "name": "Samsung C48x", "manufacturer": "Samsung",
                "model": "C48x", "plugin_id": "samsung_airscan", "backend": "sane-airscan",
                "message": "Samsung C48x ist über AirScan erreichbar.",
                "capabilities": {"duplex": False, "adf": True, "resolutions_dpi": [75,100,150,200,300,600], "color_modes": ["Farbe","Graustufen","Schwarz/Weiß"]},
            })

    if not kodak_found:
        device = usb.core.find(idVendor=_KODAK_VENDOR_ID, idProduct=_KODAK_PRODUCT_ID)
        if device is not None:
            scanners.append({
                "id": f"kodak_i2600:usb:{device.bus}:{device.address}", "name": "Kodak i2600", "manufacturer": "Kodak",
                "model": "i2600", "connection": f"usb:{device.bus}:{device.address}", "plugin_id": "kodak_i2600",
                "state": "offline", "connected": True, "backend": "libusb/pyusb", "scan_supported": False,
                "message": "USB erkannt, aber der KDS-SANE-Treiber hat den Scanner nicht geöffnet.",
                "capabilities": {"duplex": True, "adf": True, "resolutions_dpi": [100,150,200,240,300,400,600], "color_modes": ["Farbe","Graustufen","Schwarz/Weiß"]},
            })
    return {"version": web.VERSION, "scanners": scanners, "errors": errors}


def _find_scanner_without_rediscovery(scanner_id: str):
    if ":" not in scanner_id:
        return None, None
    plugin_id, connection = scanner_id.split(":", 1)
    manager = ScannerManager()
    plugin = manager.get_plugin(plugin_id)
    if plugin is None:
        return None, None
    cached = next((item for item in web._SCANNER_CACHE.snapshot().get("scanners", []) if item.get("id") == scanner_id), None)
    name = scanner_name(cached) if cached else _short_name({"plugin_id": plugin_id})
    return SimpleNamespace(plugin_id=plugin_id, connection=connection, name=name, model=(cached or {}).get("model", name)), plugin


def _perform_profile_scan(form: dict[str, list[str]]) -> dict:
    scanner_id = form.get("scanner_id", [""])[0]
    profiles = load_profiles()
    requested = form.get("profile", ["dokument"])[0]
    fallback = "dokument" if "dokument" in profiles else next(iter(profiles))
    profile_id = requested if requested in profiles else fallback
    profile = profiles[profile_id]
    dpi = int(profile.get("dpi", 300)); mode = str(profile.get("mode", "color")); output_format = str(profile.get("format", "pdf")).lower()
    title = form.get("title", [str(profile.get("label", "Dokument"))])[0].strip() or "Dokument"
    tags = [item.strip() for item in form.get("tags", [""])[0].split(",") if item.strip()]
    if output_format not in ALLOWED_FORMATS:
        raise ValueError("Ungültiges Ausgabeformat im Scanprofil")
    scanner, plugin = _find_scanner_without_rediscovery(scanner_id)
    if scanner is None or plugin is None:
        raise RuntimeError("Scanner nicht gefunden")
    if scanner.connection.startswith("usb:"):
        raise RuntimeError("Scanner ist per USB sichtbar, aber noch nicht als SANE-Gerät verfügbar")
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"scan-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{scanner.plugin_id}.{output_format}"
    target = SCAN_DIR / filename
    with web._SCAN_LOCK:
        result = plugin.start_scan(scanner.connection, {"output": str(target), "dpi": dpi, "mode": mode, "duplex": bool(profile.get("duplex")), "profile_id": profile_id})
    add_document(filename, title, scanner.name, profile_id, output_format, 1, tags, form.get("owner", [""])[0])
    ocr_error = ""
    if bool(profile.get("ocr", False)):
        try: run_ocr(filename)
        except Exception as exc: ocr_error = str(exc)
    web._SCANNER_CACHE.request_refresh()
    return {"ok": True, "filename": filename, "bytes": result.bytes_written, "download_url": f"/scans/{quote(filename)}", "ocr_error": ocr_error}


def _dashboard(message: str = "", error: bool = False, username: str = "", is_admin: bool = False, allowed_scanners: set[str] | None = None) -> str:
    payload = web._scanner_payload()
    scanners = visible_scanners(payload.get("scanners", []))
    if not is_admin and allowed_scanners is not None:
        scanners = [scanner for scanner in scanners if scanner.get("id") in allowed_scanners]
    default_id = default_scanner_id(scanners)
    profiles = load_profiles()
    actions = [item for item in load_actions()["actions"] if item.get("enabled")]
    cards, options = [], []
    for scanner in scanners:
        ready = bool(scanner.get("connected") and scanner.get("scan_supported")); name = scanner_name(scanner)
        cards.append(f'''<article class="card"><div class="headline"><h2>{html.escape(name)}</h2><span class="{'ready' if ready else 'warning'}">{'Bereit' if ready else 'Prüfen'}</span></div><p><b>Backend:</b> {html.escape(str(scanner.get('backend') or '-'))}</p><p><b>Verbindung:</b> <code>{html.escape(str(scanner.get('connection') or '-'))}</code></p><p>{html.escape(str(scanner.get('message') or ''))}</p><p><a href="/scanners">Scanner einrichten</a></p></article>''')
        if ready:
            options.append(f'<option value="{html.escape(str(scanner["id"]), quote=True)}" {"selected" if scanner.get("id") == default_id else ""}>{html.escape(name)}</option>')
    if not cards:
        cards = ["<article class='card'><h2>Kein Scanner gefunden</h2><p><a href='/scanners'>Scanner einrichten und Diagnose öffnen</a></p></article>"]
    profile_options = "".join(f'<option value="{html.escape(pid)}">{html.escape(str(p.get("label", pid)))}</option>' for pid,p in profiles.items())
    scanner_options = "".join(options)
    free_form = "<p>Kein scanfähiger Scanner verfügbar.</p>"
    action_buttons = ""
    if options:
        free_form = f'''<form method="post" action="/scan"><div class="form-grid"><label>Titel<input name="title" value="Dokument"></label><label>Scanner<select class="scanner-select" name="scanner_id">{scanner_options}</select></label><label>Scanprofil<select name="profile">{profile_options}</select></label><label>Tags<input name="tags" placeholder="Rechnung, Kunde"></label></div><p class="muted">Auflösung, Farbe, Format, OCR und Duplex kommen aus dem Scanprofil.</p><button>Scan starten</button></form>'''
        action_buttons = "".join(f'''<article class="card action-card"><h3>{a['slot']}: {html.escape(str(a['label']))}</h3><form method="post" action="/run-action"><label>Scanner<select class="scanner-select" name="scanner_id">{scanner_options}</select></label><input type="hidden" name="action_id" value="{html.escape(str(a['id']), quote=True)}"><button>Aktion starten</button></form></article>''' for a in actions)
    docs = list_documents(limit=10, owner=None if is_admin else username)
    rows = "".join(f'<tr><td><a href="/scans/{quote(d["filename"])}">{html.escape(d["title"])}</a></td><td>{html.escape(d["scanner"])}</td><td>{html.escape(d["created_at"])}</td><td>{html.escape(d["ocr_status"])}</td></tr>' for d in docs) or '<tr><td colspan="4">Noch keine Dokumente.</td></tr>'
    content = f'<section class="panel"><h2>Schnellaktionen</h2><div class="grid">{action_buttons or "<p>Keine aktiven Scanneraktionen.</p>"}</div></section><section class="panel"><h2>Freier Scan</h2>{free_form}</section><div class="headline"><h2>Scanner</h2><div><a href="/scanners">Einrichten</a> · <form class="inline-form" method="post" action="/refresh-scanners"><button>Neu suchen</button></form></div></div><div class="grid">{"".join(cards)}</div><section class="panel"><h2>Letzte Dokumente</h2><table><tr><th>Titel</th><th>Scanner</th><th>Zeit</th><th>OCR</th></tr>{rows}</table></section>'
    return web._layout(content, notice=message, error=error).replace("<head>", '<head><meta http-equiv="refresh" content="30">', 1)


class RuntimeHandler(web.Handler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/scanners":
            scanners = web._SCANNER_CACHE.snapshot().get("scanners", [])
            self._html(web._layout(render_page(scanners), "Scanner einrichten")); return
        if path == "/api/scanner-settings":
            self._json({"settings": load_settings(), "scanners": web._SCANNER_CACHE.snapshot().get("scanners", [])}); return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/scanners/"):
            super().do_POST(); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise ValueError("Ungültige Formulardaten")
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            scanners = web._SCANNER_CACHE.snapshot().get("scanners", [])
            if path == "/scanners/save":
                update_scanner(form.get("scanner_id", [""])[0], alias=form.get("alias", [""])[0], enabled=form.get("enabled", ["1"])[0] == "1", make_default=form.get("make_default", ["0"])[0] == "1")
                self._html(web._layout(render_page(scanners, notice="Scanner wurde gespeichert."), "Scanner einrichten")); return
            if path == "/scanners/test":
                result = test_connection(form.get("scanner_id", [""])[0], scanners)
                self._html(web._layout(render_page(scanners, notice="Verbindungstest abgeschlossen.", test_result=result), "Scanner einrichten")); return
            if path == "/scanners/refresh":
                web._SCANNER_CACHE.request_refresh()
                self._html(web._layout(render_page(scanners, notice="Scanner-Suche wurde gestartet."), "Scanner einrichten")); return
            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            scanners = web._SCANNER_CACHE.snapshot().get("scanners", [])
            self._html(web._layout(render_page(scanners, notice=str(exc), error=True), "Scanner einrichten"), HTTPStatus.BAD_REQUEST)


def _install_patches() -> None:
    original_layout = web._layout
    def responsive_layout(content: str, title: str = "OpenScanStation", notice: str = "", error: bool = False) -> str:
        page = original_layout(content, title, notice, error)
        page = page.replace('<a href="/documents">Dokumente</a>', '<a href="/documents">Dokumente</a><a href="/scanners">Scanner einrichten</a>', 1)
        extra = ".card,.panel,.action-card,form,label{min-width:0}input,select,button{box-sizing:border-box;max-width:100%}select.scanner-select{display:block;width:100%;min-width:0}.action-card{overflow:hidden}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f7f7;padding:.8rem;border-radius:8px}"
        return page.replace("</style>", extra + "</style>", 1)
    web._layout = responsive_layout
    web._discover_scanners = _single_discovery
    web._SCANNER_CACHE = ScannerCache(_single_discovery, interval_seconds=30)
    web._find_scanner = _find_scanner_without_rediscovery
    web._perform_scan = _perform_profile_scan
    web._dashboard = _dashboard


def main(argv: list[str] | None = None) -> int:
    _install_patches()
    parser = argparse.ArgumentParser(prog="openscanstation-web")
    parser.add_argument("--host", default=web.DEFAULT_HOST); parser.add_argument("--port", type=int, default=web.DEFAULT_PORT)
    args = parser.parse_args(argv)
    web._SCANNER_CACHE.start()
    server = web.ThreadingHTTPServer((args.host, args.port), RuntimeHandler)
    print(f"OpenScanStation WebGUI {web.VERSION} läuft auf {args.host}:{args.port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        web._SCANNER_CACHE.stop(); server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
