"""Parser UltraMsg /webhook — aceita privado, ignora grupo/fromMe/sem texto."""

from __future__ import annotations

import routes.api as api_mod
from fastapi.testclient import TestClient
from services.webhook_normalizer import analisar_webhook, normalizar_webhook


def _payload_privado(body: str = "oi", from_me: bool = False, jid: str = "5543999999999@c.us"):
    return {
        "event_type": "message_received",
        "instanceId": "instance184714",
        "id": "",
        "data": {
            "id": f"false_{jid}_ABC123",
            "from": jid,
            "to": "5543888777666@c.us",
            "author": "",
            "pushname": "Tironi",
            "fromMe": from_me,
            "type": "chat",
            "body": body,
            "time": 1710000000,
        },
    }


def _payload_grupo(body: str = "oi no grupo"):
    return {
        "event_type": "message_received",
        "instanceId": "instance184714",
        "data": {
            "id": "false_120363406783647254@g.us_A53F18D48039AA12356E5F8AFCB053FB_238778841092098@lid",
            "from": "120363406783647254@g.us",
            "to": "5543888777666@c.us",
            "author": "238778841092098@lid",
            "pushname": "Alguem",
            "fromMe": False,
            "type": "chat",
            "body": body,
            "time": 1710000000,
        },
    }


def test_code_version_ultramsg_webhook_parser():
    assert api_mod.CODE_VERSION == "2026-07-13-etapa6-handoff-humano"


def test_ultramsg_privado_aceito(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    raw = _payload_privado("quero headset")
    diag = analisar_webhook(raw)
    assert diag["ok"] is True
    assert diag["provider_detectado"] == "ultramsg"
    assert diag["parse_ok"] is True
    assert diag["eh_grupo"] is False
    assert diag["from_me"] is False
    assert diag["tem_texto"] is True
    norm = diag["payload"]
    assert norm["provider"] == "ultramsg"
    assert norm["data"]["from"] == "5543999999999"
    assert norm["data"]["body"] == "quero headset"
    assert normalizar_webhook(raw) is not None


def test_ultramsg_grupo_ignorado_motivo_claro(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    diag = analisar_webhook(_payload_grupo())
    assert diag["ok"] is False
    assert diag["motivo_ignorado"] == "mensagem_grupo_ignorada"
    assert diag["eh_grupo"] is True
    assert diag["provider_detectado"] == "ultramsg"
    assert normalizar_webhook(_payload_grupo()) is None


def test_ultramsg_from_me_ignorado(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    diag = analisar_webhook(_payload_privado("eco", from_me=True))
    assert diag["ok"] is False
    assert diag["motivo_ignorado"] == "from_me"
    assert diag["from_me"] is True


def test_ultramsg_from_me_string_true(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    raw = _payload_privado("eco")
    raw["data"]["fromMe"] = "true"
    assert analisar_webhook(raw)["motivo_ignorado"] == "from_me"


def test_ultramsg_sem_texto_ignorado(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    diag = analisar_webhook(_payload_privado(""))
    assert diag["ok"] is False
    assert diag["motivo_ignorado"] == "sem_texto"
    assert diag["tem_texto"] is False


def test_provider_env_ultramsg_mesmo_sem_campo_provider(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    raw = {
        "event_type": "message_received",
        "data": {
            "from": "5543999999999@c.us",
            "body": "oi",
            "type": "chat",
            "fromMe": False,
            "id": "x1",
        },
    }
    # Sem campo provider no JSON
    assert "provider" not in raw
    diag = analisar_webhook(raw)
    assert diag["provider_detectado"] == "ultramsg"
    assert diag["ok"] is True


def test_webhook_http_privado_chama_processar(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    chamado = {}

    def _fake_processar(data, dry_run=False, persistir=True):
        chamado["data"] = data
        return {"resposta": "ok", "persistencia_ok": True}

    monkeypatch.setattr(api_mod, "processar_mensagem", _fake_processar)

    from main import app

    client = TestClient(app)
    resp = client.post("/webhook", json=_payload_privado("manda o catalogo"))
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok"
    assert body.get("ignorado") is not True
    assert chamado.get("data") is not None
    assert chamado["data"]["provider"] == "ultramsg"
    assert chamado["data"]["data"]["body"] == "manda o catalogo"


def test_webhook_http_grupo_retorna_motivo(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    from main import app

    client = TestClient(app)
    resp = client.post("/webhook", json=_payload_grupo())
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ignorado") is True
    assert body.get("motivo") == "mensagem_grupo_ignorada"


def test_resposta_passa_whatsapp_service(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    monkeypatch.setenv("ULTRAMSG_INSTANCE_ID", "instance184714")
    monkeypatch.setenv("ULTRAMSG_TOKEN", "tok_teste")
    capturado = {}

    def _fake_enviar(numero, mensagem):
        capturado["numero"] = numero
        capturado["mensagem"] = mensagem
        return {"ok": True, "provider": "ultramsg"}

    monkeypatch.setattr("services.whatsapp_service.enviar_mensagem", _fake_enviar)
    from services.whatsapp_service import enviar_mensagem

    enviar_mensagem("5543999999999", "algumas opções do catálogo")
    assert capturado["numero"] == "5543999999999"
    assert "opções" in capturado["mensagem"] or "opcoes" in capturado["mensagem"].lower() or "catalogo" in capturado["mensagem"].lower() or "catálogo" in capturado["mensagem"]


def test_chat_continua_ok(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")

    def _fake_processar(*_a, **_k):
        return {
            "resposta": "Claro, Tironi. Posso te mostrar algumas opções.",
            "persistencia_ok": True,
        }

    monkeypatch.setattr(api_mod, "processar_mensagem", _fake_processar)
    from main import app

    client = TestClient(app)
    resp = client.post(
        "/chat",
        json={
            "telefone": "5543999999999",
            "mensagem": "oi",
            "nome": "Tironi",
            "dry_run": True,
            "persistir": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("code_version") == "2026-07-13-etapa6-handoff-humano"
    assert resp.json().get("resposta")


def test_checkout_create_order_false(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    from services.checkout_service import checkout_criar_pedido_habilitado

    assert checkout_criar_pedido_habilitado() is False


def test_data_json_string_ultramsg(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    import json

    raw = {
        "event_type": "message_received",
        "data": json.dumps(
            {
                "from": "5543999999999@c.us",
                "body": "texto via string",
                "type": "chat",
                "fromMe": False,
                "id": "id-str",
                "pushname": "Tironi",
            }
        ),
    }
    diag = analisar_webhook(raw)
    assert diag["ok"] is True
    assert diag["payload"]["data"]["body"] == "texto via string"
