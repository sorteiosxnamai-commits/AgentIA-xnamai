import requests

INSTANCE_ID = "3F4CB317B66E2245E7E58645B9B7D1FC"
TOKEN = "99C8DCB079A8020DF63E7085"
CLIENT_TOKEN = "SEU_CLIENT_TOKEN_AQUI"

def enviar_mensagem(numero, mensagem):

    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"

    headers = {
        "Client-Token": CLIENT_TOKEN
    }

    payload = {
        "phone": numero,
        "message": mensagem
    }

    response = requests.post(
        url,
        json=payload,
        headers=headers
    )

    print("STATUS ZAPI:", response.status_code)
    print("RESPOSTA ZAPI:", response.text)

    return response.text