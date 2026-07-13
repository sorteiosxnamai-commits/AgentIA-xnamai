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


def _normalizar_ultramsg(data: dict) -> dict | None:
    """Payload UltraMsg: {event_type, data:{from, body, pushname, id, ...}}."""
    evento = data.get("data")
    if not isinstance(evento, dict):
        # Aceita campos no root (alguns webhooks simplificados)
        if data.get("from") or data.get("body"):
            evento = data
        else:
            return None

    if evento.get("fromMe") is True or evento.get("self") is True:
        return None

    # Grupos UltraMsg: from termina com @g.us
    origem = str(evento.get("from") or evento.get("author") or "").strip()
    if "@g.us" in origem:
        return None

    tipo = (evento.get("type") or "chat").strip().lower()
    if tipo and tipo not in ("chat", "text", ""):
        # Aceita mídia com caption/body se houver texto
        body = (evento.get("body") or evento.get("caption") or "").strip()
        if not body:
            return None
    else:
        body = (evento.get("body") or "").strip()

    if not body:
        return None

    phone = origem.split("@")[0].replace("+", "").strip()
    if not phone:
        return None

    msg_id = (
        evento.get("id")
        or data.get("id")
        or data.get("referenceId")
        or data.get("messageId")
        or ""
    )

    return {
        "event_type": "message_received",
        "provider": "ultramsg",
        "data": {
            "from": phone,
            "body": body,
            "pushname": evento.get("pushname") or evento.get("notifyName") or "",
            "fromMe": False,
            "type": "chat",
            "id": str(msg_id).strip(),
            "time": evento.get("time") or data.get("time"),
        },
    }


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

    # UltraMsg (ou já normalizado com data.from/body)
    event_type = (data.get("event_type") or "").strip().lower()
    if event_type in ("", "message_received", "message") or "data" in data or data.get("from"):
        # Ignora acks/status UltraMsg
        if event_type and event_type not in ("message_received", "message"):
            return None
        return _normalizar_ultramsg(data)

    return None
