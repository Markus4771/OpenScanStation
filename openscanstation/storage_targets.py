"""Persistente und testbare Speicherziele für OpenScanStation.

Kennwörter werden nicht über die REST-Ausgabe zurückgegeben. Die eigentliche
Übertragung eines Scans erfolgt später über die Workflow-Engine; Phase 1 stellt
die sichere Verwaltung und Verbindungsprüfung bereit.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import smtplib
import socket
import subprocess
import tempfile
import ssl
from copy import deepcopy
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
TARGETS_FILE = DATA_DIR / "storage_targets.json"
TARGET_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SUPPORTED_TYPES = ("local", "smb", "webdav", "sftp", "email", "paperless")
SECRET_FIELDS = {"password", "token", "private_key", "smtp_password"}

DEFAULT_TARGETS = {
    "schema_version": 1,
    "targets": [
        {
            "id": "local",
            "name": "Lokaler Scanordner",
            "type": "local",
            "enabled": True,
            "default": True,
            "config": {"path": str(DATA_DIR / "scans")},
        }
    ],
}


def _text(value: object, limit: int = 512) -> str:
    return str(value or "").strip()[:limit]


def _normalize_config(target_type: str, raw: object) -> dict:
    config = raw if isinstance(raw, dict) else {}
    allowed = {
        "local": ("path",),
        "smb": ("host", "share", "path", "username", "password", "domain", "port"),
        "webdav": ("url", "username", "password", "token", "verify_tls"),
        "sftp": ("host", "port", "path", "username", "password", "private_key"),
        "email": ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "sender", "recipient", "starttls"),
        "paperless": ("url", "token", "verify_tls", "correspondent", "document_type", "storage_path", "tags"),
    }[target_type]
    result = {key: config.get(key) for key in allowed if key in config}
    for key in list(result):
        if key in {"verify_tls", "starttls"}:
            result[key] = bool(result[key])
        elif key in {"port", "smtp_port"}:
            try:
                result[key] = int(result[key])
            except (TypeError, ValueError):
                result[key] = 0
        else:
            result[key] = _text(result[key], 2048 if key in SECRET_FIELDS else 512)
    return result


def _normalize_target(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Ungültiges Speicherziel")
    target_id = _text(raw.get("id"), 64)
    if not TARGET_ID.fullmatch(target_id):
        raise ValueError("Ungültige Ziel-ID")
    target_type = _text(raw.get("type"), 32).lower()
    if target_type not in SUPPORTED_TYPES:
        raise ValueError("Nicht unterstützter Zieltyp")
    name = _text(raw.get("name"), 80)
    if not name:
        raise ValueError("Der Anzeigename fehlt")
    config = _normalize_config(target_type, raw.get("config"))
    _validate_required(target_type, config)
    return {
        "id": target_id,
        "name": name,
        "type": target_type,
        "enabled": bool(raw.get("enabled", True)),
        "default": bool(raw.get("default", False)),
        "owner": _text(raw.get("owner"), 32).lower(),
        "shared": bool(raw.get("shared", False)),
        "config": config,
    }


def _validate_required(target_type: str, config: dict) -> None:
    required = {
        "local": ("path",),
        "smb": ("host", "share"),
        "webdav": ("url",),
        "sftp": ("host", "username"),
        "email": ("smtp_host", "sender", "recipient"),
        "paperless": ("url", "token"),
    }[target_type]
    missing = [field for field in required if not config.get(field)]
    if missing:
        raise ValueError("Pflichtfelder fehlen: " + ", ".join(missing))
    if target_type in {"webdav", "paperless"} and not str(config["url"]).lower().startswith(("http://", "https://")):
        label = "WebDAV" if target_type == "webdav" else "Paperless-ngx"
        raise ValueError(f"{label}-URL muss mit http:// oder https:// beginnen")


def _normalize(data: object) -> dict:
    if not isinstance(data, dict):
        data = deepcopy(DEFAULT_TARGETS)
    raw_targets = data.get("targets", [])
    targets = []
    seen = set()
    if isinstance(raw_targets, list):
        for raw in raw_targets:
            try:
                target = _normalize_target(raw)
            except ValueError:
                continue
            if target["id"] in seen:
                continue
            seen.add(target["id"])
            targets.append(target)
    if not targets:
        targets = deepcopy(DEFAULT_TARGETS["targets"])
    defaults = [item for item in targets if item["default"] and item["enabled"]]
    chosen = defaults[0]["id"] if defaults else next((item["id"] for item in targets if item["enabled"]), targets[0]["id"])
    for item in targets:
        item["default"] = item["id"] == chosen
    return {"schema_version": 1, "targets": targets}


def load_targets(*, public: bool = False) -> dict:
    try:
        data = _normalize(json.loads(TARGETS_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = deepcopy(DEFAULT_TARGETS)
    return redact_targets(data) if public else data


def save_targets(data: dict) -> dict:
    normalized = _normalize(data)
    TARGETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="storage-targets-", suffix=".json", dir=TARGETS_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, TARGETS_FILE)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return normalized


def upsert_target(target: dict, *, create_only: bool = False) -> dict:
    normalized = _normalize_target(target)
    data = load_targets()
    existing = next((item for item in data["targets"] if item["id"] == normalized["id"]), None)
    if create_only and existing:
        raise ValueError("Die Ziel-ID existiert bereits")
    if existing:
        existing.clear()
        existing.update(normalized)
    else:
        data["targets"].append(normalized)
    if normalized["default"]:
        for item in data["targets"]:
            item["default"] = item["id"] == normalized["id"]
    return save_targets(data)


def delete_target(target_id: str, *, used_by: list[str] | None = None) -> dict:
    data = load_targets()
    if used_by:
        raise ValueError("Speicherziel wird noch verwendet: " + ", ".join(used_by))
    target = next((item for item in data["targets"] if item["id"] == target_id), None)
    if not target:
        raise ValueError("Speicherziel nicht gefunden")
    if len(data["targets"]) == 1:
        raise ValueError("Das letzte Speicherziel kann nicht gelöscht werden")
    data["targets"] = [item for item in data["targets"] if item["id"] != target_id]
    return save_targets(data)


def target_by_id(target_id: str) -> dict | None:
    return next((item for item in load_targets()["targets"] if item["id"] == target_id), None)


def targets_for_user(username: str, is_admin: bool = False, *, public: bool = False) -> dict:
    data = load_targets(public=public)
    if is_admin:
        return data
    data["targets"] = [item for item in data["targets"] if item.get("shared") or not item.get("owner") or item.get("owner") == username]
    return data


def smb_auth_file(config: dict):
    """Erzeugt eine kurzlebige smbclient-Authentifizierungsdatei."""
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="oss-smb-", delete=False)
    try:
        handle.write("username = " + str(config.get("username", "")) + "\n")
        handle.write("password = " + str(config.get("password", "")) + "\n")
        if config.get("domain"):
            handle.write("domain = " + str(config["domain"]) + "\n")
        handle.close()
        os.chmod(handle.name, 0o600)
        return Path(handle.name)
    except Exception:
        handle.close()
        try: os.unlink(handle.name)
        except OSError: pass
        raise


def redact_targets(data: dict) -> dict:
    result = deepcopy(data)
    for target in result.get("targets", []):
        config = target.get("config", {})
        for field in SECRET_FIELDS:
            if config.get(field):
                config[field] = "********"
    return result


def test_target(target_id: str, timeout: float = 5.0) -> dict:
    target = target_by_id(target_id)
    if not target:
        raise ValueError("Speicherziel nicht gefunden")
    if not target["enabled"]:
        return {"ok": False, "message": "Speicherziel ist deaktiviert"}
    config = target["config"]
    kind = target["type"]
    try:
        if kind == "local":
            path = Path(config["path"]).expanduser()
            path.mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(path)
            return {"ok": os.access(path, os.W_OK), "message": f"Lokaler Pfad erreichbar; {usage.free} Bytes frei"}
        if kind == "smb":
            port = int(config.get("port") or 445)
            auth = smb_auth_file(config)
            try:
                result = subprocess.run(["smbclient", f'//{config["host"]}/{config["share"]}', "-A", str(auth), "-p", str(port), "-D", str(config.get("path") or ""), "-c", "ls"], capture_output=True, text=True, timeout=max(5, int(timeout)))
            finally:
                auth.unlink(missing_ok=True)
            return {"ok": result.returncode == 0, "message": "SMB-Ziel erreichbar" if result.returncode == 0 else (result.stderr or result.stdout).strip()[:1000]}
        if kind == "webdav":
            request = Request(config["url"], method="OPTIONS")
            with urlopen(request, timeout=timeout) as response:
                return {"ok": 200 <= response.status < 500, "message": f"WebDAV antwortet mit HTTP {response.status}"}
        if kind == "sftp":
            port = int(config.get("port") or 22)
            with socket.create_connection((config["host"], port), timeout=timeout):
                pass
            return {"ok": True, "message": f"SFTP-Server auf Port {port} erreichbar"}
        if kind == "paperless":
            url = config["url"].rstrip("/") + "/api/"
            request = Request(url, headers={"Authorization": "Token " + config["token"], "Accept": "application/json"})
            context = ssl.create_default_context() if config.get("verify_tls", True) else ssl._create_unverified_context()
            with urlopen(request, timeout=timeout, context=context) as response:
                return {"ok": 200 <= response.status < 300, "message": f"Paperless-ngx API erreichbar (HTTP {response.status})"}
        port = int(config.get("smtp_port") or 587)
        with smtplib.SMTP(config["smtp_host"], port, timeout=timeout) as smtp:
            smtp.noop()
        return {"ok": True, "message": f"SMTP-Server auf Port {port} erreichbar"}
    except (OSError, HTTPError, URLError, smtplib.SMTPException) as exc:
        return {"ok": False, "message": str(exc)}
