"""Fix: pedido de catálogo geral não vira busca de produto inexistente."""

from __future__ import annotations

from services.intent_service import classificar_intencao
from services.product_service import listar_produtos_catalogo, buscar_por_intencao
from services.vendas.catalogo import montar_contexto_catalogo
from services.vendas.respostas import (
    cliente_quer_ver_catalogo,
    query_apenas_generica,
    resposta_fora_catalogo,
    resposta_mostrar_catalogo,
)
from services.xnamai_script import (
    cliente_perguntou_estoque,
    mensagem_nao_e_busca_produto,
    resposta_estoque_disponibilidade,
)
import routes.api as api_mod


PRODUTOS_FAKE = [
    {"nome": "Headset Gamer X1", "preco": 149.9, "estoque": None},
    {"nome": "Mouse RGB Pro", "preco": 89.9, "saldo_estoque": 3},
    {"nome": "Cabo HDMI 2m", "preco": 29.9},
]


def test_code_version_catalogo_geral():
    assert api_mod.CODE_VERSION == "2026-07-13-fix-catalogo-geral"


def test_mande_catalogo_e_catalogo_geral():
    msg = "mande o catálogo"
    assert cliente_quer_ver_catalogo(msg) is True
    assert query_apenas_generica(msg) is True
    intent = classificar_intencao(msg)
    assert intent["intent"] == "CATALOGO_GERAL"
    assert intent["product_query"] == ""
    ctx = montar_contexto_catalogo(msg, "")
    assert ctx.get("sem_match") is False
    texto = resposta_fora_catalogo("Tironi", ["mande", "catalogo"], [])
    assert "não encontrei mande" not in texto.lower()
    assert "nao encontrei mande" not in texto.lower()
    assert "catálogo" in texto.lower() or "categoria" in texto.lower()


def test_quais_produtos_disponivel_nao_pede_produto():
    msg = "quais produtos tem disponível?"
    assert cliente_quer_ver_catalogo(msg) is True
    assert cliente_perguntou_estoque(msg) is False
    intent = classificar_intencao(msg)
    assert intent["intent"] == "CATALOGO_GERAL"
    estoque = resposta_estoque_disponibilidade("Tironi")
    catalogo = resposta_mostrar_catalogo("Tironi", PRODUTOS_FAKE)
    assert "Me diga o produto" not in catalogo
    assert catalogo != estoque
    assert "opções do nosso catálogo" in catalogo or "produtos como" in catalogo


def test_o_que_voces_vendem():
    msg = "o que vocês vendem?"
    assert cliente_quer_ver_catalogo(msg) is True
    assert classificar_intencao(msg)["intent"] == "CATALOGO_GERAL"
    texto = resposta_mostrar_catalogo("Tironi", PRODUTOS_FAKE)
    assert "Headset" in texto or "Mouse" in texto or "Cabo" in texto


def test_me_passa_as_opcoes():
    msg = "me passa as opções"
    assert cliente_quer_ver_catalogo(msg) is True
    assert classificar_intencao(msg)["intent"] == "CATALOGO_GERAL"
    assert mensagem_nao_e_busca_produto(msg) is True
    ctx = montar_contexto_catalogo(msg, "")
    assert ctx.get("sem_match") is False


def test_quais_opcoes_voces_tem_e_catalogo():
    msg = "quais opções vocês têm?"
    assert cliente_quer_ver_catalogo(msg) is True
    assert classificar_intencao(msg)["intent"] == "CATALOGO_GERAL"
    assert cliente_perguntou_estoque(msg) is False
    texto = resposta_mostrar_catalogo("Tironi", PRODUTOS_FAKE)
    assert "produtos como" in texto or "opções do nosso catálogo" in texto
    assert "Me diga o produto" not in texto


def test_toalha_continua_produto_especifico():
    msg = "tem toalha vermelha?"
    assert cliente_quer_ver_catalogo(msg) is False
    assert classificar_intencao(msg)["intent"] != "CATALOGO_GERAL"
    texto = resposta_fora_catalogo("Tironi", ["toalha"], [])
    assert "não encontrei toalha" in texto.lower() or "nao encontrei toalha" in texto.lower()


def test_headset_gamer_continua_busca():
    msg = "quero um headset gamer"
    assert cliente_quer_ver_catalogo(msg) is False
    intent = classificar_intencao(msg)
    assert intent["intent"] == "BUSCA_PRODUTO"
    assert "headset" in (intent.get("product_query") or msg).lower()


def test_resposta_catalogo_vazio_inteligente():
    texto = resposta_mostrar_catalogo("Tironi", [])
    assert "não encontrei mande" not in texto.lower()
    assert "categoria" in texto.lower()
    assert "informática" in texto.lower() or "informatica" in texto.lower()


def test_resposta_catalogo_sem_estoque_confirmado():
    texto = resposta_mostrar_catalogo("Tironi", PRODUTOS_FAKE[:1])
    assert "disponibilidade eu confirmo" in texto.lower()
    assert "temos 0" not in texto.lower()


def test_resposta_catalogo_com_estoque_confirmado():
    texto = resposta_mostrar_catalogo("Tironi", [PRODUTOS_FAKE[1]])
    assert "temos 3 unidades" in texto.lower()
    assert "R$" in texto or "89" in texto


def test_listar_produtos_catalogo_reusa_geral(monkeypatch):
    from services import product_service as ps

    monkeypatch.setattr(
        "services.vendas.catalogo.montar_catalogo_geral",
        lambda limite=20: {
            "produtos": PRODUTOS_FAKE[:limite],
            "catalogo": "fake",
            "fonte": "supabase",
        },
    )
    out = listar_produtos_catalogo(limit=2)
    assert out["found"] is True
    assert len(out["products"]) <= 2

    out2 = buscar_por_intencao(
        mensagem="mande o catálogo",
        intent="CATALOGO_GERAL",
        product_query="",
    )
    assert out2["found"] is True
    assert "não encontrei" not in (out2.get("message") or "").lower()


def test_query_generica_nao_vira_inexistente(monkeypatch):
    monkeypatch.setattr(
        "services.vendas.catalogo.montar_catalogo_geral",
        lambda limite=20: {
            "produtos": PRODUTOS_FAKE,
            "catalogo": "fake",
            "fonte": "supabase",
        },
    )
    out = buscar_por_intencao(
        mensagem="mande o catálogo por favor",
        intent="BUSCA_PRODUTO",
        product_query="mande o catálogo por favor",
    )
    assert out["found"] is True
    assert out["products"]
