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
    cliente_pediu_mais_opcoes,
    cliente_perguntou_preco,
    cliente_quer_ver_catalogo,
    resposta_fora_catalogo,
    resposta_mais_opcoes,
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
from services.config_tabelas import (
    normalizar_telefone,
    status_validacao,
    tabelas_configuradas,
)
from services.historico_service import (
    montar_bloco_contexto_openai,
    registrar_perguntas_respondidas,
    sanitizar_resposta_anti_repeticao,
)
from services.webhook_guard import (
    finalizar_mensagem,
    lock_telefone,
    log_seguro,
    reclamar_mensagem,
)
from services.webhook_normalizer import normalizar_webhook
from services.webhook_service import evento_deve_ser_ignorado, extrair_id_mensagem
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

CODE_VERSION = "2026-07-10-etapa2-historico"

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


def processar_mensagem(data: dict, dry_run: bool = False):
    inicio = __import__("time").time()
    claim_ok = False
    numero = ""
    msg_id = ""

    try:

        if "data" not in data:
            print("EVENTO IGNORADO:", data)
            return None

        ignorar, motivo = evento_deve_ser_ignorado(data)
        if ignorar:
            log_seguro("webhook_ignorado", motivo=motivo)
            return None

        ok_claim, motivo_claim = reclamar_mensagem(data)
        if not ok_claim:
            log_seguro("duplicidade_detectada", motivo=motivo_claim)
            return None
        claim_ok = True

        evento = data["data"]
        msg_id = extrair_id_mensagem(data, evento)

        # Eco do bot: campos reais do payload (fromMe), não só texto
        if evento.get("fromMe") is True:
            log_seguro("eco_bot_ignorado", message_id=msg_id or "-")
            finalizar_mensagem(data, sucesso=True)
            return None

        numero_raw = evento.get("from", "")
        if "@g.us" in numero_raw:
            log_seguro("grupo_ignorado", message_id=msg_id or "-")
            finalizar_mensagem(data, sucesso=True)
            return None

        numero = normalizar_telefone(numero_raw.split("@")[0])
        mensagem = (evento.get("body") or "").strip()
        nome_cliente = evento.get("pushname") or ""

        if evento.get("type") and evento.get("type") != "chat":
            log_seguro("tipo_ignorado", tipo=evento.get("type"), message_id=msg_id or "-")
            finalizar_mensagem(data, sucesso=True)
            return None

        if not numero or not mensagem:
            log_seguro(
                "mensagem_vazia_ou_sem_telefone",
                telefone=numero or "-",
                message_id=msg_id or "-",
            )
            finalizar_mensagem(data, sucesso=True)
            return None

        # Concorrência: um processamento por telefone (preserva ordem)
        with lock_telefone(numero):
            return _processar_mensagem_locked(
                data=data,
                dry_run=dry_run,
                numero=numero,
                mensagem=mensagem,
                nome_cliente=nome_cliente,
                msg_id=msg_id,
                inicio=inicio,
            )

    except Exception as e:
        print("ERRO:")
        print(str(e))
        traceback.print_exc()
        if claim_ok:
            finalizar_mensagem(data, sucesso=False)
        return None


