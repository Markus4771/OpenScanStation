"""Einheitlicher Webzugang für OpenScanStation auf Port 8101.

Die Fachmodule laufen ausschließlich auf localhost. Das Gateway veröffentlicht
sie als Untermenüs und Pfade innerhalb einer einzigen Anwendung.
"""
from __future__ import annotations

import argparse
import http.client
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HOST = "0.0.0.0"
PORT = 8101
ROUTES = {
    "/hardware": 8107,
    "/copy": 8106,
    "/classification": 8105,
    "/workflows": 8104,
    "/storage": 8103,
    "/devices": 8102,
}
MAIN_PORT = 8111
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}

NAV = '''<nav class="oss-global-nav">
<a href="/">Dashboard</a>
<a href="/documents">Dokumente</a>
<a href="/profiles">Scanprofile</a>
<a href="/scanner-actions">Scanneraktionen</a>
<details><summary>Hardware</summary><div><a href="/hardware/">Übersicht</a><a href="/hardware/scanners">Scanner</a><a href="/hardware/printers">Drucker</a><a href="/hardware/drivers">Treiber</a><a href="/hardware/diagnostics">Diagnose</a></div></details>
<a href="/copy/">Kopieren</a>
<details><summary>Verarbeitung</summary><div><a href="/storage/">Speicherziele</a><a href="/workflows/">Workflows</a><a href="/classification/">Dokumenterkennung</a></div></details>
<a href="/system">System</a>
</nav>'''
STYLE = '''<style>.oss-global-nav{display:flex;gap:.9rem;align-items:center;flex-wrap:wrap;background:#0d1b2a;color:#fff;padding:.8rem 1.2rem;position:sticky;top:0;z-index:9999}.oss-global-nav a,.oss-global-nav summary{color:#fff;text-decoration:none;font-weight:650;cursor:pointer}.oss-global-nav details{position:relative}.oss-global-nav details div{position:absolute;min-width:190px;background:#17202a;padding:.7rem;border-radius:8px;box-shadow:0 5px 18px #0005;display:grid;gap:.55rem}.oss-global-nav details:not([open]) div{display:none}</style>'''


def _route(path: str) -> tuple[int, str, str]:
    for prefix, port in ROUTES.items():
        if path == prefix or path.startswith(prefix + "/"):
            stripped = path[len(prefix):] or "/"
            return port, stripped, prefix
    return MAIN_PORT, path, ""


def _rewrite_html(body: bytes, prefix: str) -> bytes:
    text = body.decode("utf-8", errors="replace")
    if prefix:
        for attr in ("href", "action", "src"):
            text = re.sub(rf'({attr}=["\'])/(?!/)', rf'\1{prefix}/', text)
        text = text.replace(prefix + prefix + "/", prefix + "/")
    insertion = STYLE + NAV
    if "<body" in text:
        text = re.sub(r"(<body[^>]*>)", r"\1" + insertion, text, count=1, flags=re.I)
    else:
        text = insertion + text
    return text.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy(self) -> None:
        parsed = urlsplit(self.path)
        port, backend_path, prefix = _route(parsed.path)
        target = backend_path + (("?" + parsed.query) if parsed.query else "")
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS and k.lower() != "host"}
        headers["Host"] = f"127.0.0.1:{port}"
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=300)
            conn.request(self.command, target, body=body, headers=headers)
            response = conn.getresponse()
            payload = response.read()
            ctype = response.getheader("Content-Type", "")
            if "text/html" in ctype:
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
            conn.close()
        except Exception as exc:
            message = f"Modul auf internem Port {port} nicht erreichbar: {exc}".encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)

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
