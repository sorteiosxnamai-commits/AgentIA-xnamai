"""Seleção inteligente: notebook + orçamento + finalidade (sem acessórios)."""

from __future__ import annotations

from unittest.mock import patch

from agents.vendas.guardrails import extract_budget
from agents.vendas.tools import execute_tool
from services.intent_service import classificar_intencao
from services.product_service import buscar_por_intencao, normalizar_produto_servico
from services.vendas.memoria import atualizar_sessao_turno, sessao_vazia
from services.vendas.respostas import (
    cliente_quer_ver_catalogo,
    detectar_finalidade,
    resposta_busca_produtos,
    resposta_mostrar_catalogo,
)

MSG = (
    "Estou procurando um notebook para trabalhar, até 4 mil reais. "
    "Quais opções vocês têm?"
)

CATALOGO_MISTO = [
    {"nome": "HD Externo 1TB", "preco": 299.9, "categoria": "armazenamento", "estoque": 10},
    {"nome": "Headset Gamer X1", "preco": 189.9, "categoria": "headset", "estoque": 5},
    {"nome": "Hub USB 4 portas", "preco": 79.9, "categoria": "hub", "estoque": 20},
    {"nome": "Monitor LED 24", "preco": 699.9, "categoria": "monitor", "estoque": 4},
    {"nome": "Mouse RGB Pro", "preco": 89.9, "categoria": "mouse", "estoque": 15},
    {"nome": "Notebook Intel i5", "preco": 3499.9, "categoria": "notebook", "estoque": 89},
    {"nome": "SSD 480GB", "preco": 249.9, "categoria": "armazenamento", "estoque": 8},
    {"nome": "Teclado Mecânico", "preco": 199.9, "categoria": "teclado", "estoque": 6},
    {"nome": "Notebook Gamer RTX", "preco": 5899.9, "categoria": "notebook", "estoque": 2},
]


def _norm(produtos):
    return [normalizar_produto_servico(p, source="supabase") for p in produtos]


def test_mensagem_exata_nao_e_catalogo_geral():
    assert cliente_quer_ver_catalogo(MSG) is False
    intent = classificar_intencao(MSG)
    assert intent["intent"] == "BUSCA_PRODUTO"
    assert intent.get("category") == "notebook"


def test_extract_budget_4_mil():
    assert float(extract_budget(MSG)) == 4000.0


def test_detectar_finalidade_trabalho():
    assert detectar_finalidade(MSG) == "trabalho"


def test_selecao_notebook_filtra_acessorios_e_orcamento():
    with patch(
        "services.product_service._buscar_brutos",
        return_value=(CATALOGO_MISTO, "supabase", False),
    ):
        r = buscar_por_intencao(
            mensagem=MSG,
            intent="BUSCA_PRODUTO",
            categoria_ativa="notebook",
            product_query=MSG,
            orcamento_max=4000,
            limite=3,
        )

    assert r["found"] is True
    nomes = [p["name"] for p in r["products"]]
    assert "Notebook Intel i5" in nomes
    assert all(p["price"] is not None and p["price"] <= 4000 for p in r["products"])
    for proibido in ("HD Externo", "Headset", "Hub", "Mouse", "SSD", "Teclado"):
        assert not any(proibido.lower() in n.lower() for n in nomes)
    assert "Notebook Gamer RTX" not in nomes  # acima de R$ 4.000
    assert len(r["products"]) <= 3


def test_resposta_nao_repergunta_trabalho_nem_lista_acessorios():
    produtos = _norm([CATALOGO_MISTO[5]])  # só Notebook Intel i5
    texto = resposta_busca_produtos(
        nome_cliente="Cliente",
        produtos=produtos,
        mensagem=MSG,
        categoria="notebook",
        finalidade="trabalho",
        orcamento_max=4000,
    )
    assert texto.strip()
    assert "Notebook Intel i5" in texto
    assert "3499" in texto.replace(".", "").replace(",", "")
    baixa = texto.lower()
    assert "pessoal, trabalho ou gamer" not in baixa
    assert "uso pessoal" not in baixa
    for proibido in ("hd externo", "headset", "hub", "mouse", "ssd", "teclado"):
        assert proibido not in baixa


def test_resposta_catalogo_geral_respeita_finalidade():
    texto = resposta_mostrar_catalogo(
        "Tironi",
        _norm(CATALOGO_MISTO[:2]),
        mensagem=MSG,
        finalidade="trabalho",
    )
    assert "pessoal, trabalho ou gamer" not in texto.lower()


def test_sessao_captura_orcamento_e_finalidade():
    sessao = atualizar_sessao_turno(sessao_vazia(), mensagem=MSG, historico_texto="")
    assert sessao.get("orcamento") == 4000.0
    assert sessao.get("finalidade") == "trabalho"
    assert sessao.get("categoria_interesse") == "notebook"


def test_contexto_precarregado_nao_chama_search_duplicado():
    """Com produtos no contexto, search_products usa contexto (sem 2ª ida ao Mercos)."""
    chamadas = {"mercos": 0}

    def _fake_mercos(_q):
        chamadas["mercos"] += 1
        return CATALOGO_MISTO

    produtos_ctx = _norm([CATALOGO_MISTO[5]])
    with patch("services.mercos_service.mercos_configurado", return_value=True):
        with patch(
            "services.mercos_service.buscar_produtos_por_termo",
            side_effect=_fake_mercos,
        ):
            out1 = execute_tool(
                "search_products",
                {"query": "notebook", "limit": 3},
                context_products=produtos_ctx,
            )
            out2 = execute_tool(
                "search_products",
                {"query": "notebook", "limit": 3},
                context_products=produtos_ctx,
            )

    assert out1.get("ok") is True
    assert out2.get("ok") is True
    assert chamadas["mercos"] == 0
    nomes = [p.get("name") for p in ((out1.get("data") or {}).get("products") or [])]
    assert "Notebook Intel i5" in nomes
    for n in nomes:
        baixa = (n or "").lower()
        assert "headset" not in baixa
        assert "hub" not in baixa
        assert "mouse" not in baixa
        assert "teclado" not in baixa
        assert "ssd" not in baixa
        assert "hd externo" not in baixa


def test_fluxo_completo_mensagem_exata():
    """Integra intent + Product Service + resposta determinística."""
    intent = classificar_intencao(MSG)
    assert intent["intent"] == "BUSCA_PRODUTO"

    with patch(
        "services.product_service._buscar_brutos",
        return_value=(CATALOGO_MISTO, "supabase", False),
    ):
        with patch(
            "services.vendas.catalogo.montar_catalogo_geral",
            return_value={"produtos": CATALOGO_MISTO, "fonte": "supabase"},
        ):
            r = buscar_por_intencao(
                mensagem=MSG,
                intent=intent["intent"],
                categoria_ativa=intent.get("category") or "notebook",
                product_query=intent.get("product_query") or MSG,
                orcamento_max=4000,
                limite=3,
            )

    assert r["found"] is True
    assert r["products"]
    texto = resposta_busca_produtos(
        nome_cliente="Cliente",
        produtos=r["products"],
        mensagem=MSG,
        categoria=r.get("category") or "notebook",
        finalidade=detectar_finalidade(MSG),
        orcamento_max=4000,
    )
    assert texto.strip()
    assert "Notebook Intel i5" in texto
    baixa = texto.lower()
    assert "pessoal, trabalho ou gamer" not in baixa
    for proibido in ("hd externo", "headset", "hub usb", "mouse", "ssd", "teclado"):
        assert proibido not in baixa
