"""Thread-safe background cache for scanner discovery and status data."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable


class ScannerCache:
    """Keep slow scanner discovery away from HTTP request threads."""

    def __init__(self, loader: Callable[[], dict], interval_seconds: int = 10) -> None:
        self._loader = loader
        self._interval_seconds = max(5, interval_seconds)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._payload: dict = {
            "scanners": [],
            "errors": [],
            "updated_at": None,
            "refreshing": False,
            "cache_ready": False,
        }

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._worker,
                name="openscanstation-scanner-cache",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2)

    def request_refresh(self) -> None:
        self.start()
        self._wake.set()

    def snapshot(self) -> dict:
        with self._lock:
            data = dict(self._payload)
            data["scanners"] = [dict(item) for item in self._payload.get("scanners", [])]
            data["errors"] = [dict(item) for item in self._payload.get("errors", [])]
            return data

    def _worker(self) -> None:
        while not self._stop.is_set():
            self._refresh_once()
            self._wake.wait(self._interval_seconds)
            self._wake.clear()

    def _refresh_once(self) -> None:
        with self._lock:
            self._payload["refreshing"] = True
        try:
            loaded = self._loader()
            loaded["updated_at"] = datetime.now(timezone.utc).isoformat()
            loaded["refreshing"] = False
            loaded["cache_ready"] = True
            with self._lock:
                self._payload = loaded
        except Exception as exc:
            with self._lock:
                self._payload["refreshing"] = False
                self._payload["cache_ready"] = bool(self._payload.get("updated_at"))
                self._payload["errors"] = [
                    *self._payload.get("errors", []),
                    {"plugin_id": "cache", "message": str(exc)},
                ][-10:]
                self._payload["last_error_at"] = time.time()
