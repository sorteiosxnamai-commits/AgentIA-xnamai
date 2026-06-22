import requests
import os

INSTANCE_ID = os.getenv("instance181898")
TOKEN = os.getenv("xe2moxi8yqfd51zs")

def enviar_mensagem(numero, mensagem):

    url = f"https://api.ultramsg.com/instance181898/{INSTANCE_ID}/messages/chat"

    payload = {
        "token": TOKEN,
        "to": numero,
        "body": mensagem
    }

    response = requests.post(url, data=payload)

    print(response.text)