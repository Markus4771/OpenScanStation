"""Zentrale Scanprofile für Dashboard, Hardware und Geräteanzeige."""
from __future__ import annotations
import json, os, re, tempfile
from copy import deepcopy
from pathlib import Path

PROFILE_PATH = Path(os.environ.get("OPENSCANSTATION_PROFILE_PATH", "/var/lib/openscanstation/profiles.json"))
LEGACY_HARDWARE_PROFILE_PATH = Path("/var/lib/openscanstation/hardware_scan_profiles.json")
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
ALLOWED_DPI = (75,100,150,200,240,300,400,600)
ALLOWED_MODES = ("color","gray","lineart")
ALLOWED_FORMATS = ("pdf","png","jpg")
DEFAULT_PROFILES = {
 "rechnung":{"label":"Rechnung","dpi":300,"mode":"gray","format":"pdf","ocr":True,"duplex":True},
 "lieferschein":{"label":"Lieferschein","dpi":300,"mode":"gray","format":"pdf","ocr":True,"duplex":True},
 "dokument":{"label":"Dokument","dpi":300,"mode":"color","format":"pdf","ocr":True,"duplex":False},
 "foto":{"label":"Foto","dpi":600,"mode":"color","format":"jpg","ocr":False,"duplex":False},
 "archiv":{"label":"Archiv PDF/A","dpi":300,"mode":"gray","format":"pdf","ocr":True,"duplex":True},
}

def _list(value):
    if isinstance(value,list): return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value,str): return [x.strip() for x in value.split(",") if x.strip()]
    return []

def normalize_profile(profile_id:str, raw:object)->dict:
    if not PROFILE_ID_PATTERN.fullmatch(profile_id): raise ValueError("Ungültige Profil-ID")
    if not isinstance(raw,dict): raise ValueError("Ungültige Profildaten")
    label=str(raw.get("label") or raw.get("name") or "").strip()
    if not label or len(label)>80: raise ValueError("Ungültiger Profilname")
    dpi=int(raw.get("dpi",raw.get("resolution",300)))
    if dpi not in ALLOWED_DPI: raise ValueError("Ungültige Auflösung")
    mode=str(raw.get("mode","color")).lower(); mode={"farbe":"color","graustufen":"gray","gray":"gray","lineart":"lineart"}.get(mode,mode)
    if mode not in ALLOWED_MODES: raise ValueError("Ungültiger Farbmodus")
    fmt=str(raw.get("format",raw.get("output_format","pdf"))).lower().replace("jpeg","jpg")
    if fmt not in ALLOWED_FORMATS: fmt="pdf"
    visibility=str(raw.get("visibility","all"))
    if visibility not in {"all","users","owner"}: visibility="all"
    return {
      "label":label,"dpi":dpi,"mode":mode,"format":fmt,
      "ocr":bool(raw.get("ocr",False)),"duplex":bool(raw.get("duplex",False)),
      "owner":str(raw.get("owner","")).strip()[:80],
      "visibility":visibility,"users":_list(raw.get("users",[])),
      "scanners":_list(raw.get("scanners",[])),
      "destination":str(raw.get("destination","local")).strip()[:80] or "local",
      "show_on_device":bool(raw.get("show_on_device",False)),
      "device_order":max(1,min(99,int(raw.get("device_order",10)))),
    }

def normalize_profiles(data:object, defaults_on_invalid:bool=True)->dict:
    if not isinstance(data,dict): return deepcopy(DEFAULT_PROFILES) if defaults_on_invalid else {}
    result={}
    for key,value in data.items():
        pid=str(key).strip().lower()
        try: result[pid]=normalize_profile(pid,value)
        except Exception: pass
    return result if result or not defaults_on_invalid else deepcopy(DEFAULT_PROFILES)

def _atomic_write(data:dict)->None:
    PROFILE_PATH.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix="profiles-",suffix=".json",dir=PROFILE_PATH.parent)
    try:
      with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
      os.replace(tmp,PROFILE_PATH)
    finally:
      try: os.unlink(tmp)
      except FileNotFoundError: pass

def migrate_legacy_hardware_profiles(profiles:dict)->dict:
    if not LEGACY_HARDWARE_PROFILE_PATH.exists(): return profiles
    try: legacy=json.loads(LEGACY_HARDWARE_PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception: return profiles
    items=legacy.values() if isinstance(legacy,dict) else legacy if isinstance(legacy,list) else []
    changed=False
    for idx,item in enumerate(items,1):
      if not isinstance(item,dict): continue
      base=str(item.get("id") or item.get("name") or f"hardware_{idx}").lower()
      pid=re.sub(r"[^a-z0-9_-]+","_",base).strip("_")[:32] or f"hardware_{idx}"
      if pid in profiles: continue
      try: profiles[pid]=normalize_profile(pid,item); changed=True
      except Exception: pass
    if changed: _atomic_write(profiles)
    try: LEGACY_HARDWARE_PROFILE_PATH.rename(LEGACY_HARDWARE_PROFILE_PATH.with_suffix(".json.migrated"))
    except OSError: pass
    return profiles

def load_profiles()->dict:
    PROFILE_PATH.parent.mkdir(parents=True,exist_ok=True)
    if not PROFILE_PATH.exists(): _atomic_write(normalize_profiles(deepcopy(DEFAULT_PROFILES)))
    try: data=json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception: data={}
    profiles=normalize_profiles(data,defaults_on_invalid=False)
    return migrate_legacy_hardware_profiles(profiles)

def save_profiles(profiles:dict)->dict:
    normalized=normalize_profiles(profiles,defaults_on_invalid=False); _atomic_write(normalized); return normalized

def reset_default_profiles()->dict: return save_profiles(deepcopy(DEFAULT_PROFILES))
def upsert_profile(profile_id:str, profile:dict, create_only:bool=False)->dict:
    pid=profile_id.strip().lower(); normalized=normalize_profile(pid,profile); profiles=load_profiles()
    if create_only and pid in profiles: raise ValueError("Diese Profil-ID ist bereits vorhanden")
    profiles[pid]=normalized; return save_profiles(profiles)
def delete_profile(profile_id:str)->dict:
    profiles=load_profiles()
    if profile_id not in profiles: raise ValueError("Scanprofil wurde nicht gefunden")
    del profiles[profile_id]; return save_profiles(profiles)
def delete_all_profiles()->dict: return save_profiles({})
def profiles_for_user(user:str)->dict:
    result={}
    for pid,p in load_profiles().items():
      if p["visibility"]=="all" or (p["visibility"]=="owner" and p["owner"]==user) or (p["visibility"]=="users" and user in p["users"]): result[pid]=p
    return result
