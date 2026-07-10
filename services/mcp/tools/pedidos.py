"""Tools MCP: pedidos (consulta + create gated)."""

from __future__ import annotations

from services.mcp.flags import mcp_write_orders_enabled
from services.mcp.registry import register
from services.mcp.types import SessionContext, ToolResult, ToolSpec


def _consultar(args: dict, ctx: SessionContext) -> ToolResult:
    from services.pedido_pulsedesk_service import (
        diagnosticar_pulsedesk_pedidos,
        pulsedesk_pedidos_habilitado,
    )

    tel = args.get("telefone") or ctx.telefone
    if not tel:
        return ToolResult(ok=False, error={"code": "invalid_params", "message": "telefone obrigatório"})
    if not pulsedesk_pedidos_habilitado():
        return ToolResult(
            ok=True,
            data={"habilitado": False, "mensagem": "Pedidos PulseDesk desabilitados"},
        )
    data = diagnosticar_pulsedesk_pedidos(tel)
    return ToolResult(ok=True, data=data)


def _criar_mercos(args: dict, ctx: SessionContext) -> ToolResult:
    if not mcp_write_orders_enabled():
        return ToolResult(
            ok=False,
            error={"code": "disabled", "message": "MCP_WRITE_ORDERS=false"},
        )
    from services.pedido_mercos_service import criar_pedido_fechamento_mercos

    hist = args.get("historico") or ctx.historico_texto
    cliente = args.get("cliente_supabase") or ctx.cliente or {"id": ctx.cliente_id}
    resultado = criar_pedido_fechamento_mercos(
        historico_texto=hist,
        cliente_supabase=cliente,
        telefone=ctx.telefone,
        pushname=ctx.nome_cliente,
        mensagem_atual=ctx.mensagem,
    )
    return ToolResult(ok=bool(resultado and resultado.get("pedido_id")), data=resultado)


def _criar_pulsedesk(args: dict, ctx: SessionContext) -> ToolResult:
    if not mcp_write_orders_enabled():
        return ToolResult(
            ok=False,
            error={"code": "disabled", "message": "MCP_WRITE_ORDERS=false"},
        )
    from services.pedido_pulsedesk_service import registrar_venda_pulsedesk

    hist = args.get("historico") or ctx.historico_texto
    cliente = args.get("cliente_supabase") or ctx.cliente or {"id": ctx.cliente_id}
    resultado = registrar_venda_pulsedesk(
        historico_texto=hist,
        cliente_supabase=cliente,
        telefone=ctx.telefone,
        pushname=ctx.nome_cliente,
        mensagem_atual=ctx.mensagem,
    )
    return ToolResult(ok=bool(resultado and resultado.get("pedido_id")), data=resultado)


def register_tools() -> None:
    register(
        ToolSpec(
            name="pedidos.consultar",
            description="Consulta pedidos WhatsApp do cliente no PulseDesk",
            handler=_consultar,
            parameters={"properties": {"telefone": {"type": "string"}}},
            tags=["pedidos", "read"],
        )
    )
    register(
        ToolSpec(
            name="pedidos.criar_mercos",
            description="Cria pedido no Mercos (somente rules, flag MCP_WRITE_ORDERS)",
            handler=_criar_mercos,
            write_guard=True,
            allowed_callers={"rules", "admin"},
            tags=["pedidos", "write"],
        )
    )
    register(
        ToolSpec(
            name="pedidos.criar_pulsedesk",
            description="Registra pedido sintético no PulseDesk (somente rules)",
            handler=_criar_pulsedesk,
            write_guard=True,
            allowed_callers={"rules", "admin"},
            tags=["pedidos", "write"],
        )
    )
