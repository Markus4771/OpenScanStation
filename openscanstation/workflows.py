"""Konfigurierbare Workflow-Engine für OpenScanStation."""
from __future__ import annotations

import json
import os
import shutil
import smtplib
import tempfile
from copy import deepcopy
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.request import Request, urlopen

from openscanstation.documents import SCAN_DIR, run_ocr
from openscanstation.storage_targets import target_by_id

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
WORKFLOWS_FILE = DATA_DIR / "workflows.json"
RUNS_FILE = DATA_DIR / "workflow_runs.json"
SUPPORTED_STEPS = ("ocr", "rename", "store", "tag", "notify")

DEFAULT_WORKFLOWS = {
    "schema_version": 1,
    "workflows": [{
        "id": "standard",
        "name": "Standardablage",
        "enabled": True,
        "steps": [
            {"type": "ocr", "enabled": True, "config": {}},
            {"type": "rename", "enabled": True, "config": {"template": "{date}_{title}_{filename}"}},
            {"type": "store", "enabled": True, "config": {"target_id": "local"}},
        ],
    }],
}


def _safe_id(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for ch in text):
        raise ValueError("Ungültige Workflow-ID")
    return text[:64]


def _normalize_step(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Ungültiger Workflow-Schritt")
    step_type = str(raw.get("type", "")).strip().lower()
    if step_type not in SUPPORTED_STEPS:
        raise ValueError(f"Nicht unterstützter Workflow-Schritt: {step_type}")
    config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
    return {"type": step_type, "enabled": bool(raw.get("enabled", True)), "config": {str(k)[:64]: str(v)[:1024] for k, v in config.items()}}


def _normalize_workflow(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Ungültiger Workflow")
    workflow_id = _safe_id(raw.get("id"))
    name = str(raw.get("name", "")).strip()[:80]
    if not name:
        raise ValueError("Workflow-Name fehlt")
    steps = [_normalize_step(step) for step in raw.get("steps", [])]
    if not steps:
        raise ValueError("Ein Workflow benötigt mindestens einen Schritt")
    return {"id": workflow_id, "name": name, "enabled": bool(raw.get("enabled", True)), "steps": steps[:20]}


def _normalize(data: object) -> dict:
    workflows = []
    seen = set()
    if isinstance(data, dict) and isinstance(data.get("workflows"), list):
        for raw in data["workflows"]:
            try:
                item = _normalize_workflow(raw)
            except ValueError:
                continue
            if item["id"] not in seen:
                workflows.append(item)
                seen.add(item["id"])
    if not workflows:
        workflows = deepcopy(DEFAULT_WORKFLOWS["workflows"])
    return {"schema_version": 1, "workflows": workflows}


def load_workflows() -> dict:
    try:
        return _normalize(json.loads(WORKFLOWS_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return deepcopy(DEFAULT_WORKFLOWS)


def _atomic_write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.stem + "-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try: os.unlink(temp_name)
        except FileNotFoundError: pass


def save_workflows(data: dict) -> dict:
    normalized = _normalize(data)
    _atomic_write(WORKFLOWS_FILE, normalized)
    return normalized


def upsert_workflow(workflow: dict, *, create_only: bool = False) -> dict:
    item = _normalize_workflow(workflow)
    data = load_workflows()
    existing = next((x for x in data["workflows"] if x["id"] == item["id"]), None)
    if create_only and existing:
        raise ValueError("Workflow-ID existiert bereits")
    if existing:
        existing.clear(); existing.update(item)
    else:
        data["workflows"].append(item)
    return save_workflows(data)


def delete_workflow(workflow_id: str, *, used_by: list[str] | None = None) -> dict:
    if used_by:
        raise ValueError("Workflow wird noch verwendet: " + ", ".join(used_by))
    data = load_workflows()
    if len(data["workflows"]) == 1:
        raise ValueError("Der letzte Workflow kann nicht gelöscht werden")
    before = len(data["workflows"])
    data["workflows"] = [x for x in data["workflows"] if x["id"] != workflow_id]
    if len(data["workflows"]) == before:
        raise ValueError("Workflow nicht gefunden")
    return save_workflows(data)


def workflow_by_id(workflow_id: str) -> dict | None:
    return next((x for x in load_workflows()["workflows"] if x["id"] == workflow_id), None)


def _safe_filename(value: str) -> str:
    value = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value.strip())
    return value[:180] or "scan"


def _store(path: Path, target: dict) -> str:
    cfg = target["config"]
    kind = target["type"]
    if kind == "local":
        dest_dir = Path(cfg["path"]); dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / path.name
        if path.resolve() != dest.resolve(): shutil.copy2(path, dest)
        return str(dest)
    if kind == "webdav":
        base = cfg["url"].rstrip("/")
        req = Request(base + "/" + path.name, data=path.read_bytes(), method="PUT")
        if cfg.get("username"):
            import base64
            token = base64.b64encode(f"{cfg['username']}:{cfg.get('password','')}".encode()).decode()
            req.add_header("Authorization", "Basic " + token)
        with urlopen(req, timeout=30) as response:
            if response.status >= 400: raise RuntimeError(f"WebDAV HTTP {response.status}")
        return base + "/" + path.name
    if kind == "email":
        msg = EmailMessage(); msg["From"] = cfg["sender"]; msg["To"] = cfg["recipient"]
        msg["Subject"] = "OpenScanStation: " + path.name; msg.set_content("Dokument im Anhang.")
        msg.add_attachment(path.read_bytes(), maintype="application", subtype="octet-stream", filename=path.name)
        with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port") or 587), timeout=30) as smtp:
            if cfg.get("starttls"): smtp.starttls()
            if cfg.get("smtp_user"): smtp.login(cfg["smtp_user"], cfg.get("smtp_password", ""))
            smtp.send_message(msg)
        return "mailto:" + cfg["recipient"]
    raise RuntimeError(f"Übertragung für {kind} benötigt das optionale Backend und ist noch nicht aktiv")


def execute_workflow(workflow_id: str, filename: str, *, title: str = "Dokument", tags: list[str] | None = None) -> dict:
    workflow = workflow_by_id(workflow_id)
    if not workflow or not workflow["enabled"]:
        raise ValueError("Workflow nicht gefunden oder deaktiviert")
    path = SCAN_DIR / Path(filename).name
    if not path.is_file():
        raise FileNotFoundError(path)
    context = {"filename": path.name, "title": title, "tags": list(tags or []), "date": datetime.now().strftime("%Y-%m-%d")}
    results = []
    status = "success"
    try:
        for index, step in enumerate(workflow["steps"], 1):
            if not step["enabled"]: continue
            kind, cfg = step["type"], step["config"]
            if kind == "ocr":
                run_ocr(path.name); detail = "OCR abgeschlossen"
            elif kind == "rename":
                template = cfg.get("template", "{date}_{title}_{filename}")
                new_name = _safe_filename(template.format(**context))
                if "." not in Path(new_name).name: new_name += path.suffix
                new_path = path.with_name(new_name)
                if new_path != path: path.rename(new_path); path = new_path; context["filename"] = path.name
                detail = path.name
            elif kind == "store":
                target = target_by_id(cfg.get("target_id", "local"))
                if not target or not target["enabled"]: raise ValueError("Speicherziel nicht verfügbar")
                detail = _store(path, target)
            elif kind == "tag":
                extra = [x.strip() for x in cfg.get("tags", "").split(",") if x.strip()]
                context["tags"] = sorted(set(context["tags"] + extra)); detail = ", ".join(context["tags"])
            else:
                detail = cfg.get("message", "Workflow abgeschlossen").format(**context)
            results.append({"step": index, "type": kind, "ok": True, "detail": detail})
    except Exception as exc:
        status = "failed"; results.append({"step": len(results) + 1, "type": step.get("type", "unknown"), "ok": False, "detail": str(exc)})
    run = {"workflow_id": workflow_id, "filename": path.name, "status": status, "started_at": datetime.now().isoformat(timespec="seconds"), "results": results}
    try:
        history = json.loads(RUNS_FILE.read_text(encoding="utf-8"))
        if not isinstance(history, list): history = []
    except Exception: history = []
    _atomic_write(RUNS_FILE, ([run] + history)[:200])
    if status != "success": raise RuntimeError(results[-1]["detail"])
    return run


def list_runs(limit: int = 50) -> list[dict]:
    try:
        data = json.loads(RUNS_FILE.read_text(encoding="utf-8"))
        return data[:limit] if isinstance(data, list) else []
    except Exception:
        return []
