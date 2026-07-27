"""Regressão: continuidade produto → retirada → Pix (MP_PIX_ENABLED=false)."""

from __future__ import annotations

from copy import deepcopy

from services.checkout_service import avaliar_checkout
from services.vendas.memoria import atualizar_sessao_turno, sessao_vazia


NOTEBOOK = {
    "id": "nb-i5-001",
    "mercos_id": "20405000",
    "name": "Notebook Intel i5",
    "nome": "Notebook Intel i5",
    "price": 3499.9,
    "preco": 3499.9,
    "stock_quantity": 89,
    "estoque": 89,
    "stock_confirmed": True,
    "codigo": "NB-I5",
    "source": "supabase",
    "categoria": "notebook",
}


def test_fluxo_multiturno_retirada_mantem_produto_e_bloqueia_pix(monkeypatch):
    """Catálogo → compra → retirada → Pix bloqueado por MP_PIX_ENABLED=false."""
    monkeypatch.setenv("MP_PIX_ENABLED", "false")
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    monkeypatch.setenv("MP_ACCESS_TOKEN", "TEST-fake-token-not-real")

    # 1–2: busca/apresentação do notebook com estoque
    sessao = atualizar_sessao_turno(
        sessao_vazia(),
        historico_texto="Cliente: notebook até 4000\nAssistente: Notebook Intel i5",
        mensagem="quero um notebook até 4000",
        produtos=[NOTEBOOK],
    )
    assert sessao["produto_ativo"] == "Notebook Intel i5"
    assert sessao["produto_id"] == "nb-i5-001"
    assert sessao["estoque_saldo"] == 89
    assert sessao["stock_confirmed"] is True
    assert float(sessao["preco_cotado"]) == 3499.9

    # 3: cliente confirma 1 unidade e autoriza Pix
    r1 = avaliar_checkout(
        mensagem=(
            "Quero comprar 1 unidade do Notebook Intel i5 de R$ 3.499,90. "
            "Confirmo a compra e autorizo gerar o Pix agora."
        ),
        sessao=deepcopy(sessao),
        produtos=[],  # fechamento não reconsulta catálogo no turno
        intent="COMPRA",
        dry_run=False,
        persistir=True,
    )
    assert r1["reason"] == "pix_aguarda_entrega"
    assert "retirada" in r1["reply"].lower() or "entrega" in r1["reply"].lower()
    assert r1["product"]["name"] == "Notebook Intel i5"
    assert r1["sessao"].get("quantidade") == 1
    assert r1["sessao"].get("stock_confirmed") is True
    sessao = r1["sessao"]

    # Revalidação no turno da retirada (produtos=[]): catalogo mockado
    revalidacoes = {"n": 0}

    def fake_busca(nome, historico_texto=""):
        revalidacoes["n"] += 1
        assert "notebook intel i5" in (nome or "").lower()
        return {"found": True, "products": [NOTEBOOK], "fonte": "supabase"}

    monkeypatch.setattr(
        "services.product_service.buscar_produto_por_nome",
        fake_busca,
    )

    http_calls = {"n": 0}
    monkeypatch.setattr(
        "services.mercadopago_service.requests.post",
        lambda *_a, **_k: http_calls.__setitem__("n", http_calls["n"] + 1),
    )
    monkeypatch.setattr(
        "services.mercadopago_service.requests.get",
        lambda *_a, **_k: http_calls.__setitem__("n", http_calls["n"] + 1),
    )
    upserts = {"n": 0}
    monkeypatch.setattr(
        "services.pagamento_pix_service._upsert_pagamento",
        lambda *_a, **_k: upserts.__setitem__("n", upserts["n"] + 1) or True,
    )

    # 5–9: retirada + confirmação → chega na tool Pix → trava
    r2 = avaliar_checkout(
        mensagem=(
            "Prefiro retirada. Confirmo o pedido de 1 Notebook Intel i5 "
            "por R$ 3.499,90 e autorizo gerar o Pix agora."
        ),
        sessao=deepcopy(sessao),
        produtos=[],  # não pode apagar o produto selecionado
        intent="COMPRA",
        dry_run=False,
        persistir=True,
    )

    assert r2["sessao"].get("forma_entrega") == "retirada"
    assert r2["product"]["name"] == "Notebook Intel i5"
    assert r2["product"].get("stock_confirmed") is True
    assert float(r2["product"].get("stock_quantity") or 0) == 89
    assert float(r2["product"].get("price") or 0) == 3499.9
    assert r2["reason"] == "pix_temporariamente_indisponivel"
    assert "indisponível" in r2["reply"].lower() or "indisponivel" in r2["reply"].lower()
    assert "verificar a disponibilidade" not in r2["reply"].lower()
    assert r2.get("pix", {}).get("error") == "pix_temporariamente_indisponivel"
    assert http_calls["n"] == 0
    assert upserts["n"] == 0
    assert revalidacoes["n"] >= 1


def test_retirada_sozinha_nao_apaga_produto_da_sessao():
    sessao = {
        "produto_ativo": "Notebook Intel i5",
        "produto_checkout": "Notebook Intel i5",
        "produto_id": "nb-i5-001",
        "preco_cotado": 3499.9,
        "estoque_saldo": 89,
        "stock_confirmed": True,
        "quantidade": 1,
        "forma_pagamento": "PIX",
    }
    r = avaliar_checkout(
        mensagem="Prefiro retirada",
        sessao=sessao,
        produtos=[],
        intent="ENTREGA",
    )
    assert r["sessao"]["produto_ativo"] == "Notebook Intel i5"
    assert r["sessao"]["forma_entrega"] == "retirada"
    assert r["sessao"]["stock_confirmed"] is True
    assert r["reason"] != "estoque_nao_confirmado"
