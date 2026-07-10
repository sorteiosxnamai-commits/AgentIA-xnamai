"""Etapa 5 — fluxo seguro de checkout / fechamento."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import routes.api as api_mod
from services.checkout_service import (
    avaliar_checkout,
    checkout_criar_pedido_habilitado,
    criar_pedido_se_permitido,
    processar_checkout_turno,
    sanitizar_claims_checkout,
)
from services.vendas.memoria import SESSAO_PADRAO


def _prod(nome="Headset Gamer", preco=249.9, estoque=5, confirmed=True):
    return {
        "id": "1",
        "name": nome,
        "nome": nome,
        "price": preco,
        "preco": preco,
        "stock_quantity": estoque,
        "stock_confirmed": confirmed and estoque is not None and estoque > 0,
        "estoque": estoque,
    }


# 1
def test_quero_comprar_com_produto_ativo():
    r = avaliar_checkout(
        mensagem="quero comprar",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 249.9},
        produtos=[_prod()],
        intent="COMPRA",
        nome_cliente="Arthur",
    )
    assert r["product"]["name"]
    assert "forma_entrega" in r["missing_fields"]
    assert "retirar" in r["reply"].lower() or "entrega" in r["reply"].lower()
    assert r["reply"].count("?") <= 1


# 2
def test_quero_comprar_sem_produto_ativo():
    r = avaliar_checkout(
        mensagem="quero comprar",
        sessao={},
        produtos=[],
        intent="COMPRA",
        nome_cliente="Arthur",
    )
    assert "produto" in r["missing_fields"]
    assert "qual produto" in r["reply"].lower()
    assert r["can_create_order"] is False


# 3
def test_pix_sem_produto_ativo():
    r = avaliar_checkout(
        mensagem="me manda o pix",
        sessao={},
        produtos=[],
        intent="PAGAMENTO",
    )
    assert r["reason"] == "pix_sem_produto"
    assert "qual produto" in r["reply"].lower()
    assert "pix gerado" not in r["reply"].lower()


# 4
def test_pix_com_produto_ativo():
    r = avaliar_checkout(
        mensagem="me manda o pix",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 249.9},
        produtos=[_prod()],
        intent="PAGAMENTO",
    )
    assert r["reason"] == "pix_aguarda_entrega"
    assert "entrega" in r["reply"].lower() or "retirada" in r["reply"].lower()
    assert "pix gerado" not in r["reply"].lower()


# 5
def test_produto_ativo_com_preco_real():
    r = avaliar_checkout(
        mensagem="quero comprar",
        sessao={},
        produtos=[_prod(preco=249.9)],
        intent="COMPRA",
        nome_cliente="Arthur",
    )
    assert r["product"]["price"] == 249.9
    assert "249" in r["reply"] or "249" in (r["summary"] or "")


# 6
def test_produto_ativo_sem_preco():
    r = avaliar_checkout(
        mensagem="quero comprar",
        sessao={"produto_ativo": "Headset Gamer"},
        produtos=[{"name": "Headset Gamer", "price": None, "stock_confirmed": True, "stock_quantity": 3}],
        intent="COMPRA",
    )
    assert "preco" in r["missing_fields"]
    assert r["can_create_order"] is False


# 7
def test_produto_estoque_confirmado():
    r = avaliar_checkout(
        mensagem="quero comprar",
        sessao={},
        produtos=[_prod(estoque=7, confirmed=True)],
        intent="COMPRA",
    )
    assert r["product"]["stock_confirmed"] is True
    assert r["product"]["stock_quantity"] == 7


# 8
def test_produto_estoque_nao_confirmado():
    prod = {
        "name": "Headset Gamer",
        "price": 249.9,
        "stock_quantity": None,
        "stock_confirmed": False,
    }
    # Com dados completos exceto estoque → avisa verificação
    r = avaliar_checkout(
        mensagem="ok",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "forma_entrega": "retirada",
            "quantidade": 1,
            "forma_pagamento": "PIX",
        },
        produtos=[prod],
        intent="COMPRA",
    )
    assert r["reason"] == "estoque_nao_confirmado"
    assert "verificar" in r["reply"].lower() and "disponibilidade" in r["reply"].lower()
    assert r["can_create_order"] is False


# 9
def test_produto_estoque_zero():
    r = avaliar_checkout(
        mensagem="quero comprar",
        sessao={},
        produtos=[_prod(estoque=0, confirmed=False)],
        intent="COMPRA",
    )
    assert r["reason"] == "estoque_zero"
    assert "alternativa" in r["reply"].lower() or "disponibilidade" in r["reply"].lower()


# 10
def test_cliente_escolhe_entrega():
    r = avaliar_checkout(
        mensagem="prefiro entrega",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 249.9},
        produtos=[_prod()],
        intent="ENTREGA",
    )
    assert r["sessao"].get("forma_entrega") == "entrega"
    assert "cidade" in r["missing_fields"] or "endereco" in r["missing_fields"]


# 11
def test_cliente_escolhe_retirada():
    r = avaliar_checkout(
        mensagem="vou retirar",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 249.9},
        produtos=[_prod()],
        intent="ENTREGA",
    )
    assert r["sessao"].get("forma_entrega") == "retirada"


# 12
def test_cliente_informa_quantidade():
    r = avaliar_checkout(
        mensagem="quero 2 unidades",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "forma_entrega": "retirada",
        },
        produtos=[_prod()],
        intent="COMPRA",
    )
    assert r["sessao"].get("quantidade") == 2


# 13
def test_cliente_informa_cidade():
    r = avaliar_checkout(
        mensagem="sou de Curitiba",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "forma_entrega": "entrega",
            "quantidade": 1,
        },
        produtos=[_prod()],
        intent="ENTREGA",
    )
    assert "curitiba" in (r["sessao"].get("cidade") or "").lower()


# 14
def test_cliente_informa_endereco():
    r = avaliar_checkout(
        mensagem="Rua das Flores 123",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "forma_entrega": "entrega",
            "cidade": "Curitiba",
            "quantidade": 1,
        },
        produtos=[_prod()],
        intent="ENTREGA",
    )
    assert r["sessao"].get("endereco")


# 15
def test_nao_repergunta_dado_ja_informado():
    r1 = avaliar_checkout(
        mensagem="retirada",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 249.9},
        produtos=[_prod()],
        intent="COMPRA",
    )
    assert r1["sessao"].get("forma_entrega") == "retirada"
    r2 = avaliar_checkout(
        mensagem="quero finalizar",
        sessao=r1["sessao"],
        produtos=[_prod()],
        intent="COMPRA",
    )
    assert "forma_entrega" not in r2["missing_fields"]
    assert "retirar ou receber" not in r2["reply"].lower()


# 16
def test_dry_run_nao_cria_pedido_real(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "true")
    base = avaliar_checkout(
        mensagem="ok",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "forma_entrega": "retirada",
            "quantidade": 1,
            "forma_pagamento": "PIX",
        },
        produtos=[_prod()],
        intent="COMPRA",
        dry_run=True,
        persistir=True,
    )
    assert base["ready"] is True
    assert base["can_create_order"] is False
    with patch(
        "services.pedido_mercos_service.criar_pedido_fechamento_mercos"
    ) as mock_m:
        out = criar_pedido_se_permitido(
            resultado={**base, "can_create_order": True},
            historico_texto="Cliente: quero\n",
            cliente_supabase={"id": "1"},
            telefone="5511999999999",
            dry_run=True,
            persistir=True,
        )
        mock_m.assert_not_called()
        assert out.get("pedido") is None
        assert "pedido criado" not in (out.get("reply") or "").lower()


# 17
def test_persistir_false_nao_cria_pedido(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "true")
    base = avaliar_checkout(
        mensagem="ok",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "forma_entrega": "retirada",
            "quantidade": 1,
            "forma_pagamento": "PIX",
        },
        produtos=[_prod()],
        intent="COMPRA",
        dry_run=False,
        persistir=False,
    )
    assert base["can_create_order"] is False
    with patch(
        "services.pedido_pulsedesk_service.registrar_venda_pulsedesk"
    ) as mock_p:
        out = criar_pedido_se_permitido(
            resultado={**base, "can_create_order": True},
            historico_texto="",
            cliente_supabase={"id": "1"},
            telefone="5511999999999",
            dry_run=False,
            persistir=False,
        )
        mock_p.assert_not_called()
        assert out.get("pedido") is None


# 18
def test_mercos_so_com_dados_e_flag(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "true")
    incompleto = avaliar_checkout(
        mensagem="quero comprar",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 249.9},
        produtos=[_prod()],
        intent="COMPRA",
        dry_run=False,
        persistir=True,
    )
    assert incompleto["can_create_order"] is False

    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    completo = avaliar_checkout(
        mensagem="ok",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "forma_entrega": "retirada",
            "quantidade": 1,
            "forma_pagamento": "PIX",
        },
        produtos=[_prod()],
        intent="COMPRA",
        dry_run=False,
        persistir=True,
    )
    # Flag create=false → não cria mesmo pronto
    assert completo["ready"] is True
    assert completo["can_create_order"] is False


# 19
def test_pulsedesk_so_se_configurado(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "true")
    monkeypatch.setenv("PULSEDESK_PEDIDOS_ENABLED", "false")
    monkeypatch.setenv("MERCOS_CRIAR_PEDIDO", "false")
    with patch("services.mercos_service.mercos_configurado", return_value=False):
        r = avaliar_checkout(
            mensagem="ok",
            sessao={
                "produto_ativo": "Headset Gamer",
                "preco_cotado": 249.9,
                "forma_entrega": "retirada",
                "quantidade": 1,
                "forma_pagamento": "PIX",
            },
            produtos=[_prod()],
            intent="COMPRA",
            dry_run=False,
            persistir=True,
        )
    assert r["ready"] is True
    assert r["can_create_order"] is False
    assert r["needs_human"] is True


# 20
def test_pedido_humano_sem_integracao(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "true")
    with patch("services.mercos_service.mercos_configurado", return_value=False):
        with patch(
            "services.pedido_pulsedesk_service.pulsedesk_pedidos_habilitado",
            return_value=False,
        ):
            with patch(
                "services.pedido_mercos_service.mercos_criar_pedido_habilitado",
                return_value=False,
            ):
                r = avaliar_checkout(
                    mensagem="ok",
                    sessao={
                        "produto_ativo": "Headset Gamer",
                        "preco_cotado": 249.9,
                        "forma_entrega": "retirada",
                        "quantidade": 1,
                        "forma_pagamento": "PIX",
                    },
                    produtos=[_prod()],
                    intent="COMPRA",
                    dry_run=False,
                    persistir=True,
                )
    assert r["needs_human"] is True
    assert "time" in r["reply"].lower() or "encaminhar" in r["reply"].lower()


# 21
def test_nao_usa_posso_separar():
    r = avaliar_checkout(
        mensagem="quero comprar",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 249.9},
        produtos=[_prod()],
        intent="COMPRA",
        nome_cliente="Arthur",
    )
    assert "separar" not in r["reply"].lower()
    assert "reservar" not in r["reply"].lower()


# 22
def test_nao_diz_pedido_criado_sem_pedido():
    texto = sanitizar_claims_checkout(
        "Pedido criado com sucesso! Segue o resumo.",
        pedido_criado=False,
    )
    assert "pedido criado" not in texto.lower()


# 23
def test_nao_diz_pix_gerado_sem_pix():
    texto = sanitizar_claims_checkout(
        "Pix gerado, segue o código.",
        pix_gerado=False,
    )
    assert "pix gerado" not in texto.lower()


# 24
def test_no_maximo_uma_pergunta_principal():
    r = avaliar_checkout(
        mensagem="quero comprar",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 249.9},
        produtos=[_prod()],
        intent="COMPRA",
        nome_cliente="Arthur",
    )
    assert r["reply"].count("?") <= 1


# 25
def test_chat_continua_funcionando():
    sig = inspect.signature(api_mod.processar_mensagem)
    assert "dry_run" in sig.parameters
    assert "persistir" in sig.parameters
    assert api_mod.CODE_VERSION == "2026-07-10-fix-schema-persistencia"


# 26
def test_webhook_continua_funcionando():
    assert hasattr(api_mod, "receber_webhook")
    assert hasattr(api_mod, "webhook")


def test_sessao_tem_campos_checkout():
    for campo in (
        "checkout_status",
        "produto_checkout",
        "quantidade",
        "forma_entrega",
        "cidade",
        "endereco",
        "forma_pagamento",
        "pedido_id",
        "checkout_resumo",
    ):
        assert campo in SESSAO_PADRAO


def test_processar_checkout_turno_handled():
    out = processar_checkout_turno(
        mensagem="quero comprar",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 100},
        produtos=[_prod(preco=100)],
        intent="COMPRA",
        nome_cliente="Arthur",
        dry_run=True,
        persistir=False,
    )
    assert out.get("handled") is True
    assert out.get("reply")
