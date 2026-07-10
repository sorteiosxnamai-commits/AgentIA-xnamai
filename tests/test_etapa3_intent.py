"""Etapa 3 — classificação de intenção e linguagem comercial."""

from __future__ import annotations

from services.intent_service import (
    FRASES_PROIBIDAS,
    classificar_intencao,
    resposta_atendimento_humano,
    resposta_fora_do_escopo,
    resposta_sac,
    sanitizar_frases_comerciais,
)
from services.openai_service import resposta_sem_foto
from services.vendas.prompt import INSTRUCOES_BASE
from services.vendas.respostas import cliente_pediu_mais_opcoes, resposta_mais_opcoes
from services.xnamai_script import resposta_estoque_disponibilidade


def _c(msg: str, **kwargs):
    return classificar_intencao(msg, **kwargs)


# 1
def test_saudacao_simples():
    r = _c("oi")
    assert r["intent"] == "SAUDACAO"
    assert r["confidence"] >= 0.8
    assert r["in_scope"] is True


# 2
def test_busca_produto():
    r = _c("quero um headset gamer")
    assert r["intent"] == "BUSCA_PRODUTO"
    assert r["needs_catalog"] is True
    assert r["category"] in ("headset", "fone") or "headset" in r["product_query"].lower()


# 3
def test_mais_opcoes_sem_categoria():
    msg = "tem mais opções?"
    assert cliente_pediu_mais_opcoes(msg) is True
    r = _c(msg)
    assert r["intent"] == "MAIS_OPCOES"
    assert r["needs_catalog"] is True
    resp = resposta_mais_opcoes(nome_cliente="Ana", historico_texto="", produtos=[])
    assert "opções produtos" not in resp.lower()
    assert "tipo" in resp.lower() or "procura" in resp.lower() or "headset" in resp.lower()


# 4
def test_mais_opcoes_com_categoria_no_historico():
    hist = "Cliente: quero headset\nIA: Temos o Headset Gamer.\n"
    r = _c("me mostra outros", historico_texto=hist, categoria_ativa="headset")
    assert r["intent"] == "MAIS_OPCOES"
    assert r["category"] == "headset" or "headset" in (r.get("category") or "")
    resp = resposta_mais_opcoes(
        nome_cliente="Ana",
        historico_texto=hist,
        produtos=[{"nome": "Headset Gamer", "preco": 249.9}],
    )
    assert "não trabalhamos com opções" not in resp.lower()


# 5
def test_pergunta_preco():
    r = _c("qual o valor?", produto_ativo="Headset Gamer", categoria_ativa="headset")
    assert r["intent"] == "PRECO"
    assert r["needs_catalog"] is True


# 6
def test_comparacao_entre_produtos():
    r = _c("qual é melhor, o headset A ou o headset B?")
    assert r["intent"] == "COMPARACAO"
    assert r["needs_catalog"] is True


# 7
def test_reclamacao_sac():
    r = _c("meu pedido atrasou e veio com defeito, quero reclamar")
    assert r["intent"] == "SAC"
    assert r["needs_human"] is True
    assert "transtorno" in resposta_sac("Arthur").lower() or "suporte" in resposta_sac().lower()


# 8
def test_pedido_atendimento_humano():
    r = _c("quero falar com um atendente humano")
    assert r["intent"] == "ATENDIMENTO_HUMANO"
    assert r["needs_human"] is True
    assert "humano" in resposta_atendimento_humano().lower()


# 9
def test_fora_do_escopo():
    r = _c("me ensina uma receita de bolo")
    assert r["intent"] == "FORA_DO_ESCOPO"
    assert r["in_scope"] is False
    assert "xnamai" in resposta_fora_do_escopo().lower() or "produtos" in resposta_fora_do_escopo().lower()


# 10
def test_mensagem_ambigua():
    r = _c("talvez")
    assert r["intent"] == "INDEFINIDO"
    assert r["confidence"] < 0.6


