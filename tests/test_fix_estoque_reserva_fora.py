"""Correções: estoque real, sem reserva inventada, fora de catálogo curto."""

import re

from services.intent_service import sanitizar_frases_comerciais
from services.product_service import (
    disponibilidade_texto,
    normalizar_produto_servico,
)
from services.vendas.respostas import (
    criterio_util_por_categoria,
    resposta_fora_catalogo,
    resposta_preco_em_discussao,
)


def test_stock_null_nao_disponibilidade_confirmada():
    n = normalizar_produto_servico({"nome": "Headset Gamer", "preco": 249.9})
    assert n["stock_quantity"] is None
    assert n["stock_confirmed"] is False
    txt = disponibilidade_texto(n)
    assert "disponibilidade confirmada" not in txt.lower()
    assert "verificar a disponibilidade" in txt.lower()
    sujo = "Temos o Headset Gamer por R$ 249,90, com disponibilidade confirmada."
    limpo = sanitizar_frases_comerciais(sujo, stock_confirmed=False)
    assert "disponibilidade confirmada" not in limpo.lower()
    assert "verificar a disponibilidade" in limpo.lower()


def test_stock_confirmed_false_nao_em_estoque():
    n = normalizar_produto_servico({"nome": "Headset", "preco": 100, "estoque": None})
    assert n["stock_confirmed"] is False
    limpo = sanitizar_frases_comerciais(
        "O Headset está em estoque agora.", stock_confirmed=False
    )
    assert "em estoque" not in limpo.lower()


def test_stock_zero_nao_disponivel():
    n = normalizar_produto_servico({"nome": "Headset", "preco": 100, "estoque": 0})
    assert n["stock_quantity"] == 0
    assert n["stock_confirmed"] is False
    limpo = sanitizar_frases_comerciais(
        "Headset disponível para envio.", stock_confirmed=False
    )
    assert "disponível para envio" not in limpo.lower()
    assert "disponivel para envio" not in limpo.lower()
    assert re.search(r"\bdispon[ií]vel\b", limpo.lower()) is None


def test_stock_positivo_confirmado_pode_informar():
    n = normalizar_produto_servico({"nome": "Headset", "preco": 100, "estoque": 7})
    assert n["stock_confirmed"] is True
    assert n["stock_quantity"] == 7
    txt = disponibilidade_texto(n)
    assert "7" in txt
    ok = sanitizar_frases_comerciais(
        "Temos 7 unidades no catálogo.", stock_confirmed=True
    )
    assert "7" in ok


def test_preco_nao_diz_posso_separar():
    hist = "Cliente: quero headset\nIA: Headset Gamer por R$ 249.9\n"
    resp = resposta_preco_em_discussao(
        hist,
        "Arthur",
        [{"nome": "Headset Gamer", "preco": 249.9}],
    )
    assert resp
    assert "separar" not in resp.lower()
    assert "reservar" not in resp.lower()
    assert "seguir com a compra" in resp.lower() or "próximo passo" in resp.lower()


def test_preco_pode_seguir_com_compra():
    limpo = sanitizar_frases_comerciais(
        "Headset — R$ 249,90. Posso separar 1 pra você?",
        stock_confirmed=False,
    )
    assert "separar" not in limpo.lower()
    assert "seguir com a compra" in limpo.lower()


def test_inexistente_nao_lista_hd_e_headset():
    texto = resposta_fora_catalogo(
        "Arthur",
        ["toalha", "vermelha"],
        amostra=[
            {"nome": "HD Externo 1 TB"},
            {"nome": "Headset Gamer"},
        ],
    )
    assert "HD Externo" not in texto
    assert "Headset Gamer" not in texto
    assert "entre outros" not in texto.lower()


def test_inexistente_redireciona_curto():
    texto = resposta_fora_catalogo("Arthur", ["toalha", "vermelha"], amostra=[])
    assert "não encontrei" in texto.lower() or "nao encontrei" in texto.lower()
    assert "toalha" in texto.lower()
    assert texto.count("?") <= 1
    assert (
        "informática" in texto.lower()
        or "periféricos" in texto.lower()
        or "armazenamento" in texto.lower()
    )


def test_no_maximo_uma_pergunta_simples():
    pergunta = criterio_util_por_categoria(
        "headset",
        [
            {"nome": "Headset Gamer", "preco": 100, "descricao": "gamer jogos microfone"},
            {"nome": "Headset Office", "preco": 80, "descricao": "chamadas trabalho"},
        ],
    ) or ""
    assert pergunta.count("?") <= 1
    assert not (
        "jogos" in pergunta.lower()
        and "trabalho" in pergunta.lower()
        and "chamadas" in pergunta.lower()
    )
