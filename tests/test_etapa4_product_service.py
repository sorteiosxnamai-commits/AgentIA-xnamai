"""Etapa 4 — Product Service."""

from __future__ import annotations

from unittest.mock import patch

from services.product_service import (
    buscar_mais_opcoes,
    buscar_por_intencao,
    buscar_preco,
    buscar_produto_por_nome,
    disponibilidade_texto,
    montar_catalogo_para_prompt,
    normalizar_produto_servico,
)
from services.intent_service import sanitizar_frases_comerciais
from services.vendas.respostas import criterio_util_por_categoria, resposta_mais_opcoes
import inspect
import routes.api as api_mod


def _prod(nome, preco=None, estoque=None, categoria="", desc=""):
    p = {"id": 1, "nome": nome, "categoria": categoria, "descricao": desc}
    if preco is not None:
        p["preco"] = preco
    if estoque is not None:
        p["estoque"] = estoque
        p["saldo_estoque"] = estoque
    return p


# 1
def test_busca_produto_existente():
    with patch(
        "services.product_service._buscar_brutos",
        return_value=([_prod("Headset Gamer", 249.9, 5, "headset")], "supabase", False),
    ):
        r = buscar_por_intencao(mensagem="quero headset gamer", intent="BUSCA_PRODUTO")
    assert r["found"] is True
    assert r["products"][0]["name"] == "Headset Gamer"
    assert r["products"][0]["price"] == 249.9


# 2
def test_busca_produto_inexistente():
    with patch(
        "services.product_service._buscar_brutos",
        return_value=([], "supabase", True),
    ):
        with patch("services.product_service._amostra_relacionada", return_value=[]):
            r = buscar_por_intencao(mensagem="quero toalha vermelha", intent="BUSCA_PRODUTO")
    assert r["found"] is False
    assert "não encontrei" in r["message"].lower() or "nenhum" in r["message"].lower()


# 3
def test_produto_com_preco_real():
    n = normalizar_produto_servico(_prod("Mouse X", 89.9, 3))
    assert n["price"] == 89.9


# 4
def test_produto_sem_preco():
    n = normalizar_produto_servico({"nome": "Mouse X", "estoque": 2})
    assert n["price"] is None


# 5
def test_produto_com_estoque_confirmado():
    n = normalizar_produto_servico(_prod("SSD", 199, 10))
    assert n["stock_confirmed"] is True
    assert n["stock_quantity"] == 10
    assert "estoque confirmado" in disponibilidade_texto(n).lower()


# 6
def test_produto_sem_estoque_confirmado():
    n = normalizar_produto_servico({"nome": "SSD", "preco": 199})
    assert n["stock_quantity"] is None
    assert n["stock_confirmed"] is False
    assert "verificar a disponibilidade" in disponibilidade_texto(n).lower()


# 7
def test_produto_com_estoque_zero():
    n = normalizar_produto_servico(_prod("SSD", 199, 0))
    assert n["stock_quantity"] == 0
    assert n["stock_confirmed"] is False
    cat = montar_catalogo_para_prompt([n])
    assert "disponível" not in cat.lower()


# 8
def test_mais_opcoes_com_categoria():
    with patch(
        "services.product_service.buscar_mais_opcoes",
        return_value={
            "found": True,
            "category": "headset",
            "products": [
                normalizar_produto_servico(_prod("Headset A", 100, 2, "headset")),
                normalizar_produto_servico(_prod("Headset B", 150, 1, "headset")),
            ],
            "message": "ok",
            "catalogo": "",
        },
    ):
        # chama a função real de resposta com mock interno via patch no import path
        pass
    with patch(
        "services.vendas.catalogo.montar_catalogo_geral",
        return_value={
            "produtos": [
                _prod("Headset A", 100, 2, "headset"),
                _prod("Headset B", 150, 1, "headset"),
            ],
            "fonte": "supabase",
        },
    ):
        r = buscar_mais_opcoes(categoria="headset", historico_texto="Cliente: quero headset\n")
    assert r["found"] is True
    assert r["category"] == "headset"
    assert len(r["products"]) >= 1


# 9
def test_mais_opcoes_sem_categoria():
    r = buscar_mais_opcoes(categoria="", historico_texto="")
    assert r["found"] is False
    resp = resposta_mais_opcoes(nome_cliente="Ana", historico_texto="", produtos=[])
    assert "tipo de produto" in resp.lower() or "procurando" in resp.lower()


