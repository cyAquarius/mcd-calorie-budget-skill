"""Minimal Streamable HTTP MCP client for https://mcp.mcd.cn."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


DEFAULT_URL = "https://mcp.mcd.cn"

def load_mcp_token() -> str:
    """Resolve token from env, MCD_MCP_TOKEN_FILE, or ~/.config/mcd/mcp_token."""
    env = (os.environ.get("MCD_MCP_TOKEN") or "").strip()
    if env:
        return env
    file_hint = (os.environ.get("MCD_MCP_TOKEN_FILE") or "").strip()
    candidates = []
    if file_hint:
        candidates.append(os.path.expanduser(file_hint))
    candidates.append(os.path.expanduser("~/.config/mcd/mcp_token"))
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                value = f.read().strip()
            if value:
                return value
        except OSError:
            continue
    return ""




class McpError(RuntimeError):
    """MCP transport or tool error."""


class McpClient:
    def __init__(
        self,
        token: str | None = None,
        url: str = DEFAULT_URL,
        *,
        client_name: str = "mcd-calorie-budget-cli",
        client_version: str = "0.2.0",
        timeout: float = 120.0,
    ) -> None:
        self.url = url.rstrip("/")
        self.token = (token or load_mcp_token() or "").strip()
        if not self.token:
            raise McpError(
                "缺少 MCP Token。请 export MCD_MCP_TOKEN=...，"
                "或写入 ~/.config/mcd/mcp_token，"
                "或在 https://open.mcd.cn/mcp 申请。"
            )
        self.timeout = timeout
        self.client_name = client_name
        self.client_version = client_version
        self._id = 0
        self._session_id: str | None = None
        self._initialized = False

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _post(self, payload: dict[str, Any]) -> Any:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
                ctype = resp.headers.get("Content-Type", "")
                sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get(
                    "mcp-session-id"
                )
                if sid:
                    self._session_id = sid
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if e.code == 401:
                raise McpError(
                    "401：MCP Token 无效或过期，请到 https://open.mcd.cn/mcp 重新申请。"
                ) from e
            if e.code == 429:
                raise McpError("429：触发限流，请稍后重试。") from e
            raise McpError(f"HTTP {e.code}: {err_body[:300]}") from e
        except urllib.error.URLError as e:
            raise McpError(f"网络错误: {e}") from e

        if not body.strip():
            return None
        if "text/event-stream" in ctype:
            events: list[Any] = []
            for line in body.splitlines():
                if line.startswith("data:"):
                    events.append(json.loads(line[5:].strip()))
            return events[-1] if events else None
        return json.loads(body)

    def _rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        notification: bool = False,
    ) -> Any:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notification:
            self._id += 1
            payload["id"] = self._id
        if params is not None:
            payload["params"] = params
        return self._post(payload)

    def initialize(self) -> dict[str, Any]:
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": self.client_name,
                    "version": self.client_version,
                },
            },
        )
        try:
            self._rpc("notifications/initialized", notification=True)
        except Exception:
            # Some servers return empty body for notifications; ignore.
            pass
        self._initialized = True
        if isinstance(result, dict):
            return result.get("result") or {}
        return {}

    def ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def list_tools(self) -> list[dict[str, Any]]:
        self.ensure_initialized()
        result = self._rpc("tools/list")
        if not isinstance(result, dict):
            return []
        return list((result.get("result") or {}).get("tools") or [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call a tool; returns {isError, text, raw}."""
        self.ensure_initialized()
        result = self._rpc(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )
        if not isinstance(result, dict):
            raise McpError(f"工具 {name} 返回空响应")
        if "error" in result:
            err = result["error"]
            raise McpError(f"RPC error calling {name}: {err}")
        payload = result.get("result") or {}
        content = payload.get("content") or []
        texts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        return {
            "name": name,
            "isError": bool(payload.get("isError")),
            "text": "\n".join(texts),
            "raw": result,
        }

    def redacted_token_hint(self) -> str:
        t = self.token
        if len(t) <= 8:
            return "***"
        return f"{t[:4]}…{t[-4:]} (len={len(t)})"
