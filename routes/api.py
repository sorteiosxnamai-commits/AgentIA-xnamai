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
    cliente_perguntou_preco,
    cliente_quer_ver_catalogo,
    resposta_fora_catalogo,
    resposta_mostrar_catalogo,
    resposta_preco_em_discussao,
)
from services.xnamai_script import (
    mensagem_nao_e_busca_produto,
    resposta_abrir_espaco_pedido,
    resposta_como_trabalham,
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
    cliente_quer_nova_venda,
    cliente_quer_novo_atendimento,
    conversa_em_andamento,
    eh_alteracao_pagamento,
    eh_confirmacao_fechamento,
    entrega_ja_informada,
    extrair_nome_do_historico,
    extrair_preferencia_entrega,
    historico_desde_ultimo_fechamento,
    historico_recente,
    ia_ja_pediu_endereco,
    negociacao_nova_apos_fechamento,
    pedido_ja_encerrado,
    resolver_estado_venda,
    resolver_resposta_pos_pedido,
    resposta_entrega_ja_anotada,
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
from services.pedido_mercos_service import criar_pedido_fechamento_mercos, mercos_criar_pedido_habilitado
from services.pedido_pulsedesk_service import (
    diagnosticar_pulsedesk_pedidos,
    pulsedesk_pedidos_habilitado,
    registrar_venda_pulsedesk,
    registrar_venda_retroativa_por_telefone,
)
from services.supabase_service import (
    buscar_cliente,
    criar_cliente,
    atualizar_cliente,
    salvar_mensagem,
    buscar_historico,
    atualizar_historico_json,
)
from services.sync_mercos_service import sincronizar_produtos_mercos
from services.pulsedesk_bridge import espelhar_mensagem_agente, espelhar_mensagem_cliente
from services.vendedor_service import (
    notificar_vendedor,
    processar_lead_e_notificar,
    vendedor_configurado,
)

CODE_VERSION = "2026-07-10-mcp-layer"

router = APIRouter()


def _bloqueio_diagnostico(token: str = "") -> dict | None:
    """Com DIAGNOSTICOS_ABERTOS=false (padrão), exige SYNC_TOKEN."""
    abertos = os.getenv("DIAGNOSTICOS_ABERTOS", "false").strip().lower() in (
        "1",
        "true",
        "sim",
        "yes",
    )
    if abertos:
        return None
    sync_token = os.getenv("SYNC_TOKEN", "").strip()
    if not sync_token:
        return {
            "status": "erro",
            "mensagem": "Diagnósticos fechados. Defina SYNC_TOKEN ou DIAGNOSTICOS_ABERTOS=true",
        }
    if token != sync_token:
        return {"status": "erro", "mensagem": "Token inválido"}
    return None


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
        estado_venda = resolver_estado_venda(
            historico_texto, mensagem, ultima_resposta_ia
        )
        print("ESTADO VENDA:", estado_venda)

        pedido_encerrado = estado_venda == "pos_venda"
        nova_venda_explicita = cliente_quer_nova_venda(mensagem) or (
            estado_venda == "nova_venda"
        )
        nova_venda = negociacao_nova_apos_fechamento(historico_texto, mensagem) or (
            estado_venda == "nova_venda"
        )

        # Após fechamento real: usa só o trecho da venda atual
        historico_venda = historico_texto
        if nova_venda or estado_venda in ("nova_venda", "negociando", "fechando"):
            trecho = historico_desde_ultimo_fechamento(historico_texto)
            if trecho != historico_texto:
                historico_venda = trecho

        from services.vendas.analise import detectar_modo_intencao, detectar_tom
        from services.vendas.memoria import (
            atualizar_sessao_turno,
            carregar_sessao,
            limpar_sessao,
            mensagem_ambigua_para_llm,
            persistir_sessao,
        )

        if nova_venda_explicita:
            limpar_sessao(str(cliente_id))
            sessao = carregar_sessao(None, str(cliente_id))
        else:
            sessao = carregar_sessao(cliente, str(cliente_id))

        resposta_pos_venda = None
        if estado_venda == "pos_venda":
            resposta_pos_venda = resolver_resposta_pos_pedido(
                mensagem,
                historico_texto,
                ultima_resposta_ia,
                nome_conversa,
            )

        from services.xnamai_script import (
            alinhamento_completo,
            cliente_perguntou_como_trabalham,
            cliente_perguntou_estoque,
            ia_pediu_alinhamento,
            precisa_avisar_pedido_minimo,
            resposta_alinhamento_pedido,
            resposta_estoque_disponibilidade,
            resposta_pedido_minimo,
            valor_pedido_historico,
        )

        fechamento = estado_venda == "fechando" or eh_confirmacao_fechamento(
            mensagem, historico_venda, ultima_resposta_ia
        )
        # Cliente respondeu NF/envio após o alinhamento do script → segue para fechar
        if (
            not fechamento
            and not pedido_encerrado
            and ia_pediu_alinhamento(ultima_resposta_ia)
            and alinhamento_completo(historico_venda, mensagem)
        ):
            fechamento = True
            print("ALINHAMENTO XNAMAI completo — seguindo para fechamento")

        alteracao_pagamento = eh_alteracao_pagamento(
            mensagem, historico_venda, ultima_resposta_ia
        )
        saudacao = eh_saudacao(mensagem, historico_venda)

        if estado_venda == "pos_venda":
            fechamento = False
            alteracao_pagamento = False
            if saudacao:
                saudacao = False

        # "Quero fazer outro pedido" não é busca de produto — abre catálogo direto
        pular_catalogo = (
            fechamento
            or alteracao_pagamento
            or saudacao
            or nova_venda_explicita
            or estado_venda == "nova_venda"
        )

        contexto_venda = preparar_contexto_venda(
            mensagem=mensagem,
            historico_texto=historico_venda,
            pedido_encerrado=pedido_encerrado,
            pular_catalogo=pular_catalogo,
            memoria=sessao,
        )

        if not pular_catalogo and cliente_pediu_foto(mensagem) and not contexto_venda.produtos:
            busca_historico = extrair_busca_do_historico(historico_venda)
            if busca_historico.strip():
                contexto_venda = preparar_contexto_venda(
                    mensagem=busca_historico,
                    historico_texto=historico_venda,
                    pedido_encerrado=pedido_encerrado,
                    memoria=sessao,
                )

        produtos = contexto_venda.produtos
        catalogo = contexto_venda.catalogo

        sessao = atualizar_sessao_turno(
            sessao,
            historico_texto=historico_venda,
            mensagem=mensagem,
            produtos=produtos,
            tom=detectar_tom(mensagem, historico_venda),
            intencao=detectar_modo_intencao(mensagem, historico_venda),
            nova_venda=False,
        )
        contexto_venda.memoria = sessao
        persistir_sessao(str(cliente_id), sessao)

        # MCP: tools necessárias → JSON → prompt (não altera fechamento)
        mcp_bloco = ""
        try:
            from services.mcp.router import enrich_turno

            sessao, mcp_bloco, _mcp_raw = enrich_turno(
                mensagem=mensagem,
                sessao=sessao,
                cliente_id=str(cliente_id),
                telefone=numero,
                nome_cliente=nome_conversa,
                historico_texto=historico_venda,
            )
            contexto_venda.memoria = sessao
            if mcp_bloco:
                contexto_venda.briefing = (
                    (contexto_venda.briefing or "")
                    + "\nUse RESULTADOS MCP abaixo; não invente dados fora deles."
                ).strip()
                persistir_sessao(str(cliente_id), sessao)
        except Exception as mcp_exc:
            print("MCP enrich falhou (seguindo sem MCP):", type(mcp_exc).__name__, str(mcp_exc)[:120])
            mcp_bloco = ""

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

        if resposta_pos_venda is not None:
            resposta_ia = resposta_pos_venda
        elif fechamento or alteracao_pagamento:
            frete_estimado = float(os.getenv("FRETE_ESTIMADO", "0") or "0")
            pedido_registrado = None
            ja_encerrado = pedido_ja_encerrado(ultima_resposta_ia, historico_texto) and not nova_venda

            # Script Xnamai: alinhar NF + envio antes de gravar o pedido
            if (
                not ja_encerrado
                and fechamento
                and not alinhamento_completo(historico_venda, mensagem)
            ):
                resposta_ia = resposta_alinhamento_pedido(nome_conversa)
                print("ALINHAMENTO XNAMAI: pedindo NF e forma de envio")
            elif (
                not ja_encerrado
                and fechamento
                and precisa_avisar_pedido_minimo(historico_venda)
            ):
                resposta_ia = resposta_pedido_minimo(
                    nome_conversa, valor_pedido_historico(historico_venda)
                )
                print("PEDIDO MINIMO XNAMAI: valor abaixo do mínimo")
            else:
                if not ja_encerrado and (fechamento or alteracao_pagamento):
                    # 1) Mercos (pedido real no ERP) — se habilitado
                    pedido_mercos = None
                    if mercos_criar_pedido_habilitado():
                        pedido_mercos = criar_pedido_fechamento_mercos(
                            historico_texto=historico_venda,
                            cliente_supabase=cliente,
                            telefone=numero,
                            pushname=nome_cliente,
                            mensagem_atual=mensagem,
                            ultima_resposta_ia=ultima_resposta_ia,
                            frete_estimado=frete_estimado,
                        )
                        if pedido_mercos and pedido_mercos.get("pedido_id"):
                            print("MERCOS PEDIDO CRIADO:", pedido_mercos)
                            try:
                                from services.supabase_service import atualizar_cliente

                                cliente_mercos_id = int(pedido_mercos["cliente_id"])
                                atualizar_cliente(
                                    cliente["id"],
                                    mercos_cliente_id=cliente_mercos_id,
                                )
                                cliente["mercos_cliente_id"] = cliente_mercos_id
                            except Exception as exc:
                                print("AVISO: falha ao salvar mercos_cliente_id:", exc)
                        elif pedido_mercos and pedido_mercos.get("erro"):
                            print("MERCOS PEDIDO FALHOU:", pedido_mercos["erro"])

                    # 2) PulseDesk (Supabase)
                    if pulsedesk_pedidos_habilitado():
                        pedido_registrado = registrar_venda_pulsedesk(
                            historico_texto=historico_venda,
                            cliente_supabase=cliente,
                            telefone=numero,
                            pushname=nome_cliente,
                            mensagem_atual=mensagem,
                            ultima_resposta_ia=ultima_resposta_ia,
                            frete_estimado=frete_estimado,
                            nova_venda=nova_venda,
                        )
                        if pedido_mercos and pedido_mercos.get("pedido_id"):
                            pedido_registrado = {
                                **(pedido_registrado or {}),
                                "pedido_id": pedido_mercos.get("pedido_id"),
                                "numero": pedido_mercos.get("numero")
                                or pedido_mercos.get("pedido_id"),
                                "origem": "mercos+pulsedesk",
                            }
                    elif pedido_mercos:
                        pedido_registrado = pedido_mercos
                    else:
                        pedido_registrado = None

                resposta_ia = resposta_fechamento_pedido(
                    historico_venda,
                    nome_cliente,
                    frete_estimado,
                    mensagem_atual=mensagem,
                    ultima_resposta_ia=ultima_resposta_ia,
                    mercos_pedido=pedido_registrado,
                )
                resultado_fechamento = buscar_produtos_para_atendimento(historico_venda)
                if vendedor_configurado():
                    notificar_vendedor(
                        numero_cliente=numero,
                        nome_cliente=nome_conversa,
                        interesse="pedido fechado",
                        mensagem_cliente=mensagem,
                        produtos=resultado_fechamento.get("produtos"),
                    )
                    print("VENDEDOR NOTIFICADO: pedido fechado")

                if pedido_registrado and pedido_registrado.get("pedido_id"):
                    print("PULSEDESK PEDIDO CRIADO:", pedido_registrado)
                elif pedido_registrado and pedido_registrado.get("erro"):
                    print("PULSEDESK PEDIDO FALHOU:", pedido_registrado["erro"])
        elif saudacao:
            resposta_ia = resposta_saudacao(nome_conversa)
        elif cliente_perguntou_como_trabalham(mensagem) and not pedido_encerrado:
            resposta_ia = resposta_como_trabalham(nome_conversa)
            print("SCRIPT XNAMAI: como trabalhamos (não é produto)")
        elif cliente_perguntou_estoque(mensagem) and not pedido_encerrado:
            resposta_ia = resposta_estoque_disponibilidade(nome_conversa)
            print("SCRIPT XNAMAI: resposta de estoque/disponibilidade")
        elif nova_venda_explicita:
            # Não empurrar catálogo: deixa o cliente dizer o que quer
            resposta_ia = resposta_abrir_espaco_pedido(nome_conversa)
            print("NOVA VENDA: acolhimento sem oferecer produtos")
        elif pediu_foto and produtos and not com_foto:
            resposta_ia = resposta_sem_foto(produtos[0])
        elif pediu_foto and com_foto and repetindo:
            resposta_ia = resposta_ja_informado(com_foto[0])
        elif pediu_foto and com_foto:
            resposta_ia = resposta_com_foto(com_foto[0])
        elif cliente_quer_ver_catalogo(mensagem, ultima_resposta_ia):
            cat_geral = montar_catalogo_geral()
            produtos = cat_geral["produtos"]
            catalogo = cat_geral["catalogo"]
            resposta_ia = resposta_mostrar_catalogo(nome_conversa, produtos)
        elif cliente_perguntou_preco(mensagem) and not pedido_encerrado:
            resposta_ia = resposta_preco_em_discussao(
                historico_venda,
                nome_conversa,
                produtos,
            )
            print("PRECO: resposta pelo produto em discussão")
        elif (
            not pedido_encerrado
            and mensagem_ambigua_para_llm(mensagem, sessao)
            and not cliente_perguntou_preco(mensagem)
        ):
            from services.openai_service import TEMPERATURE_CONVERSA

            ultima_para_ia = (
                ""
                if nova_venda_explicita or historico_venda != historico_texto
                else ultima_resposta_ia
            )
            resposta_ia = perguntar_ia(
                mensagem=mensagem,
                catalogo=catalogo,
                historico_texto=historico_recente(historico_venda, max_linhas=12),
                nome_cliente=nome_conversa,
                ultima_resposta_ia=ultima_para_ia,
                foto_automatica=bool(com_foto and pediu_foto),
                contexto_venda=contexto_venda,
                memoria_sessao=sessao,
                temperature=TEMPERATURE_CONVERSA,
                mcp_enrichment=mcp_bloco,
            )
            print("LLM: pergunta ambígua sobre produto ativo")
        elif (
            not pedido_encerrado
            and not cliente_quer_ver_catalogo(mensagem, ultima_resposta_ia)
            and not cliente_quer_novo_atendimento(mensagem)
            and entrega_ja_informada(historico_venda)
            and (ia_ja_pediu_endereco(historico_venda) or extrair_preferencia_entrega(mensagem))
        ):
            resposta_ia = resposta_entrega_ja_anotada(nome_conversa, historico_venda)
        elif (
            contexto_venda.sem_match
            and not mensagem_nao_e_busca_produto(mensagem)
            and not (
                conversa_em_andamento(historico_venda)
                and _mensagem_tem_confirmacao(mensagem)
            )
        ):
            resposta_ia = resposta_fora_catalogo(
                nome_cliente=nome_conversa,
                termos=contexto_venda.termos_cliente,
                amostra=contexto_venda.amostra_disponivel,
            )
        else:
            # Após reabrir venda, não reaproveita a última resposta do pedido fechado
            ultima_para_ia = (
                ""
                if nova_venda_explicita or historico_venda != historico_texto
                else ultima_resposta_ia
            )
            resposta_ia = perguntar_ia(
                mensagem=mensagem,
                catalogo=catalogo,
                historico_texto=historico_recente(historico_venda, max_linhas=12),
                nome_cliente=nome_conversa,
                ultima_resposta_ia=ultima_para_ia,
                foto_automatica=bool(com_foto and pediu_foto),
                contexto_venda=contexto_venda,
                memoria_sessao=sessao,
                mcp_enrichment=mcp_bloco,
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

        envio = enviar_mensagem(
            numero,
            resposta_ia
        )
        if isinstance(envio, dict) and not envio.get("ok"):
            print("FALHA ENVIO WHATSAPP:", envio)
        elif envio is None:
            print("FALHA ENVIO WHATSAPP: resposta vazia da Z-API")

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
        "pulsedesk_pedidos": pulsedesk_pedidos_habilitado(),
        "mercos_base_url": os.getenv("MERCOS_BASE_URL", ""),
        "vendas_consultivas": True,
        "code_version": CODE_VERSION,
        "pulsedesk_bridge": os.getenv("PULSEDESK_BRIDGE_ENABLED", "true"),
        "mcp_enabled": os.getenv("MCP_ENABLED", "true"),
        "mcp_server_enabled": os.getenv("MCP_SERVER_ENABLED", "false"),
    }


@router.get("/teste-supabase-produtos")
async def teste_supabase_produtos(token: str = ""):
    """Diagnóstico direto — lê produtos do Supabase sem montar catálogo."""
    bloqueio = _bloqueio_diagnostico(token)
    if bloqueio:
        return bloqueio
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


@router.get("/teste-pulsedesk-pedidos")
async def teste_pulsedesk_pedidos(tel: str = "554396717931", token: str = ""):
    """Diagnóstico — lê cliente/pedidos WhatsApp no Supabase PulseDesk."""
    bloqueio = _bloqueio_diagnostico(token)
    if bloqueio:
        return bloqueio
    try:
        return {
            "status": "ok",
            "code_version": CODE_VERSION,
            "pulsedesk_pedidos": pulsedesk_pedidos_habilitado(),
            **diagnosticar_pulsedesk_pedidos(tel),
        }
    except Exception as e:
        import traceback
        return {
            "status": "erro",
            "code_version": CODE_VERSION,
            "mensagem": str(e),
            "traceback": traceback.format_exc(),
        }


@router.get("/registrar-pedido-pulsedesk")
async def registrar_pedido_pulsedesk(tel: str = "", token: str = ""):
    """Backfill — grava no PulseDesk pedido fechado no WhatsApp (histórico agent)."""
    bloqueio = _bloqueio_diagnostico(token)
    if bloqueio:
        return bloqueio

    if not tel:
        return {"status": "erro", "mensagem": "Informe ?tel=554396717931"}

    try:
        resultado = registrar_venda_retroativa_por_telefone(tel)
        return {"code_version": CODE_VERSION, **resultado}
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
    """Sincroniza produtos Mercos → Supabase. Exige SYNC_TOKEN (ou DIAGNOSTICOS_ABERTOS)."""
    bloqueio = _bloqueio_diagnostico(token)
    if bloqueio:
        return bloqueio

    try:
        from services.supabase_service import invalidar_cache_produtos

        resultado = sincronizar_produtos_mercos()
        invalidar_cache_produtos()
        return {"status": "ok", **resultado}
    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}


