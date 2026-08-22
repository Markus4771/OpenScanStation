"""Einheitlicher Webzugang für OpenScanStation auf Port 8101."""
from __future__ import annotations
import argparse,http.client,html,json,re
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from openscanstation.cli import VERSION
from openscanstation.users import authenticate,create_session,delete_user,list_users,set_scanners,upsert_user,verify_session
HOST="0.0.0.0";PORT=8101;MAIN_PORT=8111
ROUTES={"/hardware":8107,"/copy":8106,"/classification":8105,"/workflows":8104,"/storage":8103,"/devices":8102}
HOP={"connection","keep-alive","proxy-authenticate","proxy-authorization","te","trailers","transfer-encoding","upgrade"}
SCRIPT="""<script>(function(){const k='oss.menu.v2',ds=[...document.querySelectorAll('details[data-menu]')];let s={};try{s=JSON.parse(localStorage.getItem(k)||'{}')}catch(e){}ds.forEach(d=>{if(d.dataset.menu in s)d.open=!!s[d.dataset.menu];d.addEventListener('toggle',()=>{s[d.dataset.menu]=d.open;localStorage.setItem(k,JSON.stringify(s))})});const p=location.pathname.replace(/\/$/,'')||'/';document.querySelectorAll('.oss-menu a').forEach(a=>{const h=(a.getAttribute('href')||'').replace(/\/$/,'')||'/';if(h==='/'?p==='/':h==='/hardware'?p===h:p===h||p.startsWith(h+'/'))a.classList.add('active')});if(p.startsWith('/hardware'))document.querySelector('[data-menu=hardware]').open=true;if(p==='/processing'||/^\/(storage|workflows|classification)/.test(p))document.querySelector('[data-menu=processing]').open=true})();</script>"""
STYLE="""<style>:root{--w:280px}body{margin:0!important;background:#f6f8fb!important}.oss-sidebar{position:fixed;inset:0 auto 0 0;width:var(--w);box-sizing:border-box;background:#0d2135;color:#fff;padding:24px 14px;overflow:auto;z-index:9999}.oss-brand{font-size:26px;font-weight:800;padding:0 10px 20px}.oss-menu{display:grid;gap:5px}.oss-menu a,.oss-menu summary{display:block;padding:11px 13px;border-radius:8px;color:#fff!important;text-decoration:none!important;font-weight:700;cursor:pointer}.oss-menu a:hover,.oss-menu a.active,.oss-menu summary:hover{background:#165cae}.oss-menu details>div{display:grid;margin-left:20px;border-left:1px solid #496075;padding-left:8px}.oss-content-shell{margin-left:var(--w);min-height:100vh}.oss-content-shell main{max-width:1500px!important;margin:0 auto!important;padding:40px 34px!important}.oss-content-shell>header,.oss-content-shell>nav{display:none!important}@media(max-width:650px){.oss-sidebar{position:relative;width:100%}.oss-content-shell{margin-left:0}}</style>"""
def sidebar():
 return f'''<aside class="oss-sidebar"><div class="oss-brand">OpenScanStation<br><small>Version {VERSION}</small></div><nav class="oss-menu"><a href="/">Dashboard</a><a href="/documents">Dokumente</a><a href="/profiles">Scanprofile</a><a href="/scanner-actions">Scanneraktionen</a><a href="/my-scanners">Meine Scanner</a><details data-menu="hardware" open><summary>Hardware</summary><div><a href="/hardware/">Übersicht</a><a href="/hardware/device-center">Gerätezentrale</a><a href="/hardware/monitor">Monitor</a><a href="/hardware/setup">Assistent</a><a href="/hardware/scanners">Scanner</a><a href="/hardware/profile-assignment">Profilzuordnung</a><a href="/hardware/printers">Drucker</a><a href="/hardware/network">Netzwerk</a><a href="/hardware/usb">USB-Geräte</a><a href="/hardware/brother">Brother-Assistent</a><a href="/hardware/brother-buttons">Brother-Tasten</a><a href="/hardware/brother-profiles">Brother-Geräteprofile</a><a href="/hardware/maintenance">Wartung</a><a href="/hardware/drivers">Treiber</a><a href="/hardware/diagnostics">Diagnose</a><a href="/hardware/support">Supportpaket</a></div></details><a href="/copy/">Kopieren</a><details data-menu="processing" open><summary>Verarbeitung</summary><div><a href="/processing">Übersicht</a><a href="/storage/">Speicherziele</a><a href="/workflows/">Workflows</a><a href="/classification/">Dokumenterkennung</a></div></details><a href="/users">Benutzer</a><a href="/system">System</a><a href="/logout">Abmelden</a></nav></aside><div class="oss-content-shell">{SCRIPT}'''
