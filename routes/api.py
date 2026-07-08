from fastapi import APIRouter, BackgroundTasks
import asyncio
import os
import traceback

from services.openai_service import (
    perguntar_ia,
    resposta_com_foto,
    resposta_ja_informado,
    resposta_saudacao,
    resposta_sem_foto,
)
from services.vendas.respostas import (
    cliente_quer_ver_catalogo,
    resposta_fora_catalogo,
    resposta_mostrar_catalogo,
)
from services.vendas.catalogo import montar_catalogo_geral
from services.whatsapp_service import (
    enviar_imagem,
    enviar_mensagem,
    provider_nome,
    whatsapp_configurado,
)
from services.produto_imagem_service import (
    cliente_pediu_foto,
    enviar_fotos_produtos,
    extrair_busca_do_historico,
    produtos_com_foto_disponivel,
)

from services.conversa_service import (
    cliente_quer_novo_atendimento,
    conversa_em_andamento,
    eh_alteracao_pagamento,
    eh_confirmacao_fechamento,
    extrair_nome_do_historico,
    historico_recente,
    pedido_ja_encerrado,
    resposta_fechamento_pedido,
    resposta_pos_fechamento,
    _mensagem_tem_confirmacao,
)
from services.webhook_normalizer import normalizar_webhook
from services.webhook_service import evento_deve_ser_ignorado, marcar_evento_processado
from services.produtos_service import (
    buscar_produtos_para_atendimento,
    eh_saudacao,
)
from services.vendas.contexto import preparar_contexto_venda
from services.mercos_service import (
    mercos_ambiente_sandbox,
    mercos_configurado,
)
from services.pedido_mercos_service import mercos_criar_pedido_habilitado
from services.supabase_service import (
    buscar_cliente,
    criar_cliente,
    atualizar_cliente,
    salvar_mensagem,
    buscar_historico,
    atualizar_historico_json,
)
from services.sync_mercos_service import sincronizar_produtos_mercos
from services.pedido_mercos_service import criar_pedido_fechamento_mercos
from services.pulsedesk_bridge import espelhar_mensagem_agente, espelhar_mensagem_cliente
from services.vendedor_service import (
    notificar_vendedor,
    processar_lead_e_notificar,
    vendedor_configurado,
)

CODE_VERSION = "2026-07-08-casual-msgs"

router = APIRouter()


