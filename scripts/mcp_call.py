#!/usr/bin/env python3
"""Call one colophon MCP tool over HTTP, handling the session handshake.

Streamable HTTP is not request/response in the naive sense. A client must first
`initialize`, keep the `Mcp-Session-Id` the server hands back, acknowledge with
`notifications/initialized`, and only then may it call a tool. A bare
`tools/list` gets `400 Bad Request: Missing session ID`.

That matters because it is the difference between "the server is up" and "the
server is reachable": a health check that skips the handshake reports a working
server as broken. This script gets it right so you can copy the shape.

Usage:
    python3 scripts/mcp_call.py colophon_gates
    python3 scripts/mcp_call.py colophon_validate '{"run_dir":"/tmp/colophon-demo"}'

Standard library only. It does not import colophon, so it works against a
server running anywhere.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000/mcp"
PROTOCOL_VERSION = "2025-06-18"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _post(url: str, payload: dict, session_id: str | None = None) -> tuple[dict, dict]:
    """POST one JSON-RPC message. Returns (response headers, parsed body)."""
    headers = dict(HEADERS)
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    body = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode()
            return dict(response.headers), raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        return dict(exc.headers), raw


def _unwrap(raw: str) -> dict:
    """Pull the JSON out of either a plain response or an SSE envelope."""
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            raw = line[len("data:") :].strip()
            break
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_unparseable": raw}


def handshake(url: str) -> str:
    """initialize → session id → notifications/initialized."""
    headers, raw = _post(
        url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcp_call", "version": "1"},
            },
        },
    )

    session_id = next(
        (v for k, v in headers.items() if k.lower() == "mcp-session-id"), None
    )
    if not session_id:
        raise SystemExit(f"no Mcp-Session-Id in response headers:\n{raw}")

    _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    return session_id


def call_tool(url: str, session_id: str, tool: str, arguments: dict) -> object:
    """tools/call, returned as the tool's own result payload."""
    _, raw = _post(
        url,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
        session_id,
    )

    message = _unwrap(raw)
    if "error" in message:
        raise SystemExit(f"server error: {message['error']}")

    result = message.get("result", {})
    if result.get("isError"):
        raise SystemExit("tool reported an error")

    # MCP wraps the return value in a content list; colophon returns one
    # structured blob, so take the first item and decode it if it is JSON text.
    content = result.get("content") or []
    for item in content:
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except json.JSONDecodeError:
                return item["text"]
    return result


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0

    url = DEFAULT_URL
    tool = argv[0]
    arguments = json.loads(argv[1]) if len(argv) > 1 else {}

    session_id = handshake(url)
    result = call_tool(url, session_id, tool, arguments)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
