"""Lokale Benutzer, Rollen und signierte Web-Sitzungen."""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
USERS_FILE = DATA_DIR / "users.json"
SESSION_KEY_FILE = DATA_DIR / "session.key"
USERNAME = re.compile(r"^[a-z][a-z0-9_.-]{2,31}$")
PBKDF2_ITERATIONS = 600_000


def _atomic(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.stem + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        try: os.unlink(name)
        except FileNotFoundError: pass


def _load() -> dict:
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {"schema_version": 1, "users": []}
    users = data.get("users") if isinstance(data, dict) else []
    return {"schema_version": 1, "users": [item for item in users if isinstance(item, dict)]}


def list_users(public: bool = True) -> list[dict]:
    users = _load()["users"]
    if not public:
        return users
    return [{key: value for key, value in user.items() if key not in {"password_hash", "salt"}} for user in users]


def _validate_username(username: str) -> str:
    value = str(username or "").strip().lower()
    if not USERNAME.fullmatch(value):
        raise ValueError("Benutzername: 3-32 Zeichen, beginnend mit a-z")
    return value


def _password_hash(password: str, salt: bytes) -> str:
    return base64.b64encode(hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)).decode("ascii")


def upsert_user(username: str, password: str | None, *, role: str = "user", display_name: str = "", enabled: bool = True) -> dict:
    username = _validate_username(username)
    if role not in {"admin", "user"}:
        raise ValueError("Ungueltige Rolle")
    data = _load()
    existing = next((item for item in data["users"] if item.get("username") == username), None)
    if not existing:
        if not password or len(password) < 10:
            raise ValueError("Das Kennwort muss mindestens 10 Zeichen lang sein")
        existing = {"username": username}
        data["users"].append(existing)
    if password:
        if len(password) < 10:
            raise ValueError("Das Kennwort muss mindestens 10 Zeichen lang sein")
        salt = secrets.token_bytes(16)
        existing["salt"] = base64.b64encode(salt).decode("ascii")
        existing["password_hash"] = _password_hash(password, salt)
    existing.update({"role": role, "display_name": str(display_name or username).strip()[:80], "enabled": bool(enabled)})
    _atomic(USERS_FILE, data)
    return {key: value for key, value in existing.items() if key not in {"password_hash", "salt"}}


def delete_user(username: str) -> None:
    username = _validate_username(username)
    data = _load()
    target = next((item for item in data["users"] if item.get("username") == username), None)
    if not target:
        raise ValueError("Benutzer nicht gefunden")
    if target.get("role") == "admin" and sum(1 for item in data["users"] if item.get("role") == "admin" and item.get("enabled")) <= 1:
        raise ValueError("Der letzte aktive Administrator kann nicht geloescht werden")
    data["users"] = [item for item in data["users"] if item.get("username") != username]
    _atomic(USERS_FILE, data)


def set_scanners(username: str, scanner_ids: list[str]) -> dict:
    username = _validate_username(username)
    data = _load()
    user = next((item for item in data["users"] if item.get("username") == username), None)
    if not user:
        raise ValueError("Benutzer nicht gefunden")
    user["scanners"] = list(dict.fromkeys(str(value).strip()[:512] for value in scanner_ids if str(value).strip()))[:50]
    _atomic(USERS_FILE, data)
    return {key: value for key, value in user.items() if key not in {"password_hash", "salt"}}


def authenticate(username: str, password: str) -> dict | None:
    username = str(username or "").strip().lower()
    user = next((item for item in _load()["users"] if item.get("username") == username and item.get("enabled")), None)
    if not user or not user.get("salt") or not user.get("password_hash"):
        hashlib.pbkdf2_hmac("sha256", str(password).encode(), b"0" * 16, PBKDF2_ITERATIONS)
        return None
    try:
        salt = base64.b64decode(user["salt"])
    except Exception:
        return None
    if not hmac.compare_digest(_password_hash(password, salt), user["password_hash"]):
        return None
    return {key: value for key, value in user.items() if key not in {"password_hash", "salt"}}


def _session_key() -> bytes:
    try:
        return base64.b64decode(SESSION_KEY_FILE.read_bytes())
    except (FileNotFoundError, ValueError, OSError):
        key = secrets.token_bytes(32)
        SESSION_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_KEY_FILE.write_bytes(base64.b64encode(key))
        os.chmod(SESSION_KEY_FILE, 0o600)
        return key


def create_session(user: dict, lifetime: int = 12 * 3600) -> str:
    payload = {"u": user["username"], "r": user["role"], "exp": int(time.time()) + lifetime, "n": secrets.token_hex(8)}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(_session_key(), encoded, hashlib.sha256).hexdigest().encode()
    return (encoded + b"." + signature).decode()


def verify_session(token: str) -> dict | None:
    try:
        encoded, signature = token.encode().split(b".", 1)
        expected = hmac.new(_session_key(), encoded, hashlib.sha256).hexdigest().encode()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4)))
        if int(payload["exp"]) < int(time.time()):
            return None
        user = next((item for item in list_users() if item["username"] == payload["u"] and item.get("enabled")), None)
        return user
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openscanstation-users")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("username")
    create.add_argument("--role", choices=("admin", "user"), default="user")
    create.add_argument("--display-name", default="")
    sub.add_parser("list")
    args = parser.parse_args(argv)
    if args.command == "list":
        print(json.dumps(list_users(), ensure_ascii=False, indent=2))
        return 0
    first = not list_users()
    role = "admin" if first else args.role
    password = getpass.getpass("Kennwort: ")
    confirmation = getpass.getpass("Kennwort wiederholen: ")
    if password != confirmation:
        raise SystemExit("Kennwoerter stimmen nicht ueberein")
    print(json.dumps(upsert_user(args.username, password, role=role, display_name=args.display_name), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
