"""Hash-chained, append-only ledger (Provability control).

Each record embeds the hash of the previous record, so any tampering breaks
the chain. intent -> approval -> execution becomes one replayable history.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterator

GENESIS = "0" * 64


class Ledger:
    def __init__(self, path: str | Path = "ledger.jsonl") -> None:
        self.path = Path(path)
        self._last_hash = GENESIS
        if self.path.exists():
            for record in self.read():
                self._last_hash = record["record_hash"]

    def append(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "ts": time.time(),
            "event": event,
            "payload": payload,
            "prev_hash": self._last_hash,
        }
        record["record_hash"] = hashlib.sha256(
            json.dumps(record, sort_keys=True).encode()
        ).hexdigest()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
        self._last_hash = record["record_hash"]
        return record

    def read(self) -> Iterator[dict[str, Any]]:
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                yield json.loads(line)

    def verify_chain(self) -> bool:
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
