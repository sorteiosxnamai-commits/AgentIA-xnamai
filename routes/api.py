from fastapi import APIRouter

from services.openai_service import perguntar_ia
from services.ultramsg_service import enviar_mensagem

from services.supabase_service import (
    buscar_cliente,
    criar_cliente,
    salvar_mensagem,
    buscar_historico,
    atualizar_historico_json,
    buscar_produtos
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

        print("================================")
        print("PRODUTOS VINDOS DO SUPABASE:")
        print(produtos)

        if produtos:
            print("TOTAL PRODUTOS:", len(produtos))
        else:
            print("TOTAL PRODUTOS: 0")

        print("================================")

        catalogo = ""

        for produto in produtos:

            catalogo += (
                f"Nome: {produto['nome']}\n"
                f"Categoria: {produto['categoria']}\n"
                f"Preço: R$ {produto['preco']}\n"
                f"Estoque: {produto['estoque']}\n"
                f"Descrição: {produto['descricao']}\n\n"
            )

        print("================================")
        print("CATALOGO MONTADO:")
        print(catalogo)
        print("================================")

        # CONTEXTO IA
        contexto_final = f"""
Você é uma atendente da Xnamai.

CATÁLOGO DE PRODUTOS:

{catalogo}

HISTÓRICO:

{historico_texto}

MENSAGEM DO CLIENTE:

{mensagem}

IMPORTANTE:

- Utilize SOMENTE os produtos do catálogo.
- Nunca invente produtos.
- Nunca invente preços.
- Nunca invente estoque.
- Se existir um produto relacionado ao pedido do cliente, apresente ele.
- Se o cliente pedir fone, procure produtos de áudio.
- Se o cliente pedir caixa de som, procure produtos de áudio.
"""

        print("CONTEXTO ENVIADO:")
        print(contexto_final)

        resposta_ia = perguntar_ia(contexto_final)

        print("RESPOSTA IA:")
        print(resposta_ia)

        salvar_mensagem(
            cliente_id,
            "ia",
            resposta_ia
        )

        atualizar_historico_json(cliente_id)

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