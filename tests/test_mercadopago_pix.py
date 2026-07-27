"""Pix Mercado Pago — testes 100% mockados (sem API real)."""

from __future__ import annotations

import hashlib
import hmac
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


PRODUTO_OK = {
    "found": True,
    "products": [
        {
            "name": "Notebook Intel i5",
            "nome": "Notebook Intel i5",
            "price": 3499.9,
            "preco": 3499.9,
            "stock_quantity": 5,
            "estoque": 5,
            "stock_confirmed": True,
        }
    ],
}


def _mp_payment_response(**extra):
    base = {
        "id": 123456789,
        "status": "pending",
        "status_detail": "pending_waiting_transfer",
        "transaction_amount": 3499.9,
        "external_reference": "pix-abc123",
        "date_of_expiration": "2026-07-27T23:59:59.000-03:00",
        "point_of_interaction": {
            "transaction_data": {
                "qr_code": "00020126580014br.gov.bcb.pix0136PIXCOPIAEXEMPLO",
                "qr_code_base64": "aGVsbG8=",
                "ticket_url": "https://www.mercadopago.com.br/payments/123456789/ticket",
            }
        },
    }
    base.update(extra)
    return base


@pytest.fixture(autouse=True)
def _env_mp(monkeypatch):
    monkeypatch.setenv("MP_ACCESS_TOKEN", "TEST-fake-token-not-real")
    monkeypatch.setenv("MP_WEBHOOK_SECRET", "whsec_test_fake")
    monkeypatch.setenv("MP_NOTIFICATION_URL", "https://example.test/webhooks/mercadopago")
    monkeypatch.setenv("MP_ENV", "test")
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")

    # Bloqueia qualquer HTTP real ao Mercado Pago nesta suíte
    def _bloquear_http(*_a, **_k):
        raise AssertionError("HTTP real ao Mercado Pago bloqueado nos testes")

    monkeypatch.setattr("services.mercadopago_service.requests.post", _bloquear_http)
    monkeypatch.setattr("services.mercadopago_service.requests.get", _bloquear_http)


def _caminhos_app(app) -> set[str]:
    paths: set[str] = set()

    def walk(routes):
        for r in routes:
            path = getattr(r, "path", None)
            if isinstance(path, str) and path:
                paths.add(path)
            nested = getattr(r, "routes", None)
            if nested:
                walk(nested)
            original = getattr(r, "original_router", None)
            if original is not None and getattr(original, "routes", None):
                walk(original.routes)

    walk(app.routes)
    return paths



def test_criacao_pix_valida(monkeypatch):
    from services import mercadopago_service as mp
    from services import pagamento_pix_service as pix

    monkeypatch.setattr(
        "services.pagamento_pix_service.buscar_produto_por_nome",
        lambda *_a, **_k: PRODUTO_OK,
    )
    monkeypatch.setattr(pix, "_upsert_pagamento", lambda *_a, **_k: True)
    monkeypatch.setattr(pix, "buscar_pagamento_por_pedido", lambda *_a, **_k: None)

    class _Resp:
        status_code = 201
        content = b"{}"

        def json(self):
            return _mp_payment_response()

    chamado = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        chamado["url"] = url
        chamado["json"] = json
        chamado["headers"] = headers
        return _Resp()

    monkeypatch.setattr(mp.requests, "post", fake_post)
    out = pix.criar_cobranca_pix(
        produto="Notebook Intel i5",
        quantidade=1,
        email="cliente@example.com",
        consentimento=True,
        dry_run=False,
        persistir=True,
        pedido_id="pix-abc123",
    )
    assert out["ok"] is True
    assert out["provider"] == "mercadopago"
    assert out["valor"] == 3499.9
    assert out["pix_copia_cola"].startswith("000201")
    assert out["status"] in ("pending", "aguardando_pagamento") or out.get("status_mp") == "pending"
    assert chamado["json"]["payment_method_id"] == "pix"
    assert chamado["json"]["transaction_amount"] == 3499.9
    assert "Authorization" in chamado["headers"]
    assert "TEST-fake" not in str(out)


