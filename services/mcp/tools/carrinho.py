"""Tools MCP: carrinho em SessionContext."""

from __future__ import annotations

from services.mcp.context import sync_carrinho_to_store
from services.mcp.registry import register
from services.mcp.types import SessionContext, ToolResult, ToolSpec


def _consultar(args: dict, ctx: SessionContext) -> ToolResult:
    return ToolResult(ok=True, data={"itens": list(ctx.carrinho), "total_itens": len(ctx.carrinho)})


def _adicionar(args: dict, ctx: SessionContext) -> ToolResult:
    nome = (args.get("nome") or "").strip()
    if not nome:
        nome = (ctx.sessao.get("produto_ativo") or "").strip()
    if not nome:
        return ToolResult(ok=False, error={"code": "invalid_params", "message": "nome do produto obrigatório"})
    try:
        qty = int(args.get("quantidade") or 1)
    except (TypeError, ValueError):
        qty = 1
    qty = max(1, min(qty, 99))
    preco = args.get("preco")
    if preco is None:
        preco = ctx.sessao.get("preco_cotado")

    for item in ctx.carrinho:
        if (item.get("nome") or "").lower() == nome.lower():
            item["quantidade"] = int(item.get("quantidade") or 1) + qty
            if preco is not None:
                item["preco"] = preco
            sync_carrinho_to_store(ctx)
            return ToolResult(ok=True, data={"itens": ctx.carrinho, "atualizado": True})

    ctx.carrinho.append({"nome": nome, "quantidade": qty, "preco": preco})
    sync_carrinho_to_store(ctx)
    return ToolResult(ok=True, data={"itens": ctx.carrinho, "adicionado": True})


def _remover(args: dict, ctx: SessionContext) -> ToolResult:
    nome = (args.get("nome") or "").strip().lower()
    if not nome:
        return ToolResult(ok=False, error={"code": "invalid_params", "message": "nome obrigatório"})
    antes = len(ctx.carrinho)
    ctx.carrinho = [i for i in ctx.carrinho if (i.get("nome") or "").lower() != nome]
    sync_carrinho_to_store(ctx)
    return ToolResult(ok=True, data={"itens": ctx.carrinho, "removidos": antes - len(ctx.carrinho)})


def _alterar_qty(args: dict, ctx: SessionContext) -> ToolResult:
    nome = (args.get("nome") or "").strip().lower()
    try:
        qty = int(args.get("quantidade"))
    except (TypeError, ValueError):
        return ToolResult(ok=False, error={"code": "invalid_params", "message": "quantidade inválida"})
    if not nome:
        return ToolResult(ok=False, error={"code": "invalid_params", "message": "nome obrigatório"})
    if qty <= 0:
        return _remover({"nome": nome}, ctx)
    for item in ctx.carrinho:
        if (item.get("nome") or "").lower() == nome:
            item["quantidade"] = min(qty, 99)
            sync_carrinho_to_store(ctx)
            return ToolResult(ok=True, data={"itens": ctx.carrinho})
    return ToolResult(ok=False, error={"code": "not_found", "message": "Item não está no carrinho"})


def register_tools() -> None:
    register(
        ToolSpec(
            name="carrinho.consultar",
            description="Consulta itens do carrinho da sessão",
            handler=_consultar,
            tags=["carrinho", "read"],
        )
    )
    register(
        ToolSpec(
            name="carrinho.adicionar",
            description="Adiciona item ao carrinho da sessão",
            handler=_adicionar,
            parameters={
                "properties": {
                    "nome": {"type": "string"},
                    "quantidade": {"type": "integer"},
                    "preco": {"type": "number"},
                }
            },
            tags=["carrinho", "write"],
        )
    )
    register(
        ToolSpec(
            name="carrinho.remover",
            description="Remove item do carrinho",
            handler=_remover,
            parameters={"properties": {"nome": {"type": "string"}}},
            required=["nome"],
            tags=["carrinho", "write"],
        )
    )
    register(
        ToolSpec(
            name="carrinho.alterar_quantidade",
            description="Altera quantidade de um item do carrinho",
            handler=_alterar_qty,
            parameters={
                "properties": {
                    "nome": {"type": "string"},
                    "quantidade": {"type": "integer"},
                }
            },
            required=["nome", "quantidade"],
            tags=["carrinho", "write"],
        )
    )
