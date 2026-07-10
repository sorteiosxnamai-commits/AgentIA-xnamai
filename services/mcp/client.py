"""Cliente MCP in-process."""

from __future__ import annotations

from typing import Any

from services.mcp import executor, registry
from services.mcp.types import SessionContext, ToolResult


class InProcessMCPClient:
    def list_tools(self) -> list[str]:
        return registry.list_names()

    def invoke(
        self,
        name: str,
        args: dict | None = None,
        ctx: SessionContext | None = None,
    ) -> ToolResult:
        return executor.invoke(name, args, ctx)

    def invoke_many(
        self,
        calls: list[dict[str, Any]],
        ctx: SessionContext | None = None,
    ) -> dict[str, ToolResult]:
        return executor.invoke_many(calls, ctx)


_client: InProcessMCPClient | None = None


def get_client() -> InProcessMCPClient:
    global _client
    if _client is None:
        _client = InProcessMCPClient()
    return _client
