import os

from services.env_loader import carregar_env

from services import ultramsg_service, zapi_service

carregar_env()


def _provider() -> str:
    return os.getenv("WHATSAPP_PROVIDER", "zapi").strip().lower()


def whatsapp_configurado() -> bool:
    if _provider() == "ultramsg":
        return ultramsg_service.ultramsg_configurado()
    return zapi_service.zapi_configurado()


def ultramsg_ativo() -> bool:
    return _provider() == "ultramsg"


def provider_nome() -> str:
    return _provider() or "zapi"


def enviar_mensagem(numero: str, mensagem: str):
    from services.webhook_guard import log_seguro

    prov = provider_nome()
    log_seguro("whatsapp_provider_usado", provider=prov)
    if prov == "ultramsg":
        return ultramsg_service.enviar_mensagem(numero, mensagem)
    return zapi_service.enviar_mensagem(numero, mensagem)


def enviar_imagem(numero: str, url_imagem: str, legenda: str = ""):
    from services.webhook_guard import log_seguro

    prov = provider_nome()
    log_seguro("whatsapp_provider_usado", provider=prov, tipo="imagem")
    if prov == "ultramsg":
        return ultramsg_service.enviar_imagem(numero, url_imagem, legenda)
    return zapi_service.enviar_imagem(numero, url_imagem, legenda)
