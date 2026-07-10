"""Tools MCP: produtos, preço e estoque."""

from __future__ import annotations

from services.mcp.registry import register
from services.mcp.types import SessionContext, ToolResult, ToolSpec


def _resumir_produto(p: dict) -> dict:
    return {
        "nome": p.get("nome"),
        "codigo": p.get("codigo"),
        "preco": p.get("preco") if p.get("preco") not in (None, "") else p.get("preco_tabela"),
        "estoque": p.get("estoque") if p.get("estoque") is not None else p.get("saldo_estoque"),
        "categoria": p.get("categoria"),
    }


def _buscar(args: dict, ctx: SessionContext) -> ToolResult:
    from services.vendas.catalogo import montar_contexto_catalogo

    consulta = (args.get("consulta") or args.get("q") or ctx.mensagem or "").strip()
    if not consulta:
        return ToolResult(ok=False, error={"code": "invalid_params", "message": "consulta obrigatória"})
    cat = montar_contexto_catalogo(consulta, ctx.historico_texto)
    produtos = [_resumir_produto(p) for p in (cat.get("produtos") or [])[:10]]
    ctx.produtos_consultados = produtos
    if produtos and not ctx.sessao.get("produto_ativo"):
        ctx.sessao["produto_ativo"] = produtos[0].get("nome") or ""
        ctx.sessao["preco_cotado"] = produtos[0].get("preco")
    return ToolResult(
        ok=True,
        data={
            "consulta": consulta,
            "fonte": cat.get("fonte"),
            "sem_match": bool(cat.get("sem_match")),
            "produtos": produtos,
            "similares": [_resumir_produto(p) for p in (cat.get("similares") or [])[:3]],
            "upsell": [_resumir_produto(p) for p in (cat.get("upsell") or [])[:2]],
        },
    )


def _preco(args: dict, ctx: SessionContext) -> ToolResult:
    nome = (args.get("nome") or ctx.sessao.get("produto_ativo") or "").strip()
    if not nome and ctx.produtos_consultados:
        nome = ctx.produtos_consultados[0].get("nome") or ""
    if not nome:
        return ToolResult(ok=False, error={"code": "no_product", "message": "Nenhum produto em discussão"})
    # Reusa busca
    res = _buscar({"consulta": nome}, ctx)
    if not res.ok:
        return res
    produtos = (res.data or {}).get("produtos") or []
    if not produtos:
        return ToolResult(ok=False, error={"code": "not_found", "message": "Produto não encontrado no catálogo"})
    p = produtos[0]
    return ToolResult(ok=True, data={"nome": p.get("nome"), "preco": p.get("preco")})


def _estoque(args: dict, ctx: SessionContext) -> ToolResult:
    nome = (args.get("nome") or ctx.sessao.get("produto_ativo") or "").strip()
    if not nome and ctx.produtos_consultados:
        nome = ctx.produtos_consultados[0].get("nome") or ""
    if not nome:
        return ToolResult(
            ok=True,
            data={
                    "politica": (
                        "Posso verificar a disponibilidade para você. "
                        "Confirme o produto que eu checo o estoque."
                    ),
            },
        )
    res = _buscar({"consulta": nome}, ctx)
    produtos = (res.data or {}).get("produtos") or []
    if not produtos:
        return ToolResult(ok=False, error={"code": "not_found", "message": "Produto não encontrado"})
    p = produtos[0]
    return ToolResult(
        ok=True,
        data={
            "nome": p.get("nome"),
            "estoque": p.get("estoque"),
            "politica": "Posso verificar a disponibilidade para você.",
        },
    )


def register_tools() -> None:
    register(
        ToolSpec(
            name="produtos.buscar",
            description="Busca produtos no catálogo (Supabase/Mercos)",
            handler=_buscar,
            parameters={"properties": {"consulta": {"type": "string"}, "q": {"type": "string"}}},
            tags=["produtos", "read"],
        )
    )
    register(
        ToolSpec(
            name="produtos.preco",
            description="Consulta preço do produto em discussão ou por nome",
            handler=_preco,
            parameters={"properties": {"nome": {"type": "string"}}},
            tags=["produtos", "preco", "read"],
        )
    )
    register(
        ToolSpec(
            name="produtos.estoque",
            description="Consulta estoque / política de disponibilidade",
            handler=_estoque,
            parameters={"properties": {"nome": {"type": "string"}}},
            tags=["produtos", "estoque", "read"],
        )
    )
