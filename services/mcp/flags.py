"""Feature flags da camada MCP."""

from __future__ import annotations

import os


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "sim", "yes")


def mcp_enabled() -> bool:
    return _flag("MCP_ENABLED", "true")


def mcp_server_enabled() -> bool:
    return _flag("MCP_SERVER_ENABLED", "false")


def mcp_tool_timeout() -> float:
    try:
        return float(os.getenv("MCP_TOOL_TIMEOUT", "8") or "8")
    except ValueError:
        return 8.0


def mcp_write_orders_enabled() -> bool:
    """Permite tools de criar pedido via MCP (ainda só caller=rules)."""
    return _flag("MCP_WRITE_ORDERS", "false")
