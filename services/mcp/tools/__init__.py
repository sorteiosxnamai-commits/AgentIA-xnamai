"""Auto-registro de tools MCP."""

from __future__ import annotations


def load_all() -> None:
    from services.mcp.tools import (
        atendimento,
        carrinho,
        cliente,
        contexto,
        historico,
        nf_envio_pagamento,
        orcamento,
        pedidos,
        produtos,
        stubs,
    )

    for mod in (
        cliente,
        produtos,
        pedidos,
        carrinho,
        nf_envio_pagamento,
        orcamento,
        atendimento,
        contexto,
        historico,
        stubs,
    ):
        if hasattr(mod, "register_tools"):
            mod.register_tools()
