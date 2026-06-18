from services.zapi_service import enviar_whatsapp

@router.post("/webhook")
async def webhook(data: dict):

    try:

        if data.get("isGroup"):
            return {"status": "grupo_ignorado"}

        mensagem = data["text"]["message"]

        numero = data["phone"]

        print("Mensagem:", mensagem)

        resposta_ia = perguntar_ia(mensagem)

        print("Resposta:", resposta_ia)

        enviar_whatsapp(numero, resposta_ia)

        return {"status": "ok"}

    except Exception as e:

        print("ERRO:", e)
        print(data)

        return {"status": "erro"}