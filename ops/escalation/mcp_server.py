#!/usr/bin/env python3
"""stdio MCP server exposing ``ask_user`` — the tkfacade fix agent's direct
channel to the maintainer (docs/tracking/SPEC.md 5.4).

Speaks newline-delimited JSON-RPC 2.0 over stdin/stdout (the MCP stdio
transport) and implements the minimum surface opencode needs: initialize,
tools/list, tools/call, ping. One tool:

    ask_user(question, context?, issue?, timeout_minutes?)

Posts the question to the escalation relay (relay.py, see its README for
deployment) and blocks until the maintainer answers or the timeout lapses.
Returns plain text:

    <the answer>                 maintainer replied — proceed with it
    [TIMEOUT] ...                nobody replied within the window — the
                                 calling agent falls back to GitHub
                                 escalation per its prompt
    [UNAVAILABLE] ...            relay not configured/not reachable — same
                                 fallback

Configuration via environment (the fix workflow injects these from repo
secrets):

    ESCALATION_RELAY_URL   public relay base URL (e.g. the Tailscale
                           Funnel https URL); empty disables the channel
    ESCALATION_TOKEN       the relay's ask-side bearer token

Stdlib only; logs go to stderr so stdout stays clean JSON-RPC.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "tkfacade-escalation", "version": "0.1.0"}

RELAY_URL = os.environ.get("ESCALATION_RELAY_URL", "").rstrip("/")
RELAY_TOKEN = os.environ.get("ESCALATION_TOKEN", "")
HTTP_TIMEOUT = 15.0
POLL_SECONDS = 100.0  # under the relay's 110s long-poll cap

TOOL = {
    "name": "ask_user",
    "description": (
        "Ask the tkfacade maintainer a question directly and block until answered "
        "(default window: 120 minutes). Use this the moment you need the maintainer's "
        "intent — ambiguous scope, a design decision, a principle conflict, a repro "
        "that contradicts the report — BEFORE guessing. Returns the answer text, or a "
        "[TIMEOUT]/[UNAVAILABLE] marker meaning: fall back to GitHub escalation "
        "(comment mentioning @GirthquakeMag11, apply the escalation label, stop)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The precise question. State the decision needed and the options you see.",
            },
            "context": {
                "type": "string",
                "description": "What you were doing, what you tried, relevant paths/commands/output.",
            },
            "issue": {
                "type": "string",
                "description": "GitHub issue number or URL this concerns, if any.",
            },
            "timeout_minutes": {
                "type": "number",
                "description": "How long to wait (default 120).",
            },
        },
        "required": ["question"],
    },
}


def _log(msg: str) -> None:
    sys.stderr.write(f"[escalation-mcp] {msg}\n")
    sys.stderr.flush()


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{RELAY_URL}{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {RELAY_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ask_user(args: dict) -> str:
    if not RELAY_URL or not RELAY_TOKEN:
        return (
            "[UNAVAILABLE] escalation relay not configured for this run — fall back "
            "to GitHub escalation: comment on the issue mentioning @GirthquakeMag11, "
            "apply the escalation label, remove ready-to-fix, and stop."
        )
    question = str(args.get("question", "")).strip()
    if not question:
        return "[UNAVAILABLE] ask_user requires a non-empty question."
    try:
        timeout_minutes = float(args.get("timeout_minutes", 120))
    except (TypeError, ValueError):
        timeout_minutes = 120.0
    run_url = os.environ.get("GITHUB_SERVER_URL", "")
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = f"{run_url}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    try:
        created = _request(
            "POST",
            "/api/ask",
            {
                "question": question,
                "context": str(args.get("context", "")),
                "issue": str(args.get("issue", "")),
                "run": run_url,
                "timeout_minutes": timeout_minutes,
            },
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"relay unreachable: {exc!r}")
        return (
            f"[UNAVAILABLE] escalation relay unreachable ({exc}) — fall back to "
            "GitHub escalation: comment on the issue mentioning @GirthquakeMag11, "
            "apply the escalation label, remove ready-to-fix, and stop."
        )
    qid = created.get("id", "")
    _log(f"question {qid} filed; waiting up to {timeout_minutes:.0f} min")
    deadline = time.monotonic() + timeout_minutes * 60.0
    while time.monotonic() < deadline:
        try:
            state = _request("GET", f"/api/ask/{qid}/wait?seconds={POLL_SECONDS:.0f}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            _log(f"poll error (retrying): {exc!r}")
            time.sleep(5.0)
            continue
        status = state.get("status")
        if status == "answered":
            return str(state.get("answer", ""))
        if status == "expired":
            break
    return (
        f"[TIMEOUT] no answer within {timeout_minutes:.0f} minutes — fall back to "
        "GitHub escalation: comment on the issue mentioning @GirthquakeMag11, "
        "apply the escalation label, remove ready-to-fix, and stop."
    )


def _reply(mid: object, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            client_ver = (msg.get("params") or {}).get("protocolVersion", PROTOCOL_VERSION)
            out = _reply(mid, {
                "protocolVersion": client_ver,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            })
        elif method in ("notifications/initialized", "initialized"):
            continue
        elif method == "ping":
            out = _reply(mid, {})
        elif method == "tools/list":
            out = _reply(mid, {"tools": [TOOL]})
        elif method == "tools/call":
            params = msg.get("params") or {}
            if params.get("name") == "ask_user":
                text = ask_user(params.get("arguments") or {})
                out = _reply(mid, {"content": [{"type": "text", "text": text}], "isError": False})
            else:
                out = {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "error": {"code": -32602, "message": f"unknown tool {params.get('name')!r}"},
                }
        else:
            if mid is None:
                continue
            out = {"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32601, "message": f"method not found: {method}"}}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
