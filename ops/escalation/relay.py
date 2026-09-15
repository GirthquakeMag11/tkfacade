#!/usr/bin/env python3
"""tkfacade escalation relay — a question queue between CI agents and the
maintainer.

Design (docs/tracking/SPEC.md 5.4): agents running in GitHub Actions need
the maintainer's intent mid-run. They call ``ask_user`` through the MCP
wrapper (``mcp_server.py``), which posts the question here and long-polls
for the answer. The maintainer reads and answers from the browser UI this
server also hosts (``ui.html``). No third-party service is involved; this
file is the whole backend — Python stdlib only.

Endpoints (Bearer token auth; two tokens, two roles):

    GET  /                      the browser UI (no auth; the UI holds the
                                UI token in localStorage)
    GET  /api/ping              health check (no auth)
    POST /api/ask               [ask token] file a question
                                {question, context?, issue?, run?,
                                 timeout_minutes?} -> {id}
    GET  /api/ask/<id>          [ask token] question state
    GET  /api/ask/<id>/wait     [ask token] long-poll (``?seconds=``,
                                capped at 110) — returns as soon as the
                                question is answered or expired
    GET  /api/questions         [ui token]  ?state=open|answered|expired|all
    POST /api/answer/<id>       [ui token]  {answer}

Configuration via environment:

    ESCALATION_HOST        bind address (default 127.0.0.1 — expose via
                           Tailscale Funnel or a reverse proxy, never by
                           binding 0.0.0.0 bare)
    ESCALATION_PORT        bind port (default 8787)
    ESCALATION_ASK_TOKEN   bearer token for the agent side (required)
    ESCALATION_UI_TOKEN    bearer token for the browser UI (required)
    ESCALATION_STATE       state file path (default ./state.json beside
                           this file)

State is a JSON file rewritten atomically under a lock; a restart loses
nothing. Deployment: see README.md beside this file.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST = os.environ.get("ESCALATION_HOST", "127.0.0.1")
PORT = int(os.environ.get("ESCALATION_PORT", "8787"))
ASK_TOKEN = os.environ.get("ESCALATION_ASK_TOKEN", "")
UI_TOKEN = os.environ.get("ESCALATION_UI_TOKEN", "")
STATE_PATH = Path(os.environ.get("ESCALATION_STATE", Path(__file__).with_name("state.json")))
UI_PATH = Path(__file__).with_name("ui.html")

MAX_WAIT_SECONDS = 110.0
DEFAULT_TIMEOUT_MINUTES = 120.0

_LOCK = threading.Lock()


def _load() -> dict[str, list[dict]]:
    if not STATE_PATH.exists():
        return {"questions": []}
    with STATE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _save(state: dict[str, list[dict]]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STATE_PATH.parent, prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
        os.replace(tmp, STATE_PATH)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _status(q: dict, now: float) -> str:
    if q.get("answer") is not None:
        return "answered"
    if now > float(q["deadline"]):
        return "expired"
    return "open"


def _public(q: dict, now: float) -> dict:
    view = dict(q)
    view["status"] = _status(q, now)
    return view


class Handler(BaseHTTPRequestHandler):
    server_version = "tkfacade-escalation/0.1"

    # --- plumbing -----------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:  # quieter, prefixed logs
        sys.stderr.write("[relay] %s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, payload: dict | list | None = None, *, raw: bytes = b"",
              content_type: str = "application/json") -> None:
        body = raw if raw else json.dumps(payload if payload is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _bearer(self) -> str:
        auth = self.headers.get("Authorization", "")
        return auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""

    def _authed(self, expected: str) -> bool:
        return bool(expected) and secrets.compare_digest(self._bearer(), expected)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    # --- routes ---------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        url = urlparse(self.path)
        path, query = url.path.rstrip("/") or "/", parse_qs(url.query)

        if path == "/api/ping":
            self._send(200, {"ok": True, "time": time.time()})
            return
        if path == "/":
            if not UI_PATH.exists():
                self._send(404, {"error": "ui.html missing beside relay.py"})
                return
            self._send(200, raw=UI_PATH.read_bytes(), content_type="text/html; charset=utf-8")
            return
        if path == "/api/questions":
            if not self._authed(UI_TOKEN):
                self._send(401, {"error": "bad ui token"})
                return
            want = (query.get("state", ["open"])[0] or "open").lower()
            now = time.time()
            with _LOCK:
                items = [_public(q, now) for q in _load()["questions"]]
            if want != "all":
                items = [q for q in items if q["status"] == want]
            items.sort(key=lambda q: q["created"])
            self._send(200, {"questions": items})
            return
        if path.startswith("/api/ask/"):
            rest = path.removeprefix("/api/ask/")
            qid, _, action = rest.partition("/")
            if not self._authed(ASK_TOKEN):
                self._send(401, {"error": "bad ask token"})
                return
            now = time.time()
            with _LOCK:
                q = next((x for x in _load()["questions"] if x["id"] == qid), None)
            if q is None:
                self._send(404, {"error": "no such question"})
                return
            if action == "wait":
                budget = min(float((query.get("seconds", ["100"])[0]) or 100), MAX_WAIT_SECONDS)
                deadline = time.monotonic() + budget
                while True:
                    now = time.time()
                    with _LOCK:
                        q = _public(next(x for x in _load()["questions"] if x["id"] == qid), now)
                    if q["status"] != "open" or time.monotonic() >= deadline:
                        break
                    time.sleep(0.5)
                self._send(200, q)
                return
            self._send(200, _public(q, now))
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        data = self._body()

        if path == "/api/ask":
            if not self._authed(ASK_TOKEN):
                self._send(401, {"error": "bad ask token"})
                return
            question = str(data.get("question", "")).strip()
            if not question:
                self._send(400, {"error": "question is required"})
                return
            try:
                timeout_minutes = float(data.get("timeout_minutes", DEFAULT_TIMEOUT_MINUTES))
            except (TypeError, ValueError):
                timeout_minutes = DEFAULT_TIMEOUT_MINUTES
            timeout_minutes = max(1.0, min(timeout_minutes, 330.0))  # CI job ceiling ~6h
            now = time.time()
            record = {
                "id": secrets.token_hex(8),
                "created": now,
                "deadline": now + timeout_minutes * 60.0,
                "question": question,
                "context": str(data.get("context", ""))[:8000],
                "issue": str(data.get("issue", ""))[:200],
                "run": str(data.get("run", ""))[:300],
                "answer": None,
                "answered_at": None,
            }
            with _LOCK:
                state = _load()
                state["questions"].append(record)
                state["questions"] = state["questions"][-500:]  # bounded history
                _save(state)
            self._send(200, {"id": record["id"], "deadline": record["deadline"]})
            return

        if path.startswith("/api/answer/"):
            qid = path.removeprefix("/api/answer/")
            if not self._authed(UI_TOKEN):
                self._send(401, {"error": "bad ui token"})
                return
            answer = str(data.get("answer", "")).strip()
            if not answer:
                self._send(400, {"error": "answer is required"})
                return
            now = time.time()
            with _LOCK:
                state = _load()
                q = next((x for x in state["questions"] if x["id"] == qid), None)
                if q is None:
                    self._send(404, {"error": "no such question"})
                    return
                q["answer"] = answer[:8000]
                q["answered_at"] = now
                _save(state)
            self._send(200, {"ok": True, "status": _status(q, now)})
            return

        self._send(404, {"error": "not found"})


def main() -> int:
    if not ASK_TOKEN or not UI_TOKEN:
        sys.stderr.write(
            "ESCALATION_ASK_TOKEN and ESCALATION_UI_TOKEN must be set (see README.md)\n"
        )
        return 2
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    sys.stderr.write(f"[relay] listening on {HOST}:{PORT}, state at {STATE_PATH}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
