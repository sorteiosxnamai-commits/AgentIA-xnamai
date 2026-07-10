"""Tools MCP: histórico do cliente."""

from __future__ import annotations

from services.mcp.registry import register
from services.mcp.types import SessionContext, ToolResult, ToolSpec


def _buscar(args: dict, ctx: SessionContext) -> ToolResult:
    from services.supabase_service import buscar_historico

    cid = args.get("cliente_id") or ctx.cliente_id
    if not cid:
        return ToolResult(ok=False, error={"code": "invalid_params", "message": "cliente_id obrigatório"})
    try:
        limit = int(args.get("limit") or 40)
    except (TypeError, ValueError):
        limit = 40
    rows = buscar_historico(cid, limit=limit) or []
    linhas = []
    for msg in rows[-limit:]:
        role = "Cliente" if msg.get("tipo") == "cliente" else "IA"
        linhas.append(f"{role}: {msg.get('mensagem')}")
    texto = "\n".join(linhas)
    ctx.historico_resumo = texto[-500:] if texto else ""
    return ToolResult(
        ok=True,
        data={"total": len(rows), "linhas": linhas[-20:], "texto_recente": "\n".join(linhas[-12:])},
    )


def register_tools() -> None:
    register(
        ToolSpec(
            name="historico.buscar",
            description="Busca histórico recente de mensagens do cliente",
            handler=_buscar,
            parameters={
                "properties": {
                    "cliente_id": {"type": "string"},
                    "limit": {"type": "integer"},
                }
            },
            tags=["historico", "read"],
        )
    )