def route(path):
 for prefix,port in ROUTES.items():
  if path==prefix or path.startswith(prefix+"/"):return port,path[len(prefix):] or "/",prefix
 return MAIN_PORT,path,""
def rewrite(body,prefix):
 text=body.decode(errors="replace")
 if prefix:
  for attr in ("href","action","src"):text=re.sub(rf'({attr}=["\'])/(?!/)',rf'\1{prefix}/',text)
  text=text.replace(prefix+prefix+"/",prefix+"/")
 text=re.sub(r"(<head[^>]*>)",lambda m:m.group(1)+STYLE,text,count=1,flags=re.I)
 text=re.sub(r"(<body[^>]*>)",lambda m:m.group(1)+sidebar(),text,count=1,flags=re.I)
 text=re.sub(r"</body>","</div></body>",text,count=1,flags=re.I)
 return text.encode()
class Handler(BaseHTTPRequestHandler):
 protocol_version="HTTP/1.1"
 def send(self,payload,status=200,ctype="text/html; charset=utf-8"):
  self.send_response(status);self.send_header("Content-Type",ctype);self.send_header("Content-Length",str(len(payload)));self.end_headers()
  try:self.wfile.write(payload)
  except (BrokenPipeError,ConnectionResetError):pass
 def profile_page(self,message="",error=False):
  from openscanstation.central_profiles_web import render
  user=self.current_user() or {}
  self.send(rewrite(render(message,error,user.get("username",""),user.get("role")=="admin").encode(),""),400 if error else 200)
 def current_user(self):
  cookie=SimpleCookie(self.headers.get("Cookie",""));item=cookie.get("oss_session")
  return verify_session(item.value) if item else None
 def redirect(self,location,cookie=None):
  self.send_response(303);self.send_header("Location",location)
  if cookie:self.send_header("Set-Cookie",cookie)
  self.send_header("Content-Length","0");self.end_headers()
 def auth_page(self,setup=False,message=""):
  title="Ersteinrichtung" if setup else "Anmeldung"
  extra='<label>Anzeigename<input name="display_name" value="Administrator"></label><label>Kennwort wiederholen<input type="password" name="confirmation" required></label>' if setup else ''
  action="/setup" if setup else "/login"
  body=f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>body{{font-family:system-ui;background:#eef2f6;display:grid;place-items:center;min-height:100vh}}main{{width:min(420px,90vw);background:white;padding:2rem;border-radius:14px;box-shadow:0 4px 24px #0002}}form,label{{display:grid;gap:.5rem;margin:.8rem 0}}input,button{{padding:.8rem;border:1px solid #abb5bf;border-radius:8px}}button{{background:#17202a;color:white;font-weight:700}}.error{{color:#922b21}}</style></head><body><main><h1>OpenScanStation</h1><h2>{title}</h2><p class="error">{html.escape(message)}</p><form method="post" action="{action}"><label>Benutzername<input name="username" value="admin" required></label>{extra}<label>Kennwort<input type="password" name="password" required></label><button>{'Administrator anlegen' if setup else 'Anmelden'}</button></form></main></body></html>'''
  self.send(body.encode(),401 if message else 200)
 def users_page(self,user,message=""):
  rows=''.join(f'<tr><td>{html.escape(x["username"])}</td><td>{html.escape(x.get("display_name",""))}</td><td>{html.escape(x.get("role","user"))}</td><td>{"aktiv" if x.get("enabled") else "gesperrt"}</td><td><form method="post" action="/users/delete"><input type="hidden" name="username" value="{html.escape(x["username"],quote=True)}"><button>Loeschen</button></form></td></tr>' for x in list_users())
  content=f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Benutzer</title></head><body><main><h1>Lokale Benutzer</h1><p>{html.escape(message)}</p><form method="post" action="/users/create"><label>Benutzername<input name="username" required></label><label>Anzeigename<input name="display_name"></label><label>Rolle<select name="role"><option value="user">Benutzer</option><option value="admin">Administrator</option></select></label><label>Kennwort<input type="password" name="password" required></label><button>Anlegen</button></form><table><tr><th>Benutzer</th><th>Name</th><th>Rolle</th><th>Status</th><th></th></tr>{rows}</table></main></body></html>'''
  self.send(rewrite(content.encode(),""))
 def proxy(self):
  p=urlsplit(self.path)
  users_exist=bool(list_users())
  if not users_exist:
   if p.path=="/setup" and self.command=="POST":
    n=int(self.headers.get("Content-Length","0") or 0);form=parse_qs(self.rfile.read(n).decode(),keep_blank_values=True);get=lambda k:form.get(k,[""])[0]
    try:
     if get("password")!=get("confirmation"):raise ValueError("Kennwoerter stimmen nicht ueberein")
     user=upsert_user(get("username"),get("password"),role="admin",display_name=get("display_name"));token=create_session(user)
     return self.redirect("/",f"oss_session={token}; Path=/; HttpOnly; SameSite=Strict")
    except Exception as exc:return self.auth_page(True,str(exc))
   return self.auth_page(True)
  if p.path=="/login":
   if self.command=="GET":return self.auth_page(False)
   n=int(self.headers.get("Content-Length","0") or 0);form=parse_qs(self.rfile.read(n).decode(),keep_blank_values=True);user=authenticate(form.get("username",[""])[0],form.get("password",[""])[0])
   if not user:return self.auth_page(False,"Benutzername oder Kennwort ist falsch")
   return self.redirect("/",f"oss_session={create_session(user)}; Path=/; HttpOnly; SameSite=Strict")
  if p.path=="/logout":return self.redirect("/login","oss_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
  user=self.current_user()
  if not user:return self.redirect("/login")
  if p.path=="/users":
   if user.get("role")!="admin":return self.send(b"Administratorrechte erforderlich",403,"text/plain; charset=utf-8")
   return self.users_page(user)
  if p.path=="/my-scanners":
   if self.command=="POST":
    n=int(self.headers.get("Content-Length","0") or 0);form=parse_qs(self.rfile.read(n).decode(),keep_blank_values=True);user=set_scanners(user["username"],form.get("scanner",[]))
   from openscanstation.web import _scanner_payload
   scanners=_scanner_payload().get("scanners",[]);selected=set(user.get("scanners",[]))
   choices=''.join(f'<label><input type="checkbox" name="scanner" value="{html.escape(s["id"],quote=True)}" {"checked" if s["id"] in selected else ""}> {html.escape(s["name"])}</label>' for s in scanners)
   page=f'<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Meine Scanner</title></head><body><main><h1>Meine Scanner</h1><p>Waehle die Scanner, die auf deinem Dashboard verfuegbar sein sollen.</p><form method="post" action="/my-scanners">{choices or "<p>Keine Scanner erkannt.</p>"}<button>Speichern</button></form></main></body></html>'
   return self.send(rewrite(page.encode(),""))
  if p.path in {"/users/create","/users/delete"} and self.command=="POST":
   if user.get("role")!="admin":return self.send(b"Administratorrechte erforderlich",403,"text/plain; charset=utf-8")
   n=int(self.headers.get("Content-Length","0") or 0);form=parse_qs(self.rfile.read(n).decode(),keep_blank_values=True);get=lambda k,d="":form.get(k,[d])[0]
   try:
    if p.path.endswith("create"):upsert_user(get("username"),get("password"),role=get("role","user"),display_name=get("display_name"))
    else:delete_user(get("username"))
    return self.users_page(user,"Benutzerverwaltung aktualisiert.")
   except Exception as exc:return self.users_page(user,str(exc))
  if user.get("role")!="admin" and (p.path.startswith("/hardware") or p.path=="/system"):
   return self.send(b"Administratorrechte erforderlich",403,"text/plain; charset=utf-8")
  if p.path=="/profiles":
   if self.command=="GET":return self.profile_page()
  if p.path in {"/central-profiles/save","/central-profiles/delete"} and self.command=="POST":
   try:
    n=int(self.headers.get("Content-Length","0") or 0);form=parse_qs(self.rfile.read(n).decode(),keep_blank_values=True);get=lambda k,d="":form.get(k,[d])[0]
    from openscanstation.profile_service import save_profile,remove_profile
    from openscanstation.profiles import load_profiles
    current=self.current_user();admin=current.get("role")=="admin";profile_id=get("profile_id");existing=load_profiles().get(profile_id)
    if existing and not admin and existing.get("owner")!=current["username"]:raise PermissionError("Profil gehoert einem anderen Benutzer")
    if p.path.endswith("save"):
     def owned_get(key,default=""):
      if not admin and key=="owner":return current["username"]
      if not admin and key=="visibility":return "owner"
      return get(key,default)
     save_profile(owned_get,False);return self.profile_page("Profil wurde gespeichert.")
    remove_profile(profile_id);return self.profile_page("Profil wurde gelöscht.")
   except Exception as exc:return self.profile_page(str(exc),True)
  port,target,prefix=route(p.path);target+=('?'+p.query) if p.query else ''
  n=int(self.headers.get("Content-Length","0") or 0);body=self.rfile.read(n) if n else None;headers={k:v for k,v in self.headers.items() if k.lower() not in HOP and k.lower()!='host' and not k.lower().startswith('x-openscanstation-')};headers['Host']=f'127.0.0.1:{port}';headers['X-OpenScanStation-User']=user['username'];headers['X-OpenScanStation-Role']=user['role'];headers['X-OpenScanStation-Scanners']=','.join(user.get('scanners',[]))
  conn=None
  try:
   conn=http.client.HTTPConnection('127.0.0.1',port,timeout=45);conn.request(self.command,target,body=body,headers=headers);r=conn.getresponse();data=r.read();ctype=r.getheader('Content-Type','')
   if 'text/html' in ctype:data=rewrite(data,prefix)
   self.send_response(r.status,r.reason)
   for k,v in r.getheaders():
    if k.lower() in HOP or k.lower()=='content-length':continue
    if k.lower()=='location' and prefix and v.startswith('/'):v=prefix+v
    self.send_header(k,v)
   self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  except Exception as exc:self.send(f'Modul nicht erreichbar: {exc}'.encode(),502,'text/plain; charset=utf-8')
  finally:
   if conn:conn.close()
 do_GET=proxy;do_POST=proxy;do_PUT=proxy;do_DELETE=proxy;do_PATCH=proxy
 def log_message(self,fmt,*args):print(fmt%args)
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--host',default=HOST);p.add_argument('--port',type=int,default=PORT);a=p.parse_args(argv);s=ThreadingHTTPServer((a.host,a.port),Handler)
 try:s.serve_forever()
 except KeyboardInterrupt:pass
 finally:s.server_close()
 return 0
if __name__=='__main__':raise SystemExit(main())
