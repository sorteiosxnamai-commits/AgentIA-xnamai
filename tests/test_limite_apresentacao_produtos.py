"""Limite de apresentação: pedidos comuns ≤3; 'mais opções' sem repetir."""

from __future__ import annotations

from services.product_service import (
    _limite_candidatos_ranqueados,
    buscar_por_intencao,
    normalizar_produto_servico,
)
from services.vendas.respostas import (
    LIMITE_APRESENTACAO_PRODUTOS,
    _filtrar_produtos_nao_apresentados,
    resposta_busca_produtos,
    resposta_mais_opcoes,
)

CATALOGO = [
    {
        "nome": "Adaptador de Tomada Universal",
        "preco": 12.9,
        "saldo_estoque": 420,
        "codigo": "ADT-UNI",
        "categoria": "adaptadores",
    },
    {
        "nome": "Adaptador de Tomada Benjamin",
        "preco": 18.5,
        "saldo_estoque": 477,
        "codigo": "ADT-BEN",
        "categoria": "adaptadores",
    },
    {
        "nome": "Adaptador de Tomada Cubo",
        "preco": 24.9,
        "saldo_estoque": 221,
        "codigo": "ADT-CUB",
        "categoria": "adaptadores",
    },
    {
        "nome": "Adaptador de Tomada Reto",
        "preco": 9.9,
        "saldo_estoque": 100,
        "codigo": "ADT-RET",
        "categoria": "adaptadores",
    },
    {
        "nome": "Adaptador de Tomada Quádruplo",
        "preco": 29.9,
        "saldo_estoque": 80,
        "codigo": "ADT-QUA",
        "categoria": "adaptadores",
    },
    {
        "nome": "Pilha Recarregável AA",
        "preco": 29.9,
        "saldo_estoque": 50,
        "codigo": "PIL-AA",
        "categoria": "pilhas",
    },
]


def _norm(produtos):
    return [normalizar_produto_servico(p, source="supabase") for p in produtos]


def test_limite_apresentacao_constante_tres():
    assert LIMITE_APRESENTACAO_PRODUTOS == 3


def test_candidatos_ranqueados_nao_cortam_em_tres():
    """Pool interno pode ser >3; o corte de exibição é na resposta."""
    assert _limite_candidatos_ranqueados(20, "adaptador") == 20
    assert _limite_candidatos_ranqueados(5, "adaptador") == 5
    assert _limite_candidatos_ranqueados(100, "") == 20


def test_pedido_comum_resposta_no_maximo_tres():
    produtos = _norm(CATALOGO[:5])
    texto = resposta_busca_produtos(
        nome_cliente="Arthur",
        produtos=produtos,
        mensagem="Estou procurando um adaptador de tomada. Quais opções vocês têm?",
        categoria="adaptador",
    )
    bullets = [ln for ln in texto.splitlines() if ln.strip().startswith("•")]
    assert len(bullets) <= 3
    assert "Adaptador de Tomada Universal" in texto
    assert "12,90" in texto or "12.90" in texto.replace(",", ".")
    assert "pilha" not in texto.lower()


def test_mais_opcoes_nao_repete_ja_mostrados():
    produtos = _norm(CATALOGO[:5])
    hist = (
        "Cliente: quero adaptador\n"
        "IA: • Adaptador de Tomada Universal — R$ 12,90\n"
        "• Adaptador de Tomada Benjamin — R$ 18,50\n"
        "• Adaptador de Tomada Cubo — R$ 24,90\n"
    )
    texto = resposta_mais_opcoes(
        "Arthur",
        hist,
        produtos,
        categoria="adaptador",
    )
    baixa = texto.lower()
    assert "temos sim" in baixa
    assert "universal" not in baixa
    assert "benjamin" not in baixa
    assert "cubo" not in baixa
    assert "reto" in baixa or "quádruplo" in baixa or "quadruplo" in baixa
    bullets = [ln for ln in texto.splitlines() if ln.strip().startswith("•")]
    assert 1 <= len(bullets) <= 3


def test_filtrar_nao_apresentados_fallback_se_todos_vistos():
    produtos = _norm(CATALOGO[:2])
    hist = "Adaptador de Tomada Universal Adaptador de Tomada Benjamin"
    out = _filtrar_produtos_nao_apresentados(produtos, hist, limite=3)
    assert len(out) == 2  # fallback aos originais


def test_busca_intencao_mantem_relevancia_e_pool(monkeypatch):
    monkeypatch.setattr(
        "services.vendas.catalogo.buscar_produtos",
        lambda: list(CATALOGO),
    )
    monkeypatch.setattr(
        "services.vendas.catalogo._usar_somente_supabase",
        lambda: True,
    )
    r = buscar_por_intencao(
        mensagem="adaptador de tomada com estoque",
        intent="BUSCA_PRODUTO",
        product_query="adaptador de tomada",
        categoria_ativa="adaptador",
        limite=20,
    )
    assert r["found"] is True
    nomes = [p["name"] for p in r["products"]]
    assert len(nomes) >= 3  # pool pode ter mais que 3
    assert all("adaptador" in n.lower() for n in nomes)
    assert all("pilha" not in n.lower() for n in nomes)
    # preço/estoque reais
    for p in r["products"]:
        assert p.get("price") is not None
        assert (p.get("stock_quantity") or 0) >= 0

    texto = resposta_busca_produtos(
        "Arthur",
        r["products"],
        mensagem="quais opções de adaptador?",
        categoria="adaptador",
    )
    assert len([ln for ln in texto.splitlines() if ln.strip().startswith("•")]) <= 3
