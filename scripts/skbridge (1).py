#!/usr/bin/env python3
"""Minimal JSON-RPC client for the SpliceKit bridge running inside the patched
Final Cut Pro (127.0.0.1:9876). Same newline-delimited protocol as the MCP
server (mcp/server.py). Useful for scripted workflows and for testing without
the MCP layer.

Usage:
  skbridge.py METHOD ['{"json":"params"}']
  skbridge.py timeline.getDetailedState '{"limit": 50}'
  skbridge.py fcpxml.import @/path/to/file.fcpxml        # file content as "xml" param

Prints the JSON result (or the error) on stdout. Exit code 1 on error.
"""
from __future__ import annotations

import json
import socket
import sys

HOST, PORT = "127.0.0.1", 9876


def call(method: str, params: dict | None = None, timeout: float = 120) -> dict:
    s = socket.create_connection((HOST, PORT), timeout=timeout)
    req = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    s.sendall(json.dumps(req).encode() + b"\n")
    buf = b""
    while True:
        while b"\n" not in buf:
            chunk = s.recv(16 * 1024 * 1024)
            if not chunk:
                s.close()
                return {"error": "connection closed by SpliceKit"}
            buf += chunk
        line, buf = buf.split(b"\n", 1)
        if not line.strip():
            continue
        try:
            resp = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "method" in resp or resp.get("id") != 1:
            continue  # event notification or stale frame
        s.close()
        if "error" in resp:
            return {"error": resp["error"]}
        return resp.get("result", {})


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    method = sys.argv[1]
    params: dict = {}
    if len(sys.argv) > 2:
        arg = sys.argv[2]
        if arg.startswith("@"):
            with open(arg[1:], encoding="utf-8") as fh:
                params = {"xml": fh.read()}
            if len(sys.argv) > 3:
                params.update(json.loads(sys.argv[3]))
        else:
            params = json.loads(arg)
    r = call(method, params)
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    return 1 if "error" in r else 0


if __name__ == "__main__":
    sys.exit(main())
