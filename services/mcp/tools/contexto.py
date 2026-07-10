"""Tools MCP: salvar/carregar contexto de sessão."""

from __future__ import annotations

from services.mcp.registry import register
from services.mcp.types import SessionContext, ToolResult, ToolSpec


def _carregar(args: dict, ctx: SessionContext) -> ToolResult:
    from services.vendas.memoria import carregar_sessao

    cid = args.get("cliente_id") or ctx.cliente_id
    sessao = carregar_sessao({"id": cid, "contexto_venda": ctx.sessao}, cid)
    ctx.sessao = sessao
    ctx.historico_resumo = sessao.get("resumo_curto") or ""
    return ToolResult(ok=True, data=sessao)


def _salvar(args: dict, ctx: SessionContext) -> ToolResult:
    from services.vendas.memoria import persistir_sessao

    cid = args.get("cliente_id") or ctx.cliente_id
    if not cid:
        return ToolResult(ok=False, error={"code": "invalid_params", "message": "cliente_id obrigatório"})
    sessao = dict(args.get("sessao") or ctx.sessao or {})
    persistir_sessao(str(cid), sessao)
    ctx.sessao = sessao
    return ToolResult(ok=True, data={"salvo": True, "resumo_curto": sessao.get("resumo_curto")})


def register_tools() -> None:
    register(
        ToolSpec(
            name="contexto.carregar",
            description="Carrega memória estruturada da sessão",
            handler=_carregar,
            parameters={"properties": {"cliente_id": {"type": "string"}}},
            tags=["contexto", "read"],
        )
    )
    register(
        ToolSpec(
            name="contexto.salvar",
            description="Persiste memória estruturada da sessão",
            handler=_salvar,
            parameters={
                "properties": {
                    "cliente_id": {"type": "string"},
                    "sessao": {"type": "object"},
                }
            },
            write_guard=True,
            allowed_callers={"rules", "admin"},
            tags=["contexto", "write"],
        )
    )
