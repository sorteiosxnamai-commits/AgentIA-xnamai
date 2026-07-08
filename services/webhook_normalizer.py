"""Normaliza webhooks Z-API e UltraMsg para o formato interno do agente."""


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


def normalizar_webhook(data: dict) -> dict | None:
    """Converte payload externo para {event_type, data:{from, body, ...}}."""
    if not isinstance(data, dict):
        return None

    if data.get("type") == "ReceivedCallback":
        if data.get("isGroup"):
            return None
        if data.get("fromMe"):
            return None
        if data.get("isStatusReply"):
            return None

        mensagem = _extrair_texto_zapi(data)
        if not mensagem:
            return None

        phone = str(data.get("phone") or "").strip()
        if not phone:
            return None

        return {
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

    if "data" in data:
        payload = dict(data)
        payload.setdefault("provider", "ultramsg")
        payload.setdefault("event_type", data.get("event_type") or "message_received")
        return payload

    return None
