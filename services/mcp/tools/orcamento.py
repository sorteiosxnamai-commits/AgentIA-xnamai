"""Tools MCP: orçamento a partir do carrinho."""

from __future__ import annotations

from services.mcp.registry import register
from services.mcp.types import SessionContext, ToolResult, ToolSpec


def _gerar(args: dict, ctx: SessionContext) -> ToolResult:
    itens = list(ctx.carrinho)
    if not itens and ctx.sessao.get("produto_ativo"):
        itens = [
            {
                "nome": ctx.sessao.get("produto_ativo"),
                "quantidade": 1,
                "preco": ctx.sessao.get("preco_cotado"),
            }
        ]
    if not itens:
        return ToolResult(ok=False, error={"code": "empty", "message": "Carrinho vazio"})

    linhas = []
    total = 0.0
    for item in itens:
        qty = int(item.get("quantidade") or 1)
        try:
            preco = float(item.get("preco")) if item.get("preco") not in (None, "") else None
        except (TypeError, ValueError):
            preco = None
        sub = (preco or 0) * qty
        if preco is not None:
            total += sub
        linhas.append(
            {
                "nome": item.get("nome"),
                "quantidade": qty,
                "preco_unitario": preco,
                "subtotal": sub if preco is not None else None,
            }
        )

    return ToolResult(
        ok=True,
        data={
            "itens": linhas,
            "total": round(total, 2) if total else None,
            "observacao": "Frete/ST a confirmar. Orçamento baseado no catálogo da sessão.",
        },
    )


def register_tools() -> None:
    register(
        ToolSpec(
            name="orcamento.gerar",
            description="Gera orçamento JSON a partir do carrinho / produto ativo",
            handler=_gerar,
            tags=["orcamento", "read"],
        )
    )
