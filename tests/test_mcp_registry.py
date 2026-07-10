"""Testes do registry e executor MCP."""

from services.mcp import registry
from services.mcp.client import get_client
from services.mcp.context import build_session_context, limpar_carrinho
from services.mcp.executor import invoke
from services.mcp.types import SessionContext


def test_registry_carrega_tools():
    names = registry.list_names()
    assert "produtos.buscar" in names
    assert "carrinho.adicionar" in names
    assert "cliente.buscar" in names
    assert "frete.cotar" in names
    assert "pedidos.criar_mercos" in names
    assert len(names) >= 15


def test_write_tool_bloqueada_para_llm():
    ctx = SessionContext(caller="llm")
    res = invoke("pedidos.criar_mercos", {}, ctx)
    assert res.ok is False
    assert res.error
    assert res.error["code"] in ("forbidden", "forbidden_write")


def test_carrinho_adicionar_consultar():
    limpar_carrinho("mcp-test-1")
    ctx = build_session_context(
        cliente_id="mcp-test-1",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 249.9},
        caller="rules",
    )
    client = get_client()
    add = client.invoke(
        "carrinho.adicionar",
        {"nome": "Headset Gamer", "quantidade": 2, "preco": 249.9},
        ctx,
    )
    assert add.ok is True
    cons = client.invoke("carrinho.consultar", {}, ctx)
    assert cons.ok is True
    assert cons.data["total_itens"] == 1
    assert cons.data["itens"][0]["quantidade"] == 2


def test_frete_e_stub():
    res = invoke("frete.cotar", {}, SessionContext(caller="rules"))
    assert res.stub is True
    assert res.error and res.error["code"] == "stub"


def test_parametro_obrigatorio():
    res = invoke("carrinho.remover", {}, SessionContext(caller="rules"))
    assert res.ok is False
    assert res.error["code"] == "invalid_params"
