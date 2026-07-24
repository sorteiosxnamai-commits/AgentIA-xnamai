"""Facade de envio WhatsApp — somente Brevo.

Z-API e UltraMsg foram removidos. Todo envio outbound passa por brevo_service.
"""

from __future__ import annotations

from services.env_loader import carregar_env

carregar_env()


def provider_nome() -> str:
    return "brevo"


def whatsapp_configurado() -> bool:
    from services.brevo_service import brevo_configurado_envio

    return bool(brevo_configurado_envio())


def enviar_mensagem(numero: str, mensagem: str):
    from services.brevo_service import enviar_resposta
    from services.texto_seguro import aplicar_formatador_final
    from services.webhook_guard import log_seguro

    texto, _dbg = aplicar_formatador_final(mensagem or "")
    log_seguro("whatsapp_provider_usado", provider="brevo")
    return enviar_resposta(texto, telefone=numero)


def enviar_imagem(numero: str, url_imagem: str, legenda: str = ""):
    """Imagem via Brevo WhatsApp ainda não está no canal transacional atual."""
    from services.webhook_guard import log_seguro

    log_seguro("whatsapp_provider_usado", provider="brevo", tipo="imagem")
    _ = (numero, url_imagem, legenda)
    return {
        "ok": False,
        "error": "brevo_envio_imagem_nao_disponivel",
        "provider": "brevo",
        "hint": "Use texto com link da imagem ou o fluxo Brevo Conversations.",
    }
