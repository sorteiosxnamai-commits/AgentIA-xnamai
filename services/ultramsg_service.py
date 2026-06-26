import os

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

INSTANCE_ID = os.getenv("ULTRAMSG_INSTANCE_ID", "")
TOKEN = os.getenv("ULTRAMSG_TOKEN", "")


def _normalizar_numero(numero: str) -> str:
    return numero.split("@")[0].replace("+", "").strip()


def ultramsg_configurado() -> bool:
    return bool(INSTANCE_ID and TOKEN)


def enviar_mensagem(numero, mensagem):

    try:
        if not ultramsg_configurado():
            print("ERRO ULTRAMSG: ULTRAMSG_INSTANCE_ID ou ULTRAMSG_TOKEN não configurados")
            return None

        numero = _normalizar_numero(numero)

        print("================================")
        print("ENVIANDO WHATSAPP")
        print("NUMERO:", numero)
        print("MENSAGEM:", mensagem)
        print("================================")

        url = f"https://api.ultramsg.com/{INSTANCE_ID}/messages/chat"

        payload = {
            "token": TOKEN,
            "to": numero,
            "body": mensagem,
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
