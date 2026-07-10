"""Tools MCP: transferir atendimento / notificar humano."""

from __future__ import annotations

from services.mcp.registry import register
from services.mcp.types import SessionContext, ToolResult, ToolSpec


def _transferir(args: dict, ctx: SessionContext) -> ToolResult:
    from services.vendedor_service import notificar_vendedor, vendedor_configurado

    if not vendedor_configurado():
        return ToolResult(
            ok=False,
            error={
                "code": "not_configured",
                "message": "Vendedor humano não configurado (VENDEDOR_WHATSAPP)",
            },
        )
    interesse = args.get("interesse") or ctx.sessao.get("produto_ativo") or "atendimento"
    motivo = args.get("motivo") or ctx.mensagem or "Cliente pediu atendimento humano"
    resp = notificar_vendedor(
        numero_cliente=ctx.telefone or "desconhecido",
        nome_cliente=ctx.nome_cliente or "Cliente",
        interesse=str(interesse),
        mensagem_cliente=str(motivo),
        produtos=ctx.produtos_consultados[:3] or None,
    )
    ok = bool(resp)
    return ToolResult(ok=ok, data={"notificado": ok, "interesse": interesse})


def register_tools() -> None:
    register(
        ToolSpec(
            name="atendimento.transferir_humano",
            description="Notifica vendedor humano via WhatsApp",
            handler=_transferir,
            parameters={
                "properties": {
                    "interesse": {"type": "string"},
                    "motivo": {"type": "string"},
                }
            },
            write_guard=True,
            allowed_callers={"rules", "admin"},
            tags=["atendimento", "write"],
        )
    )
