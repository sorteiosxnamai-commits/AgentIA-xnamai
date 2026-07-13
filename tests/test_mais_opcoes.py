from services.vendas.catalogo import montar_contexto_catalogo
from services.vendas.respostas import (
    cliente_pediu_mais_opcoes,
    resposta_fora_catalogo,
    resposta_mais_opcoes,
)
from services.xnamai_script import mensagem_nao_e_busca_produto


def test_tem_mais_opcoes_nao_e_fora_catalogo():
    msg = "tem mais opções de produtos?"
    assert cliente_pediu_mais_opcoes(msg) is True
    assert mensagem_nao_e_busca_produto(msg) is True
    ctx = montar_contexto_catalogo(msg, "")
    assert ctx.get("sem_match") is False


def test_resposta_mais_opcoes_sem_categoria():
    texto = resposta_mais_opcoes("Arthur", "", [])
    assert "Temos sim" in texto
    assert "tipo de produto" in texto.lower()
    assert "não trabalhamos" not in texto.lower()


def test_resposta_mais_opcoes_com_categoria():
    hist = "Cliente: quero headset\nIA: Headset Gamer — R$ 89,90\n"
    texto = resposta_mais_opcoes(
        "Arthur",
        hist,
        [
            {"nome": "Headset Gamer RGB", "preco": 89.9},
            {"nome": "Headset Bluetooth", "preco": 59.9},
        ],
    )
    assert "Temos sim" in texto
    assert "não trabalhamos" not in texto.lower()


def test_fora_catalogo_sem_termo_nao_inventa_frase():
    texto = resposta_fora_catalogo("Arthur", ["opcoes", "produtos"], [])
    assert "não trabalhamos com opções" not in texto.lower()
    assert "não encontrei opcoes" not in texto.lower()
    assert "nao encontrei opcoes" not in texto.lower()
    assert "HD Externo" not in texto
    assert "categoria" in texto.lower() or "catálogo" in texto.lower() or "catalogo" in texto.lower()
    assert texto.count("?") <= 2
