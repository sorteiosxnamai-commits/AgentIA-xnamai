"""Camada MCP in-process do agente de vendas xNaMai."""

from services.mcp.client import get_client
from services.mcp.flags import mcp_enabled, mcp_server_enabled
from services.mcp.registry import list_names, list_tools

__all__ = [
    "get_client",
    "mcp_enabled",
    "mcp_server_enabled",
    "list_names",
    "list_tools",
]
