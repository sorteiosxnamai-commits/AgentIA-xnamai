import os

import requests
from services.env_loader import carregar_env

carregar_env()

INSTANCE_ID = os.getenv("ZAPI_INSTANCE_ID", "").strip()
TOKEN = os.getenv("ZAPI_TOKEN", "").strip()
CLIENT_TOKEN = os.getenv("ZAPI_CLIENT_TOKEN", "").strip()
BASE_URL = os.getenv("ZAPI_BASE_URL", "https://api.z-api.io").rstrip("/")


def _normalizar_numero(numero: str) -> str:
    return numero.split("@")[0].replace("+", "").strip()


def zapi_configurado() -> bool:
    return bool(INSTANCE_ID and TOKEN)


def _headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if CLIENT_TOKEN:
        headers["Client-Token"] = CLIENT_TOKEN
    return headers


def _url(endpoint: str) -> str:
    return f"{BASE_URL}/instances/{INSTANCE_ID}/token/{TOKEN}/{endpoint}"


def _enviar(endpoint: str, payload: dict, log_tipo: str, log_conteudo: str):
    try:
        if not zapi_configurado():
            print("ERRO Z-API: ZAPI_INSTANCE_ID ou ZAPI_TOKEN não configurados")
            return None

        print("================================")
        print(f"ENVIANDO WHATSAPP Z-API ({log_tipo})")
        print("PAYLOAD:", {**payload, "message": payload.get("message", "")[:80]})
        print("CONTEUDO:", log_conteudo[:200])
        print("================================")

        response = requests.post(
            _url(endpoint),
            json=payload,
            headers=_headers(),
            timeout=30,
        )

        print("STATUS:", response.status_code)
        print("RESPOSTA:", response.text)

        if response.status_code != 200:
            return {"ok": False, "status_code": response.status_code, "body": response.text}

        return {"ok": True, "status_code": response.status_code, "body": response.text}

    except Exception as e:
        print("ERRO Z-API:", str(e))
        return {"ok": False, "error": str(e)}


def enviar_mensagem(numero: str, mensagem: str):
    numero = _normalizar_numero(numero)
    return _enviar(
        "send-text",
        {"phone": numero, "message": mensagem},
        "TEXTO",
        mensagem,
    )


def enviar_imagem(numero: str, url_imagem: str, legenda: str = ""):
    numero = _normalizar_numero(numero)
    return _enviar(
        "send-image",
        {
            "phone": numero,
            "image": url_imagem,
            "caption": legenda or "Produto",
            "viewOnce": False,
        },
        "IMAGEM",
        f"{url_imagem} | {legenda}",
    )
