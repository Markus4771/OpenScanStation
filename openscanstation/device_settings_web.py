"""Weboberfläche für gerätebezogene Scanner-Einstellungen auf Port 8102."""
from __future__ import annotations

import argparse
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from openscanstation.cli import VERSION
from openscanstation.device_settings import get_device_setting, load_device_settings, set_device_standby
from openscanstation.scanner.manager import ScannerManager

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8102


def _kodak_devices() -> list[dict]:
    manager = ScannerManager()
    result = manager.discover()
    devices = []
    for scanner in result.scanners:
        if scanner.plugin_id != "kodak_i2600":
            continue
        plugin = manager.get_plugin(scanner.plugin_id)
        status = plugin.get_status(scanner.connection) if plugin else None
        details = status.details if status else {}
        devices.append({
            "id": scanner.connection,
            "name": scanner.name,
            "connected": bool(status and status.connected),
            "backend": status.backend if status else None,
            "message": status.message if status else "Plugin nicht verfügbar",
            "details": details,
            "settings": get_device_setting(scanner.connection),
        })
    return devices


def _layout(content: str, notice: str = "", error: bool = False) -> str:
    note = ""
    if notice:
        css = "error" if error else "success"
        note = f'<div class="notice {css}">{html.escape(notice)}</div>'
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenScanStation – Geräteeinstellungen</title><style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f3f5f7;color:#17202a}}
header{{background:#17202a;color:white;padding:1.3rem 2rem}}header h1{{margin:0}}
main{{max-width:1000px;margin:1.5rem auto;padding:0 1rem}}
.card,.panel{{background:white;border-radius:12px;padding:1.2rem;box-shadow:0 2px 12px #0001;margin-bottom:1rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem}}
label{{display:grid;gap:.35rem;font-weight:700;margin:.8rem 0}}
input,button{{padding:.75rem;border:1px solid #bcc5cc;border-radius:8px}}
input[type=checkbox]{{width:auto}}button{{background:#17202a;color:white;font-weight:700;cursor:pointer}}
.notice{{padding:1rem;border-radius:8px;margin-bottom:1rem}}.success{{background:#d5f5e3}}.error{{background:#fadbd8}}
.ready{{color:#196f3d;font-weight:700}}.warning{{color:#935116;font-weight:700}}code{{overflow-wrap:anywhere}}
</style></head><body><header><h1>OpenScanStation</h1><div>Geräteeinstellungen · Version {VERSION} · Port {DEFAULT_PORT}</div></header><main>{note}{content}</main></body></html>'''


def _page(notice: str = "", error: bool = False) -> str:
    devices = _kodak_devices()
    cards = []
    for device in devices:
        setting = device["settings"]
        details = device.get("details") or {}
        supported = details.get("standby_supported")
        support_text = "Ja" if supported is True else ("Nein" if supported is False else "Noch nicht geprüft")
        option = details.get("standby_option") or "keine erkannt"
        checked = "checked" if setting.get("standby_enabled", True) else ""
        state_class = "ready" if device["connected"] else "warning"
        state_text = "Verbunden" if device["connected"] else "Nicht verbunden"
        cards.append(f'''<article class="card"><h2>{html.escape(device['name'])}</h2>
<p class="{state_class}">{state_text}</p>
<p><b>Gerät:</b> <code>{html.escape(device['id'])}</code></p>
<p><b>Backend:</b> {html.escape(device.get('backend') or '-')}</p>
<p><b>Treiberoption:</b> {html.escape(str(option))}</p>
<p><b>Standby steuerbar:</b> {support_text}</p>
<p>{html.escape(device.get('message') or '')}</p>
<form method="post" action="/standby">
<input type="hidden" name="device_id" value="{html.escape(device['id'], quote=True)}">
<label><span>Standby aktiv</span><input type="checkbox" name="enabled" value="1" {checked}></label>
<label>Standby nach Minuten<input type="number" name="minutes" min="0" max="240" required value="{int(setting.get('standby_minutes', 15))}"></label>
<button type="submit">Standby-Zeit speichern</button></form></article>''')
    if not cards:
        cards.append('''<article class="card"><h2>Kein Kodak gefunden</h2>
<p>Prüfe auf dem Server mit <code>scanimage -L</code>, ob der Kodak i2600 erkannt wird.</p></article>''')
    content = '''<section class="panel"><h2>Kodak-Energieverwaltung</h2>
<p>Hier legst du fest, nach wie vielen Minuten der Kodak i2600 in den Standby wechseln soll.</p>
<p>Die Einstellung wird gespeichert und beim nächsten Kodak-Zugriff an den SANE-Treiber übergeben.</p></section><div class="grid">''' + "".join(cards) + "</div>"
    return _layout(content, notice, error)


class Handler(BaseHTTPRequestHandler):
    server_version = f"OpenScanStation-DeviceSettings/{VERSION}"

    def _send(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, value: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(value.encode("utf-8"), "text/html; charset=utf-8", status)

    def _json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8", status)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._html(_page())
        elif path == "/health":
            self._json({"status": "ok", "service": "openscanstation-device-settings", "version": VERSION, "port": DEFAULT_PORT})
        elif path == "/api/device-settings":
            self._json({"settings": load_device_settings(), "kodak_devices": _kodak_devices()})
        else:
            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path != "/standby":
                self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16384:
                raise ValueError("Ungültige Formulardaten")
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=False)
            device_id = form.get("device_id", [""])[0]
            minutes = int(form.get("minutes", ["15"])[0])
            enabled = form.get("enabled", ["0"])[0] == "1"
            set_device_standby(device_id, minutes, enabled)
            self._html(_page("Kodak-Standby-Zeit wurde gespeichert."))
        except Exception as exc:
            self._html(_page(str(exc), True), HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openscanstation-device-settings-web")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"OpenScanStation Geräteeinstellungen {VERSION} läuft auf {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
