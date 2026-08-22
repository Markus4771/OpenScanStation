"""Hardware-Zuordnung der zentralen Scanprofile."""
from __future__ import annotations
import html
from openscanstation.profiles import load_profiles, upsert_profile
from openscanstation.hardware import inventory

STYLE="""body{font-family:system-ui;margin:0;background:#f3f6f9;color:#17202a}main{max-width:1450px;margin:1.3rem auto;padding:0 1rem}.panel,.card{background:#fff;padding:1.15rem;border-radius:14px;box-shadow:0 2px 14px #0001;margin-bottom:1rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}form{display:grid;gap:.65rem}label{display:grid;gap:.25rem}input,select,button{padding:.65rem;border:1px solid #bcc5cc;border-radius:8px}button,a.button{background:#17202a;color:#fff;border:0;text-decoration:none;font-weight:700;cursor:pointer}.muted{color:#687684}.notice{padding:1rem;background:#d5f5e3;border-radius:9px;margin-bottom:1rem}"""
def esc(v,attr=False): return html.escape(str(v),quote=attr)

def render(notice=""):
    from openscanstation.hardware import cached_inventory
    profiles=load_profiles(); devices=[d for d in cached_inventory().get("devices",[]) if d.get("kind")=="scanner"]
    options=[(str(d.get("id","")),str(d.get("name","Scanner"))) for d in devices]
    cards=[]
    for pid,p in profiles.items():
      scanner_checks=''.join(f'<label><input type="checkbox" name="scanner" value="{esc(sid,True)}" {"checked" if sid in p.get("scanners",[]) else ""}> {esc(name)}</label>' for sid,name in options) or '<p class="muted">Noch kein Scanner erkannt.</p>'
      cards.append(f'''<article class="card"><h2>{esc(p.get('label',pid))}</h2><form method="post" action="/profile-assignment/save"><input type="hidden" name="profile_id" value="{esc(pid,True)}"><label>Eigentümer<input name="owner" value="{esc(p.get('owner',''),True)}" placeholder="z. B. markus"></label><label>Sichtbarkeit<select name="visibility"><option value="all" {"selected" if p.get('visibility')=='all' else ''}>Alle Benutzer</option><option value="users" {"selected" if p.get('visibility')=='users' else ''}>Ausgewählte Benutzer</option><option value="owner" {"selected" if p.get('visibility')=='owner' else ''}>Nur Eigentümer</option></select></label><label>Benutzer, kommagetrennt<input name="users" value="{esc(', '.join(p.get('users',[])),True)}"></label><label>Speicherziel<input name="destination" value="{esc(p.get('destination','local'),True)}"></label><label><input type="checkbox" name="show_on_device" value="1" {"checked" if p.get('show_on_device') else ''}> Auf Scanner/Display anbieten</label><label>Reihenfolge<input type="number" min="1" max="99" name="device_order" value="{int(p.get('device_order',10))}"></label><fieldset><legend>Scannerzuordnung</legend>{scanner_checks}</fieldset><button>Zuordnung speichern</button></form></article>''')
    note=f'<div class="notice">{esc(notice)}</div>' if notice else ''
    body=f'''{note}<section class="panel"><h1>Profilzuordnung</h1><p>Hier werden die zentralen Scanprofile Benutzern, Scannern, Speicherzielen und der Geräteanzeige zugeordnet. Die eigentlichen Scanparameter werden nur im Hauptmenü „Scanprofile“ bearbeitet.</p><a class="button" href="/profiles">Zentrale Scanprofile öffnen</a></section><div class="grid">{''.join(cards) or '<article class="card"><h2>Keine Scanprofile vorhanden</h2></article>'}</div>'''
    return f'<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Profilzuordnung</title><style>{STYLE}</style></head><body><main>{body}</main></body></html>'

def save(profile_id:str, owner:str, visibility:str, users:str, destination:str, show_on_device:bool, device_order:int, scanners:list[str]):
    profiles=load_profiles()
    if profile_id not in profiles: raise ValueError("Profil nicht gefunden")
    p=dict(profiles[profile_id]); p.update({"owner":owner,"visibility":visibility,"users":[x.strip() for x in users.split(',') if x.strip()],"destination":destination or "local","show_on_device":show_on_device,"device_order":device_order,"scanners":scanners})
    upsert_profile(profile_id,p)
