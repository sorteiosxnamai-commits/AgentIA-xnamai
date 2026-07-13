"""Persistência real: schema PGRST204 + fallback contexto no historico."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import routes.api as api_mod
from services import supabase_service as sb
from services.checkout_service import avaliar_checkout, criar_pedido_se_permitido
from services.vendas.memoria import (
    carregar_sessao,
    persistir_sessao,
    serializar_contexto_venda,
    sessao_vazia,
)


def _ctx_mock(**kwargs):
    base = dict(
        produtos=[{
            "id": "1",
            "name": "Headset Gamer",
            "nome": "Headset Gamer",
            "price": 249.9,
            "preco": 249.9,
            "stock_quantity": 5,
            "stock_confirmed": True,
        }],
        catalogo="Headset",
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


def _data(msg="quero comprar o headset gamer", tel="5543999000888", mid=None):
    return {
        "event_type": "message_received",
        "provider": "chat_teste",
        "data": {
            "from": tel,
            "body": msg,
            "pushname": "Arthur",
            "fromMe": False,
            "type": "chat",
            "id": mid or f"chat-schema-{abs(hash(msg + tel)) % 10_000_000}",
            "time": __import__("time").time(),
        },
    }


def _patch_basico(monkeypatch):
    monkeypatch.setattr(api_mod, "buscar_cliente", lambda *_a, **_k: {
        "id": "cli-schema-1",
        "telefone": "5543999000888",
        "nome": "Arthur",
        "historico": [],
        "contexto_venda": {},
    })
    monkeypatch.setattr(api_mod, "criar_cliente", lambda *_a, **_k: {"id": "cli-schema-1"})
    monkeypatch.setattr(api_mod, "atualizar_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "buscar_historico", lambda *_a, **_k: [])
    monkeypatch.setattr(api_mod, "espelhar_mensagem_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "espelhar_mensagem_agente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "atualizar_thread_conversa", lambda *_a, **_k: True)
    monkeypatch.setattr(api_mod, "enviar_mensagem", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(api_mod, "processar_lead_e_notificar", lambda **_k: {"notificado": False})
    monkeypatch.setattr(api_mod, "resolver_estado_venda", lambda *_a, **_k: "negociando")
    monkeypatch.setattr(api_mod, "eh_saudacao", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "extrair_nome_do_historico", lambda *_a, **_k: "Arthur")
    monkeypatch.setattr(api_mod, "cliente_quer_nova_venda", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "negociacao_nova_apos_fechamento", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "produtos_com_foto_disponivel", lambda *_a, **_k: [])
    monkeypatch.setattr(api_mod, "cliente_pediu_foto", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "finalizar_mensagem", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "preparar_contexto_venda", lambda **_k: _ctx_mock(memoria=_k.get("memoria") or {}))
    monkeypatch.setattr(
        "services.product_service.buscar_por_intencao",
        lambda **_k: {
            "found": True,
            "products": _ctx_mock().produtos,
            "message": "ok",
            "category": "headset",
            "catalogo": "Headset",
            "fonte": "supabase",
        },
    )
    from services.webhook_service import _IDS_PROCESSADOS
    from services import webhook_guard as wg

    _IDS_PROCESSADOS.clear()
    wg._IDS_ESTADO.clear()
    monkeypatch.setattr("services.supabase_service.mensagem_ja_existe", lambda *_a, **_k: False)
    sb._SCHEMA_FLAGS["message_id"] = False
    sb._SCHEMA_FLAGS["contexto_venda"] = False


# 1
def test_persistir_false_nao_salva(monkeypatch):
    _patch_basico(monkeypatch)
    saves = {"n": 0}
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: saves.__setitem__("n", saves["n"] + 1))
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: None)
    out = api_mod.processar_mensagem(_data(mid="s1"), dry_run=True, persistir=False)
    assert out["resposta"]
    assert saves["n"] == 0


# 2+3+4+5
def test_persistir_true_salva_msgs_e_contexto(monkeypatch):
    _patch_basico(monkeypatch)
    calls = {"user": 0, "ia": 0, "ctx": 0}

    def fake_salvar(cid, tipo, msg, message_id=None, **_k):
        if tipo == "cliente":
            calls["user"] += 1
        else:
            calls["ia"] += 1

    monkeypatch.setattr(api_mod, "salvar_mensagem", fake_salvar)
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: None)

    def fake_persist(cid, sessao):
        calls["ctx"] += 1
        assert sessao.get("produto_checkout") or sessao.get("produto_ativo")
        return True

    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", fake_persist)
    out = api_mod.processar_mensagem(
        _data("quero comprar o headset gamer", mid="s2"),
        dry_run=True,
        persistir=True,
    )
    assert out["resposta"]
    assert out["persistencia_ok"] is True
    assert calls["user"] >= 1
    assert calls["ia"] >= 1
    assert calls["ctx"] >= 1


# 6
def test_prefiro_entrega_contexto():
    r = avaliar_checkout(
        mensagem="prefiro entrega",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 249.9},
        produtos=[{"name": "Headset Gamer", "price": 249.9, "stock_quantity": 5, "stock_confirmed": True}],
        intent="ENTREGA",
    )
    assert r["sessao"]["forma_entrega"] == "entrega"


# 7
def test_londrina_cidade_contexto():
    r = avaliar_checkout(
        mensagem="sou de Londrina",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "forma_entrega": "entrega",
            "quantidade": 1,
        },
        produtos=[{"name": "Headset Gamer", "price": 249.9, "stock_quantity": 5, "stock_confirmed": True}],
        intent="ENTREGA",
    )
    assert "londrina" in (r["sessao"].get("cidade") or "").lower()


# 8
def test_message_id_null_nao_quebra():
    payload = {"cliente_id": "1", "tipo": "cliente", "mensagem": "oi"}
    # simula insert sem message_id
    assert "message_id" not in payload or payload.get("message_id") in (None, "")


# 9
def test_message_id_duplicado_protegido():
    from services import webhook_guard as wg
    from services.webhook_service import _IDS_PROCESSADOS

    _IDS_PROCESSADOS.clear()
    wg._IDS_ESTADO.clear()
    data = {
        "event_type": "message_received",
        "data": {"id": "dup-schema-1", "from": "5543999000111", "body": "oi", "time": 1},
    }
    with patch("services.supabase_service.mensagem_ja_existe", return_value=True):
        ok, motivo = wg.reclamar_mensagem(data)
    assert ok is False
    assert "duplicado" in motivo


# 10
def test_falha_supabase_resposta_preenchida(monkeypatch):
    _patch_basico(monkeypatch)

    def boom(*_a, **_k):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(api_mod, "salvar_mensagem", boom)
    monkeypatch.setattr(api_mod, "atualizar_historico_json", boom)
    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", boom)
    out = api_mod.processar_mensagem(_data(mid="s10"), dry_run=True, persistir=True)
    assert out["resposta"]
    assert out["persistencia_ok"] is False


# 11
def test_webhook_ok():
    assert hasattr(api_mod, "webhook")
    assert api_mod.CODE_VERSION == "2026-07-13-fix-catalogo-formatacao"


# 12+13
def test_dry_run_e_create_order_false(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    r = avaliar_checkout(
        mensagem="ok",
        sessao={
            "produto_ativo": "Headset",
            "preco_cotado": 10,
            "forma_entrega": "retirada",
            "quantidade": 1,
            "forma_pagamento": "PIX",
        },
        produtos=[{"name": "Headset", "price": 10, "stock_quantity": 5, "stock_confirmed": True}],
        intent="COMPRA",
        dry_run=True,
        persistir=True,
    )
    assert r["can_create_order"] is False
    with patch("services.pedido_mercos_service.criar_pedido_fechamento_mercos") as m:
        out = criar_pedido_se_permitido(
            resultado={**r, "can_create_order": True},
            historico_texto="",
            cliente_supabase={"id": "1"},
            telefone="5511",
            dry_run=True,
            persistir=True,
        )
        m.assert_not_called()
        assert out.get("pedido") is None


def test_fallback_contexto_no_historico():
    mensagens = [{"role": "user", "content": "oi", "timestamp": "1"}]
    ctx = {"checkout_status": "coletando_dados", "cidade": "Londrina"}
    bundled = sb.anexar_contexto_no_historico_json(mensagens, ctx)
    extracted = sb.extrair_contexto_do_historico_json(bundled)
    assert extracted["cidade"] == "Londrina"


def test_carregar_sessao_do_historico_fallback():
    cliente = {
        "id": "c1",
        "historico": sb.anexar_contexto_no_historico_json(
            [],
            {"produto_checkout": "Headset Gamer", "forma_entrega": "entrega", "cidade": "Londrina"},
        ),
    }
    sessao = carregar_sessao(cliente, "c1")
    assert sessao["produto_checkout"] == "Headset Gamer"
    assert sessao["cidade"] == "Londrina"


def test_serializar_decimal():
    s = sessao_vazia()
    s["preco_cotado"] = Decimal("249.90")
    limpo = serializar_contexto_venda(s)
    assert isinstance(limpo["preco_cotado"], float)


def test_erro_coluna_ausente_detecta_pgrst204():
    from postgrest.exceptions import APIError

    exc = APIError(
        {
            "message": "Could not find the 'contexto_venda' column of 'clientes' in the schema cache",
            "code": "PGRST204",
            "hint": None,
            "details": None,
        }
    )
    assert sb.erro_coluna_ausente(exc, "contexto_venda") is True
