#!/usr/bin/env python3
"""stdio MCP server exposing the tkfacade escalation channel — the fix
agent's direct line to the maintainer (docs/tracking/SPEC.md 5.4).

Speaks newline-delimited JSON-RPC 2.0 over stdin/stdout (the MCP stdio
transport) and implements the minimum surface opencode needs: initialize,
tools/list, tools/call, ping.

Two tools, both returning in well under a second — opencode's MCP client
kills long-blocking tool calls, so the wait lives in the *agent*, not the
tool: the agent posts its question with ``ask_user``, then polls
``check_answer`` between bash sleeps until it gets a verdict.

    ask_user(question, context?, issue?, timeout_minutes?)
        Files the question with the relay. Returns a marker line:
        ``FILED id=<id> window=<minutes>m`` — then instruct the agent to
        poll — or ``UNAVAILABLE: <reason>`` when the relay is not
        configured or not reachable (agent falls back to GitHub
        escalation per its prompt).

    check_answer(question_id)
        Non-blocking status read. Returns exactly one of:
        ``PENDING elapsed=<m> window=<m>``   — keep sleeping and polling
        ``ANSWERED: <the maintainer's answer>`` — proceed with it
        ``EXPIRED window=<m>``                — nobody answered; GitHub
                                               escalation fallback
        ``UNKNOWN_ID <id>`` / ``UNAVAILABLE: <reason>``

Configuration via environment (the fix workflow injects these from repo
secrets):

    ESCALATION_RELAY_URL   public relay base URL (Tailscale Funnel https
                           URL); empty disables the channel
    ESCALATION_TOKEN       the relay's ask-side bearer token

The relay side is ops/escalation/relay.py (deployed separately; see its
README). Stdlib only; logs go to stderr so stdout stays clean JSON-RPC.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "tkfacade-escalation", "version": "0.2.0"}

RELAY_URL = os.environ.get("ESCALATION_RELAY_URL", "").rstrip("/")
RELAY_TOKEN = os.environ.get("ESCALATION_TOKEN", "")
HTTP_TIMEOUT = 20.0

POLL_INSTRUCTIONS = (
    "Poll loop: run `sleep 60` in bash, then call check_answer with this id. "
    "Repeat until ANSWERED (proceed; also post the Q&A verbatim to the GitHub "
    "issue as the durable record) or EXPIRED (GitHub escalation fallback per "
    "your prompt: comment mentioning @GirthquakeMag11 quoting this question, "
    "apply the escalation label, remove ready-to-fix and fix-in-progress, stop "
    "for this issue). Do not poll faster than once per 60 seconds."
)

TOOLS = [
    {
        "name": "ask_user",
        "description": (
            "File a question for the tkfacade maintainer (desktop/browser push "
            "notification reaches them; default answer window 120 minutes). Use "
            "the moment you need maintainer intent — ambiguous scope, a design "
            "decision, a principle conflict, a repro contradicting the report — "
            "BEFORE guessing. Returns immediately: 'FILED id=... window=...m' "
            "(then poll with check_answer between `sleep 60` calls), or "
            "'UNAVAILABLE: ...' (fall back to GitHub escalation)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The precise question: the decision needed, the options, your lean, consequences.",
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
                    "description": "Answer window in minutes (default 120).",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "check_answer",
        "description": (
            "Non-blocking status of a question filed via ask_user. Returns "
            "PENDING (keep sleeping ~60s and re-poll), ANSWERED: <text> "
            "(proceed with it), EXPIRED (maintainer away — GitHub escalation "
            "fallback), or UNAVAILABLE/UNKNOWN_ID."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question_id": {
                    "type": "string",
                    "description": "The id returned by ask_user.",
                },
            },
            "required": ["question_id"],
        },
    },
]


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


def _unavailable(reason: str) -> str:
    return (
        f"UNAVAILABLE: {reason} — fall back to GitHub escalation: comment on "
        "the issue mentioning @GirthquakeMag11 with the question you need "
        "answered, apply the escalation label, remove ready-to-fix, and stop "
        "for this issue."
    )


def ask_user(args: dict) -> str:
    if not RELAY_URL or not RELAY_TOKEN:
        return _unavailable("escalation relay not configured for this run")
    question = str(args.get("question", "")).strip()
    if not question:
        return _unavailable("ask_user requires a non-empty question")
    try:
        timeout_minutes = float(args.get("timeout_minutes", 120))
    except (TypeError, ValueError):
        timeout_minutes = 120.0
    run_url = os.environ.get("GITHUB_SERVER_URL", "")
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = (
            f"{run_url}/{os.environ.get('GITHUB_REPOSITORY', '')}"
            f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        )
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
        return _unavailable(f"relay unreachable ({exc})")
    qid = created.get("id", "")
    deadline = created.get("deadline")
    window = (
        f"{(float(deadline) - time.time()) / 60:.0f}m"
        if deadline
        else f"{timeout_minutes:.0f}m"
    )
    _log(f"question {qid} filed, window {window}")
    return f"FILED id={qid} window={window}. {POLL_INSTRUCTIONS}"


def check_answer(args: dict) -> str:
    if not RELAY_URL or not RELAY_TOKEN:
        return _unavailable("escalation relay not configured for this run")
    qid = str(args.get("question_id", "")).strip()
    if not qid:
        return "UNKNOWN_ID (empty question_id)"
    try:
        state = _request("GET", f"/api/ask/{qid}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return f"UNKNOWN_ID {qid}"
        _log(f"poll error: {exc!r}")
        return _unavailable(f"relay HTTP error ({exc.code})")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"poll error: {exc!r}")
        return _unavailable(f"relay unreachable ({exc})")
    status = state.get("status")
    if status == "answered":
        return f"ANSWERED: {state.get('answer', '')}"
    if status == "expired":
        window = (float(state.get("deadline", 0)) - float(state.get("created", 0))) / 60
        return (
            f"EXPIRED window={window:.0f}m — no answer arrived. "
            "GitHub escalation fallback per your prompt: comment on the issue "
            "mentioning @GirthquakeMag11 quoting the question, apply the "
            "escalation label, remove ready-to-fix and fix-in-progress, stop "
            "for this issue."
        )
    elapsed = (time.time() - float(state.get("created", time.time()))) / 60
    window = (float(state.get("deadline", 0)) - float(state.get("created", 0))) / 60
    return f"PENDING elapsed={elapsed:.0f}m window={window:.0f}m — `sleep 60`, then poll again."


HANDLERS = {"ask_user": ask_user, "check_answer": check_answer}


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
            out = _reply(mid, {"tools": TOOLS})
        elif method == "tools/call":
            params = msg.get("params") or {}
            handler = HANDLERS.get(params.get("name", ""))
            if handler is not None:
                text = handler(params.get("arguments") or {})
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
