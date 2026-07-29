"""Relevância da busca de produtos (Adaptador de Tomada etc.) — sem Supabase real."""

from __future__ import annotations

from services.vendas.catalogo import (
    _ranquear_produtos_por_consulta,
    montar_contexto_catalogo,
)


CATALOGO_ADAPTADOR = [
    {
        "nome": "Adaptador de Tomada Universal",
        "preco": 19.9,
        "saldo_estoque": 0,
        "categoria": "adaptadores",
    },
    {
        "nome": "Adaptador de Tomada Cubo",
        "preco": 29.9,
        "saldo_estoque": 8,
        "categoria": "adaptadores",
    },
    {
        "nome": "Pisca Pisca de Natal para Tomada",
        "preco": 39.9,
        "saldo_estoque": 2,
        "categoria": "decoracao",
    },
    {
        "nome": "Mochila Premium para Notebook",
        "preco": 199.9,
        "saldo_estoque": 5,
        "categoria": "mochilas",
    },
]


def test_adaptador_de_tomada_prioriza_frase_completa():
    ranked = _ranquear_produtos_por_consulta(
        CATALOGO_ADAPTADOR, "Adaptador de Tomada", limite=10
    )
    nomes = [p["nome"] for p in ranked]
    assert nomes[0] in (
        "Adaptador de Tomada Universal",
        "Adaptador de Tomada Cubo",
    )
    assert nomes[1] in (
        "Adaptador de Tomada Universal",
        "Adaptador de Tomada Cubo",
    )
    assert set(nomes[:2]) == {
        "Adaptador de Tomada Universal",
        "Adaptador de Tomada Cubo",
    }
    assert "Mochila Premium para Notebook" not in nomes
    # Pisca (só 'tomada') abaixo dos adaptadores ou excluído quando há match forte
    if "Pisca Pisca de Natal para Tomada" in nomes:
        assert nomes.index("Pisca Pisca de Natal para Tomada") > 1
    else:
        assert "Pisca Pisca de Natal para Tomada" not in nomes


def test_adaptador_estoque_positivo_antes_no_mesmo_nivel():
    ranked = _ranquear_produtos_por_consulta(
        CATALOGO_ADAPTADOR, "Adaptador de Tomada", limite=10
    )
    assert ranked[0]["nome"] == "Adaptador de Tomada Cubo"
    assert ranked[1]["nome"] == "Adaptador de Tomada Universal"


def test_mochila_nao_aparece_na_busca_adaptador():
    ranked = _ranquear_produtos_por_consulta(
        CATALOGO_ADAPTADOR, "Adaptador de Tomada", limite=20
    )
    assert all("mochila" not in p["nome"].lower() for p in ranked)


def test_pisca_excluido_quando_ha_adaptadores():
    ranked = _ranquear_produtos_por_consulta(
        CATALOGO_ADAPTADOR, "Adaptador de Tomada", limite=20
    )
    assert all("pisca" not in p["nome"].lower() for p in ranked)


def test_busca_sem_resultado_usa_fallback_amostra(monkeypatch):
    monkeypatch.setattr(
        "services.vendas.catalogo.buscar_produtos",
        lambda: list(CATALOGO_ADAPTADOR),
    )
    monkeypatch.setattr(
        "services.vendas.catalogo._usar_somente_supabase",
        lambda: True,
    )
    monkeypatch.setattr(
        "services.vendas.catalogo._amostra_produtos_reais",
        lambda limite=4: [
            {"nome": "Headset Gamer X", "preco": 99.0, "saldo_estoque": 1}
        ],
    )
    ctx = montar_contexto_catalogo("toalha de banho rosa", "")
    assert ctx["produtos"] == []
    assert ctx["sem_match"] is True
    assert ctx["amostra_disponivel"]
    assert "Headset" in (ctx["amostra_disponivel"][0].get("nome") or "")
    assert "Nenhum produto encontrado" in (ctx.get("catalogo") or "")


def test_contexto_adaptador_via_montar_contexto(monkeypatch):
    monkeypatch.setattr(
        "services.vendas.catalogo.buscar_produtos",
        lambda: list(CATALOGO_ADAPTADOR),
    )
    monkeypatch.setattr(
        "services.vendas.catalogo._usar_somente_supabase",
        lambda: True,
    )
    ctx = montar_contexto_catalogo("Adaptador de Tomada", "")
    nomes = [p["nome"] for p in ctx["produtos"]]
    assert set(nomes[:2]) == {
        "Adaptador de Tomada Universal",
        "Adaptador de Tomada Cubo",
    }
    assert ctx["produtos"][0]["nome"] == "Adaptador de Tomada Cubo"
    assert all("mochila" not in n.lower() for n in nomes)
    assert all("pisca" not in n.lower() for n in nomes)
    assert ctx["fonte"] == "supabase"
    assert ctx["sem_match"] is False