# 10
def test_preco_produto_ativo():
    with patch(
        "services.product_service.buscar_produto_por_nome",
        return_value={
            "found": True,
            "products": [normalizar_produto_servico(_prod("Headset Gamer", 249.9, 4))],
            "message": "ok",
            "catalogo": "",
            "category": "headset",
            "query": "Headset Gamer",
            "fonte": "supabase",
            "produtos": [normalizar_produto_servico(_prod("Headset Gamer", 249.9, 4))],
        },
    ):
        r = buscar_preco(produto_ativo="Headset Gamer")
    assert r["found"] is True
    assert r["products"][0]["price"] == 249.9


# 11
def test_comparacao_dois_produtos():
    def fake_nome(nome, historico_texto=""):
        if "a" in nome.lower() or "headset a" in nome.lower():
            p = normalizar_produto_servico(_prod("Headset A", 100, 2))
        else:
            p = normalizar_produto_servico(_prod("Headset B", 180, 1))
        return {
            "found": True,
            "products": [p],
            "produtos": [p],
            "catalogo": "",
            "message": "ok",
            "fonte": "supabase",
            "category": "",
            "query": nome,
        }

    with patch("services.product_service.buscar_produto_por_nome", side_effect=fake_nome):
        r = buscar_por_intencao(
            mensagem="qual melhor headset a ou headset b?",
            intent="COMPARACAO",
        )
    assert r["found"] is True
    assert len(r["products"]) >= 2


# 12
def test_compra_produto_existente():
    with patch(
        "services.product_service.buscar_produto_por_nome",
        return_value={
            "found": True,
            "products": [normalizar_produto_servico(_prod("Headset Gamer", 249.9, 3))],
            "produtos": [normalizar_produto_servico(_prod("Headset Gamer", 249.9, 3))],
            "message": "ok",
            "catalogo": "",
            "fonte": "supabase",
            "category": "headset",
            "query": "Headset Gamer",
        },
    ):
        r = buscar_por_intencao(
            mensagem="quero esse",
            intent="COMPRA",
            produto_ativo="Headset Gamer",
        )
    assert r["found"] is True
    assert r["products"][0]["name"] == "Headset Gamer"


# 13
def test_troca_categoria():
    with patch(
        "services.product_service._buscar_brutos",
        return_value=([_prod("HD Externo 1TB", 299, 2, "armazenamento")], "supabase", False),
    ):
        r = buscar_por_intencao(
            mensagem="na verdade quero um HD",
            intent="BUSCA_PRODUTO",
            categoria_ativa="headset",
        )
    assert r["found"] is True
    assert "hd" in r["products"][0]["name"].lower()


# 14–16
def test_nao_inventar_produto_preco_estoque():
    n = normalizar_produto_servico({"nome": "Item Sem Dados"})
    assert n["price"] is None
    assert n["stock_confirmed"] is False
    assert n["stock_quantity"] is None
    cat = montar_catalogo_para_prompt([n])
    assert "disponível" not in cat.lower()
    # sem nome → vazio
    assert normalizar_produto_servico({}) == {}


# 17
def test_chat_dry_run_persistir_false_assinatura():
    sig = inspect.signature(api_mod.processar_mensagem)
    assert "dry_run" in sig.parameters
    assert "persistir" in sig.parameters


# 18
def test_webhook_preservado():
    assert hasattr(api_mod, "receber_webhook")
    assert hasattr(api_mod, "webhook")


# 19
def test_disponivel_para_envio_sem_estoque_real():
    sujo = "Headset Gamer por R$ 249,90, disponível para envio."
    limpo = sanitizar_frases_comerciais(sujo)
    assert "disponível para envio" not in limpo.lower()
    n = normalizar_produto_servico(_prod("Headset", 249.9, None))
    assert "disponível para envio" not in disponibilidade_texto(n).lower()


# 20
def test_pergunta_sem_tres_opcoes():
    produtos = [
        {"nome": "Headset Gamer RGB", "preco": 159.9, "descricao": "gamer microfone jogos"},
        {"nome": "Headset Office", "preco": 99.9, "descricao": "trabalho chamadas"},
    ]
    pergunta = criterio_util_por_categoria("headset", produtos) or ""
    # no máximo 2 alternativas (um "ou")
    assert pergunta.count(" ou ") <= 1
    assert pergunta.count(",") < 2 or "ou" in pergunta.lower()
    # não deve listar três usos na mesma pergunta
    assert not (
        "jogos" in pergunta.lower()
        and "trabalho" in pergunta.lower()
        and "chamadas" in pergunta.lower()
    )
