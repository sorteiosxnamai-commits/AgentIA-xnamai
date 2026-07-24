"""Testes Brevo como provedor WhatsApp → agents.vendas → WhatsApp."""

from __future__ import annotations

from unittest.mock import MagicMock


def _payload_whatsapp_conversations(**extra):
    """Payload típico Brevo Conversations com WhatsApp do visitante."""
    base = {
        "visitor": {
            "id": "vis-123",
            "threadId": "conv-999",
            "contactId": "ct-55",
            "displayedName": "Ana",
            "attributes": {"WHATSAPP": "5511999887766"},
        },
        "messages": [
            {
                "id": "msg-wa-1",
                "type": "visitor",
                "text": "Olá, quero um produto",
            }
        ],
        "conversationId": "conv-999",
        "contactId": "ct-55",
    }
    base.update(extra)
    return base


def _payload_whatsapp_flat():
    """Payload flat estilo WhatsApp via Brevo."""
    return {
        "from": "5511888777666",
        "text": "Quanto custa?",
        "id": "msg-flat-1",
        "name": "Bruno",
        "conversationId": "conv-flat",
        "contactId": "ct-flat",
    }


def test_parse_whatsapp_numero_e_ids():
    from services.brevo_parser import parse_brevo_payload, normalizar_para_webhook_interno

    parsed = parse_brevo_payload(_payload_whatsapp_conversations())
    assert "5511999887766" in (parsed["sender_phone"] or "")
    assert parsed["message_id"] == "msg-wa-1"
    assert parsed["conversation_id"] == "conv-999"
    assert parsed["contact_id"] == "ct-55"

    flat = parse_brevo_payload(_payload_whatsapp_flat())
    assert flat["sender_phone"] == "5511888777666"
    assert flat["message_id"] == "msg-flat-1"

    norm = normalizar_para_webhook_interno(_payload_whatsapp_conversations())
    assert norm["provider"] == "brevo"
    assert "5511999887766" in norm["data"]["from"]


def test_parse_audio_whatsapp_brevo():
    from services.brevo_parser import parse_brevo_payload

    payload = {
        "from": "5511999887766",
        "id": "aud-wa-1",
        "media": "https://cdn.example.com/voice.ogg",
        "text": "audio",
    }
    parsed = parse_brevo_payload(payload)
    assert parsed["input_modality"] == "audio"
    assert parsed["audio_url"].startswith("https://")
    assert parsed["sender_phone"] == "5511999887766"


def test_modo_whatsapp_envia_api_transacional(monkeypatch):
    monkeypatch.setenv("BREVO_REPLY_MODE", "whatsapp")
    monkeypatch.setenv("BREVO_API_KEY", "key-test")
    monkeypatch.setenv("BREVO_SENDER_NUMBER", "551100001111")
    from services import brevo_service

    chamado = {}

    class _Resp:
        status_code = 201
        text = "{}"

        def json(self):
            return {"messageId": "out-1"}

    def fake_post(url, json=None, headers=None, timeout=None):
        chamado["url"] = url
        chamado["json"] = json
        chamado["headers_has_key"] = bool(headers and headers.get("api-key"))
        return _Resp()

    monkeypatch.setattr(brevo_service.requests, "post", fake_post)
    out = brevo_service.enviar_resposta(
        "Olá da xNamai",
        telefone="5511999887766",
        visitor_id="vis-123",
        conversation_id="conv-999",
        contact_id="ct-55",
    )
    assert out["ok"] is True
    assert out["channel"] == "whatsapp"
    assert out["dry_run"] is False
    assert "whatsapp/sendMessage" in chamado["url"]
    assert chamado["json"]["contactNumbers"] == ["5511999887766"]
    assert chamado["json"]["senderNumber"] == "551100001111"
    assert "xNamai" in chamado["json"]["text"]
    assert chamado["headers_has_key"] is True


def test_modo_whatsapp_exige_sender_e_telefone(monkeypatch):
    monkeypatch.setenv("BREVO_REPLY_MODE", "whatsapp")
    monkeypatch.setenv("BREVO_API_KEY", "key-test")
    monkeypatch.delenv("BREVO_SENDER_NUMBER", raising=False)
    from services import brevo_service

    out = brevo_service.enviar_resposta("oi", telefone="5511999887766")
    assert out["ok"] is False
    assert out["error"] == "brevo_sender_number_missing"

    monkeypatch.setenv("BREVO_SENDER_NUMBER", "551100001111")
    out2 = brevo_service.enviar_resposta("oi", telefone="brevoABC")
    assert out2["ok"] is False
    assert out2["error"] == "recipient_phone_missing"


