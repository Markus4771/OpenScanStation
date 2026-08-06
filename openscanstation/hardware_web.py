"""Fehlertoleranter modularer Hardware-Webdienst für OpenScanStation."""
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from openscanstation.cli import VERSION
from openscanstation.hardware_sections import layout, render

HOST = "127.0.0.1"
PORT = 8107


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send(self, data: str | bytes, status: int = 200,
             ctype: str = "text/html; charset=utf-8",
             disposition: str = "", head_only: bool = False) -> None:
        body = data.encode("utf-8") if isinstance(data, str) else data
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-OpenScanStation-Module", "hardware")
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        if not head_only:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _get(self, head_only: bool = False) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path in {"/device-center", "/geraetezentrale"}:
            from openscanstation.device_center import render as render_device_center
            self.send(render_device_center(), head_only=head_only)
            return
        if path == "/scanners":
            from openscanstation.scanner_admin import render as render_scanners
            self.send(render_scanners(), head_only=head_only)
            return
        if path == "/scanner/config-export":
            from openscanstation.scanner_admin import configuration
            body = json.dumps(configuration(), ensure_ascii=False, indent=2) + "\n"
            self.send(body, ctype="application/json; charset=utf-8",
                      disposition='attachment; filename="openscanstation-scanners.json"',
                      head_only=head_only)
            return

        page = render(path)
        if page is not None:
            self.send(page, head_only=head_only)
            return

        if path == "/health":
            self.send(json.dumps({"status": "ok", "service": "openscanstation-hardware", "version": VERSION, "architecture": "modular"}), ctype="application/json", head_only=head_only)
            return
        if path == "/api/device-center":
            from openscanstation.device_center import snapshot
            self.send(json.dumps(snapshot(), ensure_ascii=False), ctype="application/json", head_only=head_only)
            return
        if path == "/api/hardware":
            from openscanstation.hardware import inventory
            self.send(json.dumps(inventory(), ensure_ascii=False), ctype="application/json", head_only=head_only)
            return
        if path == "/api/monitor":
            from openscanstation.hardware_management import monitor_snapshot
            self.send(json.dumps(monitor_snapshot(), ensure_ascii=False), ctype="application/json", head_only=head_only)
            return
        if path == "/api/profiles":
            from openscanstation.hardware_management import load_profiles
            self.send(json.dumps(load_profiles(), ensure_ascii=False), ctype="application/json", head_only=head_only)
            return
        if path == "/api/scanners":
            from openscanstation.hardware import inventory
            from openscanstation.scanner_admin import manual_scanners
            from openscanstation.scanner_settings import load_settings
            payload = {"automatic": [x for x in inventory().get("devices", []) if x.get("kind") == "scanner"], "manual": manual_scanners(), "settings": load_settings()}
            self.send(json.dumps(payload, ensure_ascii=False), ctype="application/json", head_only=head_only)
            return
        if path == "/support/download":
            from openscanstation.hardware_actions import latest_support_bundle
            bundle = latest_support_bundle()
            if not bundle:
                self.send(layout("<section class='panel'><h2>Noch kein Supportpaket vorhanden</h2></section>", "Support", "Kein Paket vorhanden.", True), 404, head_only=head_only)
                return
            self.send(bundle.read_bytes(), ctype="application/gzip", disposition=f'attachment; filename="{bundle.name}"', head_only=head_only)
            return
        if path.startswith("/scanner/") or path.startswith("/printer/"):
            kind = "scanner" if path.startswith("/scanner/") else "printer"
            device_id = unquote(path.split("/", 2)[2])
            try:
                from openscanstation.hardware import inventory
                device = next((x for x in inventory().get("devices", []) if x.get("kind") == kind and x.get("id") == device_id), None)
                if not device:
                    raise ValueError("Gerät nicht gefunden")
                rows = "".join(f"<tr><th>{key}</th><td><pre>{json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else value}</pre></td></tr>" for key, value in device.items())
                self.send(layout(f"<section class='panel'><h2>{device.get('name','Gerät')}</h2><table>{rows}</table></section>", str(device.get("name", "Gerät"))), head_only=head_only)
            except Exception as exc:
                self.send(layout("<section class='panel'><h2>Gerät konnte nicht geladen werden</h2></section>", "Hardware", str(exc), True), 400, head_only=head_only)
            return
        self.send(json.dumps({"error": "not_found", "path": path}), 404, "application/json", head_only=head_only)

    def do_GET(self) -> None:
        self._get(False)

    def do_HEAD(self) -> None:
        self._get(True)

    def _form(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        values = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
        return lambda key, default="": values.get(key, [default])[0]

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            get = self._form()
            if path == "/scanner/auto-save":
                from openscanstation.scanner_admin import render as render_scanners
                from openscanstation.scanner_settings import update_scanner
                update_scanner(get("scanner_id"), alias=get("alias"), enabled=get("enabled") == "1", make_default=get("make_default") == "1")
                self.send(render_scanners("Scanner wurde gespeichert.")); return
            if path == "/scanner/auto-hide":
                from openscanstation.scanner_admin import render as render_scanners
                from openscanstation.scanner_settings import update_scanner
                update_scanner(get("scanner_id"), alias="", enabled=False, make_default=False)
                self.send(render_scanners("Scanner wurde ausgeblendet.")); return
            if path == "/scanner/restore":
                from openscanstation.scanner_admin import render as render_scanners, restore
                restore(get("scanner_id"))
                self.send(render_scanners("Scanner wurde wiederhergestellt.")); return
            if path == "/scanner/restore-all":
                from openscanstation.scanner_admin import render as render_scanners, restore_all_hidden
                restore_all_hidden()
                self.send(render_scanners("Alle Scanner wurden wiederhergestellt.")); return
            if path == "/scanner/manual-save":
                from openscanstation.scanner_admin import render as render_scanners, save_manual_scanner
                from openscanstation.scanner_settings import load_settings, save_settings
                item = save_manual_scanner(get("name"), get("uri"), get("backend"), get("original_id"))
                if get("make_default") == "1":
                    settings = load_settings(); settings["default_scanner"] = item["id"]; save_settings(settings)
                self.send(render_scanners("Manueller Scanner wurde gespeichert.")); return
            if path == "/scanner/manual-delete":
                from openscanstation.scanner_admin import delete_manual_scanner, render as render_scanners
                if get("confirm") != "yes":
                    raise ValueError("Löschen wurde nicht bestätigt")
                delete_manual_scanner(get("scanner_id"))
                self.send(render_scanners("Manueller Scanner wurde endgültig gelöscht.")); return
            if path == "/scanner/config-import":
                from openscanstation.scanner_admin import import_configuration, render as render_scanners
                result = import_configuration(get("configuration"))
                self.send(render_scanners(f"Scannerkonfiguration importiert: {result.get('imported', 0)} manuelle Scanner.")); return
            if path == "/scanner/test":
                from openscanstation.hardware import inventory
                from openscanstation.scanner_settings import test_connection
                scanners = [d for d in inventory().get("devices", []) if d.get("kind") == "scanner"]
                result = test_connection(get("scanner_id"), scanners)
                self.send(layout(f"<section class='panel'><h2>Verbindungstest</h2><pre>{json.dumps(result, ensure_ascii=False, indent=2)}</pre><a class='button' href='/scanners'>Zurück</a></section>", "Scanner-Test")); return
            if path == "/scanner/test-scan":
                from openscanstation.hardware_actions import test_scan
                result = test_scan(get("scanner_id"), resolution=int(get("resolution", "300")), mode=get("mode", "Gray"))
                self.send(layout(f"<section class='panel'><h2>Testscan erfolgreich</h2><pre>{json.dumps(result, ensure_ascii=False, indent=2)}</pre><a class='button' href='/scanners'>Zurück</a></section>", "Testscan", result.get("message", ""))); return
            if path == "/scanner/manual-add":
                from openscanstation.scanner_admin import save_manual_scanner, render as render_scanners
                save_manual_scanner(get("name"), get("uri"), get("backend"))
                self.send(render_scanners("Scanner wurde hinzugefügt.")); return
            if path == "/profile/save":
                from openscanstation.hardware_management import save_profile
                save_profile(get("profile_id"), name=get("name"), resolution=int(get("resolution", "300")), mode=get("mode", "Gray"), duplex=get("duplex") == "1", output_format=get("format", "pdf"), ocr=get("ocr") == "1", remove_blank=get("remove_blank") == "1")
                self.send(render("/profiles") or ""); return
            if path == "/profile/delete":
                from openscanstation.hardware_management import delete_profile
                delete_profile(get("profile_id")); self.send(render("/profiles") or ""); return
            if path == "/printer/add":
                from openscanstation.hardware_actions import add_ipp_printer
                result = add_ipp_printer(get("name"), get("uri"))
                self.send(layout("<section class='panel'><h2>Drucker eingerichtet</h2><a class='button' href='/printers'>Drucker öffnen</a></section>", "Drucker", result.get("message", ""))); return
            if path == "/printer/test":
                from openscanstation.hardware import print_test_page
                result = print_test_page(get("printer"))
                self.send(layout("<section class='panel'><h2>Testseite</h2><a class='button' href='/printers'>Zurück</a></section>", "Drucker", result.get("message", ""))); return
            if path == "/printer/cancel":
                from openscanstation.hardware import cancel_print_job
                cancel_print_job(get("job")); self.send(render("/printers") or ""); return
            if path == "/network/probe":
                from openscanstation.hardware import tcp_probe
                result = tcp_probe(get("host"))
                self.send(layout(f"<section class='panel'><h2>Netzwerktest</h2><pre>{json.dumps(result, ensure_ascii=False, indent=2)}</pre><a class='button' href='/network'>Zurück</a></section>", "Netzwerktest")); return
            if path == "/maintenance/save":
                from openscanstation.hardware_management import save_maintenance
                save_maintenance(get("device_id"), task=get("task"), interval_days=int(get("interval_days", "90")), last_done=get("last_done")); self.send(render("/maintenance") or ""); return
            if path == "/maintenance/complete":
                from openscanstation.hardware_management import complete_maintenance
                complete_maintenance(get("item_id")); self.send(render("/maintenance") or ""); return
            if path == "/support/create":
                from openscanstation.hardware_actions import create_support_bundle
                result = create_support_bundle()
                self.send(layout("<section class='panel'><h2>Supportpaket erstellt</h2><a class='button' href='/support/download'>Herunterladen</a></section>", "Support", result.get("message", ""))); return
            self.send(json.dumps({"error": "not_found", "path": path}), 404, "application/json")
        except Exception as exc:
            self.send(layout("<section class='panel'><h2>Aktion fehlgeschlagen</h2><a class='button' href='/scanners'>Zur Scannerverwaltung</a></section>", "Hardware", str(exc), True), HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args) -> None:
        print(fmt % args)


class HardwareServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address) -> None:
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--host", default=HOST); parser.add_argument("--port", type=int, default=PORT); args = parser.parse_args(argv)
    server = HardwareServer((args.host, args.port), Handler)
    print(f"Hardware-Zentrale (modular) auf {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
