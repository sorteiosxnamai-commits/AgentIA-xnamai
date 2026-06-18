from fastapi import APIRouter
from services.openai_service import perguntar_ia
from services.zapi_service import enviar_mensagem

router = APIRouter()

historico_conversas = {}

@router.post("/webhook")
async def webhook(data: dict):

    try:

        print("WEBHOOK RECEBIDO:")
        print(data)

        # Ignora grupos
        if data.get("isGroup"):
            return {"status": "grupo_ignorado"}

        mensagem = data["text"]["message"]
        numero = data["phone"]

        print("Mensagem recebida:", mensagem)
        print("Número:", numero)

        # Cria histórico do cliente
        if numero not in historico_conversas:
            historico_conversas[numero] = []

        historico_conversas[numero].append(
            f"Cliente: {mensagem}"
        )

        contexto = "\n".join(
            historico_conversas[numero]
        )

        print("ANTES DA IA")

        resposta_ia = perguntar_ia(contexto)

        print("DEPOIS DA IA")
        print("Resposta IA:", resposta_ia)

        historico_conversas[numero].append(
            f"IA: {resposta_ia}"
        )

        print("ANTES DE ENVIAR")

        resultado = enviar_mensagem(
            numero,
            resposta_ia
        )

        print("RESULTADO ENVIO:")
        print(resultado)

        print("MENSAGEM ENVIADA")

        return {
            "status": "ok"
        }

    except Exception as e:

        print("ERRO NO WEBHOOK:")
        print(str(e))

        return {
            "status": "erro",
            "erro": str(e)
        }