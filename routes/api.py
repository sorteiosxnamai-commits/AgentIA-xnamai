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

        # Verifica se veio evento válido
        if "data" not in data:
            return {"status": "evento_ignorado"}

        evento = data["data"]

        numero = evento.get("from")
        mensagem = evento.get("body")

        # Ignora eventos sem mensagem
        if not numero or not mensagem:
            return {"status": "sem_mensagem"}

        print("Número:", numero)
        print("Mensagem:", mensagem)

        # Busca cliente
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

        atualizar_historico_json(cliente_id)

        print("Mensagem salva")

        # ==================================
        # HISTÓRICO
        # ==================================

        historico = buscar_historico(cliente_id)

        historico_texto = ""

        for msg in historico:

            if msg["tipo"] == "cliente":
                historico_texto += f"Cliente: {msg['mensagem']}\n"
            else:
                historico_texto += f"Atendente: {msg['mensagem']}\n"

        # ==================================
        # PRODUTOS
        # ==================================

        produtos = buscar_produtos()

        print("========== PRODUTOS ==========")
        print(produtos)
        print("TOTAL PRODUTOS:", len(produtos))
        print("==============================")

        catalogo = ""

        for produto in produtos:

            catalogo += f"""
Nome: {produto['nome']}
Categoria: {produto['categoria']}
Preço: R$ {produto['preco']}
Estoque: {produto['estoque']}
Descrição: {produto['descricao']}

"""

        # ==================================
        # CONTEXTO FINAL
        # ==================================

        contexto_final = f"""
Você é uma atendente da Xnamai.

HISTÓRICO DA CONVERSA:

{historico_texto}

MENSAGEM ATUAL DO CLIENTE:

{mensagem}

CATÁLOGO DE PRODUTOS DA XNAMAI:

{catalogo}

REGRAS:

- Utilize SOMENTE os produtos cadastrados no catálogo.
- Quando encontrar um produto relacionado ao pedido do cliente, informe:
  Nome, preço, descrição e estoque.
- Nunca diga que não existem produtos sem antes consultar o catálogo.
- Se o cliente pedir um fone, procure produtos da categoria Audio.
- Se o cliente pedir caixa de som, procure produtos da categoria Audio.
"""

        print("========== CONTEXTO FINAL ==========")
        print(contexto_final)
        print("====================================")

        # ==================================
        # IA
        # ==================================

        resposta_ia = perguntar_ia(contexto_final)

        print("RESPOSTA IA:")
        print(resposta_ia)

        # Salva resposta
        salvar_mensagem(
            cliente_id,
            "ia",
            resposta_ia
        )

        atualizar_historico_json(cliente_id)

        # ==================================
        # WHATSAPP
        # ==================================

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