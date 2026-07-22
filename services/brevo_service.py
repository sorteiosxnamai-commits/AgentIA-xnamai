"""Cliente outbound Brevo — canal WhatsApp (provedor), não persona.

Modos de BREVO_REPLY_MODE:
- dry_run: simula envio (padrão seguro em dev)
- whatsapp: envia para o WhatsApp do cliente via API transacional Brevo
- conversations: envia via Brevo Conversations (chat web / visitorId)
- auto: WhatsApp se houver telefone real; senão Conversations

Variáveis:
- BREVO_API_KEY (obrigatória para envio live)
- BREVO_WEBHOOK_SECRET (auth do webhook)
- BREVO_BASE_URL (default https://api.brevo.com)
- BREVO_REPLY_MODE
- BREVO_SENDER_NUMBER (obrigatório no modo whatsapp — número WA com DDI, só dígitos)
- BREVO_SEND_URL (opcional; default /v3/whatsapp/sendMessage)
- BREVO_AGENT_ID ou BREVO_AGENT_EMAIL + BREVO_AGENT_NAME (modo conversations)
- BREVO_TIMEOUT_SEGUNDOS (default 20)
"""

from __future__ import annotations

import hmac
import os
import re
from typing import Any

import requests

from services.env_loader import carregar_env

carregar_env()

DEFAULT_BASE = "https://api.brevo.com"
CONVERSATIONS_PATH = "/v3/conversations/messages"
WHATSAPP_SEND_PATH = "/v3/whatsapp/sendMessage"


def _log(evento: str, **campos: Any) -> None:
    try:
        from services.webhook_guard import log_seguro

        log_seguro(evento, **campos)
    except Exception:
        print(f"EVT={evento}")


def brevo_api_key() -> str:
    return (os.getenv("BREVO_API_KEY") or "").strip()


def brevo_webhook_secret() -> str:
    return (os.getenv("BREVO_WEBHOOK_SECRET") or "").strip()


def brevo_base_url() -> str:
    return (os.getenv("BREVO_BASE_URL") or DEFAULT_BASE).strip().rstrip("/")


def brevo_reply_mode() -> str:
    # Padrão seguro em dev; produção WhatsApp deve usar whatsapp
    return (os.getenv("BREVO_REPLY_MODE") or "dry_run").strip().lower()


def brevo_timeout() -> float:
    try:
        return float(os.getenv("BREVO_TIMEOUT_SEGUNDOS") or "20")
    except ValueError:
        return 20.0


def brevo_sender_number() -> str:
    """Número WhatsApp remetente Brevo (DDI + dígitos, sem +/espaços)."""
    raw = (os.getenv("BREVO_SENDER_NUMBER") or "").strip()
    return re.sub(r"\D", "", raw)


def _telefone_whatsapp_valido(telefone: str | None) -> str:
    """Normaliza e rejeita chaves sintéticas (brevo...)."""
    from services.config_tabelas import normalizar_telefone

    if not telefone:
        return ""
    t = str(telefone).strip()
    if t.lower().startswith("brevo"):
        return ""
    digits = re.sub(r"\D", "", normalizar_telefone(t) or t)
    # WhatsApp internacional típico: 10–15 dígitos
    if len(digits) < 10 or len(digits) > 15:
        return ""
    return digits


def brevo_configurado_envio() -> bool:
    if not brevo_api_key():
        return False
    mode = brevo_reply_mode()
    if mode in ("whatsapp", "auto", "dry_run"):
        if brevo_sender_number():
            return True
    if mode in ("conversations", "auto", "dry_run"):
        if os.getenv("BREVO_AGENT_ID", "").strip():
            return True
        if os.getenv("BREVO_AGENT_EMAIL", "").strip() and os.getenv("BREVO_AGENT_NAME", "").strip():
            return True
    return bool(brevo_sender_number())


