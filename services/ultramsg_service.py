"""Cliente UltraMsg (WhatsApp) — usado quando WHATSAPP_PROVIDER=ultramsg."""

from __future__ import annotations

import os

import requests

from services.env_loader import carregar_env

carregar_env()


def _cfg() -> tuple[str, str, str]:
    """Lê env a cada chamada (Render/hot-reload)."""
    instance = (os.getenv("ULTRAMSG_INSTANCE_ID") or "").strip()
    token = (os.getenv("ULTRAMSG_TOKEN") or "").strip()
    api_url = (os.getenv("ULTRAMSG_API_URL") or "").strip().rstrip("/")
    return instance, token, api_url


def ultramsg_configurado() -> bool:
    instance, token, _ = _cfg()
    return bool(instance and token)


def _normalizar_numero(numero: str) -> str:
    return numero.split("@")[0].replace("+", "").strip()


def _base_url() -> str:
    """Base da API: ULTRAMSG_API_URL ou https://api.ultramsg.com/{INSTANCE_ID}."""
    instance, _, api_url = _cfg()
    if api_url:
        return api_url
    if instance:
        return f"https://api.ultramsg.com/{instance}"
    return ""


def _mascarar_token(token: str) -> str:
    if not token:
        return "-"
    if len(token) <= 4:
        return "***"
    return f"***{token[-4:]}"


def enviar_mensagem(numero, mensagem):
    return _enviar_ultramsg(
        endpoint="messages/chat",
        numero=numero,
        payload_extra={"body": mensagem},
        log_tipo="TEXTO",
        log_conteudo=(mensagem or "")[:120],
    )


def enviar_imagem(numero, url_imagem, legenda=""):
    return _enviar_ultramsg(
        endpoint="messages/image",
        numero=numero,
        payload_extra={
            "image": url_imagem,
            "caption": legenda or "Produto",
        },
        log_tipo="IMAGEM",
        log_conteudo=f"{(url_imagem or '')[:80]} | {(legenda or '')[:40]}",
    )


def _enviar_ultramsg(endpoint, numero, payload_extra, log_tipo, log_conteudo):
    from services.webhook_guard import log_seguro

    instance, token, _ = _cfg()
    try:
        if not ultramsg_configurado():
            log_seguro(
                "whatsapp_envio_erro",
                provider="ultramsg",
                erro="nao_configurado",
                tipo=log_tipo,
            )
            return {"ok": False, "error": "ultramsg_nao_configurado"}

        numero = _normalizar_numero(numero)
        base = _base_url()
        url = f"{base}/{endpoint.lstrip('/')}"

        log_seguro(
            "whatsapp_envio_tentado",
            provider="ultramsg",
            tipo=log_tipo,
            telefone=numero,
            instance=instance,
            token_sufixo=_mascarar_token(token),
            chars=len(str(log_conteudo or "")),
        )

        payload = {
            "token": token,
            "to": numero,
            **payload_extra,
        }

        response = requests.post(url, data=payload, timeout=30)

        if response.status_code != 200:
            log_seguro(
                "whatsapp_envio_falhou",
                provider="ultramsg",
                tipo=log_tipo,
                status_code=response.status_code,
                detalhe=(response.text or "")[:120],
            )
            return {
                "ok": False,
                "status_code": response.status_code,
                "body": (response.text or "")[:300],
            }

        try:
            dados = response.json()
            if isinstance(dados, dict) and dados.get("error"):
                log_seguro(
                    "whatsapp_envio_falhou",
                    provider="ultramsg",
                    tipo=log_tipo,
                    erro="api_error",
                    detalhe=str(dados.get("error"))[:120],
                )
                return {"ok": False, "error": str(dados.get("error"))[:200]}
        except ValueError:
            pass

        log_seguro(
            "whatsapp_envio_ok",
            provider="ultramsg",
            tipo=log_tipo,
            status_code=response.status_code,
            telefone=numero,
        )
        return {
            "ok": True,
            "status_code": response.status_code,
            "body": (response.text or "")[:300],
            "provider": "ultramsg",
        }

    except Exception as e:
        log_seguro(
            "whatsapp_envio_falhou",
            provider="ultramsg",
            tipo=log_tipo,
            erro=type(e).__name__,
            detalhe=str(e)[:120],
        )
        return {"ok": False, "error": type(e).__name__}
