"""UltraMsg como provedor WhatsApp (beta)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import routes.api as api_mod
from services import ultramsg_service as um
from services import whatsapp_service as wa
from services import zapi_service as zapi
from services.checkout_service import avaliar_checkout
from services.webhook_normalizer import normalizar_webhook


def test_provider_ultramsg(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    assert wa.provider_nome() == "ultramsg"
    assert wa.ultramsg_ativo() is True


def test_ultramsg_configurado_com_instance_token(monkeypatch):
    monkeypatch.setenv("ULTRAMSG_INSTANCE_ID", "instance184714")
    monkeypatch.setenv("ULTRAMSG_TOKEN", "token_teste_xyz")
    monkeypatch.delenv("ULTRAMSG_API_URL", raising=False)
    assert um.ultramsg_configurado() is True


def test_ultramsg_nao_configurado_sem_token(monkeypatch):
    monkeypatch.setenv("ULTRAMSG_INSTANCE_ID", "instance184714")
    monkeypatch.setenv("ULTRAMSG_TOKEN", "")
    assert um.ultramsg_configurado() is False


def test_base_url_com_api_url(monkeypatch):
    monkeypatch.setenv("ULTRAMSG_INSTANCE_ID", "instance184714")
    monkeypatch.setenv("ULTRAMSG_TOKEN", "tok")
    monkeypatch.setenv("ULTRAMSG_API_URL", "https://api.ultramsg.com/instance184714/")
    assert um._base_url() == "https://api.ultramsg.com/instance184714"


def test_base_url_monta_sozinha(monkeypatch):
    monkeypatch.setenv("ULTRAMSG_INSTANCE_ID", "instance184714")
    monkeypatch.setenv("ULTRAMSG_TOKEN", "tok")
    monkeypatch.delenv("ULTRAMSG_API_URL", raising=False)
    assert um._base_url() == "https://api.ultramsg.com/instance184714"


def test_envio_usa_ultramsg_nao_zapi(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    monkeypatch.setenv("ULTRAMSG_INSTANCE_ID", "instance184714")
    monkeypatch.setenv("ULTRAMSG_TOKEN", "tok_secreto_abc")
    called = {"um": 0, "zapi": 0}

    monkeypatch.setattr(
        um,
        "enviar_mensagem",
        lambda *_a, **_k: called.__setitem__("um", called["um"] + 1) or {"ok": True},
    )
    monkeypatch.setattr(
        zapi,
        "enviar_mensagem",
        lambda *_a, **_k: called.__setitem__("zapi", called["zapi"] + 1) or {"ok": True},
    )
    # whatsapp_service imports modules — patch via wa module references
    monkeypatch.setattr(wa, "ultramsg_service", um)
    monkeypatch.setattr(wa, "zapi_service", zapi)

    out = wa.enviar_mensagem("5543999999999", "oi")
    assert out["ok"] is True
    assert called["um"] == 1
    assert called["zapi"] == 0


def test_status_mostra_ultramsg(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    monkeypatch.setenv("ULTRAMSG_INSTANCE_ID", "instance184714")
    monkeypatch.setenv("ULTRAMSG_TOKEN", "tok")
    # status é async — testa provider helpers
    assert api_mod.provider_nome() == "ultramsg"
    assert api_mod.ultramsg_svc.ultramsg_configurado() is True
    assert api_mod.whatsapp_configurado() is True
    assert api_mod.CODE_VERSION == "2026-07-13-fix-espaco-unidades"


def test_webhook_normaliza_ultramsg():
    raw = {
        "event_type": "message_received",
        "instanceId": "instance184714",
        "id": "msg-1",
        "data": {
            "id": "wamid.ABC",
            "from": "5543999999999",
            "to": "5543888777666",
            "pushname": "Arthur",
            "fromMe": False,
            "type": "chat",
            "body": "quero comprar headset",
            "time": 1710000000,
        },
    }
    norm = normalizar_webhook(raw)
    assert norm is not None
    assert norm["provider"] == "ultramsg"
    assert norm["data"]["from"] == "5543999999999"
    assert norm["data"]["body"] == "quero comprar headset"
    assert norm["data"]["pushname"] == "Arthur"
    assert norm["data"]["id"] == "wamid.ABC"


def test_webhook_ignora_from_me_ultramsg():
    raw = {
        "event_type": "message_received",
        "data": {
            "from": "5543999999999",
            "body": "eco",
            "fromMe": True,
            "type": "chat",
            "id": "x",
        },
    }
    assert normalizar_webhook(raw) is None


def test_logs_nao_expoe_token(monkeypatch, capsys):
    monkeypatch.setenv("ULTRAMSG_INSTANCE_ID", "instance184714")
    monkeypatch.setenv("ULTRAMSG_TOKEN", "segredo_total_12345")
    monkeypatch.setenv("ULTRAMSG_API_URL", "https://api.ultramsg.com/instance184714")

    class FakeResp:
        status_code = 200
        text = '{"sent":"true"}'

        def json(self):
            return {"sent": "true"}

    with patch("services.ultramsg_service.requests.post", return_value=FakeResp()):
        um.enviar_mensagem("5543999999999", "oi")
    out = capsys.readouterr().out
    assert "segredo_total_12345" not in out
    assert "tok_secreto" not in out


def test_checkout_create_order_false(monkeypatch):
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
        dry_run=False,
        persistir=True,
    )
    assert r["can_create_order"] is False


def test_mascarar_token():
    assert um._mascarar_token("abcdefgh").endswith("efgh")
    assert "abcd" not in um._mascarar_token("abcdefgh") or um._mascarar_token("abcdefgh").startswith("***")
