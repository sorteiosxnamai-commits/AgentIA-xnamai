import requests

ZAPI_URL = "https://api.z-api.io/instances/3F4CB317B66E2245E7E58645B9B7D1FC/token/4C2EDD29BAA28D8A82485C7B/send-text"

def enviar_whatsapp(numero, mensagem):

    payload = {
        "phone": numero,
        "message": mensagem
    }

    requests.post(ZAPI_URL, json=payload)