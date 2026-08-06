"""Brother-Geräteprofil-Assistent für OpenScanStation.

Der ADS-2600We verwaltet Scan-to-FTP/Network-Profile über Web Based Management.
Dieses Modul übersetzt OpenScanStation-Speicherziele in Brother-kompatible
Profilvorschläge. Es verwendet absichtlich keine undokumentierten Schreib-APIs.
"""
from __future__ import annotations

import html
import json
from urllib.parse import urlparse

from openscanstation.cli import VERSION
from openscanstation.storage_targets import load_targets


def _profile_from_target(target: dict, slot: int) -> dict:
    kind = str(target.get("type", ""))
    config = dict(target.get("config", {}))
    result = {
        "slot": slot,
        "target_id": target.get("id", ""),
        "profile_name": str(target.get("name", target.get("id", "Ziel")))[:15],
        "enabled": bool(target.get("enabled", True)),
        "supported_on_device": kind in {"smb", "sftp"},
        "brother_mode": "Network" if kind == "smb" else "FTP" if kind == "sftp" else "OpenScanStation",
        "host_address": "",
        "store_directory": "",
        "username": "",
        "notes": "",
    }
    if kind == "smb":
        result.update({
            "host_address": config.get("host", ""),
            "store_directory": "/".join(x.strip("/") for x in (config.get("share", ""), config.get("path", "")) if x),
            "username": config.get("username", ""),
            "notes": "Im Brother Web Based Management als Scan to Network eintragen.",
        })
    elif kind == "sftp":
        result.update({
            "host_address": config.get("host", ""),
            "store_directory": config.get("path", ""),
            "username": config.get("username", ""),
            "notes": "Der ADS-2600We dokumentiert FTP/Network. SFTP ist geräteabhängig; gegebenenfalls über OpenScanStation ausführen.",
        })
    elif kind == "webdav":
        parsed = urlparse(str(config.get("url", "")))
        result.update({
            "host_address": parsed.hostname or "",
            "store_directory": parsed.path or "",
            "username": config.get("username", ""),
            "notes": "WebDAV wird auf diesem Brother-Modell nicht als natives Scan-to-Network-Profil dokumentiert. Ziel über OpenScanStation verwenden.",
        })
    elif kind == "local":
        result["notes"] = "Lokales OpenScanStation-Ziel; nicht direkt als Ziel auf dem Scanner erreichbar. Über OpenScanStation-Dashboard verwenden."
    elif kind == "email":
        result["notes"] = "E-Mail-Ziel wird von OpenScanStation verarbeitet; Brother-E-Mail-Konfiguration separat im Gerät verwalten."
    return result


def manifest() -> dict:
    targets = [item for item in load_targets(public=True).get("targets", []) if item.get("enabled", True)]
    profiles = [_profile_from_target(target, index) for index, target in enumerate(targets[:10], start=1)]
    return {
        "version": VERSION,
        "device": "Brother ADS-2600We",
        "automatic_push_supported": False,
        "reason": "Brother dokumentiert die Einrichtung über Web Based Management, aber keine öffentliche Schreib-API für dieses Modell.",
        "profiles": profiles,
        "native_profiles": sum(1 for item in profiles if item.get("supported_on_device")),
        "openscanstation_profiles": sum(1 for item in profiles if not item.get("supported_on_device")),
    }


def render() -> str:
    data = manifest()
    rows = []
    for item in data["profiles"]:
        status = "Nativ möglich" if item["supported_on_device"] else "Über OpenScanStation"
        rows.append(
            "<tr>"
            f"<td>{item['slot']}</td><td>{html.escape(item['profile_name'])}</td>"
            f"<td>{html.escape(item['brother_mode'])}</td><td>{html.escape(item['host_address'])}</td>"
            f"<td>{html.escape(item['store_directory'])}</td><td>{html.escape(status)}</td>"
            f"<td>{html.escape(item['notes'])}</td></tr>"
        )
    body = "".join(rows) or '<tr><td colspan="7">Noch keine aktiven Speicherziele vorhanden.</td></tr>'
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Brother Geräteprofile</title><style>
body{{font-family:system-ui;background:#f3f6f9;color:#17202a;margin:0}}main{{max-width:1500px;margin:auto;padding:1.4rem}}.panel{{background:#fff;padding:1.2rem;border-radius:14px;box-shadow:0 2px 14px #0001;margin-bottom:1rem}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.65rem;border-bottom:1px solid #e1e5e8;text-align:left;vertical-align:top}}a.button{{display:inline-block;background:#17202a;color:#fff;padding:.7rem 1rem;border-radius:8px;text-decoration:none;font-weight:700}}code{{overflow-wrap:anywhere}}.warn{{background:#fcf3cf;padding:1rem;border-radius:8px}}
</style></head><body><main><section class="panel"><h1>Brother-Geräteprofile</h1><p>Diese Seite übersetzt die in OpenScanStation konfigurierten Scan-Ziele in Einträge für das Display des Brother ADS-2600We.</p><p class="warn"><b>Wichtig:</b> Das Gerät stellt für dieses Modell keine offiziell dokumentierte externe Schreib-API bereit. Native Network-/FTP-Profile müssen deshalb einmalig in der Brother-Weboberfläche eingetragen werden. Andere Ziele bleiben als OpenScanStation-Aktionen verfügbar.</p><p><a class="button" href="/storage/">Speicherziele bearbeiten</a> <a class="button" href="/api/brother-device-profiles">JSON anzeigen</a></p></section><section class="panel"><table><tr><th>Slot</th><th>Anzeigename</th><th>Modus</th><th>Server</th><th>Verzeichnis</th><th>Status</th><th>Hinweis</th></tr>{body}</table></section><section class="panel"><h2>Einrichtung am Brother</h2><ol><li>IP-Adresse des Scanners im Browser öffnen.</li><li>Registerkarte <b>Scan</b> öffnen.</li><li><b>Scan to FTP/Network</b> auswählen.</li><li>Profilslot wählen und die oben vorbereiteten Werte übernehmen.</li><li>Profil speichern; danach erscheint es auf dem Gerätedisplay.</li></ol></section></main></body></html>'''
