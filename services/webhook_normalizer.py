"""Normaliza webhooks Z-API e UltraMsg para o formato interno do agente."""

from __future__ import annotations

import json
import os
from typing import Any


def _truthy_flag(valor: Any) -> bool:
    if valor is True or valor is False:
        return bool(valor)
    if isinstance(valor, (int, float)):
        return valor == 1
    if isinstance(valor, str):
        return valor.strip().lower() in ("1", "true", "sim", "yes")
    return False


def _extrair_texto_zapi(data: dict) -> str:
    texto = data.get("text") or {}
    if isinstance(texto, dict):
        return (texto.get("message") or "").strip()
    if isinstance(texto, str):
        return texto.strip()
    return ""


def _timestamp_zapi(data: dict):
    momento = data.get("momment") or data.get("moment")
    if momento in (None, ""):
        return None
    try:
        valor = float(momento)
        if valor > 1_000_000_000_000:
            return valor / 1000.0
        return valor
    except (TypeError, ValueError):
        return None


def _provider_configurado() -> str:
    return (os.getenv("WHATSAPP_PROVIDER") or "zapi").strip().lower()


def _detectar_provider(data: dict) -> str:
    """Detecta provider do payload + env (UltraMsg não envia campo provider)."""
    if not isinstance(data, dict):
        return "desconhecido"
    if data.get("provider") in ("ultramsg", "zapi"):
        return str(data.get("provider"))
    if data.get("type") == "ReceivedCallback":
        return "zapi"

    evento = data.get("data")
    if isinstance(evento, str):
        try:
            evento = json.loads(evento)
        except (TypeError, ValueError, json.JSONDecodeError):
            evento = {}
    if not isinstance(evento, dict):
        evento = {}

    from_raw = str(evento.get("from") or data.get("from") or "")
    # Formato típico UltraMsg: event_type + data.from com @c.us / @g.us / @lid
    if (data.get("event_type") or data.get("instanceId") or data.get("instance_id")) and (
        "data" in data or from_raw
    ):
        return "ultramsg"
    if "@c.us" in from_raw or "@g.us" in from_raw or "@lid" in from_raw:
        return "ultramsg"
    if _provider_configurado() == "ultramsg" and (
        data.get("event_type")
        or data.get("type") in ("message_received", "message", "chat")
        or "data" in data
    ):
        return "ultramsg"
    if _provider_configurado() == "ultramsg":
        return "ultramsg"
    return "desconhecido"


def _evento_ultramsg(data: dict) -> dict:
    evento = data.get("data")
    if isinstance(evento, str) and evento.strip():
        try:
            evento = json.loads(evento)
        except (TypeError, ValueError, json.JSONDecodeError):
            evento = None
    if isinstance(evento, dict):
        return evento
    # Root simplificado
    if data.get("from") or data.get("body") or data.get("message"):
        return data
    return {}


def _texto_ultramsg(evento: dict) -> str:
    for chave in ("body", "caption", "message", "text"):
        valor = evento.get(chave)
        if isinstance(valor, dict):
            texto = (valor.get("message") or valor.get("body") or valor.get("text") or "").strip()
            if texto:
                return texto
        elif isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


def _eh_grupo_ultramsg(evento: dict, msg_id: str = "") -> bool:
    if _truthy_flag(evento.get("isGroup")) or _truthy_flag(evento.get("is_group")):
        return True
    origem = str(evento.get("from") or "").strip()
    if "@g.us" in origem:
        return True
    # id WhatsApp de grupo: false_{group}@g.us_{hash}_...
    if "@g.us" in str(msg_id or ""):
        return True
    return False


def _telefone_de_jid(jid: str) -> str:
    raw = str(jid or "").strip()
    if not raw:
        return ""
    # 5543999999999@c.us → 5543999999999
    base = raw.split("@")[0].replace("+", "").strip()
    # Remove prefixos estranhos
    if base.startswith("false_"):
        base = base[6:]
    return "".join(c for c in base if c.isdigit())


