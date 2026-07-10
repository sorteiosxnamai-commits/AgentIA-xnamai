"""Testes do router de intenção MCP."""

from services.mcp.router import decide_tools


def test_decide_tools_produto():
    calls = decide_tools("quero um headset gamer", {})
    names = [c["name"] for c in calls]
    assert "contexto.carregar" in names
    assert "produtos.buscar" in names


def test_decide_tools_preco():
    calls = decide_tools("qual o valor", {"produto_ativo": "Headset Gamer"})
    names = [c["name"] for c in calls]
    assert "produtos.preco" in names


def test_decide_tools_frete():
    calls = decide_tools("quanto fica o frete?", {})
    names = [c["name"] for c in calls]
    assert "frete.cotar" in names
    assert "envio.consultar" in names


def test_decide_tools_humano():
    calls = decide_tools("quero falar com um atendente humano", {})
    names = [c["name"] for c in calls]
    assert "atendimento.transferir_humano" in names


def test_decide_tools_dedup():
    calls = decide_tools("quero headset e o valor", {})
    names = [c["name"] for c in calls]
    assert names.count("produtos.buscar") == 1
    assert names.count("contexto.carregar") == 1
