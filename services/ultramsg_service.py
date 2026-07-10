import os

import requests
from services.env_loader import carregar_env

carregar_env()

INSTANCE_ID = os.getenv("ULTRAMSG_INSTANCE_ID", "")
TOKEN = os.getenv("ULTRAMSG_TOKEN", "")


def _normalizar_numero(numero: str) -> str:
    return numero.split("@")[0].replace("+", "").strip()


def ultramsg_configurado() -> bool:
    return bool(INSTANCE_ID and TOKEN)


def enviar_mensagem(numero, mensagem):

    return _enviar_ultramsg(
        endpoint="messages/chat",
        numero=numero,
        payload_extra={"body": mensagem},
        log_tipo="TEXTO",
        log_conteudo=mensagem,
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
        log_conteudo=f"{url_imagem} | {legenda}",
    )


def _enviar_ultramsg(endpoint, numero, payload_extra, log_tipo, log_conteudo):

    try:
        if not ultramsg_configurado():
            print("ERRO ULTRAMSG: ULTRAMSG_INSTANCE_ID ou ULTRAMSG_TOKEN não configurados")
            return None

        numero = _normalizar_numero(numero)

        print("================================")
        print(f"ENVIANDO WHATSAPP ({log_tipo})")
        print("NUMERO:", numero)
        print("CONTEUDO:", log_conteudo)
        print("================================")

        url = f"https://api.ultramsg.com/{INSTANCE_ID}/{endpoint}"

        payload = {
            "token": TOKEN,
            "to": numero,
            **payload_extra,
        }

        response = requests.post(
            url,
            data=payload,
            timeout=30,
        )

        print("STATUS:", response.status_code)
        print("RESPOSTA:", response.text)

        if response.status_code != 200:
            return None

        try:
            dados = response.json()
            if isinstance(dados, dict) and dados.get("error"):
                print("ERRO ULTRAMSG:", dados["error"])
                return None
        except ValueError:
            pass

        return response.text

    except Exception as e:

        print("ERRO ULTRAMSG:", str(e))

        return None
