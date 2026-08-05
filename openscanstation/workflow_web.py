"""WebGUI für OpenScanStation-Workflows auf Port 8104."""
from __future__ import annotations
import argparse, html, json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from openscanstation.cli import VERSION
from openscanstation.scanner_actions import load_actions
from openscanstation.storage_targets import load_targets
from openscanstation.workflows import delete_workflow, execute_workflow, list_runs, load_workflows, upsert_workflow

HOST="0.0.0.0"; PORT=8104

def _layout(content: str, notice: str="", error: bool=False) -> str:
    note=f'<div class="notice {"error" if error else "success"}">{html.escape(notice)}</div>' if notice else ""
    return f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenScanStation Workflows</title><style>body{{font-family:system-ui;margin:0;background:#f3f5f7;color:#17202a}}header{{background:#17202a;color:#fff;padding:1.2rem 2rem}}main{{max-width:1200px;margin:1.5rem auto;padding:0 1rem}}.panel,.card{{background:#fff;padding:1.2rem;border-radius:12px;box-shadow:0 2px 12px #0001;margin-bottom:1rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}}form{{display:grid;gap:.7rem}}label{{display:grid;gap:.3rem;font-weight:700}}input,select,textarea,button{{padding:.7rem;border:1px solid #bcc5cc;border-radius:8px}}textarea{{min-height:120px}}button{{background:#17202a;color:#fff;font-weight:700}}.danger{{background:#922b21}}.notice{{padding:1rem;border-radius:8px;margin-bottom:1rem}}.success{{background:#d5f5e3}}.error{{background:#fadbd8}}table{{width:100%;border-collapse:collapse}}th,td{{padding:.6rem;border-bottom:1px solid #ddd;text-align:left}}code{{overflow-wrap:anywhere}}</style></head><body><header><h1>OpenScanStation Workflows</h1><div>Version {VERSION} · Port {PORT}</div></header><main>{note}{content}</main></body></html>'''

def _steps_text(steps: list[dict]) -> str:
    return "\n".join(f"{s['type']}|{'1' if s.get('enabled',True) else '0'}|"+",".join(f"{k}={v}" for k,v in s.get('config',{}).items()) for s in steps)

def _parse_steps(text: str) -> list[dict]:
    result=[]
    for line in text.splitlines():
        if not line.strip(): continue
        parts=line.split("|",2); kind=parts[0].strip(); enabled=len(parts)<2 or parts[1].strip()!="0"; cfg={}
        if len(parts)>2:
            for pair in parts[2].split(","):
                if "=" in pair:
                    k,v=pair.split("=",1); cfg[k.strip()]=v.strip()
        result.append({"type":kind,"enabled":enabled,"config":cfg})
    return result

def _page(notice: str="", error: bool=False) -> str:
    targets=load_targets(public=True)["targets"]
    cards=[]
    for wf in load_workflows()["workflows"]:
        cards.append(f'''<article class="card"><h2>{html.escape(wf['name'])}</h2><form method="post" action="/save"><input type="hidden" name="id" value="{html.escape(wf['id'],quote=True)}"><label>Name<input name="name" value="{html.escape(wf['name'],quote=True)}"></label><label>Aktiv<select name="enabled"><option value="1" {'selected' if wf['enabled'] else ''}>Ja</option><option value="0" {'selected' if not wf['enabled'] else ''}>Nein</option></select></label><label>Schritte<textarea name="steps">{html.escape(_steps_text(wf['steps']))}</textarea></label><button>Speichern</button></form><form method="post" action="/delete"><input type="hidden" name="id" value="{html.escape(wf['id'],quote=True)}"><button class="danger">Löschen</button></form></article>''')
    target_info="".join(f"<li><code>{html.escape(t['id'])}</code> – {html.escape(t['name'])}</li>" for t in targets)
    runs="".join(f"<tr><td>{html.escape(r.get('started_at',''))}</td><td>{html.escape(r.get('workflow_id',''))}</td><td>{html.escape(r.get('filename',''))}</td><td>{html.escape(r.get('status',''))}</td></tr>" for r in list_runs(20)) or '<tr><td colspan="4">Noch keine Läufe.</td></tr>'
    create='''<section class="panel"><h2>Workflow hinzufügen</h2><form method="post" action="/create"><label>ID<input name="id" pattern="[a-z0-9_-]+" required></label><label>Name<input name="name" required></label><label>Schritte<textarea name="steps">ocr|1|\nrename|1|template={date}_{title}_{filename}\nstore|1|target_id=local</textarea></label><button>Workflow anlegen</button></form><p>Format je Zeile: <code>typ|1|schlüssel=wert</code>. Typen: ocr, rename, store, tag, notify.</p><h3>Verfügbare Speicherziele</h3><ul>'''+target_info+'</ul></section>'
    history=f'<section class="panel"><h2>Letzte Workflow-Läufe</h2><table><tr><th>Zeit</th><th>Workflow</th><th>Datei</th><th>Status</th></tr>{runs}</table></section>'
    return _layout(create+'<div class="grid">'+''.join(cards)+'</div>'+history,notice,error)

def _used_by(wid: str) -> list[str]:
    return [a.get("label",a["id"]) for a in load_actions()["actions"] if a.get("workflow")==wid]

class Handler(BaseHTTPRequestHandler):
    def _send(self,data,status=200,ctype="text/html; charset=utf-8"):
        body=data.encode() if isinstance(data,str) else data; self.send_response(status); self.send_header("Content-Type",ctype); self.send_header("Content-Length",str(len(body))); self.send_header("X-Frame-Options","DENY"); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/": self._send(_page())
        elif path=="/health": self._send(json.dumps({"status":"ok","service":"openscanstation-workflows","version":VERSION,"port":PORT}),ctype="application/json")
        elif path=="/api/workflows": self._send(json.dumps(load_workflows(),ensure_ascii=False),ctype="application/json")
        elif path=="/api/runs": self._send(json.dumps({"runs":list_runs()},ensure_ascii=False),ctype="application/json")
        else: self._send(json.dumps({"error":"not_found"}),404,"application/json")
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            length=int(self.headers.get("Content-Length","0")); form=parse_qs(self.rfile.read(length).decode(),keep_blank_values=True)
            wid=form.get("id",[""])[0]
            if path in {"/create","/save"}:
                upsert_workflow({"id":wid,"name":form.get("name",[""])[0],"enabled":form.get("enabled",["1"])[0]=="1","steps":_parse_steps(form.get("steps",[""])[0])},create_only=path=="/create")
                self._send(_page("Workflow gespeichert.")); return
            if path=="/delete": delete_workflow(wid,used_by=_used_by(wid)); self._send(_page("Workflow gelöscht.")); return
            if path=="/execute":
                run=execute_workflow(wid,form.get("filename",[""])[0],title=form.get("title",["Dokument"])[0]); self._send(json.dumps(run,ensure_ascii=False),ctype="application/json"); return
            self._send(json.dumps({"error":"not_found"}),404,"application/json")
        except Exception as exc: self._send(_page(str(exc),True),HTTPStatus.BAD_REQUEST)
    def log_message(self,fmt,*args): print(fmt%args)

def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("--host",default=HOST); parser.add_argument("--port",type=int,default=PORT); args=parser.parse_args(argv)
    server=ThreadingHTTPServer((args.host,args.port),Handler); print(f"Workflow-WebGUI auf {args.host}:{args.port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0

if __name__=="__main__": raise SystemExit(main())