def processar_mensagem(data: dict):

    try:

        if "data" not in data:
            print("EVENTO IGNORADO:", data)
            return

        ignorar, motivo = evento_deve_ser_ignorado(data)
        if ignorar:
            print("WEBHOOK IGNORADO:", motivo)
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
        espelhar_mensagem_cliente(numero, nome_cliente, mensagem)

        atualizar_historico_json(cliente_id)

        # =========================
        # HISTÓRICO
        # =========================

        historico = buscar_historico(cliente_id)

        historico_texto = ""
        ultima_resposta_ia = ""

        for msg in historico:

            if msg["tipo"] == "cliente":
                historico_texto += f"Cliente: {msg['mensagem']}\n"
            else:
                historico_texto += f"IA: {msg['mensagem']}\n"
                ultima_resposta_ia = msg["mensagem"]

        # =========================
        # PRODUTOS
        # =========================

        nome_conversa = extrair_nome_do_historico(historico_texto, nome_cliente)
        fechamento = eh_confirmacao_fechamento(
            mensagem, historico_texto, ultima_resposta_ia
        )
        alteracao_pagamento = eh_alteracao_pagamento(mensagem, historico_texto)
        saudacao = eh_saudacao(mensagem, historico_texto)

        if pedido_ja_encerrado(ultima_resposta_ia, historico_texto):
            if fechamento and not alteracao_pagamento:
                fechamento = False
            if saudacao:
                saudacao = False

        pedido_encerrado = pedido_ja_encerrado(ultima_resposta_ia, historico_texto)
        pular_catalogo = fechamento or alteracao_pagamento or saudacao

        contexto_venda = preparar_contexto_venda(
            mensagem=mensagem,
            historico_texto=historico_texto,
            pedido_encerrado=pedido_encerrado,
            pular_catalogo=pular_catalogo,
        )

        if not pular_catalogo and cliente_pediu_foto(mensagem) and not contexto_venda.produtos:
            busca_historico = extrair_busca_do_historico(historico_texto)
            if busca_historico.strip():
                contexto_venda = preparar_contexto_venda(
                    mensagem=busca_historico,
                    historico_texto=historico_texto,
                    pedido_encerrado=pedido_encerrado,
                )

        produtos = contexto_venda.produtos
        catalogo = contexto_venda.catalogo

        if not pular_catalogo:
            print("================================")
            print("ESTAGIO VENDA:", contexto_venda.estagio)
            print("FONTE PRODUTOS:", contexto_venda.fonte)
            if contexto_venda.erro_mercos:
                print("MERCOS INDISPONIVEL:", contexto_venda.erro_mercos)
            print("PRODUTOS ENCONTRADOS:", produtos)
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

        com_foto = produtos_com_foto_disponivel(produtos, mensagem) if produtos else []
        pediu_foto = cliente_pediu_foto(mensagem)
        repetindo = (
            pediu_foto
            and ultima_resposta_ia
            and any(
                p in ultima_resposta_ia.lower()
                for p in ("vou te enviar", "já te mando", "segue a foto", "foto do")
            )
        )

        if fechamento or alteracao_pagamento:
            frete_estimado = float(os.getenv("FRETE_ESTIMADO", "0") or "0")
            mercos_pedido = None
            ja_encerrado = pedido_ja_encerrado(ultima_resposta_ia, historico_texto)

            if not ja_encerrado and (fechamento or alteracao_pagamento):
                mercos_pedido = criar_pedido_fechamento_mercos(
                    historico_texto=historico_texto,
                    cliente_supabase=cliente,
                    telefone=numero,
                    pushname=nome_cliente,
                    mensagem_atual=mensagem,
                    ultima_resposta_ia=ultima_resposta_ia,
                    frete_estimado=frete_estimado,
                )

            resposta_ia = resposta_fechamento_pedido(
                historico_texto,
                nome_cliente,
                frete_estimado,
                mensagem_atual=mensagem,
                ultima_resposta_ia=ultima_resposta_ia,
                mercos_pedido=mercos_pedido,
            )
            resultado_fechamento = buscar_produtos_para_atendimento(historico_texto)
            if vendedor_configurado():
                notificar_vendedor(
                    numero_cliente=numero,
                    nome_cliente=nome_conversa,
                    interesse="pedido fechado",
                    mensagem_cliente=mensagem,
                    produtos=resultado_fechamento.get("produtos"),
                )
                print("VENDEDOR NOTIFICADO: pedido fechado")

            if mercos_pedido and mercos_pedido.get("pedido_id"):
                print("MERCOS PEDIDO CRIADO:", mercos_pedido)
            elif mercos_pedido and mercos_pedido.get("erro"):
                print("MERCOS PEDIDO FALHOU:", mercos_pedido["erro"])
        elif saudacao:
            resposta_ia = resposta_saudacao(nome_conversa)
        elif pediu_foto and produtos and not com_foto:
            resposta_ia = resposta_sem_foto(produtos[0])
        elif pediu_foto and com_foto and repetindo:
            resposta_ia = resposta_ja_informado(com_foto[0])
        elif pediu_foto and com_foto:
            resposta_ia = resposta_com_foto(com_foto[0])
        elif pedido_ja_encerrado(ultima_resposta_ia, historico_texto) and not (
            fechamento or alteracao_pagamento or cliente_quer_novo_atendimento(mensagem)
        ):
            resposta_ia = resposta_pos_fechamento(nome_conversa)
        elif cliente_quer_ver_catalogo(mensagem, ultima_resposta_ia):
            cat_geral = montar_catalogo_geral()
            produtos = cat_geral["produtos"]
            catalogo = cat_geral["catalogo"]
            resposta_ia = resposta_mostrar_catalogo(nome_conversa, produtos)
        elif contexto_venda.sem_match and not (
            conversa_em_andamento(historico_texto) and _mensagem_tem_confirmacao(mensagem)
        ):
            resposta_ia = resposta_fora_catalogo(
                nome_cliente=nome_conversa,
                termos=contexto_venda.termos_cliente,
                amostra=contexto_venda.amostra_disponivel,
            )
        else:
            resposta_ia = perguntar_ia(
                mensagem=mensagem,
                catalogo=catalogo,
                historico_texto=historico_recente(historico_texto),
                nome_cliente=nome_conversa,
                ultima_resposta_ia=ultima_resposta_ia,
                foto_automatica=bool(com_foto and pediu_foto),
                contexto_venda=contexto_venda,
            )

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
        espelhar_mensagem_agente(numero, nome_cliente, resposta_ia)

        atualizar_historico_json(cliente_id)

        # =========================
        # ENVIA WHATSAPP
        # =========================

        enviar_mensagem(
            numero,
            resposta_ia
        )

        if produtos and not saudacao:
            fotos_enviadas = enviar_fotos_produtos(numero, produtos, mensagem)
            if fotos_enviadas:
                print(f"FOTOS ENVIADAS: {fotos_enviadas}")

        print("PROCESSAMENTO CONCLUIDO")
        marcar_evento_processado(data)

    except Exception as e:

        print("ERRO:")
        print(str(e))
        traceback.print_exc()


async def receber_webhook(data: dict, background_tasks: BackgroundTasks | None = None):

    print("WEBHOOK RECEBIDO:")
    print(data)

    payload = normalizar_webhook(data)
    if not payload:
        print("WEBHOOK IGNORADO: formato não suportado ou evento descartado")
        return {"status": "ok", "ignorado": True}

    if background_tasks is not None:
        background_tasks.add_task(processar_mensagem, payload)
    else:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, processar_mensagem, payload)

    return {"status": "ok"}


