"""Tools MCP: cliente."""

from __future__ import annotations

from services.mcp.registry import register
from services.mcp.types import SessionContext, ToolResult, ToolSpec


def _buscar(args: dict, ctx: SessionContext) -> ToolResult:
    from services.supabase_service import buscar_cliente

    telefone = args.get("telefone") or ctx.telefone
    if not telefone:
        return ToolResult(ok=False, error={"code": "invalid_params", "message": "telefone obrigatório"})
    cliente = buscar_cliente(telefone)
    if cliente:
        ctx.cliente = {
            "id": cliente.get("id"),
            "telefone": cliente.get("telefone"),
            "nome": cliente.get("nome"),
        }
    return ToolResult(ok=True, data=ctx.cliente or {"encontrado": False})


def _salvar(args: dict, ctx: SessionContext) -> ToolResult:
    from services.supabase_service import atualizar_cliente, buscar_cliente, criar_cliente

    telefone = args.get("telefone") or ctx.telefone
    nome = args.get("nome") or ctx.nome_cliente or ""
    if not telefone:
        return ToolResult(ok=False, error={"code": "invalid_params", "message": "telefone obrigatório"})
    existente = buscar_cliente(telefone)
    if existente:
        if nome and existente.get("nome") != nome:
            atualizar_cliente(cliente_id=existente["id"], nome=nome)
            existente["nome"] = nome
        ctx.cliente = {"id": existente.get("id"), "telefone": telefone, "nome": existente.get("nome")}
        return ToolResult(ok=True, data={**ctx.cliente, "criado": False})
    novo = criar_cliente(telefone, nome=nome)
    ctx.cliente = {"id": novo.get("id"), "telefone": telefone, "nome": nome}
    return ToolResult(ok=True, data={**ctx.cliente, "criado": True})


def register_tools() -> None:
    register(
        ToolSpec(
            name="cliente.buscar",
            description="Busca cliente pelo telefone no Supabase do agente",
            handler=_buscar,
            parameters={"properties": {"telefone": {"type": "string"}}},
            tags=["cliente", "read"],
        )
    )
    register(
        ToolSpec(
            name="cliente.salvar",
            description="Cria ou atualiza cliente do agente",
            handler=_salvar,
            parameters={
                "properties": {
                    "telefone": {"type": "string"},
                    "nome": {"type": "string"},
                }
            },
            write_guard=True,
            allowed_callers={"rules", "admin"},
            tags=["cliente", "write"],
        )
    )
