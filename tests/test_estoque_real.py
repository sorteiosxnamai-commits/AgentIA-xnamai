"""Disponibilidade só com estoque real do catálogo."""

from services.intent_service import sanitizar_frases_comerciais
from services.mercos_service import (
    estoque_confirmado,
    montar_catalogo_texto,
)


def test_catalogo_sem_estoque_nao_diz_disponivel():
    texto = montar_catalogo_texto(
        [{"nome": "Headset Gamer", "preco": 249.9, "estoque": None}]
    )
    assert "disponível" not in texto.lower()
    assert "verificar disponibilidade" in texto.lower() or "não confirmado" in texto.lower()


def test_catalogo_estoque_zero_nao_afirma_disponivel():
    texto = montar_catalogo_texto(
        [{"nome": "Headset Gamer", "preco": 249.9, "estoque": 0}]
    )
    assert "disponível" not in texto.lower()
    assert "0" in texto


def test_catalogo_com_estoque_real_mostra_quantidade():
    texto = montar_catalogo_texto(
        [{"nome": "Headset Gamer", "preco": 249.9, "saldo_estoque": 12}]
    )
    assert "12" in texto
    assert estoque_confirmado({"saldo_estoque": 12}) is True
    assert estoque_confirmado({"estoque": 0}) is False
    assert estoque_confirmado({}) is False


def test_sanitiza_disponivel_para_envio():
    sujo = "Headset Gamer por R$ 249,90, disponível para envio."
    limpo = sanitizar_frases_comerciais(sujo)
    assert "disponível para envio" not in limpo.lower()
    assert "verificar a disponibilidade" in limpo.lower()


def test_frases_ruins_continuam_bloqueadas():
    sujo = (
        "A princípio temos em estoque (sujeito à separação). "
        "Aqui no chat não tenho foto."
    )
    limpo = sanitizar_frases_comerciais(sujo).lower()
    assert "a princípio temos em estoque" not in limpo
    assert "sujeito à separação" not in limpo
    assert "aqui no chat não tenho foto" not in limpo
