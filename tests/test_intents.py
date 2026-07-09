"""Regressão das intenções críticas do vendedor WhatsApp."""

from services.conversa_service import (
    _parse_preco,
    cliente_quer_nova_venda,
    eh_confirmacao_fechamento,
    fechamento_pronto,
    ia_pediu_fechamento,
    negociacao_nova_apos_fechamento,
    resolver_estado_venda,
)
from services.vendas.catalogo import (
    _expandir_aliases,
    _score_produto,
    termos_produto_relevantes,
)


def test_parse_preco_249_9_nao_vira_2499():
    assert _parse_preco("249.9") == 249.9
    assert _parse_preco("249.90") == 249.9
    assert _parse_preco("249,90") == 249.9
    assert _parse_preco("29.9") == 29.9
    assert _parse_preco("1.249,90") == 1249.9
    assert _parse_preco("3.499") == 3499.0
    assert _parse_preco("1.249") == 1249.0


def test_quero_fazer_outro_pedido_e_nova_venda():
    msg = "Quero fazer outro pedido"
    assert cliente_quer_nova_venda(msg) is True
    assert negociacao_nova_apos_fechamento("", msg) is True
    assert resolver_estado_venda("", msg, "") == "nova_venda"


def test_ok_sem_oferta_fechamento_nao_fecha():
    historico = (
        "Cliente: quero um headset gamer\n"
        "IA: Show! Headset Gamer por R$ 249.9 — temos disponível.\n"
        "Cliente: e tem garantia?\n"
        "IA: Sim, garantia de fábrica. Qualquer dúvida me chama.\n"
    )
    assert eh_confirmacao_fechamento("ok", historico, "Sim, garantia de fábrica.") is False
    assert resolver_estado_venda(historico, "ok", "Sim, garantia de fábrica.") != "fechando"


def test_fechamos_sim_apos_oferta_fecha():
    historico = (
        "Cliente: quero um headset gamer\n"
        "IA: Show! Headset Gamer por R$ 249.9 — temos disponível; fechamos 1 unidade?\n"
    )
    ultima = "Show! Headset Gamer por R$ 249.9 — temos disponível; fechamos 1 unidade?"
    assert ia_pediu_fechamento(ultima) is True
    assert fechamento_pronto(historico, ultima) is True
    assert eh_confirmacao_fechamento("fechamos sim", historico, ultima) is True
    assert resolver_estado_venda(historico, "fechamos sim", ultima) == "fechando"


def test_ok_apos_fechamos_fecha():
    historico = (
        "Cliente: quero cabo hdmi\n"
        "IA: Cabo HDMI 2m por R$ 29.9. Fechamos 1 unidade?\n"
    )
    ultima = "Cabo HDMI 2m por R$ 29.9. Fechamos 1 unidade?"
    assert eh_confirmacao_fechamento("ok", historico, ultima) is True


def test_soft_pos_venda_com_nova_negociacao_permite_fechar():
    historico = (
        "Cliente: quero cabo\n"
        "IA: Fechado! Resumo do pedido:\n📦 Cabo HDMI 2m\nPedido registrado!\n"
        "Cliente: quero um headset gamer\n"
        "IA: Headset Gamer por R$ 249.9. Fechamos 1 unidade?\n"
        "IA: Oi! Seu pedido já está registrado. Precisa de algo mais?\n"
    )
    # Soft pós-venda na última, mas há oferta de headset na venda nova
    assert negociacao_nova_apos_fechamento(historico, "fechamos sim") is True
    assert cliente_quer_nova_venda("quero fazer outro pedido") is True


def test_aliases_headset():
    termos = _expandir_aliases(["headset", "gamer"])
    assert "headset" in termos
    assert "fone" in termos


def test_score_headset_gamer():
    produto = {"nome": "Headset Gamer", "codigo": "PRD009", "categoria": "", "descricao": ""}
    score = _score_produto(produto, ["headset", "gamer"])
    assert score >= 10
    assert termos_produto_relevantes(["quero", "headset", "gamer"]) == ["headset", "gamer"]


def test_outro_pedido_nao_e_termo_produto():
    relevantes = termos_produto_relevantes(
        ["quero", "fazer", "outro", "pedido"]
    )
    assert "pedido" not in relevantes
    assert "quero" not in relevantes
    assert "outro" not in relevantes


def test_retirar_nao_vira_termo_produto():
    from services.vendas.catalogo import _termos_do_cliente, montar_contexto_catalogo

    hist = (
        "Cliente: quero notebook\n"
        "IA: Notebook Intel i5 por R$ 3499\n"
        "Cliente: retirar\n"
        "IA: Tironi, não trabalhamos com retirar...\n"
    )
    termos = _termos_do_cliente("qual o valor", hist)
    assert "retirar" not in termos
    assert "sei" not in termos

    ctx = montar_contexto_catalogo("qual o valor", hist)
    assert ctx["sem_match"] is False

    ctx2 = montar_contexto_catalogo("eu sei que não", hist + "Cliente: eu sei que não\n")
    assert ctx2["sem_match"] is False
    assert "retirar" not in (ctx2.get("termos_cliente") or [])
