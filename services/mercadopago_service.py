"""Cliente Mercado Pago — Pix (backend only).

Nunca registra Access Token em logs. Timeout e erros controlados.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
import uuid
from typing import Any

import requests

from services.env_loader import carregar_env

carregar_env()

MP_API_BASE = "https://api.mercadopago.com"
DEFAULT_TIMEOUT = 20.0


def _log(evento: str, **campos: Any) -> None:
    try:
        from services.webhook_guard import log_seguro

        log_seguro(evento, **{k: v for k, v in campos.items() if k not in ("token", "access_token", "authorization")})
    except Exception:
        print(evento, {k: v for k, v in campos.items() if "token" not in k.lower()})


def mp_env() -> str:
    return (os.getenv("MP_ENV") or "test").strip().lower()


def mp_access_token() -> str:
    return (os.getenv("MP_ACCESS_TOKEN") or "").strip()


def mp_webhook_secret() -> str:
    return (os.getenv("MP_WEBHOOK_SECRET") or "").strip()


def mp_notification_url() -> str:
    return (os.getenv("MP_NOTIFICATION_URL") or "").strip()


def mp_configurado() -> bool:
    return bool(mp_access_token())


def mp_pix_enabled() -> bool:
    """Trava geral: Pix só cria cobrança se MP_PIX_ENABLED=true. Default false."""
    raw = (os.getenv("MP_PIX_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes", "sim", "on")


def mp_em_producao() -> bool:
    return mp_env() in ("production", "prod", "live")


def _timeout() -> float:
    try:
        return max(5.0, float(os.getenv("MP_TIMEOUT_SEGUNDOS", str(DEFAULT_TIMEOUT)) or DEFAULT_TIMEOUT))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT


def _headers(idempotency_key: str | None = None) -> dict[str, str]:
    token = mp_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    return headers


def gerar_idempotency_key(pedido_id: str) -> str:
    """Chave estável por pedido — não regenerar na mesma cobrança."""
    base = f"xnamai-pix:{str(pedido_id).strip()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _extrair_pix(payment: dict[str, Any]) -> dict[str, Any]:
    poi = payment.get("point_of_interaction") or {}
    td = poi.get("transaction_data") or {}
    if not isinstance(td, dict):
        td = {}
    return {
        "pix_copia_cola": (td.get("qr_code") or "").strip() or None,
        "qr_code_base64": (td.get("qr_code_base64") or "").strip() or None,
        "ticket_url": (td.get("ticket_url") or payment.get("transaction_details", {}).get("external_resource_url") or "").strip()
        or None,
    }


def normalizar_pagamento(payment: dict[str, Any]) -> dict[str, Any]:
    """Normaliza resposta MP para o contrato interno (sem credenciais)."""
    if not isinstance(payment, dict):
        return {"ok": False, "error": "pagamento_invalido", "provider": "mercadopago"}

    status_mp = str(payment.get("status") or "").strip().lower()
    pix = _extrair_pix(payment)
    valor = payment.get("transaction_amount")
    try:
        valor_f = float(valor) if valor is not None else None
    except (TypeError, ValueError):
        valor_f = None

    return {
        "ok": True,
        "provider": "mercadopago",
        "payment_id": str(payment.get("id") or "").strip() or None,
        "external_reference": str(payment.get("external_reference") or "").strip() or None,
        "status": status_mp or "unknown",
        "status_detail": str(payment.get("status_detail") or "").strip() or None,
        "valor": valor_f,
        "pix_copia_cola": pix.get("pix_copia_cola"),
        "qr_code_base64": pix.get("qr_code_base64"),
        "ticket_url": pix.get("ticket_url"),
        "expira_em": (
            (payment.get("date_of_expiration") or "")
            or ((payment.get("point_of_interaction") or {}).get("transaction_data") or {}).get("expiration_date")
            or None
        ),
        "date_created": payment.get("date_created"),
        "date_approved": payment.get("date_approved"),
    }


def mapear_status_interno(status_mp: str) -> str:
    s = (status_mp or "").strip().lower()
    if s in ("approved",):
        return "pago"
    if s in ("pending", "in_process", "in_mediation"):
        return "aguardando_pagamento"
    if s in ("rejected", "cancelled", "canceled"):
        return "recusado_ou_cancelado"
    if s in ("refunded", "charged_back"):
        return "reembolsado_ou_contestado"
    return "aguardando_pagamento"


def criar_pagamento_pix(
    *,
    valor: float,
    description: str,
    external_reference: str,
    idempotency_key: str,
    payer_email: str,
    payer_first_name: str | None = None,
    payer_last_name: str | None = None,
    payer_cpf: str | None = None,
    notification_url: str | None = None,
) -> dict[str, Any]:
    """POST /v1/payments — payment_method_id=pix."""
    if not mp_pix_enabled():
        _log("mp_pix_desabilitado", mp_env=mp_env())
        return {"ok": False, "error": "pix_temporariamente_indisponivel", "provider": "mercadopago"}
    if not mp_configurado():
        return {"ok": False, "error": "mp_access_token_ausente", "provider": "mercadopago"}

    if not mp_em_producao():
        _log("mp_ambiente_teste", mp_env=mp_env())

    try:
        amount = round(float(valor), 2)
    except (TypeError, ValueError):
        return {"ok": False, "error": "valor_invalido", "provider": "mercadopago"}
    if amount <= 0:
        return {"ok": False, "error": "valor_invalido", "provider": "mercadopago"}

    email = (payer_email or "").strip()
    if not email or "@" not in email:
        return {"ok": False, "error": "payer_email_obrigatorio", "provider": "mercadopago"}

    notif = (notification_url or mp_notification_url() or "").strip()
    payer: dict[str, Any] = {"email": email}
    if payer_first_name:
        payer["first_name"] = str(payer_first_name).strip()[:60]
    if payer_last_name:
        payer["last_name"] = str(payer_last_name).strip()[:60]
    cpf_digits = re.sub(r"\D", "", payer_cpf or "")
    if cpf_digits:
        payer["identification"] = {"type": "CPF", "number": cpf_digits}

    body: dict[str, Any] = {
        "transaction_amount": amount,
        "description": (description or "Pedido xNamai")[:230],
        "payment_method_id": "pix",
        "external_reference": str(external_reference).strip()[:256],
        "payer": payer,
    }
    if notif:
        body["notification_url"] = notif

    url = f"{MP_API_BASE}/v1/payments"
    try:
        resp = requests.post(
            url,
            json=body,
            headers=_headers(idempotency_key),
            timeout=_timeout(),
        )
    except requests.Timeout:
        _log("mp_pix_timeout", external_reference=external_reference[:40])
        return {"ok": False, "error": "mp_timeout", "provider": "mercadopago"}
    except requests.RequestException as exc:
        _log("mp_pix_erro_rede", erro=type(exc).__name__)
        return {"ok": False, "error": f"mp_rede:{type(exc).__name__}", "provider": "mercadopago"}

    try:
        data = resp.json() if resp.content else {}
    except Exception:
        data = {}

    if resp.status_code >= 400 or not isinstance(data, dict):
        _log(
            "mp_pix_http_erro",
            status=resp.status_code,
            external_reference=external_reference[:40],
            mp_status=(data.get("message") or data.get("error") or "")[:80] if isinstance(data, dict) else "",
        )
        return {
            "ok": False,
            "error": "mp_http_erro",
            "provider": "mercadopago",
            "http_status": resp.status_code,
        }

    out = normalizar_pagamento(data)
    out["idempotency_key"] = idempotency_key
    _log(
        "mp_pix_criado",
        payment_id=out.get("payment_id") or "-",
        status=out.get("status") or "-",
        mp_env=mp_env(),
        producao=mp_em_producao(),
    )
    return out


def consultar_pagamento(payment_id: str) -> dict[str, Any]:
    """GET /v1/payments/{id} — fonte de verdade do status."""
    pid = str(payment_id or "").strip()
    if not pid:
        return {"ok": False, "error": "payment_id_ausente", "provider": "mercadopago"}
    if not mp_configurado():
        return {"ok": False, "error": "mp_access_token_ausente", "provider": "mercadopago"}

    url = f"{MP_API_BASE}/v1/payments/{pid}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=_timeout())
    except requests.Timeout:
        return {"ok": False, "error": "mp_timeout", "provider": "mercadopago"}
    except requests.RequestException as exc:
        return {"ok": False, "error": f"mp_rede:{type(exc).__name__}", "provider": "mercadopago"}

    try:
        data = resp.json() if resp.content else {}
    except Exception:
        data = {}

    if resp.status_code >= 400 or not isinstance(data, dict):
        _log("mp_consulta_http_erro", status=resp.status_code, payment_id=pid[:40])
        return {"ok": False, "error": "mp_http_erro", "provider": "mercadopago", "http_status": resp.status_code}

    return normalizar_pagamento(data)


def validar_assinatura_webhook(
    *,
    x_signature: str | None,
    x_request_id: str | None,
    data_id: str | None,
) -> tuple[bool, str]:
    """Valida x-signature do Mercado Pago (HMAC-SHA256)."""
    secret = mp_webhook_secret()
    if not secret:
        if mp_em_producao():
            return False, "mp_webhook_secret_ausente"
        _log("mp_webhook_secret_ausente_dev")
        return True, "secret_ausente_dev"

    sig = (x_signature or "").strip()
    if not sig:
        return False, "missing_signature"

    # Formato: ts=...,v1=...
    partes = {}
    for chunk in sig.split(","):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            partes[k.strip()] = v.strip()
    ts = partes.get("ts") or ""
    v1 = partes.get("v1") or ""
    if not ts or not v1:
        return False, "signature_malformada"

    # Janela de 5 minutos
    try:
        idade = abs(time.time() - int(ts))
        if idade > 300:
            return False, "signature_expirada"
    except (TypeError, ValueError):
        return False, "signature_ts_invalido"

    manifest = f"id:{data_id or ''};request-id:{x_request_id or ''};ts:{ts};"
    esperado = hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(esperado, v1):
        return False, "signature_invalida"
    return True, "ok"


def novo_pedido_interno_id() -> str:
    return f"pix-{uuid.uuid4().hex[:16]}"
