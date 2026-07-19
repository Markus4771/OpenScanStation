"""Produktiver Webstart mit Kodak-schonender Erkennung und Profilbindung.

Der proprietäre KDS-i2000-Treiber darf nicht parallel oder mehrfach kurz
hintereinander geöffnet werden. Dieses Modul ergänzt die bestehende WebGUI,
ohne langsame SANE-Abfragen in HTTP-Anfragen auszuführen.
"""
from __future__ import annotations

import argparse
import html
import re
import subprocess
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import quote

import usb.core

from openscanstation import web
from openscanstation.documents import SCAN_DIR, add_document, list_documents, run_ocr
from openscanstation.profiles import ALLOWED_FORMATS, load_profiles
from openscanstation.scanner.manager import ScannerManager
from openscanstation.scanner_cache import ScannerCache
from openscanstation.scanner_actions import load_actions


_DEVICE_PATTERN = re.compile(r"device `(?P<device>[^']+)' is a (?P<label>.+)")
_KODAK_VENDOR_ID = 0x040A
_KODAK_PRODUCT_ID = 0x601D


def _short_name(scanner: dict) -> str:
    if scanner.get("plugin_id") == "kodak_i2600":
        return "Kodak i2600"
    if scanner.get("plugin_id") == "samsung_airscan":
        return "Samsung C48x"
    return str(scanner.get("model") or scanner.get("name") or "Scanner")