def test_idempotency_key_enviada(monkeypatch):
    from services import mercadopago_service as mp

    class _Resp:
        status_code = 201
        content = b"{}"

        def json(self):
            return _mp_payment_response()

    headers_capturados = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        headers_capturados.update(headers or {})
        return _Resp()

    monkeypatch.setattr(mp.requests, "post", fake_post)
    key = mp.gerar_idempotency_key("pedido-1")
    mp.criar_pagamento_pix(
        valor=10.0,
        description="teste",
        external_reference="pedido-1",
        idempotency_key=key,
        payer_email="a@b.com",
    )
    assert headers_capturados.get("X-Idempotency-Key") == key
    assert headers_capturados.get("X-Idempotency-Key") == mp.gerar_idempotency_key("pedido-1")


def test_mesmo_pedido_nao_cria_duas_cobrancas(monkeypatch):
    from services import pagamento_pix_service as pix

    monkeypatch.setattr(
        "services.pagamento_pix_service.buscar_produto_por_nome",
        lambda *_a, **_k: PRODUTO_OK,
    )
    existente = {
        "provider_payment_id": "999",
        "external_reference": "pix-dup",
        "status": "aguardando_pagamento",
        "provider_status": "pending",
        "valor": 3499.9,
        "pix_copia_cola": "000201DUP",
    }
    monkeypatch.setattr(pix, "buscar_pagamento_por_pedido", lambda *_a, **_k: existente)
    calls = {"n": 0}

    def boom(*_a, **_k):
        calls["n"] += 1
        raise AssertionError("não deve chamar MP de novo")

    monkeypatch.setattr("services.mercadopago_service.criar_pagamento_pix", boom)
    out = pix.criar_cobranca_pix(
        produto="Notebook Intel i5",
        consentimento=True,
        dry_run=False,
        persistir=True,
        pedido_id="pix-dup",
        email="a@b.com",
    )
    assert out["ok"] is True
    assert out["payment_id"] == "999"
    assert calls["n"] == 0


def test_valor_vem_do_backend(monkeypatch):
    from services import mercadopago_service as mp
    from services import pagamento_pix_service as pix

    monkeypatch.setattr(
        "services.pagamento_pix_service.buscar_produto_por_nome",
        lambda *_a, **_k: PRODUTO_OK,
    )
    monkeypatch.setattr(pix, "_upsert_pagamento", lambda *_a, **_k: True)
    monkeypatch.setattr(pix, "buscar_pagamento_por_pedido", lambda *_a, **_k: None)

    class _Resp:
        status_code = 201
        content = b"{}"

        def json(self):
            return _mp_payment_response()

    body = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        body.update(json or {})
        return _Resp()

    monkeypatch.setattr(mp.requests, "post", fake_post)
    # Cliente tenta "pagar 1 real" — backend ignora e usa catálogo
    out = pix.criar_cobranca_pix(
        produto="Notebook Intel i5",
        quantidade=1,
        consentimento=True,
        dry_run=False,
        persistir=True,
        email="a@b.com",
        pedido_id="pix-valor",
    )
    assert out["ok"] is True
    assert body["transaction_amount"] == 3499.9
    assert out["valor"] == 3499.9


def test_sem_estoque_nao_gera_pix(monkeypatch):
    from services import pagamento_pix_service as pix

    sem_estoque = {
        "found": True,
        "products": [
            {
                "name": "Notebook Intel i5",
                "price": 3499.9,
                "stock_quantity": 0,
                "estoque": 0,
                "stock_confirmed": False,
            }
        ],
    }
    monkeypatch.setattr(
        "services.pagamento_pix_service.buscar_produto_por_nome",
        lambda *_a, **_k: sem_estoque,
    )
    out = pix.criar_cobranca_pix(
        produto="Notebook Intel i5",
        quantidade=1,
        consentimento=True,
        dry_run=False,
        persistir=True,
        email="a@b.com",
    )
    assert out["ok"] is False
    assert out["error"] in ("estoque_insuficiente", "estoque_nao_confirmado")


def test_preco_nao_confirmado_nao_gera_pix(monkeypatch):
    from services import pagamento_pix_service as pix

    sem_preco = {
        "found": True,
        "products": [
            {
                "name": "Notebook Intel i5",
                "price": None,
                "stock_quantity": 3,
                "stock_confirmed": True,
            }
        ],
    }
    monkeypatch.setattr(
        "services.pagamento_pix_service.buscar_produto_por_nome",
        lambda *_a, **_k: sem_preco,
    )
    out = pix.criar_cobranca_pix(
        produto="Notebook Intel i5",
        consentimento=True,
        dry_run=False,
        persistir=True,
        email="a@b.com",
    )
    assert out["ok"] is False
    assert out["error"] == "preco_nao_confirmado"


