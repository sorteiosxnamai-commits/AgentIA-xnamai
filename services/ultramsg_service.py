import requests

INSTANCE_ID = "instance181898"
TOKEN = "xe2moxi8yqfd51zs"

def enviar_mensagem(numero, mensagem):

    url = f"https://api.ultramsg.com/{INSTANCE_ID}/messages/chat"

    payload = {
        "token": TOKEN,
        "to": numero,
        "body": mensagem
    }

    response = requests.post(url, data=payload)

    print("STATUS:", response.status_code)
    print("RESPOSTA:", response.text)