def verificar_webhook_token(provided: str | None, query_token: str | None = None) -> tuple[bool, str]:
    secret = brevo_webhook_secret()
    token = (provided or query_token or "").strip()
    if not secret:
        env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").strip().lower()
        if env in ("production", "prod"):
            return False, "webhook_secret_not_configured"
        _log("brevo_webhook_secret_ausente", modo="dev_aceito")
        return True, "secret_ausente_dev"
    if not token:
        return False, "missing_token"
    if token == "replace-with-a-random-secret":
        return False, "placeholder_token"
    if not hmac.compare_digest(token, secret):
        return False, "invalid_token"
    return True, "ok"


def _agent_payload() -> dict[str, str]:
    agent_id = (os.getenv("BREVO_AGENT_ID") or "").strip()
    if agent_id:
        return {"agentId": agent_id}
    email = (os.getenv("BREVO_AGENT_EMAIL") or "").strip()
    name = (os.getenv("BREVO_AGENT_NAME") or "xNamai Vendas").strip()
    received = (os.getenv("BREVO_RECEIVED_FROM") or name).strip()
    if email and name:
        return {"agentEmail": email, "agentName": name, "receivedFrom": received}
    return {}


def _dry_run_result(
    texto: str,
    *,
    channel: str,
    telefone: str | None = None,
    visitor_id: str | None = None,
    conversation_id: str | None = None,
    contact_id: str | None = None,
) -> dict[str, Any]:
    _log(
        "brevo_envio_dry_run",
        channel=channel,
        telefone_ok=bool(_telefone_whatsapp_valido(telefone)),
        sender_ok=bool(brevo_sender_number()),
        chars=len(texto or ""),
    )
    return {
        "ok": True,
        "dry_run": True,
        "provider": "brevo",
        "channel": channel,
        "to": _telefone_whatsapp_valido(telefone) or None,
        "sender_number": brevo_sender_number() or None,
        "visitor_id": visitor_id,
        "conversation_id": conversation_id,
        "contact_id": contact_id,
        "text": texto,
    }


def enviar_resposta_conversa(
    *,
    texto: str,
    visitor_id: str,
    conversation_id: str | None = None,
    contact_id: str | None = None,
) -> dict[str, Any]:
    """Fallback Conversations (chat). Uso principal WhatsApp = _enviar_whatsapp_transacional."""
    if brevo_reply_mode() == "dry_run" or _env_dry_run():
        return _dry_run_result(
            texto,
            channel="conversations",
            visitor_id=visitor_id,
            conversation_id=conversation_id,
            contact_id=contact_id,
        )

    api_key = brevo_api_key()
    if not api_key:
        return {"ok": False, "error": "brevo_api_key_missing", "provider": "brevo"}
    if not (visitor_id or "").strip():
        return {"ok": False, "error": "brevo_visitor_id_missing", "provider": "brevo"}

    agent = _agent_payload()
    if not agent:
        return {"ok": False, "error": "brevo_agent_not_configured", "provider": "brevo"}

    payload: dict[str, Any] = {
        "text": (texto or "").strip() or " ",
        "visitorId": visitor_id.strip(),
        **agent,
    }
    url = f"{brevo_base_url()}{CONVERSATIONS_PATH}"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": api_key,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=brevo_timeout())
        ok = 200 <= resp.status_code < 300
        if not ok:
            _log("brevo_envio_falhou", channel="conversations", status=resp.status_code)
            return {
                "ok": False,
                "error": "brevo_conversations_send_failed",
                "status_code": resp.status_code,
                "provider": "brevo",
                "channel": "conversations",
            }
        return {
            "ok": True,
            "dry_run": False,
            "status_code": resp.status_code,
            "provider": "brevo",
            "channel": "conversations",
            "visitor_id": visitor_id,
            "conversation_id": conversation_id,
            "contact_id": contact_id,
        }
    except requests.Timeout:
        return {"ok": False, "error": "brevo_timeout", "provider": "brevo", "channel": "conversations"}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"brevo_erro:{type(exc).__name__}",
            "provider": "brevo",
            "channel": "conversations",
        }


def _env_dry_run() -> bool:
    return (os.getenv("DRY_RUN") or "").strip().lower() in ("1", "true", "sim", "yes")


