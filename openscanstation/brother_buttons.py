"""Automatische Brother-Tastenregistrierung und Ereignislistener.

Brother-Netzwerkscanner registrieren ein Scan-to-PC-Ziel per SNMP und senden
Tastenereignisse anschließend per UDP an Port 54925. Das Protokoll ist nicht
Teil einer stabilen öffentlichen Brother-API und muss daher am jeweiligen
Modell/Firmwarestand getestet werden.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
CONFIG_FILE = DATA_DIR / "brother_buttons.json"
STATUS_FILE = DATA_DIR / "brother_buttons_status.json"
REGISTER_OID = ".1.3.6.1.4.1.2435.2.3.9.2.11.1.1.0"
COMMUNITY = "internal"
DEFAULT_PORT = 54925
FUNCTIONS = {"IMAGE": "1", "EMAIL": "2", "OCR": "3", "FILE": "5"}


def _atomic_write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.stem + "-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def _address(value: object, field: str) -> str:
    text = str(value or "").strip()
    try:
        ipaddress.ip_address(text)
    except ValueError as exc:
        raise ValueError(f"{field} muss eine IP-Adresse sein") from exc
    return text


def normalize_config(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Ungültige Brother-Tastenkonfiguration")
    scanner_ip = _address(raw.get("scanner_ip"), "scanner_ip")
    server_ip = _address(raw.get("server_ip"), "server_ip")
    scanner_id = str(raw.get("scanner_id", "")).strip()[:512]
    if not scanner_id:
        raise ValueError("scanner_id fehlt")
    port = int(raw.get("listen_port") or DEFAULT_PORT)
    if not 1024 <= port <= 65535:
        raise ValueError("listen_port ist ungültig")
    actions = raw.get("actions") if isinstance(raw.get("actions"), dict) else {}
    normalized_actions = {
        function: str(actions.get(function, "")).strip()[:64]
        for function in FUNCTIONS
        if str(actions.get(function, "")).strip()
    }
    if not normalized_actions:
        normalized_actions = {"FILE": "action-1"}
    return {
        "enabled": bool(raw.get("enabled", True)),
        "scanner_ip": scanner_ip,
        "server_ip": server_ip,
        "scanner_id": scanner_id,
        "listen_port": port,
        "display_name": str(raw.get("display_name", "OpenScanStation")).strip()[:15] or "OpenScanStation",
        "register_interval": min(3600, max(60, int(raw.get("register_interval") or 300))),
        "actions": normalized_actions,
    }


def load_config() -> dict:
    try:
        return normalize_config(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except FileNotFoundError as exc:
        raise ValueError(f"Konfiguration fehlt: {CONFIG_FILE}") from exc


def save_config(data: dict) -> dict:
    result = normalize_config(data)
    _atomic_write(CONFIG_FILE, result)
    return result


def registration_payload(function: str, config: dict) -> str:
    function = function.upper()
    if function not in FUNCTIONS:
        raise ValueError("Unbekannte Brother-Funktion")
    return (
        f'TYPE=BR;BUTTON=SCAN;USER="{config["display_name"]}";'
        f'FUNC={function};HOST={config["server_ip"]}:{config["listen_port"]};'
        f'APPNUM={FUNCTIONS[function]};DURATION=360;BRID=;'
    )


def registration_commands(config: dict) -> list[list[str]]:
    return [
        ["snmpset", "-v1", "-c", COMMUNITY, config["scanner_ip"], REGISTER_OID, "s", registration_payload(function, config)]
        for function in config["actions"]
    ]


def register(config: dict, runner=subprocess.run) -> dict:
    results = []
    for command in registration_commands(config):
        try:
            completed = runner(command, capture_output=True, text=True, timeout=15)
            results.append({"function": command[-1].split("FUNC=", 1)[1].split(";", 1)[0], "ok": completed.returncode == 0, "message": (completed.stdout or completed.stderr).strip()[:1000]})
        except (OSError, subprocess.SubprocessError) as exc:
            results.append({"function": command[-1].split("FUNC=", 1)[1].split(";", 1)[0], "ok": False, "message": str(exc)})
    status = {"timestamp": datetime.now().isoformat(timespec="seconds"), "registered": all(x["ok"] for x in results), "results": results}
    _atomic_write(STATUS_FILE, status)
    return status


def parse_event(payload: bytes) -> str | None:
    text = payload.decode("utf-8", "replace")
    if "BUTTON=SCAN" not in text:
        return None
    for function in FUNCTIONS:
        if f"FUNC={function}" in text:
            return function
    return None


def dispatch(function: str, config: dict) -> dict:
    action_id = config["actions"].get(function)
    if not action_id:
        raise ValueError(f"Für {function} ist keine Scanneraktion zugeordnet")
    from openscanstation.web import _perform_action
    return _perform_action(config["scanner_id"], action_id)


def run(config: dict) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", config["listen_port"]))
    sock.settimeout(5)
    last_register = 0.0
    while True:
        now = time.monotonic()
        if now - last_register >= config["register_interval"]:
            register(config)
            last_register = now
        try:
            payload, address = sock.recvfrom(4096)
        except socket.timeout:
            continue
        if address[0] != config["scanner_ip"]:
            continue
        function = parse_event(payload)
        if not function:
            continue
        try:
            result = dispatch(function, config)
            status = {"timestamp": datetime.now().isoformat(timespec="seconds"), "last_event": function, "last_action_ok": True, "result": result}
        except Exception as exc:
            status = {"timestamp": datetime.now().isoformat(timespec="seconds"), "last_event": function, "last_action_ok": False, "error": str(exc)}
        _atomic_write(STATUS_FILE, status)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openscanstation-brother-buttons")
    sub = parser.add_subparsers(dest="command", required=True)
    configure = sub.add_parser("configure")
    configure.add_argument("--scanner-ip", required=True)
    configure.add_argument("--server-ip", required=True)
    configure.add_argument("--scanner-id", required=True)
    configure.add_argument("--display-name", default="OpenScanStation")
    configure.add_argument("--listen-port", type=int, default=DEFAULT_PORT)
    configure.add_argument("--image-action", default="")
    configure.add_argument("--email-action", default="")
    configure.add_argument("--ocr-action", default="")
    configure.add_argument("--file-action", default="action-1")
    sub.add_parser("register")
    sub.add_parser("status")
    sub.add_parser("run")
    args = parser.parse_args(argv)
    if args.command == "configure":
        actions = {"IMAGE": args.image_action, "EMAIL": args.email_action, "OCR": args.ocr_action, "FILE": args.file_action}
        print(json.dumps(save_config({"scanner_ip": args.scanner_ip, "server_ip": args.server_ip, "scanner_id": args.scanner_id, "display_name": args.display_name, "listen_port": args.listen_port, "actions": actions}), ensure_ascii=False, indent=2))
        return 0
    if args.command == "status":
        try:
            print(STATUS_FILE.read_text(encoding="utf-8"))
            return 0
        except FileNotFoundError:
            print(json.dumps({"configured": CONFIG_FILE.exists(), "status": "not_run"}))
            return 1
    config = load_config()
    if args.command == "register":
        result = register(config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["registered"] else 1
    run(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
