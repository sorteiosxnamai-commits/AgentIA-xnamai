from fastapi import APIRouter
from services.openai_service import perguntar_ia

router = APIRouter()

@router.get("/chat")
def chat(mensagem: str):

    resposta = perguntar_ia(mensagem)

    return {
        "pergunta": mensagem,
        "resposta": resposta
    }

@router.post("/webhook")
async def webhook(data: dict):

    print("DADOS RECEBIDOS:", data)

    mensagem = data.get("mensagem", "")

    resposta = perguntar_ia(mensagem)

    return {
        "resposta": resposta
    }