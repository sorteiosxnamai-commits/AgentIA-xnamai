from fastapi import APIRouter
import asyncio
import os
import traceback

from services.openai_service import perguntar_ia
from services.ultramsg_service import enviar_mensagem, ultramsg_configurado

from services.produtos_service import (
    buscar_produtos_para_atendimento,
    eh_saudacao,
)
from services.mercos_service import montar_catalogo_texto
from services.supabase_service import (
    buscar_cliente,
    criar_cliente,
    atualizar_cliente,
    salvar_mensagem,
    buscar_historico,
    atualizar_historico_json,
    salvar_openai_thread_id,
)
from services.vendedor_service import (
    notificar_vendedor,
    processar_lead_e_notificar,
    vendedor_configurado,
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

        numero_raw = evento.get("from", "")
        if "@g.us" in numero_raw:
            print("MENSAGEM DE GRUPO IGNORADA:", numero_raw)
            return

        numero = numero_raw.split("@")[0].replace("+", "").strip()
        mensagem = evento.get("body")
        nome_cliente = evento.get("pushname") or ""

        if evento.get("type") and evento.get("type") != "chat":
            print("TIPO IGNORADO:", evento.get("type"))
            return

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
            cliente = criar_cliente(numero, nome=nome_cliente)
            print("CLIENTE NOVO CADASTRADO:", numero)
        elif nome_cliente and cliente.get("nome") != nome_cliente:
            atualizar_cliente(cliente_id=cliente["id"], nome=nome_cliente)
            cliente["nome"] = nome_cliente

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
        limite_catalogo = 3 if eh_saudacao(mensagem) else 8
        catalogo = montar_catalogo_texto(produtos[:limite_catalogo])
        saudacao = eh_saudacao(mensagem)

        print("================================")
        print("FONTE PRODUTOS:", resultado_produtos["fonte"])
        if resultado_produtos["erro_mercos"]:
            print("MERCOS INDISPONIVEL:", resultado_produtos["erro_mercos"])
        print("PRODUTOS ENCONTRADOS:")
        print(produtos)
        print("================================")

        # =========================
        # LEADS + NOTIFICA VENDEDOR
        # =========================

        resultado_lead = processar_lead_e_notificar(
            cliente_id=cliente_id,
            numero_cliente=numero,
            nome_cliente=nome_cliente,
            mensagem=mensagem,
            produtos=produtos,
        )

        if resultado_lead["notificado"]:
            print("VENDEDOR NOTIFICADO:", resultado_lead["interesse"])

        # =========================
        # CONTEXTO IA
        # =========================

        print("ENVIANDO PARA IA")

        thread_id = cliente.get("openai_thread_id")
        resposta_ia, thread_id = perguntar_ia(
            mensagem=mensagem,
            catalogo=catalogo,
            historico_texto=historico_texto,
            nome_cliente=nome_cliente,
            eh_saudacao=saudacao,
            thread_id=thread_id,
        )

        if thread_id and thread_id != cliente.get("openai_thread_id"):
            try:
                salvar_openai_thread_id(cliente_id, thread_id)
            except Exception as thread_error:
                print("AVISO: não salvou openai_thread_id:", thread_error)

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

        print("PROCESSAMENTO CONCLUIDO")

    except Exception as e:

        print("ERRO:")
        print(str(e))
        traceback.print_exc()


async def receber_webhook(data: dict):

    print("WEBHOOK RECEBIDO:")
    print(data)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, processar_mensagem, data)

    return {"status": "ok"}


@router.post("/webhook")
async def webhook(data: dict):
    return await receber_webhook(data)


@router.get("/status")
async def status():
    return {
        "status": "online",
        "ultramsg_configurado": ultramsg_configurado(),
        "vendedor_configurado": vendedor_configurado(),
        "produtos_fonte": os.getenv("PRODUTOS_FONTE", "auto"),
    }


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


@router.get("/teste-vendedor")
async def teste_vendedor():
    """Envia notificação de teste para o WhatsApp do vendedor."""
    if not vendedor_configurado():
        return {
            "status": "erro",
            "mensagem": "Configure VENDEDOR_WHATSAPP no .env / Render (ex: 5543999999999)",
        }

    resposta = notificar_vendedor(
        numero_cliente="5543000000000",
        nome_cliente="Cliente Teste",
        interesse="fone",
        mensagem_cliente="Quero comprar um fone",
        produtos=[{"nome": "Fone Bluetooth HMaston RS60"}],
    )

    return {
        "status": "ok" if resposta else "erro",
        "resposta_ultramsg": resposta,
    }


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