def _single_discovery() -> dict:
    """Fragt die SANE-Geräteliste nur einmal ab.

    Während eines Scans wird der zuletzt bekannte Zustand zurückgegeben. So
    kann der Hintergrund-Cache den alten Kodak-Treiber nicht parallel öffnen.
    """
    if web._SCAN_LOCK.locked():
        current = web._SCANNER_CACHE.snapshot()
        return {
            "version": web.VERSION,
            "scanners": current.get("scanners", []),
            "errors": current.get("errors", []),
        }

    scanners: list[dict] = []
    errors: list[dict] = []
    try:
        result = subprocess.run(
            ["scanimage", "-L"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout
    except FileNotFoundError:
        output = ""
        errors.append({"plugin_id": "sane", "message": "scanimage ist nicht installiert"})
    except subprocess.TimeoutExpired:
        output = ""
        errors.append({"plugin_id": "sane", "message": "Scannererkennung hat nach 60 Sekunden nicht geantwortet"})
    except subprocess.CalledProcessError as exc:
        output = exc.stdout or ""
        errors.append({
            "plugin_id": "sane",
            "message": (exc.stderr or "SANE-Erkennung fehlgeschlagen").strip(),
        })

    kodak_found = False
    for line in output.splitlines():
        match = _DEVICE_PATTERN.search(line.strip())
        if not match:
            continue
        connection = match.group("device")
        label = match.group("label")
        searchable = f"{connection} {label}".lower()

        if "kds_i2000" in searchable or "kodak" in searchable or "i2600" in searchable:
            kodak_found = True
            scanners.append({
                "id": f"kodak_i2600:{connection}",
                "name": "Kodak i2600",
                "manufacturer": "Kodak",
                "model": "i2600",
                "connection": connection,
                "plugin_id": "kodak_i2600",
                "state": "bereit",
                "connected": True,
                "backend": connection.split(":", 1)[0],
                "scan_supported": True,
                "message": "Kodak i2600 ist über den KDS-SANE-Treiber bereit.",
                "capabilities": {
                    "duplex": True,
                    "adf": True,
                    "resolutions_dpi": [100, 150, 200, 240, 300, 400, 600],
                    "color_modes": ["Farbe", "Graustufen", "Schwarz/Weiß"],
                },
            })
            continue

        if "samsung" in searchable:
            scanners.append({
                "id": f"samsung_airscan:{connection}",
                "name": "Samsung C48x",
                "manufacturer": "Samsung",
                "model": "C48x",
                "connection": connection,
                "plugin_id": "samsung_airscan",
                "state": "bereit",
                "connected": True,
                "backend": "sane-airscan",
                "scan_supported": True,
                "message": "Samsung C48x ist über AirScan erreichbar.",
                "capabilities": {
                    "duplex": False,
                    "adf": True,
                    "resolutions_dpi": [75, 100, 150, 200, 300, 600],
                    "color_modes": ["Farbe", "Graustufen", "Schwarz/Weiß"],
                },
            })

    if not kodak_found:
        device = usb.core.find(idVendor=_KODAK_VENDOR_ID, idProduct=_KODAK_PRODUCT_ID)
        if device is not None:
            scanners.append({
                "id": f"kodak_i2600:usb:{device.bus}:{device.address}",
                "name": "Kodak i2600",
                "manufacturer": "Kodak",
                "model": "i2600",
                "connection": f"usb:{device.bus}:{device.address}",
                "plugin_id": "kodak_i2600",
                "state": "offline",
                "connected": True,
                "backend": "libusb/pyusb",
                "scan_supported": False,
                "message": "USB erkannt, aber der KDS-SANE-Treiber hat den Scanner nicht geöffnet.",
                "capabilities": {
                    "duplex": True,
                    "adf": True,
                    "resolutions_dpi": [100, 150, 200, 240, 300, 400, 600],
                    "color_modes": ["Farbe", "Graustufen", "Schwarz/Weiß"],
                },
            })

    return {"version": web.VERSION, "scanners": scanners, "errors": errors}


def _find_scanner_without_rediscovery(scanner_id: str):
    """Verwendet die Cache-ID, ohne direkt vor dem Scan erneut scanimage -L aufzurufen."""
    if ":" not in scanner_id:
        return None, None
    plugin_id, connection = scanner_id.split(":", 1)
    manager = ScannerManager()
    plugin = manager.get_plugin(plugin_id)
    if plugin is None:
        return None, None

    cached = next(
        (item for item in web._SCANNER_CACHE.snapshot().get("scanners", []) if item.get("id") == scanner_id),
        None,
    )
    name = _short_name(cached or {"plugin_id": plugin_id})
    scanner = SimpleNamespace(
        plugin_id=plugin_id,
        connection=connection,
        name=name,
        model="i2600" if plugin_id == "kodak_i2600" else name,
    )
    return scanner, plugin


def _perform_profile_scan(form: dict[str, list[str]]) -> dict:
    """Wendet das gewählte Profil vollständig auf den Scanner an."""
    scanner_id = form.get("scanner_id", [""])[0]
    requested_profile_id = form.get("profile", ["dokument"])[0]
    profiles = load_profiles()
    default_profile_id = "dokument" if "dokument" in profiles else next(iter(profiles))
    profile_id = requested_profile_id if requested_profile_id in profiles else default_profile_id
    profile = profiles[profile_id]

    dpi = int(profile.get("dpi", 300))
    mode = str(profile.get("mode", "color"))
    output_format = str(profile.get("format", "pdf")).lower()
    title = form.get("title", [str(profile.get("label", "Dokument"))])[0].strip() or "Dokument"
    tags = [item.strip() for item in form.get("tags", [""])[0].split(",") if item.strip()]
    do_ocr = bool(profile.get("ocr", False))
    duplex = bool(profile.get("duplex", False))

    if output_format not in ALLOWED_FORMATS:
        raise ValueError("Ungültiges Ausgabeformat im Scanprofil")

    scanner, plugin = _find_scanner_without_rediscovery(scanner_id)
    if scanner is None or plugin is None:
        raise RuntimeError("Scanner nicht gefunden")
    if scanner.connection.startswith("usb:"):
        raise RuntimeError("Kodak ist per USB sichtbar, aber noch nicht als KDS-SANE-Gerät verfügbar")

    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"scan-{stamp}-{scanner.plugin_id}.{output_format}"
    target = SCAN_DIR / filename

    with web._SCAN_LOCK:
        result = plugin.start_scan(scanner.connection, {
            "output": str(target),
            "dpi": dpi,
            "mode": mode,
            "duplex": duplex,
            "profile_id": profile_id,
        })

    add_document(filename, title, scanner.name, profile_id, output_format, 1, tags)
    ocr_error = ""
    if do_ocr:
        try:
            run_ocr(filename)
        except Exception as exc:
            ocr_error = str(exc)
    web._SCANNER_CACHE.request_refresh()
    return {
        "ok": True,
        "filename": filename,
        "bytes": result.bytes_written,
        "download_url": f"/scans/{quote(filename)}",
        "ocr_error": ocr_error,
    }


def _dashboard(message: str = "", error: bool = False) -> str:
    payload = web._scanner_payload()
    profiles = load_profiles()
    actions = [item for item in load_actions()["actions"] if item.get("enabled")]
    cards: list[str] = []
    options: list[str] = []

    for scanner in payload.get("scanners", []):
        ready = bool(scanner.get("connected") and scanner.get("scan_supported"))
        short = _short_name(scanner)
        cards.append(
            f'''<article class="card"><div class="headline"><h2>{html.escape(short)}</h2>'''
            f'''<span class="{'ready' if ready else 'warning'}">{'Bereit' if ready else 'Prüfen'}</span></div>'''
            f'''<p><b>Backend:</b> {html.escape(str(scanner.get('backend') or '-'))}</p>'''
            f'''<p><b>Verbindung:</b> <code>{html.escape(str(scanner.get('connection') or '-'))}</code></p>'''
            f'''<p>{html.escape(str(scanner.get('message') or ''))}</p></article>'''
        )
        if ready:
            options.append(
                f'<option value="{html.escape(str(scanner["id"]), quote=True)}">{html.escape(short)}</option>'
            )

    if not cards:
        text = "Scannerstatus wird im Hintergrund geladen." if not payload.get("cache_ready") else "Kein Scanner gefunden."
        cards = [f"<article class='card'><h2>Scanner</h2><p>{html.escape(text)}</p></article>"]

    profile_options = "".join(
        f'<option value="{html.escape(profile_id)}">{html.escape(str(profile.get("label", profile_id)))}</option>'
        for profile_id, profile in profiles.items()
    )
    scanner_options = "".join(options)
    free_form = "<p>Kein scanfähiger Scanner verfügbar.</p>"
    action_buttons = ""

    if options:
        free_form = f'''<form method="post" action="/scan"><div class="form-grid">'''
        free_form += '''<label>Titel<input name="title" value="Dokument"></label>'''
        free_form += f'''<label>Scanner<select class="scanner-select" name="scanner_id">{scanner_options}</select></label>'''
        free_form += f'''<label>Scanprofil<select name="profile">{profile_options}</select></label>'''
        free_form += '''<label>Tags<input name="tags" placeholder="Rechnung, Kunde"></label></div>'''
        free_form += '''<p class="muted">Auflösung, Farbe, Format, OCR und Duplex werden vollständig aus dem gewählten Profil übernommen.</p><button type="submit">Scan starten</button></form>'''

        action_cards: list[str] = []
        for action in actions:
            profile_id = str(action.get("profile", "dokument"))
            profile_label = str(profiles.get(profile_id, {}).get("label", profile_id))
            action_cards.append(
                f'''<article class="card action-card"><h3>{action['slot']}: {html.escape(str(action['label']))}</h3>'''
                f'''<p>{html.escape(str(action['title']))} · {html.escape(profile_label)}</p>'''
                f'''<form method="post" action="/run-action"><label>Scanner'''
                f'''<select class="scanner-select" name="scanner_id">{scanner_options}</select></label>'''
                f'''<input type="hidden" name="action_id" value="{html.escape(str(action['id']), quote=True)}">'''
                f'''<button>Aktion starten</button></form></article>'''
            )
        action_buttons = "".join(action_cards)

    docs = list_documents(limit=10)
    rows = "".join(
        f'<tr><td><a href="/scans/{quote(item["filename"])}">{html.escape(item["title"])}</a></td>'
        f'<td>{html.escape(item["scanner"])}</td><td>{html.escape(item["created_at"])}</td>'
        f'<td>{html.escape(item["ocr_status"])}</td></tr>'
        for item in docs
    ) or '<tr><td colspan="4">Noch keine Dokumente.</td></tr>'

    updated = html.escape(str(payload.get("updated_at") or "noch nicht abgeschlossen"))
    content = (
        f'<section class="panel"><h2>Schnellaktionen</h2><div class="grid">'
        f'{action_buttons or "<p>Keine aktiven Scanneraktionen oder kein Scanner verfügbar.</p>"}</div></section>'
        f'<section class="panel"><h2>Freier Scan</h2>{free_form}</section>'
        f'<div class="headline"><h2>Scanner</h2><form class="inline-form" method="post" action="/refresh-scanners">'
        f'<button>Scanner neu suchen</button></form></div>'
        f'<p class="muted">Scannerstatus: {updated} · automatische Erkennung im Hintergrund</p>'
        f'<div class="grid">{"".join(cards)}</div>'
        f'<section class="panel"><h2>Letzte Dokumente</h2><table><tr><th>Titel</th><th>Scanner</th>'
        f'<th>Zeit</th><th>OCR</th></tr>{rows}</table></section>'
    )
    page = web._layout(content, notice=message, error=error)
    return page.replace("<head>", '<head><meta http-equiv="refresh" content="30">', 1)


def _install_patches() -> None:
    original_layout = web._layout

    def responsive_layout(content: str, title: str = "OpenScanStation", notice: str = "", error: bool = False) -> str:
        page = original_layout(content, title, notice, error)
        extra = (
            ".card,.panel,.action-card,form,label{min-width:0}"
            "input,select,button{box-sizing:border-box;max-width:100%}"
            "select.scanner-select{display:block;width:100%;min-width:0;overflow:hidden;text-overflow:ellipsis}"
            ".action-card{overflow:hidden}"
        )
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
    parser.add_argument("--host", default=web.DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=web.DEFAULT_PORT)
    args = parser.parse_args(argv)
    web._SCANNER_CACHE.start()
    server = web.ThreadingHTTPServer((args.host, args.port), web.Handler)
    print(f"OpenScanStation WebGUI {web.VERSION} läuft auf {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        web._SCANNER_CACHE.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