def _resultado_diag(
    *,
    ok: bool,
    payload: dict | None = None,
    motivo: str = "",
    provider_detectado: str = "desconhecido",
    tipo_evento: str = "",
    tem_texto: bool = False,
    from_me: bool = False,
    eh_grupo: bool = False,
    parse_ok: bool = False,
) -> dict:
    return {
        "ok": bool(ok),
        "payload": payload,
        "motivo_ignorado": motivo or "",
        "provider_detectado": provider_detectado,
        "tipo_evento": tipo_evento or "-",
        "tem_texto": bool(tem_texto),
        "from_me": bool(from_me),
        "eh_grupo": bool(eh_grupo),
        "parse_ok": bool(parse_ok),
    }


def analisar_webhook(data: dict) -> dict:
    """Analisa payload e devolve diagnóstico + payload normalizado (se ok)."""
    if not isinstance(data, dict):
        return _resultado_diag(ok=False, motivo="payload_invalido")

    provider = _detectar_provider(data)
    tipo_evento = str(
        data.get("event_type") or data.get("type") or ""
    ).strip().lower()

    # ---------- Z-API ----------
    if data.get("type") == "ReceivedCallback":
        from_me = _truthy_flag(data.get("fromMe"))
        eh_grupo = _truthy_flag(data.get("isGroup"))
        mensagem = _extrair_texto_zapi(data)
        if eh_grupo:
            return _resultado_diag(
                ok=False,
                motivo="mensagem_grupo_ignorada",
                provider_detectado="zapi",
                tipo_evento=tipo_evento or "ReceivedCallback",
                tem_texto=bool(mensagem),
                from_me=from_me,
                eh_grupo=True,
                parse_ok=True,
            )
        if from_me:
            return _resultado_diag(
                ok=False,
                motivo="from_me",
                provider_detectado="zapi",
                tipo_evento=tipo_evento or "ReceivedCallback",
                tem_texto=bool(mensagem),
                from_me=True,
                eh_grupo=False,
                parse_ok=True,
            )
        if _truthy_flag(data.get("isStatusReply")):
            return _resultado_diag(
                ok=False,
                motivo="status_reply",
                provider_detectado="zapi",
                tipo_evento=tipo_evento or "ReceivedCallback",
                tem_texto=bool(mensagem),
                parse_ok=True,
            )
        if not mensagem:
            return _resultado_diag(
                ok=False,
                motivo="sem_texto",
                provider_detectado="zapi",
                tipo_evento=tipo_evento or "ReceivedCallback",
                tem_texto=False,
                parse_ok=True,
            )
        phone = str(data.get("phone") or "").strip()
        if not phone:
            return _resultado_diag(
                ok=False,
                motivo="sem_telefone",
                provider_detectado="zapi",
                tipo_evento=tipo_evento or "ReceivedCallback",
                tem_texto=True,
                parse_ok=True,
            )
        payload = {
            "event_type": "message_received",
            "provider": "zapi",
            "data": {
                "from": phone,
                "body": mensagem,
                "pushname": data.get("senderName") or data.get("chatName") or "",
                "fromMe": False,
                "type": "chat",
                "id": data.get("messageId") or data.get("id") or "",
                "time": _timestamp_zapi(data),
            },
        }
        return _resultado_diag(
            ok=True,
            payload=payload,
            provider_detectado="zapi",
            tipo_evento=tipo_evento or "ReceivedCallback",
            tem_texto=True,
            parse_ok=True,
        )

    # ---------- UltraMsg (ou provider env=ultramsg) ----------
    eventos_ok = ("", "message_received", "message", "chat")
    parece_ultra = (
        provider == "ultramsg"
        or tipo_evento in ("message_received", "message")
        or "data" in data
        or data.get("from")
        or data.get("instanceId")
        or data.get("instance_id")
    )
    if not parece_ultra:
        return _resultado_diag(
            ok=False,
            motivo="formato_ou_evento_descartado",
            provider_detectado=provider,
            tipo_evento=tipo_evento or "-",
            parse_ok=False,
        )

    # Ignora acks/status UltraMsg
    if tipo_evento and tipo_evento not in eventos_ok and tipo_evento not in (
        "message_create",
        "message_ack",
    ):
        # message_create / ack → descartar com motivo claro
        if tipo_evento in ("message_ack", "message_create", "ack"):
            return _resultado_diag(
                ok=False,
                motivo=f"evento_{tipo_evento}_ignorado",
                provider_detectado="ultramsg",
                tipo_evento=tipo_evento,
                parse_ok=True,
            )
        # se WHATSAPP_PROVIDER=ultramsg e tem data, ainda tenta message_received shape
        if tipo_evento not in ("message_received", "message", "chat", ""):
            if not (isinstance(data.get("data"), (dict, str)) or data.get("body")):
                return _resultado_diag(
                    ok=False,
                    motivo="formato_ou_evento_descartado",
                    provider_detectado=provider or "ultramsg",
                    tipo_evento=tipo_evento,
                    parse_ok=False,
                )

    evento = _evento_ultramsg(data)
    if not evento:
        return _resultado_diag(
            ok=False,
            motivo="sem_data",
            provider_detectado="ultramsg",
            tipo_evento=tipo_evento or "message_received",
            parse_ok=False,
        )

    msg_id = str(
        evento.get("id")
        or data.get("id")
        or data.get("referenceId")
        or data.get("messageId")
        or ""
    ).strip()
    from_me = _truthy_flag(evento.get("fromMe")) or _truthy_flag(evento.get("self"))
    eh_grupo = _eh_grupo_ultramsg(evento, msg_id)
    body = _texto_ultramsg(evento)
    tipo_msg = str(evento.get("type") or "chat").strip().lower()

    if from_me:
        return _resultado_diag(
            ok=False,
            motivo="from_me",
            provider_detectado="ultramsg",
            tipo_evento=tipo_evento or "message_received",
            tem_texto=bool(body),
            from_me=True,
            eh_grupo=eh_grupo,
            parse_ok=True,
        )

    if eh_grupo:
        return _resultado_diag(
            ok=False,
            motivo="mensagem_grupo_ignorada",
            provider_detectado="ultramsg",
            tipo_evento=tipo_evento or "message_received",
            tem_texto=bool(body),
            from_me=False,
            eh_grupo=True,
            parse_ok=True,
        )

    if tipo_msg and tipo_msg not in ("chat", "text", ""):
        if not body:
            return _resultado_diag(
                ok=False,
                motivo="sem_texto",
                provider_detectado="ultramsg",
                tipo_evento=tipo_evento or "message_received",
                tem_texto=False,
                parse_ok=True,
            )

    if not body:
        return _resultado_diag(
            ok=False,
            motivo="sem_texto",
            provider_detectado="ultramsg",
            tipo_evento=tipo_evento or "message_received",
            tem_texto=False,
            parse_ok=True,
        )

    # Remetente privado: from (@c.us) — não usar author de grupo aqui
    origem = str(evento.get("from") or "").strip()
    phone = _telefone_de_jid(origem)
    if not phone:
        # fallback raro
        phone = _telefone_de_jid(str(evento.get("author") or ""))
    if not phone:
        return _resultado_diag(
            ok=False,
            motivo="sem_telefone",
            provider_detectado="ultramsg",
            tipo_evento=tipo_evento or "message_received",
            tem_texto=True,
            parse_ok=True,
        )

    payload = {
        "event_type": "message_received",
        "provider": "ultramsg",
        "data": {
            "from": phone,
            "body": body,
            "pushname": evento.get("pushname") or evento.get("notifyName") or "",
            "fromMe": False,
            "type": "chat",
            "id": msg_id,
            "time": evento.get("time") or data.get("time"),
        },
    }
    return _resultado_diag(
        ok=True,
        payload=payload,
        provider_detectado="ultramsg",
        tipo_evento=tipo_evento or "message_received",
        tem_texto=True,
        from_me=False,
        eh_grupo=False,
        parse_ok=True,
    )


def normalizar_webhook(data: dict) -> dict | None:
    """Converte payload externo para {event_type, data:{from, body, ...}}."""
    diag = analisar_webhook(data)
    if diag.get("ok") and isinstance(diag.get("payload"), dict):
        return diag["payload"]
    return None


def _normalizar_ultramsg(data: dict) -> dict | None:
    """Compat: mantém símbolo antigo usado em testes/imports."""
    return normalizar_webhook(data)
