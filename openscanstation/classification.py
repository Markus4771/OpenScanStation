"""Regelbasierte Dokumenterkennung für OpenScanStation.

Die Erkennung arbeitet nachvollziehbar mit OCR-Text, Dateiname, Tags sowie
optional übergebenen Barcode-/QR-Inhalten. Regeln bleiben konfigurierbar und
können später durch KI-Klassifizierer als Plugin ergänzt werden.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path

DATA_DIR = Path(os.environ.get("OPENSCANSTATION_DATA_DIR", "/var/lib/openscanstation"))
RULES_FILE = DATA_DIR / "classification_rules.json"
RESULTS_FILE = DATA_DIR / "classification_results.json"
RULE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

DEFAULT_RULES = {
    "schema_version": 1,
    "rules": [
        {"id": "rechnung", "name": "Rechnung", "document_type": "rechnung", "enabled": True, "priority": 100,
         "keywords_any": ["rechnung", "rechnungsnummer", "invoice", "zahlungsziel", "gesamtbetrag"],
         "keywords_all": [], "filename_contains": [], "tag_contains": [], "barcode_prefixes": ["INV:"]},
        {"id": "lieferschein", "name": "Lieferschein", "document_type": "lieferschein", "enabled": True, "priority": 90,
         "keywords_any": ["lieferschein", "lieferdatum", "delivery note", "wareneingang"],
         "keywords_all": [], "filename_contains": [], "tag_contains": [], "barcode_prefixes": ["DEL:"]},
        {"id": "vertrag", "name": "Vertrag", "document_type": "vertrag", "enabled": True, "priority": 80,
         "keywords_any": ["vertrag", "vertragsnummer", "vereinbarung", "kündigungsfrist"],
         "keywords_all": [], "filename_contains": [], "tag_contains": [], "barcode_prefixes": ["CON:"]},
        {"id": "brief", "name": "Brief", "document_type": "brief", "enabled": True, "priority": 50,
         "keywords_any": ["sehr geehrte", "mit freundlichen grüßen", "anschreiben"],
         "keywords_all": [], "filename_contains": [], "tag_contains": [], "barcode_prefixes": []},
        {"id": "foto", "name": "Foto", "document_type": "foto", "enabled": True, "priority": 20,
         "keywords_any": [], "keywords_all": [], "filename_contains": ["foto", "photo", "bild"],
         "tag_contains": ["foto"], "barcode_prefixes": []},
    ],
}


def _items(value: object, limit: int = 30) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item).strip()[:120]
        if text and text.casefold() not in {x.casefold() for x in result}:
            result.append(text)
    return result[:limit]


def _normalize_rule(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Ungültige Klassifizierungsregel")
    rule_id = str(raw.get("id", "")).strip().lower()[:64]
    if not RULE_ID.fullmatch(rule_id):
        raise ValueError("Ungültige Regel-ID")
    name = str(raw.get("name", "")).strip()[:80]
    document_type = str(raw.get("document_type", "")).strip().lower()[:64]
    if not name or not document_type:
        raise ValueError("Name und Dokumenttyp sind erforderlich")
    try:
        priority = max(0, min(1000, int(raw.get("priority", 0))))
    except (TypeError, ValueError):
        priority = 0
    return {
        "id": rule_id, "name": name, "document_type": document_type,
        "enabled": bool(raw.get("enabled", True)), "priority": priority,
        "keywords_any": _items(raw.get("keywords_any")),
        "keywords_all": _items(raw.get("keywords_all")),
        "filename_contains": _items(raw.get("filename_contains")),
        "tag_contains": _items(raw.get("tag_contains")),
        "barcode_prefixes": _items(raw.get("barcode_prefixes")),
    }


def _normalize(data: object) -> dict:
    rules, seen = [], set()
    source = data.get("rules", []) if isinstance(data, dict) else []
    for raw in source if isinstance(source, list) else []:
        try:
            rule = _normalize_rule(raw)
        except ValueError:
            continue
        if rule["id"] not in seen:
            rules.append(rule); seen.add(rule["id"])
    if not rules:
        rules = deepcopy(DEFAULT_RULES["rules"])
    rules.sort(key=lambda item: (-item["priority"], item["id"]))
    return {"schema_version": 1, "rules": rules}


def _atomic_write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.stem + "-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try: os.unlink(temp_name)
        except FileNotFoundError: pass


def load_rules() -> dict:
    try:
        return _normalize(json.loads(RULES_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return deepcopy(DEFAULT_RULES)


def save_rules(data: dict) -> dict:
    normalized = _normalize(data); _atomic_write(RULES_FILE, normalized); return normalized


def upsert_rule(rule: dict, *, create_only: bool = False) -> dict:
    item = _normalize_rule(rule); data = load_rules()
    existing = next((x for x in data["rules"] if x["id"] == item["id"]), None)
    if create_only and existing:
        raise ValueError("Regel-ID existiert bereits")
    if existing: existing.clear(); existing.update(item)
    else: data["rules"].append(item)
    return save_rules(data)


def delete_rule(rule_id: str) -> dict:
    data = load_rules(); before = len(data["rules"])
    data["rules"] = [x for x in data["rules"] if x["id"] != rule_id]
    if len(data["rules"]) == before: raise ValueError("Regel nicht gefunden")
    if not data["rules"]: raise ValueError("Die letzte Regel kann nicht gelöscht werden")
    return save_rules(data)


def classify(*, text: str = "", filename: str = "", tags: list[str] | None = None,
             barcodes: list[str] | None = None) -> dict:
    haystack = str(text or "").casefold()
    filename_cf = str(filename or "").casefold()
    tags_cf = [str(x).casefold() for x in (tags or [])]
    barcode_values = [str(x).strip() for x in (barcodes or []) if str(x).strip()]
    candidates = []
    for rule in load_rules()["rules"]:
        if not rule["enabled"]: continue
        any_hits = [k for k in rule["keywords_any"] if k.casefold() in haystack]
        all_ok = all(k.casefold() in haystack for k in rule["keywords_all"])
        file_hits = [k for k in rule["filename_contains"] if k.casefold() in filename_cf]
        tag_hits = [k for k in rule["tag_contains"] if any(k.casefold() in tag for tag in tags_cf)]
        code_hits = [p for p in rule["barcode_prefixes"] if any(code.startswith(p) for code in barcode_values)]
        has_positive = bool(any_hits or file_hits or tag_hits or code_hits or rule["keywords_all"])
        if not all_ok or not has_positive: continue
        score = rule["priority"] + len(any_hits) * 10 + len(file_hits) * 15 + len(tag_hits) * 15 + len(code_hits) * 40 + len(rule["keywords_all"]) * 20
        candidates.append({"rule_id": rule["id"], "document_type": rule["document_type"], "name": rule["name"], "score": score,
                           "matches": {"keywords": any_hits, "filename": file_hits, "tags": tag_hits, "barcodes": code_hits}})
    candidates.sort(key=lambda item: (-item["score"], item["rule_id"]))
    best = candidates[0] if candidates else None
    result = {"document_type": best["document_type"] if best else "dokument", "confidence": min(1.0, (best["score"] / 200.0)) if best else 0.0,
              "rule_id": best["rule_id"] if best else None, "matches": best["matches"] if best else {}, "candidates": candidates[:10],
              "barcodes": barcode_values}
    return result


def save_result(filename: str, result: dict) -> None:
    try:
        data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict): data = {}
    except Exception: data = {}
    data[Path(filename).name] = result
    _atomic_write(RESULTS_FILE, data)


def result_for(filename: str) -> dict | None:
    try:
        data = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        return data.get(Path(filename).name) if isinstance(data, dict) else None
    except Exception:
        return None
