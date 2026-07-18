"""Einfache OpenScanStation-WebGUI und REST-Endpunkte auf Port 8101."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from openscanstation.cli import VERSION
from openscanstation.scanner.manager import ScannerManager

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8101


def _scanner_payload() -> dict:
    manager = ScannerManager()
    result = manager.discover()
    scanners = []
    for scanner in result.scanners:
        plugin = manager.get_plugin(scanner.plugin_id)
        status = plugin.get_status(scanner.connection) if plugin else None
        scanners.append(
            {
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
            }
        )
    return {
        "version": VERSION,
        "scanners": scanners,
        "errors": [
            {"plugin_id": error.plugin_id, "message": error.message}
            for error in result.errors
        ],
    }


def _html_page(payload: dict) -> str:
    cards = []
    for scanner in payload["scanners"]:
        ready = scanner["connected"] and scanner["scan_supported"]
        status_class = "ready" if ready else "warning"
        status_text = "Bereit" if ready else "Treiber/Verbindung prüfen"
        cards.append(
            f"""
            <article class="card">
              <div class="headline"><h2>{scanner['name']}</h2><span class="{status_class}">{status_text}</span></div>
              <dl>
                <dt>Modell</dt><dd>{scanner['manufacturer']} {scanner['model']}</dd>
                <dt>Verbindung</dt><dd><code>{scanner['connection']}</code></dd>
                <dt>Backend</dt><dd>{scanner['backend'] or '-'}</dd>
                <dt>Scannen</dt><dd>{'Ja' if scanner['scan_supported'] else 'Noch nicht'}</dd>
                <dt>ADF / Duplex</dt><dd>{'Ja' if scanner['capabilities']['adf'] else 'Nein'} / {'Ja' if scanner['capabilities']['duplex'] else 'Nein'}</dd>
              </dl>
              <p>{scanner['message']}</p>
            </article>
            """
        )
    if not cards:
        cards.append("<article class='card'><h2>Kein Scanner gefunden</h2><p>Prüfe USB-Passthrough, Stromversorgung und Treiber.</p></article>")

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenScanStation</title>
<style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f4f6f8;color:#17202a}}
header{{background:#17202a;color:white;padding:1.4rem 2rem}}
main{{max-width:1100px;margin:2rem auto;padding:0 1rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}}
.card{{background:white;border-radius:12px;padding:1.3rem;box-shadow:0 2px 12px #0001}}
.headline{{display:flex;justify-content:space-between;gap:1rem;align-items:center}}
.ready,.warning{{padding:.3rem .6rem;border-radius:999px;font-size:.85rem;font-weight:700}}
.ready{{background:#d5f5e3;color:#196f3d}} .warning{{background:#fdebd0;color:#935116}}
dl{{display:grid;grid-template-columns:120px 1fr;gap:.45rem}}dt{{font-weight:700}}dd{{margin:0;overflow-wrap:anywhere}}
nav a{{color:white;margin-right:1rem}}code{{font-size:.85rem}}
</style>
</head>
<body>
<header><h1>OpenScanStation</h1><p>Version {VERSION} · WebGUI Port {DEFAULT_PORT}</p><nav><a href="/">Dashboard</a><a href="/api/scanners">Scanner-API</a><a href="/health">Health</a></nav></header>
<main><h2>Scannerstatus</h2><div class="grid">{''.join(cards)}</div></main>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = f"OpenScanStation/{VERSION}"

    def _send_json(self, data: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({"status": "ok", "service": "openscanstation", "version": VERSION, "port": DEFAULT_PORT})
            return
        if path == "/version":
            self._send_json({"version": VERSION})
            return
        if path == "/api/scanners":
            self._send_json(_scanner_payload())
            return
        if path == "/":
            self._send_html(_html_page(_scanner_payload()))
            return
        self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openscanstation-web")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"OpenScanStation WebGUI {VERSION} läuft auf {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
