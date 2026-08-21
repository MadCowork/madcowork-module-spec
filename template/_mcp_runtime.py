"""Small JSON-RPC stdio runtime used by packaged modules."""

from __future__ import annotations

import json
import sys
import traceback

FALLBACK_PROTOCOL = "2025-06-18"


class McpServer:
    def __init__(self, name: str, version: str, tools: list[dict], handler):
        self.name = name
        self.version = version
        self.tools = tools
        self.handler = handler

    def log(self, message: str) -> None:
        print(f"[{self.name}] {message}", file=sys.stderr, flush=True)

    @staticmethod
    def _result(request_id, payload):
        return {"jsonrpc": "2.0", "id": request_id, "result": payload}

    @staticmethod
    def _error(request_id, code: int, message: str):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def dispatch(self, message: dict):
        method = message.get("method")
        request_id = message.get("id")
        if request_id is None:
            return None
        if method == "initialize":
            requested = (message.get("params") or {}).get("protocolVersion")
            return self._result(
                request_id,
                {
                    "protocolVersion": requested or FALLBACK_PROTOCOL,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": self.version},
                },
            )
        if method == "tools/list":
            return self._result(request_id, {"tools": self.tools})
        if method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            try:
                result = self.handler(name, arguments)
                text = result if isinstance(result, str) else json.dumps(
                    result, ensure_ascii=False, indent=2, sort_keys=True
                )
                return self._result(
                    request_id, {"content": [{"type": "text", "text": text}]}
                )
            except Exception as exc:  # noqa: BLE001
                self.log(f"tool {name} failed: {exc}\n{traceback.format_exc()}")
                return self._result(
                    request_id,
                    {
                        "content": [
                            {"type": "text", "text": f"{type(exc).__name__}: {exc}"}
                        ],
                        "isError": True,
                    },
                )
        if method == "ping":
            return self._result(request_id, {})
        return self._error(request_id, -32601, f"method not found: {method}")

    def run(self) -> None:
        self.log("started")
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
                response = self.dispatch(message)
            except Exception as exc:  # noqa: BLE001
                self.log(f"dispatch failed: {exc}\n{traceback.format_exc()}")
                response = self._error(None, -32603, f"internal error: {exc}")
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
                sys.stdout.flush()
        self.log("stdin closed")
