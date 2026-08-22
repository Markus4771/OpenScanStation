"""Eingangsdienst fuer native Brother-Scan-to-Network-Profile."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

from openscanstation.scanner_actions import action_by_id

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
CONFIG_FILE = DATA_DIR / "brother_network.json"
STATUS_FILE = DATA_DIR / "brother_network_status.json"
INBOX_ROOT = DATA_DIR / "network-inbox"
ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def _atomic_write(path: Path, data: object, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.stem + "-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def _profile_name(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or len(text) > 32 or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for ch in text):
        raise ValueError("Profilname darf nur a-z, 0-9, _ und - enthalten")
    return text


def normalize_config(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Ungueltige Brother-Netzwerkkonfiguration")
    profiles = {}
    source = raw.get("profiles") if isinstance(raw.get("profiles"), dict) else {}
    for name, action_id in source.items():
        profile = _profile_name(name)
        action = str(action_id or "").strip()[:64]
        if action:
            profiles[profile] = action
    if not profiles:
        raise ValueError("Mindestens ein Netzwerkprofil ist erforderlich")
    return {
        "enabled": bool(raw.get("enabled", True)),
        "poll_interval": min(30.0, max(0.5, float(raw.get("poll_interval", 2)))),
        "settle_seconds": min(60.0, max(1.0, float(raw.get("settle_seconds", 3)))),
        "profiles": profiles,
    }


def save_config(data: dict) -> dict:
    config = normalize_config(data)
    for profile in config["profiles"]:
        _ensure_profile_directory(profile)
    _atomic_write(CONFIG_FILE, config)
    return config


def _ensure_profile_directory(profile: str) -> Path:
    """Create an SMB inbox with the ownership inherited from the share root."""
    INBOX_ROOT.mkdir(parents=True, exist_ok=True)
    root_stat = INBOX_ROOT.stat()
    path = INBOX_ROOT / _profile_name(profile)
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chown(path, root_stat.st_uid, root_stat.st_gid)
    except (AttributeError, PermissionError):
        pass
    os.chmod(path, 0o770)
    return path


def upsert_profile(profile: str, action_id: str) -> dict:
    name = _profile_name(profile)
    action = str(action_id or "").strip()[:64]
    if not action:
        raise ValueError("Scanneraktion fehlt")
    try:
        config = load_config()
    except ValueError:
        config = {"enabled": True, "poll_interval": 2, "settle_seconds": 3, "profiles": {}}
    config["profiles"][name] = action
    return save_config(config)


def delete_profile(profile: str) -> dict:
    name = _profile_name(profile)
    config = load_config()
    if name not in config["profiles"]:
        raise ValueError("To-Network-Profil wurde nicht gefunden")
    if len(config["profiles"]) == 1:
        raise ValueError("Mindestens ein To-Network-Profil muss erhalten bleiben")
    del config["profiles"][name]
    return save_config(config)


def load_config() -> dict:
    try:
        return normalize_config(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except FileNotFoundError as exc:
        raise ValueError(f"Konfiguration fehlt: {CONFIG_FILE}") from exc


def parse_profile(value: str) -> tuple[str, str]:
    try:
        name, action = value.split("=", 1)
    except ValueError as exc:
        raise ValueError("Profil muss NAME=ACTION-ID entsprechen") from exc
    name, action = _profile_name(name), action.strip()
    if not action:
        raise ValueError("Scanneraktion fehlt")
    return name, action[:64]


def _unique_destination(source: Path, scan_dir: Path) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in source.name)
    safe = safe[:180] or ("network-scan" + source.suffix.lower())
    destination = scan_dir / safe
    if not destination.exists():
        return destination
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return scan_dir / f"{Path(safe).stem}-{stamp}{Path(safe).suffix}"


def process_file(source: Path, profile: str, action_id: str) -> dict:
    action = action_by_id(action_id)
    if not action or not action.get("enabled"):
        raise ValueError(f"Scanneraktion {action_id} ist nicht aktiviert")
    if source.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"Dateityp {source.suffix or '(ohne Endung)'} wird nicht unterstuetzt")

    from openscanstation import documents
    from openscanstation.workflows import execute_workflow

    documents.SCAN_DIR.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination(source, documents.SCAN_DIR)
    shutil.move(str(source), destination)
    fmt = destination.suffix.lower().lstrip(".").replace("jpeg", "jpg")
    documents.add_document(
        destination.name,
        action.get("title", action.get("label", "Netzwerkscan")),
        "Brother Scan to Network",
        action.get("profile", profile),
        fmt,
        1,
        action.get("tags", []),
    )
    workflow_id = str(action.get("workflow") or "standard")
    run = execute_workflow(
        workflow_id,
        destination.name,
        title=action.get("title", action.get("label", "Netzwerkscan")),
        tags=action.get("tags", []),
    )
    return {"ok": True, "profile": profile, "action_id": action_id, "filename": run["filename"], "workflow": workflow_id}


def scan_once(config: dict, state: dict[str, tuple[int, float]]) -> list[dict]:
    now = time.monotonic()
    results = []
    active = set()
    for profile, action_id in config["profiles"].items():
        inbox = INBOX_ROOT / profile
        inbox.mkdir(parents=True, exist_ok=True)
        for source in sorted(inbox.iterdir()):
            if not source.is_file() or source.name.startswith("."):
                continue
            key = str(source)
            active.add(key)
            try:
                size = source.stat().st_size
            except OSError:
                continue
            previous = state.get(key)
            if previous is None or previous[0] != size:
                state[key] = (size, now)
                continue
            if now - previous[1] < config["settle_seconds"]:
                continue
            try:
                result = process_file(source, profile, action_id)
                status = {"timestamp": datetime.now().isoformat(timespec="seconds"), "last_import_ok": True, "result": result}
            except Exception as exc:
                status = {"timestamp": datetime.now().isoformat(timespec="seconds"), "last_import_ok": False, "profile": profile, "filename": source.name, "error": str(exc)}
            _atomic_write(STATUS_FILE, status)
            results.append(status)
            state.pop(key, None)
    for key in list(state):
        if key not in active:
            state.pop(key, None)
    return results


def run(config: dict) -> None:
    state: dict[str, tuple[int, float]] = {}
    while True:
        scan_once(config, state)
        time.sleep(config["poll_interval"])


def setup_samba(config: dict, username: str, password: str, runner=subprocess.run, smb_conf: Path = Path("/etc/samba/smb.conf")) -> None:
    if os.geteuid() != 0:
        raise PermissionError("setup-samba muss als root ausgefuehrt werden")
    if not username or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in username):
        raise ValueError("Ungueltiger SMB-Benutzername")
    if len(password) < 8:
        raise ValueError("Das SMB-Passwort muss mindestens 8 Zeichen lang sein")
    for profile in config["profiles"]:
        path = INBOX_ROOT / profile
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o770)
    runner(["chown", "-R", f"{username}:openscanstation", str(INBOX_ROOT)], check=True)
    completed = runner(["smbpasswd", "-a", "-s", username], input=password + "\n" + password + "\n", text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "smbpasswd fehlgeschlagen").strip())
    marker = "# BEGIN OPENSCANSTATION\n"
    end = "# END OPENSCANSTATION\n"
    block = (
        marker + "[OpenScan]\n"
        f"   path = {INBOX_ROOT}\n"
        "   browseable = yes\n   read only = no\n   guest ok = no\n"
        f"   valid users = {username}\n   force group = openscanstation\n"
        "   create mask = 0660\n   directory mask = 0770\n" + end
    )
    text = smb_conf.read_text(encoding="utf-8") if smb_conf.exists() else "[global]\n"
    if marker in text and end in text:
        text = text.split(marker, 1)[0] + text.split(end, 1)[1]
    smb_conf.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
    runner(["testparm", "-s"], check=True, capture_output=True, text=True)
    runner(["systemctl", "restart", "smbd"], check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openscanstation-brother-network")
    sub = parser.add_subparsers(dest="command", required=True)
    configure = sub.add_parser("configure")
    configure.add_argument("--profile", action="append", required=True, metavar="NAME=ACTION-ID")
    configure.add_argument("--poll-interval", type=float, default=2)
    configure.add_argument("--settle-seconds", type=float, default=3)
    samba = sub.add_parser("setup-samba")
    samba.add_argument("--username", default="openscanstation")
    samba.add_argument("--password", help="Optional; ohne Angabe erfolgt eine verdeckte Passwortabfrage")
    sub.add_parser("status")
    sub.add_parser("run")
    args = parser.parse_args(argv)
    if args.command == "configure":
        profiles = dict(parse_profile(item) for item in args.profile)
        print(json.dumps(save_config({"profiles": profiles, "poll_interval": args.poll_interval, "settle_seconds": args.settle_seconds}), ensure_ascii=False, indent=2))
        return 0
    if args.command == "status":
        try:
            print(STATUS_FILE.read_text(encoding="utf-8"))
            return 0
        except FileNotFoundError:
            print(json.dumps({"configured": CONFIG_FILE.exists(), "status": "not_run"}))
            return 1
    config = load_config()
    if args.command == "setup-samba":
        password = args.password or getpass.getpass("SMB-Passwort: ")
        setup_samba(config, args.username, password)
        print(json.dumps({"ok": True, "share": "OpenScan", "profiles": list(config["profiles"])}))
        return 0
    run(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