def enviar_resposta(
    texto: str,
    *,
    visitor_id: str | None = None,
    conversation_id: str | None = None,
    contact_id: str | None = None,
    telefone: str | None = None,
) -> dict[str, Any]:
    """Envia resposta ao cliente. Prioridade: WhatsApp (modo whatsapp/auto)."""
    mode = brevo_reply_mode()
    phone = _telefone_whatsapp_valido(telefone)

    if mode == "dry_run" or _env_dry_run():
        channel = "whatsapp" if phone else ("conversations" if visitor_id else "whatsapp")
        return _dry_run_result(
            texto,
            channel=channel,
            telefone=phone or telefone,
            visitor_id=visitor_id,
            conversation_id=conversation_id,
            contact_id=contact_id,
        )

    # Canal oficial xNamai: WhatsApp via Brevo
    if mode == "whatsapp":
        if not phone:
            return {
                "ok": False,
                "error": "recipient_phone_missing",
                "provider": "brevo",
                "channel": "whatsapp",
            }
        return _enviar_whatsapp_transacional(texto, phone)

    if mode == "conversations":
        if not visitor_id:
            return {"ok": False, "error": "brevo_visitor_id_missing", "channel": "conversations"}
        return enviar_resposta_conversa(
            texto=texto,
            visitor_id=visitor_id,
            conversation_id=conversation_id,
            contact_id=contact_id,
        )

    # auto: WhatsApp se telefone real; senão Conversations
    if phone:
        return _enviar_whatsapp_transacional(texto, phone)
    if visitor_id:
        return enviar_resposta_conversa(
            texto=texto,
            visitor_id=visitor_id,
            conversation_id=conversation_id,
            contact_id=contact_id,
        )
    return {"ok": False, "error": "brevo_recipient_missing", "provider": "brevo"}


def _enviar_whatsapp_transacional(texto: str, telefone: str) -> dict[str, Any]:
    """POST /v3/whatsapp/sendMessage — resposta no WhatsApp do cliente."""
    api_key = brevo_api_key()
    sender = brevo_sender_number()
    recipient = _telefone_whatsapp_valido(telefone)
    if not api_key:
        return {"ok": False, "error": "brevo_api_key_missing", "channel": "whatsapp"}
    if not sender:
        return {"ok": False, "error": "brevo_sender_number_missing", "channel": "whatsapp"}
    if not recipient:
        return {"ok": False, "error": "recipient_phone_missing", "channel": "whatsapp"}

    send_url = (os.getenv("BREVO_SEND_URL") or f"{brevo_base_url()}{WHATSAPP_SEND_PATH}").strip()
    payload = {
        "contactNumbers": [recipient],
        "senderNumber": sender,
        "text": (texto or "").strip() or " ",
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": api_key,
    }
    try:
        resp = requests.post(send_url, json=payload, headers=headers, timeout=brevo_timeout())
        ok = 200 <= resp.status_code < 300
        if not ok:
            _log(
                "brevo_whatsapp_envio_falhou",
                status=resp.status_code,
                # não loga números completos
                to_sufixo=recipient[-4:],
                sender_sufixo=sender[-4:],
            )
        else:
            _log(
                "brevo_whatsapp_envio_ok",
                status=resp.status_code,
                to_sufixo=recipient[-4:],
                sender_sufixo=sender[-4:],
            )
        return {
            "ok": ok,
            "dry_run": False,
            "status_code": resp.status_code,
            "error": None if ok else "brevo_whatsapp_send_failed",
            "provider": "brevo",
            "channel": "whatsapp",
            "to": recipient,
            "sender_number": sender,
        }
    except requests.Timeout:
        _log("brevo_whatsapp_timeout", to_sufixo=recipient[-4:])
        return {"ok": False, "error": "brevo_timeout", "provider": "brevo", "channel": "whatsapp"}
    except Exception as exc:
        _log("brevo_whatsapp_erro", erro=type(exc).__name__)
        return {
            "ok": False,
            "error": f"brevo_erro:{type(exc).__name__}",
            "provider": "brevo",
            "channel": "whatsapp",
        }
