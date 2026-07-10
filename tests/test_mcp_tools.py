"""Testes de tools MCP (carrinho / orçamento / formatter)."""

from services.mcp.context import build_session_context, limpar_carrinho
from services.mcp.executor import invoke
from services.mcp.formatter import para_prompt
from services.mcp.types import ToolResult


def test_orcamento_com_carrinho():
    limpar_carrinho("mcp-orc-1")
    ctx = build_session_context(cliente_id="mcp-orc-1", caller="rules")
    invoke(
        "carrinho.adicionar",
        {"nome": "Cabo HDMI", "quantidade": 2, "preco": 29.9},
        ctx,
    )
    res = invoke("orcamento.gerar", {}, ctx)
    assert res.ok is True
    assert res.data["total"] == round(29.9 * 2, 2)


def test_formatter_para_prompt():
    resultados = {
        "produtos.preco": ToolResult(ok=True, data={"nome": "Headset", "preco": 249.9}),
    }
    texto = para_prompt(resultados)
    assert "RESULTADOS MCP" in texto
    assert "Headset" in texto


def test_alterar_quantidade_e_remover():
    limpar_carrinho("mcp-qty-1")
    ctx = build_session_context(cliente_id="mcp-qty-1", caller="rules")
    invoke("carrinho.adicionar", {"nome": "Mouse", "quantidade": 1, "preco": 50}, ctx)
    alt = invoke("carrinho.alterar_quantidade", {"nome": "Mouse", "quantidade": 3}, ctx)
    assert alt.ok and alt.data["itens"][0]["quantidade"] == 3
    rem = invoke("carrinho.remover", {"nome": "Mouse"}, ctx)
    assert rem.ok is True
    assert rem.data["itens"] == []
    assert rem.data.get("removidos", 0) >= 1