@router.get("/webhook")
async def webhook_info():
    return {
        "status": "ok",
        "mensagem": "POST aqui para receber mensagens da Z-API",
        "url": "https://agent-ia-xnamai.onrender.com/webhook",
        "provider": provider_nome(),
    }


@router.post("/webhook")
async def webhook(data: dict, background_tasks: BackgroundTasks):
    return await receber_webhook(data, background_tasks)


@router.get("/status")
async def status():
    return {
        "status": "online",
        "whatsapp_provider": provider_nome(),
        "whatsapp_configurado": whatsapp_configurado(),
        "ultramsg_configurado": whatsapp_configurado(),
        "vendedor_configurado": vendedor_configurado(),
        "produtos_fonte": os.getenv("PRODUTOS_FONTE", "auto"),
        "mercos_configurado": mercos_configurado(),
        "mercos_sandbox": mercos_ambiente_sandbox(),
        "mercos_criar_pedido": mercos_criar_pedido_habilitado(),
        "mercos_base_url": os.getenv("MERCOS_BASE_URL", ""),
        "vendas_consultivas": True,
        "code_version": CODE_VERSION,
        "pulsedesk_bridge": os.getenv("PULSEDESK_BRIDGE_ENABLED", "true"),
    }


@router.get("/teste-supabase-produtos")
async def teste_supabase_produtos():
    """Diagnóstico direto — lê produtos do Supabase sem montar catálogo."""
    try:
        from services.supabase_service import buscar_produtos

        produtos = buscar_produtos()
        return {
            "status": "ok",
            "code_version": CODE_VERSION,
            "total": len(produtos),
            "amostra": produtos[:3],
        }
    except Exception as e:
        import traceback
        return {
            "status": "erro",
            "code_version": CODE_VERSION,
            "mensagem": str(e),
            "traceback": traceback.format_exc(),
        }


@router.post("/sync-produtos")
@router.get("/sync-produtos")
async def sync_produtos(token: str = ""):
    """Sincroniza produtos Mercos → Supabase. Opcional: ?token=SEU_SYNC_TOKEN"""
    sync_token = os.getenv("SYNC_TOKEN", "").strip()

    if sync_token and token != sync_token:
        return {"status": "erro", "mensagem": "Token inválido"}

    try:
        resultado = sincronizar_produtos_mercos()
        return {"status": "ok", **resultado}
    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}


@router.get("/teste-produtos")
async def teste_produtos(q: str = ""):
    """Testa busca de produtos (Mercos primeiro, Supabase fallback)."""
    try:
        from services.vendas.contexto import preparar_contexto_venda

        mensagem = q or "produto"
        ctx = preparar_contexto_venda(mensagem)

        return {
            "status": "ok",
            "fonte": ctx.fonte,
            "estagio": ctx.estagio,
            "busca": mensagem,
            "total": len(ctx.produtos),
            "produtos": ctx.produtos,
            "similares": ctx.similares,
            "upsell": ctx.upsell,
            "complementos": ctx.complementos,
            "catalogo": ctx.catalogo,
            "erro_mercos": ctx.erro_mercos,
        }
    except Exception as e:
        import traceback
        return {
            "status": "erro",
            "code_version": CODE_VERSION,
            "mensagem": str(e),
            "traceback": traceback.format_exc(),
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
        "resposta_whatsapp": resposta,
    }


@router.get("/teste-imagem")
async def teste_imagem(tel: str = "", url: str = ""):
    """Envia imagem de teste via WhatsApp (Z-API ou UltraMsg)."""
    if not tel or not url:
        return {
            "status": "erro",
            "mensagem": "Informe ?tel=5543988601234&url=https://...jpg",
        }

    if not whatsapp_configurado():
        return {"status": "erro", "mensagem": "WhatsApp não configurado"}

    resposta = enviar_imagem(tel, url, "Teste de imagem — Xnamai")

    return {
        "status": "ok" if resposta else "erro",
        "provider": provider_nome(),
        "resposta_whatsapp": resposta,
    }


@router.get("/teste-ultramsg")
@router.get("/teste-zapi")
@router.get("/teste-whatsapp")
async def teste_whatsapp(tel: str = ""):
    """Envia mensagem de teste direto pelo provedor WhatsApp configurado."""
    if not tel:
        return {"status": "erro", "mensagem": "Informe ?tel=5543988601234"}

    if not whatsapp_configurado():
        return {
            "status": "erro",
            "mensagem": "Configure ZAPI_INSTANCE_ID e ZAPI_TOKEN no Render",
            "provider": provider_nome(),
        }

    resposta = enviar_mensagem(
        tel,
        f"Teste do agente Xnamai ({provider_nome()}). Se chegou, o WhatsApp está ok.",
    )

    return {
        "status": "ok" if resposta else "erro",
        "provider": provider_nome(),
        "resposta_whatsapp": resposta,
    }