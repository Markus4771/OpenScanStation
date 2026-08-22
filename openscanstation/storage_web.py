"""Weboberfläche zur Verwaltung der OpenScanStation-Speicherziele."""
from __future__ import annotations

import argparse
import html
import json
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from openscanstation.cli import VERSION
from openscanstation.brother_network import (
    delete_profile as delete_brother_network_profile,
    load_config as load_brother_network,
    save_config as save_brother_network,
    setup_samba,
    upsert_profile as upsert_brother_network_profile,
)
from openscanstation.scanner_actions import load_actions
from openscanstation.storage_targets import (
    SUPPORTED_TYPES,
    delete_target,
    load_targets,
    test_target,
    upsert_target,
    targets_for_user,
)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8103
TYPE_LABELS = {
    "local": "Lokaler Ordner",
    "smb": "SMB / Windows / NAS",
    "webdav": "Nextcloud / WebDAV",
    "sftp": "SFTP",
    "email": "E-Mail / SMTP",
    "paperless": "Paperless-ngx",
}


def _layout(content: str, notice: str = "", error: bool = False) -> str:
    note = f'<div class="notice {"error" if error else "success"}">{html.escape(notice)}</div>' if notice else ""
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenScanStation Speicherziele</title><style>
body{{font-family:system-ui,sans-serif;margin:0;background:#f3f5f7;color:#17202a}}header{{background:#17202a;color:white;padding:1.2rem 2rem}}main{{max-width:1200px;margin:1.5rem auto;padding:0 1rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem}}.card,.panel{{background:white;border-radius:12px;padding:1.2rem;box-shadow:0 2px 12px #0001;margin-bottom:1rem}}form{{display:grid;gap:.7rem}}label{{display:grid;gap:.25rem;font-weight:700}}input,select,textarea,button{{padding:.7rem;border:1px solid #bcc5cc;border-radius:8px}}textarea{{font:inherit}}button{{background:#17202a;color:white;font-weight:700;cursor:pointer}}button.danger{{background:#922b21}}.row{{display:flex;gap:.6rem;flex-wrap:wrap}}.row form{{display:inline-block}}.muted{{color:#65727e;font-size:.9rem}}.notice{{padding:1rem;border-radius:8px;margin-bottom:1rem}}.success{{background:#d5f5e3}}.error{{background:#fadbd8}}code{{overflow-wrap:anywhere}}
</style></head><body><header><h1>OpenScanStation · Speicherziele</h1><div>Version {VERSION} · Port {DEFAULT_PORT}</div></header><main>{note}{content}</main></body></html>'''


def _config_fields(target: dict) -> str:
    config = target.get("config", {})
    kind = target.get("type", "local")
    fields = {
        "local": (("path", "Zielpfad", "/srv/scans"),),
        "smb": (("host", "Server", "nas.local"), ("share", "Freigabe", "Dokumente"), ("path", "Unterordner", "Scans"), ("username", "Benutzer", "scanner"), ("password", "Kennwort", ""), ("domain", "Domäne", ""), ("port", "Port", "445")),
        "webdav": (("url", "WebDAV-URL", "https://cloud.example/remote.php/dav/files/user/Scans"), ("username", "Benutzer", ""), ("password", "Kennwort", ""), ("token", "App-Passwort / Token", "")),
        "sftp": (("host", "Server", "sftp.example"), ("port", "Port", "22"), ("path", "Zielpfad", "/upload"), ("username", "Benutzer", "scanner"), ("password", "Kennwort", ""), ("private_key", "Privater Schlüssel / Pfad", "")),
        "email": (("smtp_host", "SMTP-Server", "mail.example"), ("smtp_port", "Port", "587"), ("smtp_user", "SMTP-Benutzer", ""), ("smtp_password", "SMTP-Kennwort", ""), ("sender", "Absender", "scanner@example"), ("recipient", "Empfänger", "archiv@example")),
        "paperless": (("url", "Paperless-ngx URL", "https://paperless.example"), ("token", "API-Token", ""), ("correspondent", "Korrespondenten-ID", ""), ("document_type", "Dokumenttyp-ID", ""), ("storage_path", "Speicherpfad-ID", ""), ("tags", "Tag-IDs (kommagetrennt)", "")),
    }[kind]
    rendered = []
    for name, label, placeholder in fields:
        secret = name in {"password", "token", "smtp_password"}
        value = "" if secret else str(config.get(name, ""))
        rendered.append(f'<label>{html.escape(label)}<input name="cfg_{name}" type="{"password" if secret else "text"}" value="{html.escape(value, quote=True)}" placeholder="{html.escape(placeholder, quote=True)}"></label>')
    if kind in {"webdav", "paperless"}:
        rendered.append(f'<label><span>TLS-Zertifikat prüfen</span><input type="checkbox" name="cfg_verify_tls" value="1" {"checked" if config.get("verify_tls", True) else ""}></label>')
    if kind == "email":
        rendered.append(f'<label><span>STARTTLS verwenden</span><input type="checkbox" name="cfg_starttls" value="1" {"checked" if config.get("starttls", True) else ""}></label>')
    return "".join(rendered)


def _page(message: str = "", error: bool = False, username: str = "", is_admin: bool = False) -> str:
    targets = targets_for_user(username, is_admin)["targets"]
    actions = load_actions()["actions"]
    cards = []
    for target in targets:
        used = [a.get("label", a["id"]) for a in actions if a.get("destination") == target["id"]]
        types = ''.join(f'<option value="{kind}" {"selected" if kind == target["type"] else ""}>{TYPE_LABELS[kind]}</option>' for kind in SUPPORTED_TYPES)
        delete = '<p class="muted">Das Ziel wird von Scanneraktionen verwendet.</p>' if used else f'<form method="post" action="/delete"><input type="hidden" name="id" value="{html.escape(target["id"], quote=True)}"><button class="danger">Löschen</button></form>'
        cards.append(f'''<article class="card"><h2>{html.escape(target['name'])}</h2><p><code>{html.escape(target['id'])}</code> · {TYPE_LABELS[target['type']]}</p><form method="post" action="/save"><input type="hidden" name="id" value="{html.escape(target['id'], quote=True)}"><label>Name<input name="name" value="{html.escape(target['name'], quote=True)}" required></label><label>Typ<select name="type">{types}</select></label><label><span>Aktiv</span><input type="checkbox" name="enabled" value="1" {"checked" if target['enabled'] else ""}></label><label><span>Standardziel</span><input type="checkbox" name="default" value="1" {"checked" if target['default'] else ""}></label><label><span>Mit anderen Benutzern teilen</span><input type="checkbox" name="shared" value="1" {"checked" if target.get('shared') else ""}></label>{_config_fields(target)}<button>Speichern</button></form><div class="row"><form method="post" action="/test"><input type="hidden" name="id" value="{html.escape(target['id'], quote=True)}"><button>Verbindung testen</button></form>{delete}</div>{f'<p class="muted">Verwendet von: {html.escape(", ".join(used))}</p>' if used else ''}</article>''')
    create_types = ''.join(f'<option value="{kind}">{TYPE_LABELS[kind]}</option>' for kind in SUPPORTED_TYPES)
    create = f'''<section class="panel"><h2>Neues Speicherziel</h2><p class="muted">Nach dem Anlegen können die typspezifischen Felder bearbeitet werden.</p><form method="post" action="/create"><label>Ziel-ID<input name="id" pattern="[a-z0-9][a-z0-9_-]*" placeholder="nextcloud" required></label><label>Name<input name="name" placeholder="Nextcloud Dokumente" required></label><label>Typ<select name="type">{create_types}</select></label><button>Ziel anlegen</button></form></section>'''
    samba = ""
    if is_admin:
        try:
            network = load_brother_network()
        except ValueError:
            network = {"profiles": {}}

        def action_options(selected: str = "") -> str:
            return "".join(
                f'<option value="{html.escape(action["id"], quote=True)}" {"selected" if action["id"] == selected else ""}>{html.escape(action.get("label", action["id"]))} ({html.escape(action["id"])})</option>'
                for action in actions if action.get("enabled", True)
            )

        profile_cards = []
        for profile, action_id in network["profiles"].items():
            profile_cards.append(f'''<article class="card"><h3>{html.escape(profile)}</h3><p class="muted">Brother-Pfad: <code>\\\\SERVER-IP\\OpenScan\\{html.escape(profile)}</code></p><form method="post" action="/network-profile/save"><input type="hidden" name="profile" value="{html.escape(profile, quote=True)}"><label>Scanneraktion<select name="action_id" required>{action_options(action_id)}</select></label><button>Zuordnung speichern</button></form><form method="post" action="/network-profile/delete"><input type="hidden" name="profile" value="{html.escape(profile, quote=True)}"><button class="danger">To-Network-Button löschen</button></form></article>''')
        profile_manager = f'''<section class="panel"><h2>Brother „To Network“-Buttons</h2><p>Lege einen Namen für das Brother-Display fest und ordne ihm eine Scanneraktion zu. Der gleichnamige Samba-Unterordner wird automatisch erzeugt.</p><form method="post" action="/network-profile/save"><label>Button-/Profilname<input name="profile" pattern="[a-z0-9][a-z0-9_-]*" placeholder="rechnung" maxlength="32" required></label><label>Scanneraktion<select name="action_id" required>{action_options()}</select></label><button>To-Network-Button anlegen</button></form></section><div class="grid">{"".join(profile_cards)}</div>'''
        mappings = "\n".join(f"{name}={action}" for name, action in network["profiles"].items()) or "rechnung=action-1"
        samba_setup = f'''<section class="panel"><h2>Samba-Freigabe aktivieren</h2><p class="muted">Dieser Schritt richtet die geschützte Freigabe <code>OpenScan</code> und deren Zugang ein. Er ist nach der ersten Einrichtung oder einer Kennwortänderung erforderlich.</p><form method="post" action="/samba-setup"><label>SMB-Benutzer<input name="username" value="openscanstation" required></label><label>Neues SMB-Kennwort<input type="password" name="password" minlength="8" required></label><input type="hidden" name="mappings" value="{html.escape(mappings, quote=True)}"><button>Samba-Freigabe einrichten</button></form></section>'''
        samba = profile_manager + samba_setup
    return _layout(samba + create + '<div class="grid">' + ''.join(cards) + '</div>', message, error)


def _from_form(form: dict[str, list[str]], existing: dict | None = None) -> dict:
    existing = existing or {}
    old_config = existing.get("config", {})
    config = dict(old_config)
    for key, values in form.items():
        if key.startswith("cfg_"):
            field = key[4:]
            value = values[0]
            if value or field not in {"password", "token", "smtp_password"}:
                config[field] = value
    for field in ("verify_tls", "starttls"):
        if f"cfg_{field}" in form or field in config:
            config[field] = form.get(f"cfg_{field}", ["0"])[0] == "1"
    return {
        "id": form.get("id", [existing.get("id", "")])[0],
        "name": form.get("name", [existing.get("name", "")])[0],
        "type": form.get("type", [existing.get("type", "local")])[0],
        "enabled": form.get("enabled", ["0"])[0] == "1",
        "default": form.get("default", ["0"])[0] == "1",
        "owner": existing.get("owner", ""),
        "shared": form.get("shared", ["0"])[0] == "1",
        "config": config,
    }


class Handler(BaseHTTPRequestHandler):
    def identity(self):
        return self.headers.get("X-OpenScanStation-User", ""), self.headers.get("X-OpenScanStation-Role", "") == "admin"
    def _send(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            user, admin = self.identity(); self._send(_page(username=user, is_admin=admin).encode(), "text/html; charset=utf-8")
        elif path == "/health":
            self._send(json.dumps({"status": "ok", "service": "openscanstation-storage", "version": VERSION}).encode(), "application/json")
        elif path == "/api/storage-targets":
            user, admin = self.identity(); self._send(json.dumps(targets_for_user(user, admin, public=True), ensure_ascii=False, indent=2).encode(), "application/json; charset=utf-8")
        else:
            self._send(b'{"error":"not_found"}', "application/json", HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise ValueError("Ungültige Formulardaten")
            form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            username, is_admin = self.identity()
            if path == "/network-profile/save":
                if not is_admin:
                    raise PermissionError("Administratorrechte erforderlich")
                profile = form.get("profile", [""])[0]
                action_id = form.get("action_id", [""])[0]
                if not any(action["id"] == action_id and action.get("enabled", True) for action in load_actions()["actions"]):
                    raise ValueError("Scanneraktion wurde nicht gefunden oder ist deaktiviert")
                upsert_brother_network_profile(profile, action_id)
                subprocess.run(["systemctl", "restart", "openscanstation-brother-network.service"], check=True, capture_output=True, text=True)
                page = _page("To-Network-Button wurde gespeichert.", username=username, is_admin=is_admin)
                self._send(page.encode(), "text/html; charset=utf-8")
                return
            if path == "/network-profile/delete":
                if not is_admin:
                    raise PermissionError("Administratorrechte erforderlich")
                delete_brother_network_profile(form.get("profile", [""])[0])
                subprocess.run(["systemctl", "restart", "openscanstation-brother-network.service"], check=True, capture_output=True, text=True)
                page = _page("To-Network-Button wurde gelöscht.", username=username, is_admin=is_admin)
                self._send(page.encode(), "text/html; charset=utf-8")
                return
            if path == "/samba-setup":
                if not is_admin:
                    raise PermissionError("Administratorrechte erforderlich")
                mappings = {}
                for line in form.get("mappings", [""])[0].splitlines():
                    if not line.strip(): continue
                    if "=" not in line: raise ValueError("Zuordnung muss ordner=action-id entsprechen")
                    name, action = line.split("=", 1); mappings[name.strip()] = action.strip()
                config = save_brother_network({"profiles": mappings})
                setup_samba(config, form.get("username", ["openscanstation"])[0], form.get("password", [""])[0])
                page = _page("Samba-Eingang wurde eingerichtet.", username=username, is_admin=is_admin)
                self._send(page.encode(), "text/html; charset=utf-8")
                return
            if path == "/create":
                kind = form.get("type", ["local"])[0]
                defaults = {"local": {"path": "/var/lib/openscanstation/scans"}, "smb": {"host": "server", "share": "scans"}, "webdav": {"url": "https://server/remote.php/dav/files/user/Scans"}, "sftp": {"host": "server", "username": "scanner"}, "email": {"smtp_host": "server", "sender": "scanner@localhost", "recipient": "archiv@localhost"}, "paperless": {"url": "https://paperless.example", "token": "TOKEN_EINTRAGEN", "verify_tls": True}}[kind]
                target = _from_form(form)
                target.update({"enabled": True, "config": defaults})
                target["owner"] = username
                upsert_target(target, create_only=True)
                page = _page("Speicherziel wurde angelegt.", username=username, is_admin=is_admin)
            elif path == "/save":
                target_id = form.get("id", [""])[0]
                existing = next((item for item in load_targets()["targets"] if item["id"] == target_id), None)
                if not existing:
                    raise ValueError("Speicherziel nicht gefunden")
                upsert_target(_from_form(form, existing))
                if not is_admin and existing.get("owner") not in {"", username}: raise PermissionError("Speicherziel gehoert einem anderen Benutzer")
                page = _page("Speicherziel wurde gespeichert.", username=username, is_admin=is_admin)
            elif path == "/delete":
                target_id = form.get("id", [""])[0]
                used = [a.get("label", a["id"]) for a in load_actions()["actions"] if a.get("destination") == target_id]
                delete_target(target_id, used_by=used)
                page = _page("Speicherziel wurde gelöscht.", username=username, is_admin=is_admin)
            elif path == "/test":
                result = test_target(form.get("id", [""])[0])
                page = _page(result["message"], not result["ok"], username=username, is_admin=is_admin)
            else:
                self._send(b'{"error":"not_found"}', "application/json", HTTPStatus.NOT_FOUND)
                return
            self._send(page.encode(), "text/html; charset=utf-8")
        except Exception as exc:
            self._send(_page(str(exc), True).encode(), "text/html; charset=utf-8", HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openscanstation-storage-web")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"OpenScanStation Speicherziele {VERSION} läuft auf {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