# 11
def test_cliente_muda_de_assunto():
    r = _c(
        "na verdade quero um HD de 1TB",
        categoria_ativa="headset",
        historico_texto="Cliente: quero headset\n",
    )
    assert r["intent"] == "BUSCA_PRODUTO"
    assert r["category"] == "armazenamento"
    assert r["reason"] in ("mudanca_assunto", "busca_produto", "categoria_na_mensagem")


# 12
def test_cliente_responde_orcamento():
    r = _c(
        "meu orçamento é até R$ 300",
        ultima_pergunta_agente="Qual sua faixa de preço?",
        categoria_ativa="headset",
    )
    assert r["intent"] == "BUSCA_PRODUTO"
    assert r["reason"] == "resposta_orcamento"
    assert r["needs_catalog"] is True


# 13
def test_cliente_quer_comprar():
    r = _c("quero comprar esse, pode fechar", produto_ativo="Headset Gamer")
    assert r["intent"] == "COMPRA"


# 14
def test_cliente_pergunta_entrega():
    r = _c("quanto tempo demora a entrega?")
    assert r["intent"] == "ENTREGA"


# 15
def test_cliente_pergunta_garantia():
    r = _c("tem garantia?", produto_ativo="Headset Gamer")
    assert r["intent"] == "GARANTIA"


# 16
def test_cliente_pergunta_pagamento():
    r = _c("aceita pix?")
    assert r["intent"] == "PAGAMENTO"


# 17
def test_recomendacao_headset_para_jogos_tom_vendedor():
    """Comportamento esperado: produto + benefício + 1 pergunta; sem frases ruins."""
    r = _c("preciso de headset para jogos")
    assert r["intent"] == "BUSCA_PRODUTO"
    assert "headset" in (r.get("category") or r.get("product_query") or "").lower()

    exemplo_bom = (
        "Para jogos, Arthur, eu indicaria o Headset Gamer de R$ 249,90. "
        "Ele é uma boa opção para quem quer conforto e áudio melhor durante as partidas. "
        "Você prefere algo mais econômico ou quer priorizar qualidade?"
    )
    for frase in FRASES_PROIBIDAS:
        assert frase.lower() not in exemplo_bom.lower()
    assert "indicaria" in exemplo_bom.lower() or "indico" in exemplo_bom.lower()
    assert exemplo_bom.count("?") <= 1


# 18–20
def test_evitar_a_principio_temos_em_estoque():
    sujo = (
        "Oi, Arthur! Recomendo o Headset Gamer — R$ 249,90. "
        "A princípio temos em estoque (sujeito à separação). "
        "Aqui no chat não tenho foto. Quer ver o catálogo?"
    )
    limpo = sanitizar_frases_comerciais(sujo)
    assert "a princípio temos em estoque" not in limpo.lower()
    assert "sujeito à separação" not in limpo.lower()
    assert "aqui no chat não tenho foto" not in limpo.lower()
    assert "verificar a disponibilidade" in limpo.lower() or "opções" in limpo.lower()


def test_evitar_sujeito_a_separacao_no_script_estoque():
    texto = resposta_estoque_disponibilidade("Arthur")
    assert "a princípio" not in texto.lower()
    assert "sujeito" not in texto.lower()
    assert "verificar a disponibilidade" in texto.lower()


def test_evitar_aqui_no_chat_nao_tenho_foto():
    texto = resposta_sem_foto({"nome": "Headset Gamer", "preco": 249.9})
    assert "aqui no chat" not in texto.lower()
    assert "não tenho foto" not in texto.lower()
    assert "headset" in texto.lower()
    # Prompt proíbe falar de falta de foto de forma ruim
    assert "nunca diga que" in INSTRUCOES_BASE.lower() or "não tem foto" in INSTRUCOES_BASE.lower()
    assert 'estoque: "a princípio sim"' not in INSTRUCOES_BASE.lower()


def test_classificador_nao_e_resposta():
    """Classificação só retorna JSON estruturado — sem texto ao cliente."""
    r = _c("quero mouse")
    assert set(r.keys()) >= {
        "intent",
        "confidence",
        "in_scope",
        "needs_catalog",
        "needs_human",
        "product_query",
        "category",
        "reason",
    }
    assert isinstance(r["intent"], str)
    assert isinstance(r["confidence"], float)
