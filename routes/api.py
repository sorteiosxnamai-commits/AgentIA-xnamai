from fastapi import APIRouter, BackgroundTasks

from services.openai_service import perguntar_ia
from services.ultramsg_service import enviar_mensagem, ultramsg_configurado

from services.produtos_service import (
    buscar_produtos_para_atendimento,
)
from services.mercos_service import montar_catalogo_texto
from services.supabase_service import (
    buscar_cliente,
    criar_cliente,
    salvar_mensagem,
    buscar_historico,
    atualizar_historico_json,
    criar_lead,
    buscar_lead
)

router = APIRouter()


def processar_mensagem(data: dict):

    try:

        if "data" not in data:
            print("EVENTO IGNORADO:", data)
            return

        evento = data["data"]

        if evento.get("fromMe"):
            print("MENSAGEM PROPRIA IGNORADA")
            return

        numero = evento.get("from", "").split("@")[0].replace("+", "").strip()
        mensagem = evento.get("body")

        if not numero or not mensagem:
            print("SEM NUMERO OU MENSAGEM:", evento)
            return

        print("Número:", numero)
        print("Mensagem:", mensagem)

        # =========================
        # CLIENTE
        # =========================

        cliente = buscar_cliente(numero)

        if not cliente:
            cliente = criar_cliente(numero)

        cliente_id = cliente["id"]

        print("CLIENTE ID:", cliente_id)

        # =========================
        # SALVA MENSAGEM
        # =========================

        salvar_mensagem(
            cliente_id,
            "cliente",
            mensagem
        )

        atualizar_historico_json(cliente_id)

        # =========================
        # HISTÓRICO
        # =========================

        historico = buscar_historico(cliente_id)

        historico_texto = ""

        for msg in historico:

            if msg["tipo"] == "cliente":
                historico_texto += f"Cliente: {msg['mensagem']}\n"
            else:
                historico_texto += f"IA: {msg['mensagem']}\n"

        # =========================
        # PRODUTOS
        # =========================

        resultado_produtos = buscar_produtos_para_atendimento(mensagem)
        produtos = resultado_produtos["produtos"]
        catalogo = montar_catalogo_texto(produtos)

        print("================================")
        print("FONTE PRODUTOS:", resultado_produtos["fonte"])
        if resultado_produtos["erro_mercos"]:
            print("MERCOS INDISPONIVEL:", resultado_produtos["erro_mercos"])
        print("PRODUTOS ENCONTRADOS:")
        print(produtos)
        print("================================")

        # =========================
        # LEADS AUTOMÁTICOS
        # =========================

        mensagem_lower = mensagem.lower()

        if "fone" in mensagem_lower:

            if not buscar_lead(cliente_id, "fone"):
                criar_lead(cliente_id, "fone")
                print("LEAD SALVO: fone")

        elif "caixa de som" in mensagem_lower:

            if not buscar_lead(cliente_id, "caixa de som"):
                criar_lead(cliente_id, "caixa de som")
                print("LEAD SALVO: caixa de som")

        elif "notebook" in mensagem_lower:

            if not buscar_lead(cliente_id, "notebook"):
                criar_lead(cliente_id, "notebook")
                print("LEAD SALVO: notebook")

        elif "celular" in mensagem_lower:

            if not buscar_lead(cliente_id, "celular"):
                criar_lead(cliente_id, "celular")
                print("LEAD SALVO: celular")

        elif "carregador" in mensagem_lower:

            if not buscar_lead(cliente_id, "carregador"):
                criar_lead(cliente_id, "carregador")
                print("LEAD SALVO: carregador")

        elif "smartwatch" in mensagem_lower:

            if not buscar_lead(cliente_id, "smartwatch"):
                criar_lead(cliente_id, "smartwatch")
                print("LEAD SALVO: smartwatch")

        elif "tablet" in mensagem_lower:

            if not buscar_lead(cliente_id, "tablet"):
                criar_lead(cliente_id, "tablet")
                print("LEAD SALVO: tablet")

        elif "monitor" in mensagem_lower:

            if not buscar_lead(cliente_id, "monitor"):
                criar_lead(cliente_id, "monitor")
                print("LEAD SALVO: monitor")

        # =========================
        # CONTEXTO IA
        # =========================

        contexto = f"""
Você é uma atendente da Xnamai.

HISTÓRICO DA CONVERSA:

{historico_texto}

MENSAGEM ATUAL DO CLIENTE:

{mensagem}

PRODUTOS DISPONÍVEIS:

{catalogo}

Responda de forma amigável e utilize os produtos disponíveis quando fizer sentido.
"""

        print("ENVIANDO PARA IA")

        resposta_ia = perguntar_ia(contexto)

        print("RESPOSTA IA:")
        print(resposta_ia)

        # =========================
        # SALVA RESPOSTA IA
        # =========================

        salvar_mensagem(
            cliente_id,
            "ia",
            resposta_ia
        )

        atualizar_historico_json(cliente_id)

        # =========================
        # ENVIA WHATSAPP
        # =========================

        enviar_mensagem(
            numero,
            resposta_ia
        )

        print("MENSAGEM ENVIADA")

    except Exception as e:

        print("ERRO:")
        print(str(e))


@router.post("/webhook")
async def webhook(data: dict, background_tasks: BackgroundTasks):

    print("WEBHOOK RECEBIDO:")
    print(data)

    background_tasks.add_task(processar_mensagem, data)

    return {"status": "recebido"}


@router.get("/teste-produtos")
async def teste_produtos(q: str = ""):
    """Testa busca de produtos (Mercos ou Supabase)."""
    try:
        mensagem = q or "produto"
        resultado = buscar_produtos_para_atendimento(mensagem)
        produtos = resultado["produtos"]

        return {
            "status": "ok",
            "fonte": resultado["fonte"],
            "busca": mensagem,
            "total": len(produtos),
            "produtos": produtos,
            "catalogo": montar_catalogo_texto(produtos),
            "erro_mercos": resultado["erro_mercos"],
        }
    except Exception as e:
        return {
            "status": "erro",
            "mensagem": str(e),
        }


@router.get("/teste-mercos")
async def teste_mercos(q: str = ""):
    return await teste_produtos(q)


@router.get("/teste-ultramsg")
async def teste_ultramsg(tel: str = ""):
    """Envia mensagem de teste direto pela UltraMsg (Render → WhatsApp)."""
    if not tel:
        return {"status": "erro", "mensagem": "Informe ?tel=5543988601234"}

    if not ultramsg_configurado():
        return {
            "status": "erro",
            "mensagem": "Configure ULTRAMSG_INSTANCE_ID e ULTRAMSG_TOKEN no Render",
        }

    resposta = enviar_mensagem(
        tel,
        "Teste do agente Xnamai no Render. Se chegou, a UltraMsg está ok.",
    )

    return {
        "status": "ok" if resposta else "erro",
        "resposta_ultramsg": resposta,
    }