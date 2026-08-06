"""Gerätezentrale für Scanner, Statistiken und Brother-Funktionen."""
from __future__ import annotations

import html
import json
import subprocess
from collections import Counter
from datetime import date, datetime

from openscanstation.cli import VERSION
from openscanstation.documents import list_documents
from openscanstation.hardware import driver_status, inventory
from openscanstation.hardware_management import maintenance_items
from openscanstation.profiles import load_profiles
from openscanstation.scanner_settings import load_settings

STYLE = """
body{font-family:system-ui;margin:0;background:#f3f6f9;color:#17202a}main{max-width:1500px;margin:1.3rem auto;padding:0 1rem}.panel,.card{background:#fff;padding:1.15rem;border-radius:14px;box-shadow:0 2px 14px #0001;margin-bottom:1rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem}.metric{font-size:2rem;font-weight:800}.status{display:inline-block;padding:.25rem .6rem;border-radius:999px;font-weight:700}.ok{background:#d5f5e3;color:#196f3d}.bad{background:#fadbd8;color:#922b21}.warn{background:#fcf3cf;color:#7d6608}.muted{color:#687684}.hero,.actions{display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap}a.button{display:inline-block;background:#17202a;color:#fff;padding:.68rem .95rem;border-radius:8px;text-decoration:none;font-weight:700}a.secondary{background:#e9eef3;color:#17202a}table{width:100%;border-collapse:collapse}th,td{padding:.65rem;border-bottom:1px solid #e1e5e8;text-align:left;vertical-align:top}code{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow:auto;background:#f6f7f8;padding:1rem;border-radius:8px}
"""


def esc(value: object) -> str:
    return html.escape(str(value))


def _scan_statistics() -> dict:
    docs = list_documents(limit=5000)
    today = date.today().isoformat()
    month = today[:7]
    scanner_counts = Counter(str(item.get("scanner", "Unbekannt")) for item in docs)
    profile_counts = Counter(str(item.get("profile", "Unbekannt")) for item in docs)
    pages = sum(int(item.get("pages", 1) or 1) for item in docs)
    return {
        "documents": len(docs),
        "pages": pages,
        "today": sum(1 for item in docs if str(item.get("created_at", "")).startswith(today)),
        "month": sum(1 for item in docs if str(item.get("created_at", "")).startswith(month)),
        "scanner_counts": scanner_counts,
        "profile_counts": profile_counts,
        "last_scan": docs[0].get("created_at", "") if docs else "",
    }


def _source_capabilities(device: str) -> dict:
    try:
        result = subprocess.run(
            ["scanimage", "--device-name", device, "--help"],
            capture_output=True, text=True, timeout=8,
        )
        text = (result.stdout + result.stderr)
    except (OSError, subprocess.TimeoutExpired):
        return {"sources": [], "raw_available": False}
    sources: list[str] = []
    for line in text.splitlines():
        lower = line.casefold()
        if "--source" in lower and "[" in line and "]" in line:
            values = line.split("[", 1)[1].rsplit("]", 1)[0]
            sources.extend(v.strip() for v in values.split("|") if v.strip())
    unique = list(dict.fromkeys(sources))
    return {"sources": unique, "raw_available": bool(text)}


def snapshot() -> dict:
    inv = inventory()
    settings = load_settings()
    stats = _scan_statistics()
    profiles = load_profiles()
    maintenance = maintenance_items()
    scanners = []
    for device in inv.get("devices", []):
        if device.get("kind") != "scanner":
            continue
        connection = str(device.get("connection", ""))
        caps = _source_capabilities(connection) if connection else {"sources": [], "raw_available": False}
        scanners.append({
            **device,
            "is_default": str(device.get("id", "")) == settings.get("default_scanner", ""),
            "sources": caps.get("sources", []),
            "firmware": "nicht über SANE verfügbar",
            "serial_number": "nicht über SANE verfügbar",
            "temperature": "nicht verfügbar",
            "paper_sensor": device.get("capabilities", {}).get("paper_sensor", "nicht verfügbar"),
        })
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "scanners": scanners,
        "printers": [d for d in inv.get("devices", []) if d.get("kind") == "printer"],
        "drivers": driver_status(),
        "statistics": stats,
        "profiles": profiles,
        "maintenance": maintenance,
    }


