from fastapi import APIRouter
from services.openai_service import perguntar_ia

router = APIRouter()

@router.post("/webhook")
async def webhook(data: dict):

    print("WEBHOOK RECEBIDO:")
    print(data)

    try:

        if data.get("isGroup"):
            return {"status": "grupo_ignorado"}

        mensagem = data.get("text", {}).get("message", "")

        print("Mensagem recebida:", mensagem)

        resposta_ia = perguntar_ia(mensagem)

        print("Resposta IA:", resposta_ia)

        return {
            "status": "ok",
            "resposta": resposta_ia
        }

    except Exception as e:

        print("ERRO:", str(e))

        return {
            "status": "erro"
        }