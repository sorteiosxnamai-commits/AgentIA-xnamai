"""Parser defensivo de webhooks Brevo Conversations / WhatsApp-like.

Não define identidade do agente — Brevo é apenas o canal técnico.
"""

from __future__ import annotations

from typing import Any


def _get_nested(data: dict[str, Any], *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        text = str(value).strip()
        if text:
            return text
    return None


def _extract_visitor(payload: dict[str, Any]) -> dict[str, Any]:
    visitor = payload.get("visitor")
    return visitor if isinstance(visitor, dict) else {}


def _extract_last_visitor_message(payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return {}
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("type") == "visitor":
            return message
    return {}


def _extract_primary_message(payload: dict[str, Any]) -> dict[str, Any]:
    last_visitor = _extract_last_visitor_message(payload)
    if last_visitor:
        return last_visitor
    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict):
            return last
    return {}


def _is_audio_file(obj: dict[str, Any] | None) -> bool:
    if not isinstance(obj, dict):
        return False
    mime = str(obj.get("mimeType") or obj.get("mimetype") or "").lower()
    name = str(obj.get("name") or "").lower()
    if mime.startswith("audio/") or "ogg" in mime or "opus" in mime:
        return True
    return any(name.endswith(ext) for ext in (".ogg", ".opus", ".mp3", ".m4a", ".wav", ".webm"))


def _extract_audio(message: dict[str, Any]) -> dict[str, Any] | None:
    if not message:
        return None
    file_obj = message.get("file")
    if isinstance(file_obj, dict) and _is_audio_file(file_obj) and file_obj.get("link"):
        return file_obj
    attachments = message.get("attachments")
    if isinstance(attachments, list):
        for attachment in attachments:
            if isinstance(attachment, dict) and _is_audio_file(attachment) and attachment.get("link"):
                return attachment
    return None


def should_skip_auto_reply(payload: dict[str, Any]) -> bool:
    """Ignora eco do agente / mensagens empurradas (não do visitante)."""
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        # Payload flat: se fromMe explícito
        if payload.get("fromMe") is True or payload.get("isFromAgent") is True:
            return True
        return False

    last = messages[-1]
    if not isinstance(last, dict):
        return False
    if last.get("type") != "visitor":
        return True
    return bool(last.get("isPushed") or last.get("isTrigger") or last.get("fromMe"))


def parse_brevo_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extrai campos úteis do webhook Brevo (texto/áudio/ids)."""
    visitor_obj = _extract_visitor(payload)
    msg = _extract_primary_message(payload)
    audio_file = _extract_audio(msg)

    text = _first_non_empty(
        msg.get("text") if isinstance(msg.get("text"), str) else None,
        msg.get("body") if isinstance(msg.get("body"), str) else None,
        payload.get("text"),
        payload.get("message") if isinstance(payload.get("message"), str) else None,
        payload.get("body"),
        payload.get("content"),
    ) or ""

    sender_phone = _first_non_empty(
        payload.get("sender"),
        payload.get("from"),
        payload.get("phone"),
        payload.get("waId"),
        payload.get("wa_id"),
        payload.get("contactNumber"),
        payload.get("contact_number"),
        payload.get("contactNumbers")[0]
        if isinstance(payload.get("contactNumbers"), list) and payload.get("contactNumbers")
        else None,
        _get_nested(payload, "contact", "phone"),
        _get_nested(payload, "contact", "whatsapp"),
        _get_nested(payload, "contact", "whatsApp"),
        _get_nested(payload, "sender", "phone"),
        _get_nested(payload, "from", "phone"),
        _get_nested(visitor_obj, "attributes", "SMS"),
        _get_nested(visitor_obj, "attributes", "WHATSAPP"),
        _get_nested(visitor_obj, "attributes", "PHONE"),
        _get_nested(visitor_obj, "contactAttributes", "SMS"),
        _get_nested(visitor_obj, "contactAttributes", "WHATSAPP"),
        _get_nested(visitor_obj, "contactAttributes", "PHONE"),
        _get_nested(visitor_obj, "formattedAttributes", "SMS"),
        _get_nested(visitor_obj, "formattedAttributes", "WHATSAPP"),
        msg.get("from"),
        msg.get("waId"),
        msg.get("phone"),
    )

    # Áudio também no payload raiz (webhooks WA flat)
    if not audio_file:
        audio_file = _extract_audio(payload) or _extract_audio(
            payload.get("message") if isinstance(payload.get("message"), dict) else {}
        )
        root_media = payload.get("media") or payload.get("audio") or payload.get("voice")
        if isinstance(root_media, str) and root_media.startswith("http"):
            audio_file = {"link": root_media, "mimeType": "audio/ogg", "name": "voice.ogg"}
        elif isinstance(root_media, dict) and (
            root_media.get("link") or root_media.get("url")
        ):
            audio_file = {
                "link": root_media.get("link") or root_media.get("url"),
                "mimeType": root_media.get("mimeType")
                or root_media.get("mimetype")
                or "audio/ogg",
                "name": root_media.get("name") or "voice.ogg",
            }

    sender_name = _first_non_empty(
        payload.get("name"),
        payload.get("senderName"),
        _get_nested(payload, "contact", "name"),
        _get_nested(visitor_obj, "displayedName"),
        _get_nested(visitor_obj, "attributes", "FIRSTNAME"),
    )

    visitor_id = _first_non_empty(payload.get("visitorId"), visitor_obj.get("id"))
    contact_id = _first_non_empty(
        payload.get("contactId"),
        payload.get("contact_id"),
        _get_nested(payload, "contact", "id"),
        visitor_obj.get("contactId"),
    )
    conversation_id = _first_non_empty(
        payload.get("conversationId"),
        payload.get("conversation_id"),
        payload.get("threadId"),
        visitor_obj.get("threadId"),
    )
    message_id = _first_non_empty(
        payload.get("id"),
        payload.get("messageId"),
        payload.get("message_id"),
        msg.get("id"),
    )

    input_modality = "text"
    audio_url = None
    audio_mime = None
    if audio_file:
        input_modality = "audio"
        audio_url = str(audio_file.get("link") or "").strip() or None
        audio_mime = str(audio_file.get("mimeType") or audio_file.get("mimetype") or "")
        # Placeholder típico de áudio
        if text.strip().lower() in {"", "audio", "voice", "ptt", "(audio)", "[audio]"}:
            text = ""

    return {
        "text": text,
        "sender_phone": sender_phone,
        "sender_name": sender_name,
        "visitor_id": visitor_id,
        "contact_id": contact_id,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "input_modality": input_modality,
        "audio_url": audio_url,
        "audio_mime": audio_mime,
        "from_me": should_skip_auto_reply(payload),
    }


def normalizar_para_webhook_interno(payload: dict[str, Any]) -> dict[str, Any]:
    """Converte payload Brevo no formato interno usado por ``processar_mensagem``."""
    parsed = parse_brevo_payload(payload)
    phone = parsed.get("sender_phone") or ""
    if not phone and parsed.get("visitor_id"):
        # Chave estável para memória/cliente quando o telefone não veio no payload
        phone = f"brevo{str(parsed['visitor_id']).replace('-', '')[:18]}"

    tipo = "audio" if parsed.get("input_modality") == "audio" else "chat"
    return {
        "event_type": "message_received",
        "provider": "brevo",
        "data": {
            "from": phone,
            "body": parsed.get("text") or "",
            "pushname": parsed.get("sender_name") or "",
            "fromMe": bool(parsed.get("from_me")),
            "type": tipo,
            "id": parsed.get("message_id") or "",
            "time": __import__("time").time(),
            "input_modality": parsed.get("input_modality") or "text",
            "audio_url": parsed.get("audio_url") or "",
            "audio_mime": parsed.get("audio_mime") or "",
            "visitor_id": parsed.get("visitor_id") or "",
            "contact_id": parsed.get("contact_id") or "",
            "conversation_id": parsed.get("conversation_id") or "",
        },
        "brevo_meta": {
            "visitor_id": parsed.get("visitor_id"),
            "contact_id": parsed.get("contact_id"),
            "conversation_id": parsed.get("conversation_id"),
            "message_id": parsed.get("message_id"),
        },
    }
