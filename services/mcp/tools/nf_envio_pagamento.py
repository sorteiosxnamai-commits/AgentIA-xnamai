"""Tools MCP: NF, envio e pagamento (extractors existentes)."""

from __future__ import annotations

from services.mcp.registry import register
from services.mcp.types import SessionContext, ToolResult, ToolSpec


def _nf(args: dict, ctx: SessionContext) -> ToolResult:
    from services.xnamai_script import extrair_preferencia_nf

    nf = extrair_preferencia_nf(ctx.historico_texto, ctx.mensagem)
    if nf:
        ctx.preferencias["nf"] = nf
        ctx.dados_confirmados["nf"] = nf
    return ToolResult(
        ok=True,
        data={
            "nf": nf,
            "politica": "Alinhar NF (e %) antes de registrar o pedido, se ainda faltar.",
        },
    )


def _envio(args: dict, ctx: SessionContext) -> ToolResult:
    from services.xnamai_script import extrair_forma_envio

    envio = extrair_forma_envio(ctx.historico_texto, ctx.mensagem)
    if envio:
        valor = envio if envio in ("retirada", "envio") else "envio"
        ctx.preferencias["envio"] = valor
        ctx.dados_confirmados["envio"] = valor
    return ToolResult(
        ok=True,
        data={
            "envio": ctx.preferencias.get("envio") or envio,
            "politica": "Forma de envio ou retirada deve ser confirmada antes do registro.",
        },
    )


def _pagamento(args: dict, ctx: SessionContext) -> ToolResult:
    from services.conversa_service import extrair_pagamento

    pag = extrair_pagamento(ctx.historico_texto, mensagem_atual=ctx.mensagem)
    if pag and pag != "a combinar":
        ctx.preferencias["pagamento"] = pag
        ctx.dados_confirmados["pagamento"] = pag
    return ToolResult(
        ok=True,
        data={
            "pagamento": pag,
            "politica": (
                "Pagamento antecipado é preferência (não obrigatório) "
                "para agilizar separação."
            ),
        },
    )


def register_tools() -> None:
    register(
        ToolSpec(
            name="nf.consultar",
            description="Consulta preferência de NF já informada na conversa",
            handler=_nf,
            tags=["nf", "read"],
        )
    )
    register(
        ToolSpec(
            name="envio.consultar",
            description="Consulta forma de envio/retirada informada",
            handler=_envio,
            tags=["envio", "read"],
        )
    )
    register(
        ToolSpec(
            name="pagamento.consultar",
            description="Consulta forma de pagamento e política antecipada",
            handler=_pagamento,
            tags=["pagamento", "read"],
        )
    )