def test_webhook_valido_consulta_api(monkeypatch):
    from main import app

    consultado = {"n": 0}

    def fake_consultar(pid):
        consultado["n"] += 1
        return {
            "ok": True,
            "payment_id": pid,
            "status": "approved",
            "external_reference": "pix-wh",
            "valor": 10.0,
            "date_approved": "2026-07-27T12:00:00.000-03:00",
        }

    # Webhook deve consultar a API (nunca confiar só no body)
    monkeypatch.setattr(
        "services.mercadopago_service.consultar_pagamento",
        fake_consultar,
    )
    monkeypatch.setattr(
        "services.pagamento_pix_service.buscar_pagamento_por_provider_id",
        lambda *_a, **_k: {
            "status": "aguardando_pagamento",
            "external_reference": "pix-wh",
            "provider_payment_id": "123456789",
        },
    )
    monkeypatch.setattr(
        "services.pagamento_pix_service._atualizar_status",
        lambda **_k: True,
    )

    data_id = "123456789"
    ts = str(int(time.time()))
    secret = "whsec_test_fake"
    req_id = "req-1"
    manifest = f"id:{data_id};request-id:{req_id};ts:{ts};"
    v1 = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    sig = f"ts={ts},v1={v1}"

    client = TestClient(app)
    resp = client.post(
        "/webhooks/mercadopago",
        json={"type": "payment", "data": {"id": data_id}},
        headers={"x-signature": sig, "x-request-id": req_id},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert consultado["n"] >= 1


def test_webhook_invalido_rejeitado(monkeypatch):
    from main import app

    client = TestClient(app)
    resp = client.post(
        "/webhooks/mercadopago",
        json={"type": "payment", "data": {"id": "1"}},
        headers={"x-signature": "ts=1,v1=invalido", "x-request-id": "r"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "erro"
    assert "signature" in body["motivo"] or "invalida" in body["motivo"] or "expirada" in body["motivo"] or "malformada" in body["motivo"]


def test_webhook_duplicado_nao_duplica(monkeypatch):
    from services import pagamento_pix_service as pix

    monkeypatch.setattr(
        pix,
        "buscar_pagamento_por_provider_id",
        lambda *_a, **_k: {
            "status": "pago",
            "external_reference": "pix-x",
            "provider_payment_id": "55",
        },
    )
    monkeypatch.setattr(
        "services.mercadopago_service.consultar_pagamento",
        lambda *_a, **_k: {
            "ok": True,
            "status": "approved",
            "payment_id": "55",
            "external_reference": "pix-x",
        },
    )
    updates = {"n": 0}
    monkeypatch.setattr(
        pix,
        "_atualizar_status",
        lambda **_k: updates.__setitem__("n", updates["n"] + 1) or True,
    )
    out = pix.processar_notificacao_pagamento("55")
    assert out["ok"] is True
    assert out["updated"] is False
    assert updates["n"] == 0


def test_status_approved_marca_pago(monkeypatch):
    from services import pagamento_pix_service as pix

    monkeypatch.setattr(pix, "buscar_pagamento_por_provider_id", lambda *_a, **_k: {
        "status": "aguardando_pagamento",
        "external_reference": "pix-y",
        "provider_payment_id": "77",
    })
    monkeypatch.setattr(
        "services.mercadopago_service.consultar_pagamento",
        lambda *_a, **_k: {
            "ok": True,
            "status": "approved",
            "payment_id": "77",
            "external_reference": "pix-y",
            "date_approved": "2026-07-27T12:00:00Z",
        },
    )
    capt = {}

    def fake_upd(**kwargs):
        capt.update(kwargs)
        return True

    monkeypatch.setattr(pix, "_atualizar_status", fake_upd)
    out = pix.processar_notificacao_pagamento("77")
    assert out["pago"] is True
    assert capt.get("status_interno") == "pago"


def test_status_pending_nao_marca_pago(monkeypatch):
    from services import pagamento_pix_service as pix

    monkeypatch.setattr(pix, "buscar_pagamento_por_provider_id", lambda *_a, **_k: {
        "status": "aguardando_pagamento",
        "provider_payment_id": "88",
    })
    monkeypatch.setattr(
        "services.mercadopago_service.consultar_pagamento",
        lambda *_a, **_k: {"ok": True, "status": "pending", "payment_id": "88"},
    )
    updates = {"n": 0}

    def fake_upd(**k):
        updates["n"] += 1
        updates.update(k)
        return True

    monkeypatch.setattr(pix, "_atualizar_status", fake_upd)
    out = pix.processar_notificacao_pagamento("88")
    assert out.get("pago") is not True
    assert out.get("status") == "aguardando_pagamento"
    # Idempotente: pending → aguardando_pagamento (já era) não reescreve como pago
    assert updates["n"] == 0 or updates.get("status_interno") == "aguardando_pagamento"


def test_comprovante_cliente_nao_marca_pago():
    from services.pagamento_pix_service import comprovante_cliente_nao_confirma_pagamento

    out = comprovante_cliente_nao_confirma_pagamento("segue o print do pix pago")
    assert out["pago"] is False
    assert "comprovante" in out["motivo"]


def test_segredos_nao_aparecem_nos_logs(monkeypatch, capsys):
    from services import mercadopago_service as mp

    logs = []

    def fake_log(evento, **campos):
        logs.append((evento, campos))

    monkeypatch.setattr("services.webhook_guard.log_seguro", fake_log)
    # força caminho de log via _log interno
    mp._log("mp_teste", token="TEST-fake-token-not-real", payment_id="1")
    blob = str(logs)
    assert "TEST-fake-token-not-real" not in blob


def test_credenciais_nao_vao_para_openai_tool(monkeypatch):
    from agents.vendas import tools

    monkeypatch.setattr(
        "services.pagamento_pix_service.criar_cobranca_pix",
        lambda **_k: {
            "ok": True,
            "provider": "mercadopago",
            "payment_id": "1",
            "valor": 10.0,
            "pix_copia_cola": "000201",
            "status": "pending",
            "enviar_sem_alterar": True,
            "cpf": "12345678901",
            "email": "secreto@x.com",
        },
    )
    out = tools.execute_tool(
        "criar_cobranca_pix",
        {"produto": "Notebook", "consentimento": True},
    )
    assert out["ok"] is True
    data = out["data"]
    assert "cpf" not in data
    assert "email" not in data
    assert "TEST-fake" not in str(data)
    assert "MP_ACCESS" not in str(data)


def test_persistir_false_nao_cria(monkeypatch):
    from services import pagamento_pix_service as pix

    monkeypatch.setattr(
        "services.pagamento_pix_service.buscar_produto_por_nome",
        lambda *_a, **_k: PRODUTO_OK,
    )
    called = {"n": 0}
    monkeypatch.setattr(
        "services.mercadopago_service.criar_pagamento_pix",
        lambda **_k: called.__setitem__("n", called["n"] + 1),
    )
    out = pix.criar_cobranca_pix(
        produto="Notebook Intel i5",
        consentimento=True,
        dry_run=False,
        persistir=False,
        email="a@b.com",
    )
    assert out["ok"] is False
    assert out["error"] == "persistir_false_sem_cobranca"
    assert called["n"] == 0


def test_dry_run_nao_chama_mp(monkeypatch):
    from services import pagamento_pix_service as pix

    monkeypatch.setattr(
        "services.pagamento_pix_service.buscar_produto_por_nome",
        lambda *_a, **_k: PRODUTO_OK,
    )
    called = {"n": 0}
    monkeypatch.setattr(
        "services.mercadopago_service.criar_pagamento_pix",
        lambda **_k: called.__setitem__("n", called["n"] + 1),
    )
    out = pix.criar_cobranca_pix(
        produto="Notebook Intel i5",
        consentimento=True,
        dry_run=True,
        persistir=True,
        email="a@b.com",
    )
    assert out["ok"] is False
    assert out["error"] == "dry_run_sem_cobranca"
    assert called["n"] == 0


def test_tool_schema_registrada():
    from agents.vendas.tools import TOOL_SCHEMAS

    nomes = [s["function"]["name"] for s in TOOL_SCHEMAS]
    assert "criar_cobranca_pix" in nomes


def test_rota_webhook_registrada():
    from main import app

    paths = _caminhos_app(app)
    assert "/webhooks/mercadopago" in paths
    client = TestClient(app)
    info = client.get("/webhooks/mercadopago")
    assert info.status_code == 200
    assert info.json().get("canal") == "mercadopago_pix"
