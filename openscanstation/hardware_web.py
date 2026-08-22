"""Modularer Hardware-Webdienst."""
from __future__ import annotations
import argparse,json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import parse_qs,urlparse
from openscanstation.cli import VERSION
from openscanstation.hardware_sections import layout,render
HOST="127.0.0.1"; PORT=8107

class Handler(BaseHTTPRequestHandler):
 protocol_version="HTTP/1.1"
 def send(self,data,status=200,ctype="text/html; charset=utf-8",head=False):
  body=data.encode() if isinstance(data,str) else data
  self.send_response(status); self.send_header("Content-Type",ctype); self.send_header("Content-Length",str(len(body))); self.send_header("X-OpenScanStation-Module","hardware"); self.end_headers()
  if not head:
   try:self.wfile.write(body)
   except (BrokenPipeError,ConnectionResetError):pass
 def _get(self,head=False):
  path=urlparse(self.path).path.rstrip("/") or "/"
  try:
   if path in {"/device-center","/geraetezentrale"}:
    from openscanstation.device_center import render as page; return self.send(page(),head=head)
   if path=="/scanners":
    from openscanstation.scanner_admin import render as page; return self.send(page(),head=head)
   if path in {"/profiles","/profile-assignment"}:
    from openscanstation.profile_assignment import render as page; return self.send(page(),head=head)
   if path=="/brother-profiles":
    from openscanstation.brother_device_profiles import render as page; return self.send(page(),head=head)
   if path=="/api/brother-device-profiles":
    from openscanstation.brother_device_profiles import manifest; return self.send(json.dumps(manifest(),ensure_ascii=False),ctype="application/json",head=head)
   if path=="/api/profiles":
    from openscanstation.profiles import load_profiles; return self.send(json.dumps(load_profiles(),ensure_ascii=False),ctype="application/json",head=head)
   if path=="/api/device-center":
    from openscanstation.device_center import snapshot; return self.send(json.dumps(snapshot(),ensure_ascii=False),ctype="application/json",head=head)
   if path=="/api/hardware":
    from openscanstation.hardware import cached_inventory; return self.send(json.dumps(cached_inventory(),ensure_ascii=False),ctype="application/json",head=head)
   if path=="/api/scanners":
    from openscanstation.hardware import cached_inventory
    from openscanstation.scanner_admin import manual_scanners
    from openscanstation.scanner_settings import load_settings
    return self.send(json.dumps({"automatic":[x for x in cached_inventory().get("devices",[]) if x.get("kind")=="scanner"],"manual":manual_scanners(),"settings":load_settings()},ensure_ascii=False),ctype="application/json",head=head)
   if path=="/health": return self.send(json.dumps({"status":"ok","service":"openscanstation-hardware","version":VERSION,"architecture":"modular"}),ctype="application/json",head=head)
   page=render(path)
   if page is not None:return self.send(page,head=head)
   return self.send(json.dumps({"error":"not_found","path":path}),404,"application/json",head)
  except Exception as exc:
   return self.send(layout("<section class='panel'><h2>Untermenü konnte nicht geladen werden</h2></section>","Hardware",str(exc),True),200,head=head)
 def do_GET(self):self._get(False)
 def do_HEAD(self):self._get(True)
 def _form(self):
  n=int(self.headers.get("Content-Length","0") or 0); return parse_qs(self.rfile.read(n).decode(),keep_blank_values=True)
 def do_POST(self):
  path=urlparse(self.path).path.rstrip("/") or "/"; form=self._form(); one=lambda k,d="":form.get(k,[d])[0]
  try:
   if path=="/profile-assignment/save":
    from openscanstation.profile_assignment import save,render as page
    save(one("profile_id"),one("owner"),one("visibility","all"),one("users"),one("destination","local"),one("show_on_device")=="1",int(one("device_order","10")),form.get("scanner",[])); return self.send(page("Zuordnung wurde gespeichert."))
   if path=="/scanner/auto-save":
    from openscanstation.scanner_settings import update_scanner
    from openscanstation.scanner_admin import render as page
    update_scanner(one("scanner_id"),alias=one("alias"),enabled=one("enabled")=="1",make_default=one("make_default")=="1"); return self.send(page("Scanner gespeichert."))
   if path=="/scanner/auto-hide":
    from openscanstation.scanner_settings import update_scanner
    from openscanstation.scanner_admin import render as page
    update_scanner(one("scanner_id"),alias="",enabled=False,make_default=False); return self.send(page("Scanner ausgeblendet."))
   if path=="/scanner/manual-save":
    from openscanstation.scanner_admin import save_manual_scanner,render as page
    save_manual_scanner(one("name"),one("uri"),one("backend"),one("original_id")); return self.send(page("Scanner gespeichert."))
   if path=="/scanner/manual-delete":
    from openscanstation.scanner_admin import delete_manual_scanner,render as page
    delete_manual_scanner(one("scanner_id")); return self.send(page("Scanner gelöscht."))
   if path=="/network/probe":
    from openscanstation.hardware import tcp_probe
    return self.send(layout(f"<section class='panel'><pre>{json.dumps(tcp_probe(one('host')),ensure_ascii=False,indent=2)}</pre></section>","Netzwerktest"))
   if path=="/printer/test":
    from openscanstation.hardware import print_test_page
    return self.send(layout("<section class='panel'><h2>Testseite gesendet</h2></section>","Drucker",print_test_page(one("printer")).get("message","")))
   if path=="/maintenance/complete":
    from openscanstation.hardware_management import complete_maintenance
    complete_maintenance(one("item_id")); return self.send(render("/maintenance") or "")
   return self.send(json.dumps({"error":"not_found"}),404,"application/json")
  except Exception as exc:return self.send(layout("<section class='panel'><h2>Aktion fehlgeschlagen</h2></section>","Hardware",str(exc),True),HTTPStatus.BAD_REQUEST)
 def log_message(self,fmt,*args):print(fmt%args)
class Server(ThreadingHTTPServer): daemon_threads=True; allow_reuse_address=True

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--host",default=HOST);p.add_argument("--port",type=int,default=PORT);a=p.parse_args(argv);s=Server((a.host,a.port),Handler)
 try:s.serve_forever()
 except KeyboardInterrupt:pass
 finally:s.server_close()
 return 0
if __name__=="__main__":raise SystemExit(main())
