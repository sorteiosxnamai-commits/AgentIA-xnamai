"""Fix: persistência resiliente no /chat com persistir=true."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import routes.api as api_mod
from services.checkout_service import avaliar_checkout, criar_pedido_se_permitido
from services.vendas.memoria import (
    carregar_sessao,
    persistir_sessao,
    serializar_contexto_venda,
    sessao_vazia,
)
from services.webhook_guard import lock_telefone


def _ctx_mock(**kwargs):
    base = dict(
        produtos=[],
        catalogo="",
        sem_match=False,
        termos_cliente=[],
        amostra_disponivel=[],
        estagio="atencao",
        fonte="teste",
        erro_mercos=None,
        briefing="",
        memoria={},
    )
    base.update(kwargs)
    return MagicMock(**base)


def _data(msg="quero comprar o headset gamer", tel="5543999000999", mid=None):
    return {
        "event_type": "message_received",
        "provider": "chat_teste",
        "data": {
            "from": tel,
            "body": msg,
            "pushname": "Arthur",
            "fromMe": False,
            "type": "chat",
            "id": mid or f"chat-test-{abs(hash(msg + tel)) % 10_000_000}",
            "time": __import__("time").time(),
        },
    }


def _patch_fluxo_basico(monkeypatch, *, produtos=None):
    produtos = produtos or [
        {
            "id": "1",
            "name": "Headset Gamer",
            "nome": "Headset Gamer",
            "price": 249.9,
            "preco": 249.9,
            "stock_quantity": 5,
            "stock_confirmed": True,
        }
    ]
    monkeypatch.setattr(api_mod, "buscar_cliente", lambda *_a, **_k: {
        "id": "cli-1",
        "telefone": "5543999000999",
        "nome": "Arthur",
        "contexto_venda": {
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
        },
    })
    monkeypatch.setattr(api_mod, "criar_cliente", lambda *_a, **_k: {"id": "cli-1"})
    monkeypatch.setattr(api_mod, "atualizar_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "buscar_historico", lambda *_a, **_k: [])
    monkeypatch.setattr(api_mod, "espelhar_mensagem_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "espelhar_mensagem_agente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "atualizar_thread_conversa", lambda *_a, **_k: True)
    monkeypatch.setattr(api_mod, "enviar_mensagem", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(
        api_mod,
        "processar_lead_e_notificar",
        lambda **_k: {"notificado": False},
    )
    monkeypatch.setattr(api_mod, "resolver_estado_venda", lambda *_a, **_k: "negociando")
    monkeypatch.setattr(api_mod, "eh_saudacao", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "extrair_nome_do_historico", lambda *_a, **_k: "Arthur")
    monkeypatch.setattr(api_mod, "cliente_quer_nova_venda", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "negociacao_nova_apos_fechamento", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "produtos_com_foto_disponivel", lambda *_a, **_k: [])
    monkeypatch.setattr(api_mod, "cliente_pediu_foto", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "finalizar_mensagem", lambda *_a, **_k: None)
    monkeypatch.setattr(
        api_mod,
        "preparar_contexto_venda",
        lambda **_k: _ctx_mock(produtos=produtos, memoria=_k.get("memoria") or {}),
    )
    monkeypatch.setattr(
        "services.product_service.buscar_por_intencao",
        lambda **_k: {
            "found": True,
            "products": produtos,
            "message": "ok",
            "category": "headset",
            "catalogo": "Headset Gamer — R$ 249,90",
            "fonte": "supabase",
        },
    )
    from services.webhook_service import _IDS_PROCESSADOS
    from services import webhook_guard as wg

    _IDS_PROCESSADOS.clear()
    wg._IDS_ESTADO.clear()
    monkeypatch.setattr(
        "services.supabase_service.mensagem_ja_existe",
        lambda *_a, **_k: False,
    )


# 1
def test_chat_persistir_false_continua(monkeypatch):
    _patch_fluxo_basico(monkeypatch)
    saves = {"n": 0}
    monkeypatch.setattr(
        api_mod,
        "salvar_mensagem",
        lambda *_a, **_k: saves.__setitem__("n", saves["n"] + 1),
    )
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: None)
    out = api_mod.processar_mensagem(
        _data(mid="pf-1"), dry_run=True, persistir=False
    )
    assert isinstance(out, dict)
    assert out["resposta"]
    assert "Headset" in out["resposta"] or "retirar" in out["resposta"].lower()
    assert saves["n"] == 0


# 2
def test_chat_persistir_true_funciona(monkeypatch):
    _patch_fluxo_basico(monkeypatch)
    saves = {"msgs": 0, "hist": 0, "ctx": 0}
    monkeypatch.setattr(
        api_mod,
        "salvar_mensagem",
        lambda *_a, **_k: saves.__setitem__("msgs", saves["msgs"] + 1),
    )
    monkeypatch.setattr(
        api_mod,
        "atualizar_historico_json",
        lambda *_a, **_k: saves.__setitem__("hist", saves["hist"] + 1),
    )
    monkeypatch.setattr(
        "services.vendas.memoria.persistir_sessao",
        lambda *_a, **_k: saves.__setitem__("ctx", saves["ctx"] + 1),
    )
    # re-import path used inside api via local import — patch api's usage via memoria module
    import services.vendas.memoria as mem

    monkeypatch.setattr(
        mem,
        "persistir_sessao",
        lambda *_a, **_k: (saves.__setitem__("ctx", saves["ctx"] + 1) or True),
    )
    out = api_mod.processar_mensagem(
        _data(mid="pt-1"), dry_run=True, persistir=True
    )
    assert isinstance(out, dict)
    assert out["resposta"]
    assert out.get("persistencia_ok") is True
    assert saves["msgs"] >= 1


# 3
def test_chat_persistir_omitido_funciona(monkeypatch):
    """persistir omitido = True (default)."""
    _patch_fluxo_basico(monkeypatch)
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: None)
    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", lambda *_a, **_k: True)
    out = api_mod.processar_mensagem(_data(mid="po-1"), dry_run=True)  # persistir default True
    assert out and out.get("resposta")
    assert out.get("persistencia_ok") is True


# 4
def test_quero_comprar_persistir_salva_contexto(monkeypatch):
    _patch_fluxo_basico(monkeypatch)
    sessao_salva = {}

    def fake_persist(cid, sessao):
        sessao_salva.update(sessao)
        return True

    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", fake_persist)
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: None)
    out = api_mod.processar_mensagem(
        _data("quero comprar o headset gamer", mid="qc-1"),
        dry_run=True,
        persistir=True,
    )
    assert out["resposta"]
    assert out.get("persistencia_ok") is True
    assert "entrega" in out["resposta"].lower() or "retirar" in out["resposta"].lower()
    assert sessao_salva.get("produto_checkout") or sessao_salva.get("produto_ativo")


# 5
def test_prefiro_entrega_continua_checkout():
    r = avaliar_checkout(
        mensagem="prefiro entrega",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "checkout_status": "coletando_dados",
        },
        produtos=[{
            "name": "Headset Gamer",
            "price": 249.9,
            "stock_quantity": 5,
            "stock_confirmed": True,
        }],
        intent="ENTREGA",
    )
    assert r["sessao"]["forma_entrega"] == "entrega"
    assert "cidade" in r["missing_fields"] or "endereco" in r["missing_fields"]


# 6
def test_sou_de_londrina_atualiza_cidade():
    r = avaliar_checkout(
        mensagem="sou de Londrina",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "forma_entrega": "entrega",
            "quantidade": 1,
        },
        produtos=[{
            "name": "Headset Gamer",
            "price": 249.9,
            "stock_quantity": 5,
            "stock_confirmed": True,
        }],
        intent="ENTREGA",
    )
    assert "londrina" in (r["sessao"].get("cidade") or "").lower()


# 7 + 8
def test_falha_supabase_nao_retorna_vazio_nem_derruba(monkeypatch):
    _patch_fluxo_basico(monkeypatch)

    def boom(*_a, **_k):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(api_mod, "salvar_mensagem", boom)
    monkeypatch.setattr(api_mod, "atualizar_historico_json", boom)
    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", boom)
    out = api_mod.processar_mensagem(
        _data(mid="fail-1"), dry_run=True, persistir=True
    )
    assert isinstance(out, dict)
    assert out.get("resposta")  # não vazio
    assert out.get("persistencia_ok") is False


# 9
def test_objeto_nao_serializavel_convertido():
    from datetime import datetime

    sujo = sessao_vazia()
    sujo["preco_cotado"] = Decimal("249.90")
    sujo["produto_checkout"] = "Headset"
    sujo["quantidade"] = 1
    # campo extra ignorado; força valor problemático em campo conhecido
    limpo = serializar_contexto_venda(sujo)
    assert isinstance(limpo["preco_cotado"], float)
    assert limpo["produto_checkout"] == "Headset"
    # datetime em fato via json path
    sujo2 = sessao_vazia()
    sujo2["checkout_resumo"] = {"quando": datetime(2026, 7, 10)}
    limpo2 = serializar_contexto_venda(sujo2)
    assert isinstance(limpo2["checkout_resumo"], (str, dict))


# 10
def test_dry_run_nao_cria_pedido(monkeypatch):
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
        produtos=[{
            "name": "Headset Gamer",
            "price": 249.9,
            "stock_quantity": 5,
            "stock_confirmed": True,
        }],
        intent="COMPRA",
        dry_run=True,
        persistir=True,
    )
    with patch(
        "services.pedido_mercos_service.criar_pedido_fechamento_mercos"
    ) as mock_m:
        out = criar_pedido_se_permitido(
            resultado={**base, "can_create_order": True},
            historico_texto="",
            cliente_supabase={"id": "1"},
            telefone="5511",
            dry_run=True,
            persistir=True,
        )
        mock_m.assert_not_called()
        assert out.get("pedido") is None


# 11
def test_checkout_create_order_false_impede(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    r = avaliar_checkout(
        mensagem="ok",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "forma_entrega": "retirada",
            "quantidade": 1,
            "forma_pagamento": "PIX",
        },
        produtos=[{
            "name": "Headset Gamer",
            "price": 249.9,
            "stock_quantity": 5,
            "stock_confirmed": True,
        }],
        intent="COMPRA",
        dry_run=False,
        persistir=True,
    )
    assert r["can_create_order"] is False


# 12
def test_lock_liberado_mesmo_com_exception():
    tel = "5543888777666"
    lock = lock_telefone(tel)
    assert lock.acquire(blocking=False)
    lock.release()
    # simula with + exception
    try:
        with lock_telefone(tel):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert lock.acquire(blocking=False)
    lock.release()


# 13
def test_webhook_continua():
    assert hasattr(api_mod, "receber_webhook")
    assert hasattr(api_mod, "webhook")
    assert api_mod.CODE_VERSION == "2026-07-13-fix-formatador-final"


def test_dry_run_nao_chama_bridge_cliente(monkeypatch):
    _patch_fluxo_basico(monkeypatch)
    called = {"bridge": 0}
    monkeypatch.setattr(
        api_mod,
        "espelhar_mensagem_cliente",
        lambda *_a, **_k: called.__setitem__("bridge", called["bridge"] + 1),
    )
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: None)
    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", lambda *_a, **_k: True)
    api_mod.processar_mensagem(_data(mid="br-1"), dry_run=True, persistir=True)
    assert called["bridge"] == 0
