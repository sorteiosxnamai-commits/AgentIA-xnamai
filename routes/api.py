from fastapi import APIRouter

from services.openai_service import perguntar_ia
from services.ultramsg_service import enviar_mensagem

from services.supabase_service import (
    buscar_cliente,
    criar_cliente,
    salvar_mensagem,
    buscar_historico,
    atualizar_historico_json,
    buscar_produtos,
    criar_atendimento,
    buscar_atendimento_aberto,
    criar_lead,
    buscar_lead
)

router = APIRouter()


@router.post("/webhook")
async def webhook(data: dict):

    try:

        print("WEBHOOK RECEBIDO:")
        print(data)

        if "data" not in data:
            return {"status": "evento_ignorado"}

        evento = data["data"]

        numero = evento.get("from")
        mensagem = evento.get("body")

        if not numero or not mensagem:
            return {"status": "sem_mensagem"}

        print("Número:", numero)
        print("Mensagem:", mensagem)

        # CLIENTE
        cliente = buscar_cliente(numero)

        if not cliente:
            cliente = criar_cliente(numero)

        cliente_id = cliente["id"]

        print("CLIENTE ID:", cliente_id)

        # ATENDIMENTO
        atendimento = buscar_atendimento_aberto(cliente_id)

        if not atendimento:
            criar_atendimento(cliente_id)

        # LEADS
        texto = mensagem.lower()

        interesses = [
            "fone",
            "caixa de som",
            "carregador",
            "cabo",
            "suporte"
        ]

        for interesse in interesses:

            if interesse in texto:

                lead = buscar_lead(
                    cliente_id,
                    interesse
                )

                if not lead:
                    criar_lead(
                        cliente_id,
                        interesse
                    )

                break

        # SALVA MENSAGEM
        salvar_mensagem(
            cliente_id,
            "cliente",
            mensagem
        )

        atualizar_historico_json(cliente_id)

        # HISTÓRICO
        historico = buscar_historico(cliente_id)

        historico_texto = ""

        for msg in historico:

            if msg["tipo"] == "cliente":
                historico_texto += f"Cliente: {msg['mensagem']}\n"
            else:
                historico_texto += f"Atendente: {msg['mensagem']}\n"

        # PRODUTOS
        produtos = buscar_produtos()

        catalogo = ""

        for produto in produtos:

            catalogo += (
                f"Nome: {produto['nome']}\n"
                f"Categoria: {produto['categoria']}\n"
                f"Preço: R$ {produto['preco']}\n"
                f"Estoque: {produto['estoque']}\n"
                f"Descrição: {produto['descricao']}\n\n"
            )

        contexto_final = f"""
HISTÓRICO:

{historico_texto}

MENSAGEM DO CLIENTE:

{mensagem}

CATÁLOGO DE PRODUTOS:

{catalogo}
"""

        print("CONTEXTO ENVIADO PARA IA:")
        print(contexto_final)

        resposta_ia = perguntar_ia(contexto_final)

        print("RESPOSTA IA:")
        print(resposta_ia)

        # SALVA RESPOSTA
        salvar_mensagem(
            cliente_id,
            "ia",
            resposta_ia
        )

        atualizar_historico_json(cliente_id)

        # ENVIA WHATSAPP
        enviar_mensagem(
            numero,
            resposta_ia
        )

        return {
            "status": "ok"
        }

    except Exception as e:

        print("ERRO:", str(e))

        return {
            "status": "erro",
            "mensagem": str(e)
        }