def _processar_mensagem_locked(
    *,
    data: dict,
    dry_run: bool,
    numero: str,
    mensagem: str,
    nome_cliente: str,
    msg_id: str,
    inicio: float,
):
    try:
        log_seguro(
            "processamento_inicio",
            telefone=numero,
            message_id=msg_id or "-",
            etapa="inicio",
        )

        # =========================
        # CLIENTE (isolado por telefone normalizado)
        # =========================

        cliente = buscar_cliente(numero)

        if not cliente:
            cliente = criar_cliente(numero, nome=nome_cliente)
            log_seguro("cliente_novo", telefone=numero, message_id=msg_id or "-")
        elif nome_cliente and cliente.get("nome") != nome_cliente:
            atualizar_cliente(cliente_id=cliente["id"], nome=nome_cliente)
            cliente["nome"] = nome_cliente

        cliente_id = cliente["id"]

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

        log_seguro(
            "historico_carregado",
            telefone=numero,
            message_id=msg_id or "-",
            linhas=historico_texto.count("\n"),
        )

        # =========================
        # PRODUTOS
        # =========================

        nome_conversa = extrair_nome_do_historico(historico_texto, nome_cliente)
        estado_venda = resolver_estado_venda(
            historico_texto, mensagem, ultima_resposta_ia
        )
        log_seguro(
            "estado_venda",
            telefone=numero,
            message_id=msg_id or "-",
            etapa=estado_venda,
        )

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
            nome_cliente=nome_conversa or nome_cliente,
        )
        sessao = registrar_perguntas_respondidas(sessao, mensagem)
        contexto_venda.memoria = sessao
        persistir_sessao(str(cliente_id), sessao)

        historico_para_ia = montar_bloco_contexto_openai(
            historico_texto=historico_venda,
            mensagem_atual=mensagem,
            contexto=sessao,
            info_cliente=cliente,
            max_linhas=16,
        )
        log_seguro(
            "contexto_extraido",
            telefone=numero,
            message_id=msg_id or "-",
            resumo=sessao.get("resumo_curto") or "-",
            estagio=sessao.get("estagio_conversa") or "-",
            cat=sessao.get("categoria_interesse") or "-",
        )

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
        elif cliente_pediu_mais_opcoes(mensagem) and not pedido_encerrado:
            # "tem mais opções?" — NUNCA cair em "não trabalhamos com opções produtos"
            # Avaliado ANTES de cliente_quer_ver_catalogo para não perder "me mostra outros"
            cat_geral = montar_catalogo_geral()
            produtos_op = cat_geral.get("produtos") or produtos
            resposta_ia = resposta_mais_opcoes(
                nome_cliente=nome_conversa,
                historico_texto=historico_venda,
                produtos=produtos_op,
            )
            print("MAIS OPCOES: resposta consultiva (sem fora_catalogo)")
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
                historico_texto=historico_para_ia,
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
            and not cliente_pediu_mais_opcoes(mensagem)
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
                historico_texto=historico_para_ia,
                nome_cliente=nome_conversa,
                ultima_resposta_ia=ultima_para_ia,
                foto_automatica=bool(com_foto and pediu_foto),
                contexto_venda=contexto_venda,
                memoria_sessao=sessao,
                mcp_enrichment=mcp_bloco,
            )

        resposta_ia, motivos_evitados = sanitizar_resposta_anti_repeticao(
            resposta_ia,
            historico_venda,
            sessao,
            mensagem,
        )
        if motivos_evitados:
            log_seguro(
                "pergunta_evitada",
                telefone=numero,
                message_id=msg_id or "-",
                motivos=",".join(motivos_evitados),
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
        if not dry_run:
            espelhar_mensagem_agente(numero, nome_cliente, resposta_ia)

        atualizar_historico_json(cliente_id)

        # Atualiza última pergunta do agente na sessão
        from services.historico_service import extrair_ultima_pergunta_ia

        sessao["ultima_pergunta_agente"] = extrair_ultima_pergunta_ia(
            historico_venda + f"\nIA: {resposta_ia}\n"
        ) or sessao.get("ultima_pergunta_agente") or ""
        persistir_sessao(str(cliente_id), sessao)

        # =========================
        # ENVIA WHATSAPP
        # =========================

        if dry_run:
            print("DRY_RUN: WhatsApp não enviado")
            finalizar_mensagem(data, sucesso=True)
            log_seguro(
                "processamento_fim",
                telefone=numero,
                message_id=msg_id or "-",
                etapa="dry_run",
                ms=int((__import__("time").time() - inicio) * 1000),
            )
            return resposta_ia

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
        finalizar_mensagem(data, sucesso=True)
        log_seguro(
            "processamento_fim",
            telefone=numero,
            message_id=msg_id or "-",
            etapa=sessao.get("estagio_conversa") or "fim",
            ms=int((__import__("time").time() - inicio) * 1000),
        )
        return resposta_ia

    except Exception as e:
        print("ERRO:")
        print(str(e))
        traceback.print_exc()
        finalizar_mensagem(data, sucesso=False)
        return None


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


@router.post("/chat")
async def chat_teste(payload: dict):
    """
    Teste local do agente sem enviar WhatsApp.
    Body: {"telefone": "5543999999999", "mensagem": "tem mais opções?", "nome": "Arthur"}
    """
    telefone = normalizar_telefone(
        str(payload.get("telefone") or payload.get("phone") or "")
    )
    mensagem = str(payload.get("mensagem") or payload.get("message") or "").strip()
    nome = str(payload.get("nome") or payload.get("name") or "Cliente").strip()

    if not telefone or not mensagem:
        return {
            "status": "erro",
            "mensagem": "Informe telefone e mensagem",
            "code_version": CODE_VERSION,
        }

    data = {
        "event_type": "message_received",
        "provider": "chat_teste",
        "data": {
            "from": telefone,
            "body": mensagem,
            "pushname": nome,
            "fromMe": False,
            "type": "chat",
            "id": f"chat-{telefone}-{int(__import__('time').time()*1000)}-{abs(hash(mensagem)) % 10_000_000}",
            "time": __import__("time").time(),
        },
    }

    loop = asyncio.get_event_loop()
    resposta = await loop.run_in_executor(
        None, lambda: processar_mensagem(data, dry_run=True)
    )

    return {
        "status": "ok" if resposta else "erro",
        "telefone": telefone,
        "mensagem": mensagem,
        "resposta": resposta,
        "code_version": CODE_VERSION,
    }


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
        "tabelas": tabelas_configuradas(),
        "tabelas_validacao": status_validacao(),
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