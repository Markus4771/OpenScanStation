"""OpenScanStation-WebGUI und REST-Endpunkte auf Port 8101."""

from __future__ import annotations

import argparse
import html
import json
import re
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from openscanstation.cli import VERSION
from openscanstation.scanner.manager import ScannerManager

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8101
SCAN_DIR = Path("/var/lib/openscanstation/scans")
_SCAN_LOCK = threading.Lock()
_SAFE_FILE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _scanner_payload() -> dict:
    manager = ScannerManager()
    result = manager.discover()
    scanners = []
    for scanner in result.scanners:
        plugin = manager.get_plugin(scanner.plugin_id)
        status = plugin.get_status(scanner.connection) if plugin else None
        scanners.append(
            {
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
            }
        )
    return {
        "version": VERSION,
        "scanners": scanners,
        "errors": [{"plugin_id": error.plugin_id, "message": error.message} for error in result.errors],
    }


def _recent_scans() -> list[dict]:
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted((p for p in SCAN_DIR.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "name": item.name,
            "size": item.stat().st_size,
            "created": datetime.fromtimestamp(item.stat().st_mtime).strftime("%d.%m.%Y %H:%M:%S"),
            "url": f"/scans/{quote(item.name)}",
        }
        for item in files[:25]
    ]


def _find_scanner(scanner_id: str):
    manager = ScannerManager()
    result = manager.discover()
    for scanner in result.scanners:
        candidate = f"{scanner.plugin_id}:{scanner.connection}"
        if candidate == scanner_id:
            plugin = manager.get_plugin(scanner.plugin_id)
            return scanner, plugin
    return None, None


def _perform_scan(form: dict[str, list[str]]) -> dict:
    scanner_id = form.get("scanner_id", [""])[0]
    dpi = int(form.get("dpi", ["300"])[0])
    mode = form.get("mode", ["color"])[0]
    output_format = form.get("format", ["pdf"])[0].lower()
    if output_format not in {"pdf", "png", "jpg"}:
        raise ValueError("Ungültiges Ausgabeformat")

    scanner, plugin = _find_scanner(scanner_id)
    if scanner is None or plugin is None:
        raise RuntimeError("Der ausgewählte Scanner wurde nicht gefunden")
    status = plugin.get_status(scanner.connection)
    if not status.scan_supported:
        raise RuntimeError(status.message or "Der Scanner ist nicht scanfähig")

    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"scan-{stamp}-{scanner.plugin_id}.{output_format}"
    target = SCAN_DIR / filename
    with _SCAN_LOCK:
        result = plugin.start_scan(scanner.connection, {"output": str(target), "dpi": dpi, "mode": mode})
    return {
        "ok": True,
        "scanner": scanner.name,
        "backend": result.backend,
        "filename": filename,
        "bytes": result.bytes_written,
        "download_url": f"/scans/{quote(filename)}",
    }


