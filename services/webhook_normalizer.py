"""Normalização de webhooks legados (Z-API / UltraMsg) — desativada.

O canal ativo é Brevo (`/webhooks/brevo/whatsapp`). Payloads Z-API/UltraMsg
são ignorados de forma explícita para não processar integrações removidas.
"""

from __future__ import annotations

from typing import Any


def _detectar_provider(data: dict) -> str:
    """Identifica payload legado apenas para diagnóstico (nunca aceita)."""
    if not isinstance(data, dict):
        return "desconhecido"
    if data.get("provider") in ("ultramsg", "zapi", "brevo"):
        return str(data.get("provider"))
    if data.get("type") == "ReceivedCallback":
        return "zapi"
    if data.get("event_type") or (
        isinstance(data.get("data"), dict)
        and ("@c.us" in str((data.get("data") or {}).get("from") or ""))
    ):
        return "ultramsg"
    return "desconhecido"


def analisar_webhook(data: dict) -> dict[str, Any]:
    """Sempre rejeita webhooks legados; use o endpoint Brevo."""
    provider = _detectar_provider(data if isinstance(data, dict) else {})
    return {
        "ok": False,
        "payload": None,
        "motivo_ignorado": "legado_zapi_ultramsg_removido_use_brevo",
        "provider_detectado": provider,
        "tipo_evento": "",
        "tem_texto": False,
        "from_me": False,
        "eh_grupo": False,
        "parse_ok": False,
    }


def normalizar_webhook(data: dict) -> dict | None:
    """Compatibilidade: legado nunca normaliza para o pipeline interno."""
    _ = data
    return None
