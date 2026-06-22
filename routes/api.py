from fastapi import APIRouter

from services.openai_service import perguntar_ia
from services.ultramsg_service import enviar_mensagem

from services.supabase_service import (
    buscar_cliente,
    criar_cliente,
    salvar_mensagem,
    buscar_historico,
    atualizar_historico_json
)

router = APIRouter()


@router.post("/webhook")
async def webhook(data: dict):

    try:

        print("WEBHOOK RECEBIDO:")
        print(data)

        # UltraMsg envia vários tipos de eventos
        if "data" not in data:
            return {"status": "evento_ignorado"}

        evento = data["data"]

        numero = evento.get("from")
        mensagem = evento.get("body")

        if not numero or not mensagem:
            return {"status": "sem_mensagem"}

        print("Número:", numero)
        print("Mensagem:", mensagem)

        # Procura cliente
        cliente = buscar_cliente(numero)

        print("CLIENTE ENCONTRADO:", cliente)

        # Cria cliente se não existir
        if not cliente:
            cliente = criar_cliente(numero)

        cliente_id = cliente["id"]

        print("CLIENTE ID:", cliente_id)

        # Salva mensagem do cliente
        salvar_mensagem(
            cliente_id,
            "cliente",
            mensagem
        )

        print("Mensagem salva")

        # Busca histórico
        historico = buscar_historico(cliente_id)

        contexto = ""

        for msg in historico:

            if msg["tipo"] == "cliente":
                contexto += f"Cliente: {msg['mensagem']}\n"
            else:
                contexto += f"IA: {msg['mensagem']}\n"

        print("ENVIANDO PARA IA")

        resposta_ia = perguntar_ia(contexto)

        print("RESPOSTA IA:", resposta_ia)

        # Salva resposta da IA
        salvar_mensagem(
            cliente_id,
            "ia",
            resposta_ia
        )

        print("Resposta salva")

        # Envia para WhatsApp
        enviar_mensagem(
            numero,
            resposta_ia
        )

        print("Mensagem enviada para WhatsApp")

        return {
            "status": "ok"
        }

    except Exception as e:

        print("ERRO:", str(e))

        return {
            "status": "erro",
            "mensagem": str(e)
        }