"""MCP stdio smoke test — lists the FortyGuard MCP tools without any API call.

This only performs the JSON-RPC handshake (`initialize`, `notifications/initialized`,
`tools/list`). It never submits an analysis, so it spends no credits.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 0,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "fortyguard-demo", "version": "0.0.1"},
    },
}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
TOOLS_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


def _spawn() -> subprocess.Popen:
    candidates = [["fortyguard-mcp"], [sys.executable, "-m", "fortyguard_mcp"]]
    last_error = None
    for cmd in candidates:
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return proc
        except FileNotFoundError as exc:  # noqa: PERF203
            last_error = exc
            continue
    raise RuntimeError(
        "Could not start the FortyGuard MCP server. Install it first:\n"
        "  pip install fortyguard-mcp\n"
        f"(last error: {last_error})"
    )


def _read(proc: subprocess.Popen, expected_id: int, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("Server closed stdout before responding.")
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("id") == expected_id:
            return message
    raise TimeoutError(f"No response for id={expected_id} within {timeout}s.")


def main() -> None:
    proc = _spawn()
    try:
        proc.stdin.write(json.dumps(INITIALIZE) + "\n")
        proc.stdin.flush()
        init_response = _read(proc, 0)
        print("initialize:", init_response.get("result", {}).get("serverInfo", {}), "\n")

        proc.stdin.write(json.dumps(INITIALIZED) + "\n")
        proc.stdin.flush()

        proc.stdin.write(json.dumps(TOOLS_LIST) + "\n")
        proc.stdin.flush()
        response = _read(proc, 1)
        tools = response.get("result", {}).get("tools", [])
        print(f"{len(tools)} tools exposed:\n")
        for tool in tools:
            print(f"- {tool.get('name')}: {tool.get('description', '')[:90]}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
