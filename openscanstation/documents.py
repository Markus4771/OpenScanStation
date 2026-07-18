"""Persistente Dokumentenverwaltung und OCR für OpenScanStation."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("/var/lib/openscanstation")
SCAN_DIR = DATA_DIR / "scans"
DB_PATH = DATA_DIR / "documents.db"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            scanner TEXT NOT NULL,
            profile TEXT NOT NULL,
            format TEXT NOT NULL,
            pages INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            ocr_text TEXT NOT NULL DEFAULT '',
            ocr_status TEXT NOT NULL DEFAULT 'offen'
        )
    """)
    db.commit()
    return db


def add_document(filename: str, title: str, scanner: str, profile: str, fmt: str, pages: int = 1, tags: list[str] | None = None) -> int:
    with _connect() as db:
        cur = db.execute(
            "INSERT OR REPLACE INTO documents(filename,title,scanner,profile,format,pages,created_at,tags) VALUES(?,?,?,?,?,?,?,?)",
            (filename, title, scanner, profile, fmt, pages, datetime.now().isoformat(timespec="seconds"), json.dumps(tags or [], ensure_ascii=False)),
        )
        db.commit()
        return int(cur.lastrowid)


def list_documents(query: str = "", limit: int = 100) -> list[dict]:
    with _connect() as db:
        if query:
            needle = f"%{query}%"
            rows = db.execute(
                "SELECT * FROM documents WHERE title LIKE ? OR filename LIKE ? OR scanner LIKE ? OR tags LIKE ? OR ocr_text LIKE ? ORDER BY id DESC LIMIT ?",
                (needle, needle, needle, needle, needle, limit),
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM documents ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item.get("tags") or "[]")
        result.append(item)
    return result


def _ocr_image(source: Path, language: str) -> str:
    result = subprocess.run(
        ["tesseract", str(source), "stdout", "-l", language],
        check=True, capture_output=True, text=True, timeout=600,
    )
    return result.stdout.strip()


def run_ocr(filename: str, language: str = "deu") -> str:
    source = SCAN_DIR / filename
    if not source.is_file():
        raise FileNotFoundError(filename)
    try:
        if source.suffix.lower() == ".pdf":
            with tempfile.TemporaryDirectory(prefix="openscanstation-ocr-") as tmp:
                prefix = Path(tmp) / "page"
                subprocess.run(
                    ["pdftoppm", "-png", "-r", "300", str(source), str(prefix)],
                    check=True, capture_output=True, timeout=600,
                )
                pages = sorted(Path(tmp).glob("page-*.png"))
                if not pages:
                    raise RuntimeError("PDF konnte nicht in Bilder umgewandelt werden")
                text = "\n\n".join(_ocr_image(page, language) for page in pages).strip()
        else:
            text = _ocr_image(source, language)
    except FileNotFoundError as exc:
        raise RuntimeError("Tesseract oder pdftoppm ist nicht installiert") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        raise RuntimeError(stderr.strip() or "OCR fehlgeschlagen") from exc
    with _connect() as db:
        db.execute("UPDATE documents SET ocr_text=?, ocr_status=? WHERE filename=?", (text, "fertig", filename))
        db.commit()
    return text
