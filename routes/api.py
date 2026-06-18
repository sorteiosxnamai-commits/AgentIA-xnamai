@router.post("/webhook")
async def webhook(data: dict):

    try:

        if data.get("isGroup"):
            return {"status": "grupo_ignorado"}

        mensagem = data["text"]["message"]

        print("Mensagem recebida:", mensagem)

        resposta_ia = perguntar_ia(mensagem)

        print("Resposta IA:", resposta_ia)

        return {
            "status": "ok",
            "resposta": resposta_ia
        }

    except Exception as e:
        print("ERRO:", e)
        print(data)

        return {"status": "erro"}