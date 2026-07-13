"""Formatação e mojibake seguros na resposta de catálogo."""

from __future__ import annotations

import routes.api as api_mod
from services.texto_seguro import (
    garantir_espacos_whatsapp,
    parece_mojibake,
    reparar_mojibake,
    texto_para_exibicao,
)
from services.vendas.respostas import resposta_mostrar_catalogo


PRODUTOS = [
    {"nome": "HD Externo 1 TB", "preco": 429.9, "saldo_estoque": 33},
    {"nome": "Headset Gamer", "preco": 249.9, "saldo_estoque": 50},
    {"nome": "Hub USB 4 Portas", "preco": 69.9, "saldo_estoque": 29},
    {"nome": "Mouse Óptico", "preco": 39.9, "saldo_estoque": 10},
]


def test_code_version_formatacao():
    assert api_mod.CODE_VERSION == "2026-07-13-fix-espaco-unidades"


def test_catalogo_sem_palavras_coladas():
    texto = resposta_mostrar_catalogo("Tironi", PRODUTOS)
    for ruim in (
        "algumasopções",
        "algumasopcoes",
        "parauso",
        ")(",
        "catÃ",
        "VocÃ",
        "opÃ",
    ):
        assert ruim not in texto, f"encontrou {ruim!r} em {texto!r}"
    assert "algumas opções" in texto
    assert "para uso pessoal" in texto
    assert ") (" in texto or "(temos" in texto
    # Preço e estoque com espaço entre parênteses
    assert "(R$ 69,90) (temos 29 unidades)" in texto


def test_garantir_espacos_corrige_colagem():
    sujo = (
        "Posso te mostrar algumasopções do nosso catálogo. "
        "Hub (R$ 69,90)(temos 29 unidades). Você procura algo parauso pessoal?"
    )
    limpo = garantir_espacos_whatsapp(sujo)
    assert "algumasopções" not in limpo
    assert "parauso" not in limpo
    assert ")(" not in limpo
    assert "algumas opções" in limpo
    assert "para uso pessoal" in limpo
    assert ") (" in limpo


def test_mojibake_repara_entrada_sem_alterar_correto():
    ok = "mande o catálogo por favor"
    assert reparar_mojibake(ok) == ok
    assert not parece_mojibake(ok)

    quebrado = "mande o catÃ¡logo"
    fix = reparar_mojibake(quebrado)
    assert "catálogo" in fix
    assert "catÃ" not in fix

    voce = "VocÃª procura"
    assert "Você" in reparar_mojibake(voce)


def test_nome_produto_mojibake_so_na_exibicao():
    # UTF-8 "Óptico" lido como Latin-1 vira "Ã³ptico"
    nome_quebrado = "Mouse Ã³ptico"
    assert parece_mojibake(nome_quebrado)
    exib = texto_para_exibicao(nome_quebrado)
    assert "Óptico" in exib or "Óptico".casefold() in exib.casefold()
    assert "Ã³" not in exib
    assert "catÃ" not in exib

    # Produto no "banco" permanece intacto; só a string de exibição muda
    produto = {"nome": nome_quebrado, "preco": 39.9}
    texto = resposta_mostrar_catalogo("Tironi", [produto])
    assert "Ã³" not in texto
    assert produto["nome"] == nome_quebrado


def test_stock_confirmed_false_nao_inventa_estoque():
    produtos = [
        {
            "nome": "Headset",
            "preco": 100,
            "stock_confirmed": False,
            "stock_quantity": 50,
            "saldo_estoque": 50,
        }
    ]
    texto = resposta_mostrar_catalogo("Tironi", produtos)
    assert "temos 50" not in texto.lower()
    assert "disponibilidade eu confirmo" in texto.lower()