def render() -> str:
    data = snapshot(); stats = data["statistics"]
    scanner_cards = []
    for scanner in data["scanners"]:
        status = '<span class="status ok">Online</span>' if scanner.get("online") else '<span class="status bad">Offline</span>'
        default = '<span class="status ok">Standard</span>' if scanner.get("is_default") else ''
        sources = ", ".join(scanner.get("sources", [])) or "vom Treiber automatisch gewählt"
        scanner_cards.append(f'''<article class="card"><div class="actions"><div>{status} {default}</div><a class="button secondary" href="/scanners">Verwalten</a></div><h2>{esc(scanner.get('name','Scanner'))}</h2><p><b>Verbindung:</b> <code>{esc(scanner.get('connection','-'))}</code></p><p><b>ADF-Quellen:</b> {esc(sources)}</p><p><b>Firmware:</b> {esc(scanner.get('firmware'))}<br><b>Seriennummer:</b> {esc(scanner.get('serial_number'))}</p></article>''')
    scanner_html = "".join(scanner_cards) or '<article class="card"><h2>Kein Scanner erkannt</h2><p>Öffne den Assistenten oder die Scannerverwaltung.</p></article>'
    profile_rows = "".join(f'<tr><td>{esc(pid)}</td><td>{esc(p.get("label",pid))}</td><td>{esc(p.get("dpi"))} dpi</td><td>{esc(p.get("mode"))}</td><td>{esc(p.get("format"))}</td></tr>' for pid,p in data["profiles"].items())
    due = [x for x in data["maintenance"] if str(x.get("next_due", "9999")) <= date.today().isoformat()]
    due_text = f'{len(due)} fällig' if due else 'keine fällige Wartung'
    content = f'''<section class="panel hero"><div><h1>Gerätezentrale</h1><p class="muted">OpenScanStation {VERSION} · Stand {esc(data['updated_at'])}</p></div><div class="actions"><a class="button" href="/setup">Einrichtungsassistent</a><a class="button secondary" href="/scanners">Scanner verwalten</a><a class="button secondary" href="/maintenance">Wartung</a></div></section>
<div class="metrics"><article class="card"><b>Scans heute</b><div class="metric">{stats['today']}</div></article><article class="card"><b>Scans im Monat</b><div class="metric">{stats['month']}</div></article><article class="card"><b>Dokumente gesamt</b><div class="metric">{stats['documents']}</div></article><article class="card"><b>Seiten gesamt</b><div class="metric">{stats['pages']}</div></article><article class="card"><b>Wartung</b><div class="metric">{esc(due_text)}</div></article></div>
<section class="panel"><h2>Scanner</h2></section><div class="grid">{scanner_html}</div>
<section class="panel"><h2>Scanprofile</h2><table><tr><th>ID</th><th>Name</th><th>DPI</th><th>Modus</th><th>Format</th></tr>{profile_rows}</table><p><a class="button secondary" href="/profiles">Profile bearbeiten</a></p></section>
<section class="panel"><h2>Unterstützungsstatus</h2><p>Firmware-Version, Seriennummer, Temperatur und echte Wartungszähler werden nur angezeigt, wenn das verwendete Backend diese Werte liefert. Beim Brother ADS-2600We stellt SANE diese Angaben üblicherweise nicht bereit; OpenScanStation zeigt dann bewusst „nicht verfügbar“.</p></section>'''
    return f'<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gerätezentrale</title><style>{STYLE}</style></head><body><main>{content}</main></body></html>'
