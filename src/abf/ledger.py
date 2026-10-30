"""Hash-chained, append-only ledger (Provability control).

Each record embeds the hash of the previous record, so any tampering breaks
the chain. intent -> approval -> execution becomes one replayable history.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]

GENESIS = "0" * 64


class Ledger:
    def __init__(self, path: str | Path = "ledger.jsonl") -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._last_hash = GENESIS
        if self.path.exists():
            for record in self.read():
                self._last_hash = record["record_hash"]

    def _tail_hash_unlocked(self) -> str:
        """Read the latest record_hash from disk while holding the lock."""
        if not self.path.exists():
            return GENESIS
        last = GENESIS
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = json.loads(line)["record_hash"]
        return last

    def append(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a+", encoding="utf-8") as f:
                if fcntl is not None:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.seek(0)
                    last_on_disk = GENESIS
                    for line in f:
                        s = line.strip()
                        if s:
                            last_on_disk = json.loads(s)["record_hash"]
                    self._last_hash = last_on_disk
                    record: dict[str, Any] = {
                        "ts": time.time(),
                        "event": event,
                        "payload": payload,
                        "prev_hash": self._last_hash,
                    }
                    record["record_hash"] = hashlib.sha256(
                        json.dumps(record, sort_keys=True).encode()
                    ).hexdigest()
                    f.seek(0, 2)
                    f.write(json.dumps(record, sort_keys=True) + "\n")
                    f.flush()
                    self._last_hash = record["record_hash"]
                finally:
                    if fcntl is not None:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return record

    def read(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with self._lock:
            with self.path.open(encoding="utf-8") as f:
                lines = f.readlines()
        for line in lines:
            line = line.strip()
            if line:
                yield json.loads(line)

    def verify_chain(self) -> bool:
        with self._lock:
            prev = GENESIS
            for record in self.read():
                claimed = record["record_hash"]
                body = {k: v for k, v in record.items() if k != "record_hash"}
                recomputed = hashlib.sha256(
                    json.dumps(body, sort_keys=True).encode()
                ).hexdigest()
                if record["prev_hash"] != prev or claimed != recomputed:
                    return False
                prev = claimed
            return True

