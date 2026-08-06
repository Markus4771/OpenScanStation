"""Kommandozeile für OpenScanStation."""
from __future__ import annotations
import argparse,json,platform,shutil,subprocess
from pathlib import Path
from openscanstation.scanner.manager import ScannerManager
VERSION="0.16.0"
def command_version(_):print(VERSION);return 0
def command_scanners(_):
 r=ScannerManager().discover()
 for s in r.scanners:print(f"{s.name} [{s.plugin_id}]\n  Verbindung: {s.connection}\n  Duplex: {s.capabilities.duplex}\n  ADF: {s.capabilities.adf}")
 for e in r.errors:print(f"Fehler [{e.plugin_id}]: {e.message}")
 return 0 if r.scanners else 1
def command_hardware(_):
 from openscanstation.hardware import inventory_fallback
 print(json.dumps(inventory_fallback(),ensure_ascii=False,indent=2));return 0
def command_device_center(_):
 from openscanstation.device_center import snapshot
 print(json.dumps(snapshot(),ensure_ascii=False,indent=2));return 0
def command_brother_profiles(_):
 from openscanstation.brother_device_profiles import manifest
 print(json.dumps(manifest(),ensure_ascii=False,indent=2));return 0
def command_hardware_check(a):
 from openscanstation.hardware_health import load_last_report,run_hardware_checks
 r=load_last_report() if a.last else run_hardware_checks();print(json.dumps(r,ensure_ascii=False,indent=2) if a.json else f"Hardwareprüfung: {r.get('summary',{}).get('passed',0)}/{r.get('summary',{}).get('total',0)} Module OK")
 if not a.json:
  for x in r.get('results',[]):print(f"{'OK' if x.get('ok') else 'FEHLER':<7} {x.get('module',''):<18} {x.get('message','')}")
 return 0 if r and r.get('ok') else 1
def command_hardware_refresh(_):
 from openscanstation.hardware_health import clear_hardware_cache
 from openscanstation.hardware import inventory_fallback
 print(json.dumps({'cache':clear_hardware_cache(),'inventory':inventory_fallback()},ensure_ascii=False,indent=2));return 0
def command_doctor(_):
 print(f"OpenScanStation {VERSION}\nSystem: {platform.platform()}")
 failed=False
 for c in ('scanimage','airscan-discover','tesseract','pdftoppm','zbarimg','lp','lpstat','lpoptions'):
  p=shutil.which(c);print(f"{c}: {p or 'nicht gefunden'}");failed|=p is None
 return 1 if failed else 0
def build_parser():
 p=argparse.ArgumentParser(prog='openscanstation');s=p.add_subparsers(dest='command')
 for name,helptext,func in [('version','Version anzeigen',command_version),('scanners','Scanner erkennen',command_scanners),('hardware','Hardware als JSON',command_hardware),('device-center','Gerätezentrale als JSON',command_device_center),('brother-profiles','Brother-Geräteprofile',command_brother_profiles),('hardware-refresh','Hardwarecache erneuern',command_hardware_refresh),('doctor','Systemdiagnose',command_doctor)]:
  x=s.add_parser(name,help=helptext);x.set_defaults(func=func)
 x=s.add_parser('hardware-check',help='Hardwaremodule prüfen');x.add_argument('--json',action='store_true');x.add_argument('--last',action='store_true');x.set_defaults(func=command_hardware_check)
 return p
def main(argv=None):
 p=build_parser();a=p.parse_args(argv)
 if not getattr(a,'command',None):p.print_help();return 0
 return a.func(a)
if __name__=='__main__':raise SystemExit(main())
