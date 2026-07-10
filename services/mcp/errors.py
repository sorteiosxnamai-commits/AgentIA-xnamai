"""Erros padronizados MCP — nunca expor internals ao cliente."""

from __future__ import annotations

from services.mcp.types import ToolResult


class MCPError(Exception):
    def __init__(self, code: str, message: str = "", *, public: str | None = None):
        self.code = code
        self.message = message or code
        self.public = public or "Não foi possível concluir a consulta agora."
        super().__init__(self.message)


def result_from_exception(exc: Exception, tool: str = "") -> ToolResult:
    if isinstance(exc, MCPError):
        return ToolResult(
            ok=False,
            error={"code": exc.code, "message": exc.public},
            meta={"tool": tool, "internal": exc.message[:200]},
        )
    return ToolResult(
        ok=False,
        error={"code": "tool_error", "message": "Falha temporária na ferramenta."},
        meta={"tool": tool, "exc_type": type(exc).__name__},
    )


def stub_result(message: str, *, policy_ref: str = "", data: dict | None = None) -> ToolResult:
    return ToolResult(
        ok=False,
        stub=True,
        data=data or {},
        error={"code": "stub", "message": message},
        meta={"policy_ref": policy_ref} if policy_ref else {},
    )
