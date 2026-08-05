"""Einheitlicher Webzugang für OpenScanStation auf Port 8101."""
from __future__ import annotations

import argparse
import http.client
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from openscanstation.cli import VERSION

HOST = "0.0.0.0"
PORT = 8101
MAIN_PORT = 8111
ROUTES = {
    "/hardware": 8107,
    "/copy": 8106,
    "/classification": 8105,
    "/workflows": 8104,
    "/storage": 8103,
    "/devices": 8102,
}
HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


def _sidebar() -> str:
    return f'''<aside class="oss-sidebar">
<div class="oss-brand"><strong>OpenScanStation</strong><span>Version {VERSION} · Port 8101</span></div>
<nav class="oss-menu">
<a href="/">⌂ <span>Dashboard</span></a>
<a href="/documents">▤ <span>Dokumente</span></a>
<a href="/profiles">⚙ <span>Scanprofile</span></a>
<a href="/scanner-actions">▣ <span>Scanneraktionen</span></a>
<details open><summary>▰ <span>Hardware</span><span class="oss-arrow">⌄</span></summary><div>
<a href="/hardware/">Übersicht</a>
<a href="/hardware/scanners">Scanner</a>
<a href="/hardware/printers">Drucker</a>
<a href="/hardware/maintenance">Wartung</a>
<a href="/hardware/drivers">Treiber</a>
<a href="/hardware/diagnostics">Diagnose</a>
</div></details>
<a href="/copy/">▣ <span>Kopieren</span></a>
<details open><summary>▧ <span>Verarbeitung</span><span class="oss-arrow">⌄</span></summary><div>
<a href="/processing">Übersicht</a>
<a href="/storage/">Speicherziele</a>
<a href="/workflows/">Workflows</a>
<a href="/classification/">Dokumenterkennung</a>
</div></details>
<a href="/system">⚙ <span>System</span></a>
</nav>
<div class="oss-status"><b>● OpenScanStation aktiv</b><span>Systemstatus</span></div>
</aside><div class="oss-content-shell">'''


STYLE = '''<style>
:root{--oss-sidebar:280px;--oss-navy:#0d2135}
html,body{min-height:100%}body{margin:0!important;background:#f6f8fb!important}
body>header,body>nav,header nav,.oss-global-nav{display:none!important}
.oss-sidebar{position:fixed;inset:0 auto 0 0;width:var(--oss-sidebar);box-sizing:border-box;background:linear-gradient(180deg,#0b2135,#0a1a2b);color:#fff;padding:24px 14px 18px;overflow-y:auto;z-index:9999;display:flex;flex-direction:column}
.oss-brand{padding:0 10px 24px}.oss-brand strong{display:block;font-size:27px;line-height:1.15}.oss-brand span{display:block;margin-top:7px;color:#d6e0ea;font-size:14px}
.oss-menu{display:grid;gap:5px}.oss-menu>a,.oss-menu summary{display:flex;gap:13px;align-items:center;padding:12px 14px;border-radius:9px;color:#fff!important;text-decoration:none!important;font-weight:700;cursor:pointer;list-style:none;user-select:none}
.oss-menu>a:hover,.oss-menu summary:hover{background:#165cae}.oss-menu summary::-webkit-details-marker{display:none}.oss-menu summary::marker{display:none;content:""}
.oss-menu summary .oss-arrow{margin-left:auto;transition:transform .18s ease}.oss-menu details:not([open]) summary .oss-arrow{transform:rotate(-90deg)}
.oss-menu details>div{display:grid;gap:2px;margin:3px 0 8px 31px;border-left:1px solid #496075;padding-left:10px}.oss-menu details>div a{padding:9px 12px;color:#fff!important;text-decoration:none!important;border-radius:7px}.oss-menu details>div a:hover{background:#183c5c}
.oss-status{margin-top:auto;padding:18px 10px 0;border-top:1px solid #2d4154;display:grid;gap:5px}.oss-status b{color:#fff}.oss-status span{font-size:13px;color:#c6d2dd;margin-left:22px}
.oss-content-shell{margin-left:var(--oss-sidebar);min-height:100vh}.oss-content-shell main{max-width:1500px!important;margin:0 auto!important;padding:42px 38px 50px!important}.oss-content-shell header,.oss-content-shell nav{display:none!important}
.oss-processing{font-family:system-ui,sans-serif;max-width:1200px;margin:0 auto;padding:42px 38px}.oss-processing h1{font-size:2rem;margin:0 0 .4rem}.oss-processing .lead{color:#65727e;margin-bottom:1.8rem}.oss-processing-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem}.oss-processing-card{background:#fff;border-radius:14px;padding:1.4rem;box-shadow:0 2px 14px #0001;border:1px solid #e7ebef}.oss-processing-card h2{margin:.2rem 0 .5rem}.oss-processing-card p{color:#65727e;min-height:3rem}.oss-processing-card a{display:inline-block;padding:.7rem 1rem;background:#0d2135;color:#fff;text-decoration:none;border-radius:8px;font-weight:700}.oss-status-pill{display:inline-block;padding:.25rem .6rem;border-radius:999px;font-size:.85rem;font-weight:700;margin-bottom:.7rem}.oss-ok{background:#d5f5e3;color:#196f3d}.oss-bad{background:#fadbd8;color:#922b21}
@media(max-width:900px){:root{--oss-sidebar:225px}.oss-sidebar{padding-left:8px;padding-right:8px}.oss-brand strong{font-size:21px}.oss-content-shell main,.oss-processing{padding:24px 16px!important}}
@media(max-width:650px){.oss-sidebar{position:relative;width:100%;height:auto}.oss-content-shell{margin-left:0}.oss-menu details>div{margin-left:18px}}
</style>'''