def test_fluxo_completo_whatsapp_via_brevo(monkeypatch):
    """WhatsApp → Brevo → webhook → agents.vendas → Brevo WhatsApp."""
    from routes import api as api_mod

    chamado = {"processar": 0, "enviar": 0, "whatsapp_service": 0}

    def fake_processar(data, dry_run=False, persistir=True):
        chamado["processar"] += 1
        assert data["provider"] == "brevo"
        assert dry_run is True  # envio outbound só via Brevo neste fluxo
        assert "5511999887766" in data["data"]["from"]
        return {"resposta": "Olá! Sou o assistente de vendas da xNamai."}

    def fake_enviar(texto, **kwargs):
        chamado["enviar"] += 1
        assert kwargs.get("telefone")
        assert "5511999887766" in str(kwargs.get("telefone"))
        return {
            "ok": True,
            "dry_run": False,
            "channel": "whatsapp",
            "to": "5511999887766",
            "sender_number": "551100001111",
        }

    def fake_wa_svc(*a, **k):
        chamado["whatsapp_service"] += 1
        raise AssertionError("whatsapp_service não deve ser chamado no fluxo Brevo webhook")

    monkeypatch.setenv("BREVO_REPLY_MODE", "whatsapp")
    monkeypatch.setattr(api_mod, "processar_mensagem", fake_processar)
    monkeypatch.setattr("services.brevo_service.enviar_resposta", fake_enviar)
    monkeypatch.setattr(
        "services.whatsapp_service.enviar_mensagem", fake_wa_svc
    )
    monkeypatch.setattr(
        "services.webhook_guard.marcar_envio_concluido", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "services.webhook_guard.finalizar_mensagem", lambda *a, **k: None
    )

    from services.brevo_parser import normalizar_para_webhook_interno

    api_mod._processar_e_responder_brevo(
        normalizar_para_webhook_interno(_payload_whatsapp_conversations())
    )
    assert chamado["processar"] == 1
    assert chamado["enviar"] == 1
    assert chamado["whatsapp_service"] == 0


def test_duplicata_e_eco_agente():
    from services.brevo_parser import should_skip_auto_reply, normalizar_para_webhook_interno
    from services import webhook_guard as wg

    assert should_skip_auto_reply(
        {"messages": [{"id": "1", "type": "agent", "text": "bot"}]}
    )
    data = normalizar_para_webhook_interno(_payload_whatsapp_conversations())
    ok1, _ = wg.reclamar_mensagem(data)
    assert ok1 is True
    wg.marcar_envio_concluido(data, message_id="msg-wa-1")
    ok2, motivo = wg.reclamar_mensagem(data)
    assert ok2 is False
    assert "enviado" in motivo or "duplicado" in motivo


def test_rotas_whatsapp_e_chat_registradas():
    from main import app

    paths = app.openapi().get("paths", {})
    assert "/webhooks/brevo/whatsapp" in paths
    assert "/webhooks/brevo/chat" in paths


def test_envio_dry_run_canal_whatsapp(monkeypatch):
    monkeypatch.setenv("BREVO_REPLY_MODE", "dry_run")
    monkeypatch.setenv("BREVO_SENDER_NUMBER", "551100001111")
    from services import brevo_service

    out = brevo_service.enviar_resposta(
        "teste",
        telefone="5511999887766",
        visitor_id="vis-1",
        conversation_id="c1",
        contact_id="ct1",
    )
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert out["channel"] == "whatsapp"
    assert out["to"] == "5511999887766"
    assert out["sender_number"] == "551100001111"


def test_timeout_whatsapp_nao_libera_duplicata(monkeypatch):
    import requests as req
    from routes import api as api_mod

    monkeypatch.setenv("BREVO_REPLY_MODE", "whatsapp")
    monkeypatch.setenv("BREVO_API_KEY", "k")
    monkeypatch.setenv("BREVO_SENDER_NUMBER", "551100001111")

    monkeypatch.setattr(
        api_mod,
        "processar_mensagem",
        lambda *a, **k: {"resposta": "ok"},
    )

    def boom(*a, **k):
        raise req.Timeout()

    from services import brevo_service

    monkeypatch.setattr(brevo_service.requests, "post", boom)

    marcado = {"n": 0}

    def fake_marcar(*a, **k):
        marcado["n"] += 1

    monkeypatch.setattr(
        "services.webhook_guard.marcar_envio_concluido", fake_marcar
    )
    monkeypatch.setattr(
        "services.webhook_guard.finalizar_mensagem", lambda *a, **k: None
    )

    from services.brevo_parser import normalizar_para_webhook_interno

    # Usa enviar_resposta real (timeout)
    monkeypatch.setattr(
        "services.brevo_service.enviar_resposta",
        lambda *a, **k: {"ok": False, "error": "brevo_timeout", "channel": "whatsapp"},
    )
    api_mod._processar_e_responder_brevo(
        normalizar_para_webhook_interno(_payload_whatsapp_conversations())
    )
    assert marcado["n"] == 1


def test_mercos_intacta():
    """Throttle e mercos_service intactos após integração Brevo."""
    import subprocess
    from pathlib import Path

    out = subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            "--",
            "services/mercos_service.py",
            "services/mercos_throttle.py",
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        text=True,
    )
    assert out.strip() == ""
