"""Einheitlicher Webzugang für OpenScanStation auf Port 8101."""
from __future__ import annotations
import argparse,http.client,json,re
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from openscanstation.cli import VERSION
HOST="0.0.0.0";PORT=8101;MAIN_PORT=8111
ROUTES={"/hardware":8107,"/copy":8106,"/classification":8105,"/workflows":8104,"/storage":8103,"/devices":8102}
HOP={"connection","keep-alive","proxy-authenticate","proxy-authorization","te","trailers","transfer-encoding","upgrade"}
SCRIPT="""<script>(function(){const k='oss.menu.v2',ds=[...document.querySelectorAll('details[data-menu]')];let s={};try{s=JSON.parse(localStorage.getItem(k)||'{}')}catch(e){}ds.forEach(d=>{if(d.dataset.menu in s)d.open=!!s[d.dataset.menu];d.addEventListener('toggle',()=>{s[d.dataset.menu]=d.open;localStorage.setItem(k,JSON.stringify(s))})});const p=location.pathname.replace(/\/$/,'')||'/';document.querySelectorAll('.oss-menu a').forEach(a=>{const h=(a.getAttribute('href')||'').replace(/\/$/,'')||'/';if(h==='/'?p==='/':p===h||p.startsWith(h+'/'))a.classList.add('active')});if(p.startsWith('/hardware'))document.querySelector('[data-menu=hardware]').open=true;if(p==='/processing'||/^\/(storage|workflows|classification)/.test(p))document.querySelector('[data-menu=processing]').open=true})();</script>"""
STYLE="""<style>:root{--w:280px}body{margin:0!important;background:#f6f8fb!important}.oss-sidebar{position:fixed;inset:0 auto 0 0;width:var(--w);box-sizing:border-box;background:#0d2135;color:#fff;padding:24px 14px;overflow:auto;z-index:9999}.oss-brand{font-size:26px;font-weight:800;padding:0 10px 20px}.oss-menu{display:grid;gap:5px}.oss-menu a,.oss-menu summary{display:block;padding:11px 13px;border-radius:8px;color:#fff!important;text-decoration:none!important;font-weight:700;cursor:pointer}.oss-menu a:hover,.oss-menu a.active,.oss-menu summary:hover{background:#165cae}.oss-menu details>div{display:grid;margin-left:20px;border-left:1px solid #496075;padding-left:8px}.oss-content-shell{margin-left:var(--w);min-height:100vh}.oss-content-shell main{max-width:1500px!important;margin:0 auto!important;padding:40px 34px!important}.oss-content-shell>header,.oss-content-shell>nav{display:none!important}@media(max-width:650px){.oss-sidebar{position:relative;width:100%}.oss-content-shell{margin-left:0}}</style>"""
def sidebar():
 return f'''<aside class="oss-sidebar"><div class="oss-brand">OpenScanStation<br><small>Version {VERSION}</small></div><nav class="oss-menu"><a href="/">Dashboard</a><a href="/documents">Dokumente</a><a href="/profiles">Scanprofile</a><a href="/scanner-actions">Scanneraktionen</a><details data-menu="hardware" open><summary>Hardware</summary><div><a href="/hardware/">Übersicht</a><a href="/hardware/device-center">Gerätezentrale</a><a href="/hardware/monitor">Monitor</a><a href="/hardware/setup">Assistent</a><a href="/hardware/scanners">Scanner</a><a href="/hardware/profile-assignment">Profilzuordnung</a><a href="/hardware/printers">Drucker</a><a href="/hardware/network">Netzwerk</a><a href="/hardware/usb">USB-Geräte</a><a href="/hardware/brother">Brother-Assistent</a><a href="/hardware/brother-profiles">Brother-Geräteprofile</a><a href="/hardware/maintenance">Wartung</a><a href="/hardware/drivers">Treiber</a><a href="/hardware/diagnostics">Diagnose</a><a href="/hardware/support">Supportpaket</a></div></details><a href="/copy/">Kopieren</a><details data-menu="processing" open><summary>Verarbeitung</summary><div><a href="/processing">Übersicht</a><a href="/storage/">Speicherziele</a><a href="/workflows/">Workflows</a><a href="/classification/">Dokumenterkennung</a></div></details><a href="/system">System</a></nav></aside><div class="oss-content-shell">{SCRIPT}'''
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
 def proxy(self):
  p=urlsplit(self.path);port,target,prefix=route(p.path);target+=('?'+p.query) if p.query else ''
  n=int(self.headers.get("Content-Length","0") or 0);body=self.rfile.read(n) if n else None;headers={k:v for k,v in self.headers.items() if k.lower() not in HOP and k.lower()!='host'};headers['Host']=f'127.0.0.1:{port}'
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