def _route(path: str) -> tuple[int, str, str]:
    for prefix, port in ROUTES.items():
        if path == prefix or path.startswith(prefix + "/"):
            return port, path[len(prefix):] or "/", prefix
    return MAIN_PORT, path, ""


def _module_health(port: int) -> bool:
    conn = None
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/health")
        response = conn.getresponse()
        response.read()
        return 200 <= response.status < 300
    except Exception:
        return False
    finally:
        if conn is not None:
            conn.close()


def _processing_page() -> bytes:
    modules = [
        ("Speicherziele", 8103, "/storage/", "Lokale Ordner, SMB, Nextcloud/WebDAV, SFTP und E-Mail verwalten."),
        ("Workflows", 8104, "/workflows/", "Dokumente automatisch verarbeiten, benennen, klassifizieren und ablegen."),
        ("Dokumenterkennung", 8105, "/classification/", "Rechnungen, Lieferscheine, Verträge, Briefe sowie Barcodes und QR-Codes erkennen."),
    ]
    cards = []
    for name, port, href, description in modules:
        online = _module_health(port)
        cards.append(f'''<article class="oss-processing-card">
<span class="oss-status-pill {'oss-ok' if online else 'oss-bad'}">{'Bereit' if online else 'Nicht erreichbar'}</span>
<h2>{name}</h2><p>{description}</p><a href="{href}">Öffnen</a></article>''')
    html = f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Verarbeitung – OpenScanStation</title>{STYLE}</head><body>{_sidebar()}<section class="oss-processing"><h1>Verarbeitung</h1><p class="lead">Zentrale Verwaltung der Dokumentverarbeitung und Ablage.</p><div class="oss-processing-grid">{''.join(cards)}</div></section></div></body></html>'''
    return html.encode("utf-8")


def _rewrite_html(body: bytes, prefix: str) -> bytes:
    text = body.decode("utf-8", errors="replace")
    if prefix:
        for attr in ("href", "action", "src"):
            text = re.sub(rf'({attr}=["\'])/(?!/)', rf'\1{prefix}/', text)
        text = text.replace(prefix + prefix + "/", prefix + "/")
    if "<head" in text:
        text = re.sub(r"(<head[^>]*>)", lambda match: match.group(1) + STYLE, text, count=1, flags=re.I)
    else:
        text = STYLE + text
    shell = _sidebar()
    if "<body" in text:
        text = re.sub(r"(<body[^>]*>)", lambda match: match.group(1) + shell, text, count=1, flags=re.I)
        text = re.sub(r"</body>", "</div></body>", text, count=1, flags=re.I)
    else:
        text = STYLE + shell + text + "</div>"
    return text.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_bytes(self, payload: bytes, status: int = 200, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-OpenScanStation-Gateway", "1")
        self.end_headers()
        self.wfile.write(payload)

    def _proxy(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path in {"/processing", "/processing/"}:
            self._send_bytes(_processing_page())
            return
        if parsed.path == "/api/gateway/modules":
            payload = json.dumps({
                "storage": _module_health(8103),
                "workflows": _module_health(8104),
                "classification": _module_health(8105),
            }).encode("utf-8")
            self._send_bytes(payload, ctype="application/json")
            return

        port, backend_path, prefix = _route(parsed.path)
        target = backend_path + (("?" + parsed.query) if parsed.query else "")
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None
        headers = {key: value for key, value in self.headers.items() if key.lower() not in HOP_HEADERS and key.lower() != "host"}
        headers["Host"] = f"127.0.0.1:{port}"
        conn = None
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=300)
            conn.request(self.command, target, body=body, headers=headers)
            response = conn.getresponse()
            payload = response.read()
            if "text/html" in response.getheader("Content-Type", ""):
                payload = _rewrite_html(payload, prefix)
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                lower = key.lower()
                if lower in HOP_HEADERS or lower == "content-length":
                    continue
                if lower == "location" and prefix and value.startswith("/"):
                    value = prefix + value
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-OpenScanStation-Gateway", "1")
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:
            message = f"Modul auf internem Port {port} nicht erreichbar: {exc}".encode("utf-8")
            self._send_bytes(message, 502, "text/plain; charset=utf-8")
        finally:
            if conn is not None:
                conn.close()

    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_DELETE = _proxy
    do_PATCH = _proxy

    def log_message(self, fmt: str, *args) -> None:
        print(fmt % args)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"OpenScanStation Gateway läuft auf {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