def _html_page(payload: dict, message: str = "", error: bool = False) -> str:
    cards = []
    scanner_options = []
    dpi_values: set[int] = set()
    for scanner in payload["scanners"]:
        ready = scanner["connected"] and scanner["scan_supported"]
        status_class = "ready" if ready else "warning"
        status_text = "Bereit" if ready else "Treiber/Verbindung prüfen"
        name = html.escape(scanner["name"])
        connection = html.escape(scanner["connection"])
        cards.append(f"""
        <article class="card">
          <div class="headline"><h2>{name}</h2><span class="{status_class}">{status_text}</span></div>
          <dl>
            <dt>Hersteller</dt><dd>{html.escape(scanner['manufacturer'])}</dd>
            <dt>Verbindung</dt><dd><code>{connection}</code></dd>
            <dt>Backend</dt><dd>{html.escape(scanner['backend'] or '-')}</dd>
            <dt>Scannen</dt><dd>{'Ja' if scanner['scan_supported'] else 'Noch nicht'}</dd>
            <dt>ADF / Duplex</dt><dd>{'Ja' if scanner['capabilities']['adf'] else 'Nein'} / {'Ja' if scanner['capabilities']['duplex'] else 'Nein'}</dd>
          </dl>
          <p>{html.escape(scanner['message'])}</p>
        </article>""")
        if ready:
            scanner_options.append(f'<option value="{html.escape(scanner["id"], quote=True)}">{name}</option>')
            dpi_values.update(scanner["capabilities"]["resolutions_dpi"])

    if not cards:
        cards.append("<article class='card'><h2>Kein Scanner gefunden</h2><p>Prüfe USB-Passthrough, Netzwerk, Stromversorgung und Treiber.</p></article>")

    dpi_options = "".join(f'<option value="{dpi}" {"selected" if dpi == 300 else ""}>{dpi} dpi</option>' for dpi in sorted(dpi_values or {150, 200, 300, 600}))
    scan_form = "<p>Kein scanfähiger Scanner verfügbar.</p>"
    if scanner_options:
        scan_form = f"""
        <form method="post" action="/scan">
          <label>Scanner<select name="scanner_id" required>{''.join(scanner_options)}</select></label>
          <label>Auflösung<select name="dpi">{dpi_options}</select></label>
          <label>Farbmodus<select name="mode"><option value="color">Farbe</option><option value="gray">Graustufen</option><option value="lineart">Schwarz/Weiß</option></select></label>
          <label>Format<select name="format"><option value="pdf">PDF</option><option value="png">PNG</option><option value="jpg">JPEG</option></select></label>
          <button type="submit">Scan starten</button>
        </form>"""

    recent = _recent_scans()
    scan_rows = "".join(
        f'<tr><td><a href="{item["url"]}">{html.escape(item["name"])}</a></td><td>{item["created"]}</td><td>{item["size"]:,} Bytes</td></tr>'
        for item in recent
    ) or '<tr><td colspan="3">Noch keine Scans vorhanden.</td></tr>'
    notice = f'<div class="notice {"error" if error else "success"}">{html.escape(message)}</div>' if message else ""

    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenScanStation</title><style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f4f6f8;color:#17202a}}header{{background:#17202a;color:white;padding:1.4rem 2rem}}main{{max-width:1100px;margin:2rem auto;padding:0 1rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}}.card,.panel{{background:white;border-radius:12px;padding:1.3rem;box-shadow:0 2px 12px #0001;margin-bottom:1rem}}.headline{{display:flex;justify-content:space-between;gap:1rem;align-items:center}}.ready,.warning{{padding:.3rem .6rem;border-radius:999px;font-size:.85rem;font-weight:700}}.ready{{background:#d5f5e3;color:#196f3d}}.warning{{background:#fdebd0;color:#935116}}dl{{display:grid;grid-template-columns:120px 1fr;gap:.45rem}}dt{{font-weight:700}}dd{{margin:0;overflow-wrap:anywhere}}nav a{{color:white;margin-right:1rem}}code{{font-size:.85rem}}form{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;align-items:end}}label{{display:grid;gap:.35rem;font-weight:700}}select,button{{padding:.7rem;border:1px solid #bbc3ca;border-radius:8px;background:white}}button{{background:#17202a;color:white;font-weight:700;cursor:pointer}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:.65rem;border-bottom:1px solid #e5e8eb}}.notice{{padding:1rem;border-radius:8px;margin-bottom:1rem}}.success{{background:#d5f5e3}}.error{{background:#fadbd8}}
</style></head><body>
<header><h1>OpenScanStation</h1><p>Version {VERSION} · WebGUI Port {DEFAULT_PORT}</p><nav><a href="/">Dashboard</a><a href="/api/scanners">Scanner-API</a><a href="/health">Health</a></nav></header>
<main>{notice}<section class="panel"><h2>Dokument scannen</h2>{scan_form}</section><h2>Scannerstatus</h2><div class="grid">{''.join(cards)}</div><section class="panel"><h2>Letzte Scans</h2><table><thead><tr><th>Datei</th><th>Zeit</th><th>Größe</th></tr></thead><tbody>{scan_rows}</tbody></table></section></main>
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

    def _send_html(self, body_text: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = body_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path) -> None:
        suffix_types = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", suffix_types.get(file_path.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({"status": "ok", "service": "openscanstation", "version": VERSION, "port": DEFAULT_PORT})
        elif path == "/version":
            self._send_json({"version": VERSION})
        elif path == "/api/scanners":
            self._send_json(_scanner_payload())
        elif path == "/api/scans":
            self._send_json({"scans": _recent_scans()})
        elif path.startswith("/scans/"):
            filename = unquote(path.removeprefix("/scans/"))
            if not _SAFE_FILE.fullmatch(filename):
                self._send_json({"error": "invalid_filename"}, HTTPStatus.BAD_REQUEST)
                return
            target = SCAN_DIR / filename
            if not target.is_file():
                self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_file(target)
        elif path == "/":
            self._send_html(_html_page(_scanner_payload()))
        else:
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/scan":
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise ValueError("Ungültige Formulardaten")
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=False)
            result = _perform_scan(form)
            self._send_html(_html_page(_scanner_payload(), f"Scan erfolgreich: {result['filename']}"))
        except Exception as exc:
            self._send_html(_html_page(_scanner_payload(), f"Scan fehlgeschlagen: {exc}", error=True), HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openscanstation-web")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
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