@router.get("/teste-produtos")
async def teste_produtos(q: str = "", token: str = ""):
    """Testa busca de produtos (Mercos primeiro, Supabase fallback)."""
    bloqueio = _bloqueio_diagnostico(token)
    if bloqueio:
        return bloqueio
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
async def teste_mercos(q: str = "", token: str = ""):
    return await teste_produtos(q, token)


@router.get("/teste-vendedor")
async def teste_vendedor(token: str = ""):
    """Envia notificação de teste para o WhatsApp do vendedor."""
    bloqueio = _bloqueio_diagnostico(token)
    if bloqueio:
        return bloqueio
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
async def teste_imagem(tel: str = "", url: str = "", token: str = ""):
    """Envia imagem de teste via WhatsApp (Z-API ou UltraMsg)."""
    bloqueio = _bloqueio_diagnostico(token)
    if bloqueio:
        return bloqueio
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
async def teste_whatsapp(tel: str = "", token: str = ""):
    """Envia mensagem de teste direto pelo provedor WhatsApp configurado."""
    bloqueio = _bloqueio_diagnostico(token)
    if bloqueio:
        return bloqueio
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

    ok = isinstance(resposta, dict) and resposta.get("ok")
    return {
        "status": "ok" if ok else "erro",
        "provider": provider_nome(),
        "zapi_client_token_configurado": bool(os.getenv("ZAPI_CLIENT_TOKEN", "").strip()),
        "resposta_whatsapp": resposta,
    }