"""Stdlib HTTP PEP so the TypeScript Agent SDK does not reimplement controls.

POST /execute  {action, params, session_id, resource?}
GET  /health
GET  /ledger?session_id=
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_ROOT / "src"), str(_ROOT / "examples")]

from harnesses.common.boundary import HarnessRuntime
from harnesses.common.cache_session import CacheSession

HOST = "127.0.0.1"
PORT = 8765
_RUNTIMES: dict[str, HarnessRuntime] = {}


def runtime_for(session_id: str) -> HarnessRuntime:
    if session_id not in _RUNTIMES:
        _RUNTIMES[session_id] = HarnessRuntime.start(session=CacheSession.new(session_id))
    return _RUNTIMES[session_id]


def execute_payload(body: dict[str, Any]) -> dict[str, Any]:
    session_id = str(body.get("session_id") or "bridge-default")
    action = str(body["action"])
    params = dict(body.get("params") or {})
    resource = body.get("resource")
    rt = runtime_for(session_id)
    try:
        result = rt.tools.execute(action, params, resource=resource)
        return {"ok": True, "result": result, "instance_id": rt.session.instance_id}
    except PermissionError as exc:
        return {"ok": False, "denied": str(exc), "instance_id": rt.session.instance_id}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("abf-bridge: " + fmt % args + "\n")

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, {"ok": True, "sessions": list(_RUNTIMES)})
            return
        if parsed.path == "/ledger":
            qs = parse_qs(parsed.query)
            sid = (qs.get("session_id") or ["bridge-default"])[0]
            rt = runtime_for(sid)
            rows = list(rt.ledger.read())
            self._send(200, {"ok": True, "records": rows, "verified": rt.ledger.verify_chain()})
            return
        self._send(404, {"ok": False, "denied": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/execute":
            self._send(404, {"ok": False, "denied": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        result = execute_payload(body)
        self._send(200 if result["ok"] else 403, result)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    server = ThreadingHTTPServer((HOST, port), Handler)
    print(f"ABF PEP bridge on http://{HOST}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
