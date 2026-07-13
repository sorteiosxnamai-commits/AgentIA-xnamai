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
from services import ultramsg_service as ultramsg_svc
from services import zapi_service as zapi_svc
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
from services.intent_service import (
    classificar_intencao,
    resposta_atendimento_humano,
    resposta_fora_do_escopo,
    resposta_sac,
    sanitizar_frases_comerciais,
)
from services.product_service import (
    aplicar_resultado_no_contexto,
    buscar_por_intencao,
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
from services.pedido_mercos_service import mercos_criar_pedido_habilitado
from services.pedido_pulsedesk_service import (
    diagnosticar_pulsedesk_pedidos,
    pulsedesk_pedidos_habilitado,
    registrar_venda_retroativa_por_telefone,
)
from services.checkout_service import (
    checkout_criar_pedido_habilitado,
    checkout_habilitado,
    intent_e_checkout,
    processar_checkout_turno,
    sanitizar_claims_checkout,
)
from services.supabase_service import (
    buscar_cliente,
    criar_cliente,
    atualizar_cliente,
    salvar_mensagem,
    buscar_historico,
    atualizar_historico_json,
    diagnosticar_schema_persistencia,
    diagnosticar_supabase_status,
    diagnosticar_persistencia_cliente,
    atualizar_thread_conversa,
    limpar_ultimo_erro_cliente,
    obter_ultimo_erro_cliente,
    registrar_erro_cliente,
    erro_cliente_para_debug,
    clientes_tem_historico,
    diagnostico_coluna_historico,
    limpar_ultimo_erro_historico,
    obter_ultimo_erro_historico,
)

CODE_VERSION = "2026-07-13-fix-ultramsg-webhook-parser"
from services.sync_mercos_service import sincronizar_produtos_mercos
from services.pulsedesk_bridge import espelhar_mensagem_agente, espelhar_mensagem_cliente
from services.vendedor_service import (
    notificar_vendedor,
    processar_lead_e_notificar,
    vendedor_configurado,
)


def _resposta_texto(resultado) -> str | None:
    """Extrai texto da resposta (str legado ou dict Etapa 5+)."""
    if isinstance(resultado, dict):
        return resultado.get("resposta")
    return resultado


def _montar_resultado(
    resposta: str | None,
    persistencia_ok: bool = True,
    persistencia_etapas: dict | None = None,
    cliente_debug: dict | None = None,
    historico_debug: dict | None = None,
    formatacao_debug: dict | None = None,
) -> dict:
    out = {
        "resposta": resposta,
        "persistencia_ok": bool(persistencia_ok) if resposta else False,
    }
    if persistencia_etapas is not None:
        out["persistencia_etapas"] = persistencia_etapas
    if cliente_debug is not None:
        out["cliente_debug"] = cliente_debug
    if historico_debug is not None:
        out["historico_debug"] = historico_debug
    if formatacao_debug is not None:
        out["formatacao_debug"] = formatacao_debug
    return out


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


def processar_mensagem(data: dict, dry_run: bool = False, persistir: bool = True):
    """
    Processa mensagem do webhook /chat.

    dry_run=True  → não envia WhatsApp (padrão do /chat).
    persistir=False → não grava no Supabase (mensagens, histórico, lead, sessão)
                      nem envia WhatsApp. Útil para testar resposta sem sujar o banco.
    Se persistir não for informado (padrão True), mantém o comportamento atual
    (grava no banco mesmo com dry_run=True).
    """
    inicio = __import__("time").time()
    claim_ok = False
    numero = ""
    msg_id = ""

    try:

        if "data" not in data:
            log_seguro("evento_ignorado", motivo="sem_data")
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
        # Mojibake só para intenção/resposta — não reescreve catálogo no banco
        from services.texto_seguro import reparar_mojibake

        mensagem = reparar_mojibake((evento.get("body") or "").strip())
        nome_cliente = reparar_mojibake(evento.get("pushname") or "")

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
                persistir=persistir,
                numero=numero,
                mensagem=mensagem,
                nome_cliente=nome_cliente,
                msg_id=msg_id,
                inicio=inicio,
            )

    except Exception as e:
        print("ERRO:")
        print(type(e).__name__, str(e)[:200])
        traceback.print_exc()
        if claim_ok:
            finalizar_mensagem(data, sucesso=False)
        return None


def _processar_mensagem_locked(
    *,
    data: dict,
    dry_run: bool,
    persistir: bool,
    numero: str,
    mensagem: str,
    nome_cliente: str,
    msg_id: str,
    inicio: float,
):
    persistencia_ok = True
    resposta_ia = None
    # Com persistir: começa False — só True após gravação real no banco
    etapas = {
        "cliente_ok": not persistir,
        "contexto_ok": not persistir,
        "historico_ok": not persistir,
        "thread_ok": not persistir,
        "message_log_ok": not persistir,
    }
    origem_cliente = "desconhecido"
    contexto_salvo_em = "nenhum"
    historico_salvo_em = "nenhum"

    def _tentar_persistir(
        etapa: str,
        fn,
        *,
        ok_se_truthy: bool = False,
        essencial: bool = True,
        etapa_flag: str | None = None,
    ):
        nonlocal persistencia_ok
        if not persistir:
            return None
        try:
            result = fn()
            if ok_se_truthy and not result:
                if etapa_flag:
                    etapas[etapa_flag] = False
                if essencial:
                    persistencia_ok = False
                    log_seguro(
                        "chat_erro_persistencia",
                        telefone=numero,
                        message_id=msg_id or "-",
                        etapa=etapa,
                        erro="persistencia_retornou_falso",
                    )
                else:
                    log_seguro(
                        "chat_aviso_persistencia",
                        telefone=numero,
                        message_id=msg_id or "-",
                        etapa=etapa,
                        erro="opcional_retornou_falso",
                    )
            elif etapa_flag:
                etapas[etapa_flag] = True
            return result
        except Exception as exc:
            if etapa_flag:
                etapas[etapa_flag] = False
            if etapa in ("criar_cliente", "buscar_cliente") or etapa_flag == "cliente_ok":
                try:
                    registrar_erro_cliente(etapa, exc)
                except Exception:
                    pass
            if essencial:
                persistencia_ok = False
                log_seguro(
                    "chat_erro_persistencia",
                    telefone=numero,
                    message_id=msg_id or "-",
                    etapa=etapa,
                    erro=type(exc).__name__,
                    detalhe=str(exc)[:120],
                )
            else:
                log_seguro(
                    "chat_aviso_persistencia",
                    telefone=numero,
                    message_id=msg_id or "-",
                    etapa=etapa,
                    erro=type(exc).__name__,
                    detalhe=str(exc)[:120],
                )
            return None

    try:
        log_seguro(
            "processamento_inicio",
            telefone=numero,
            message_id=msg_id or "-",
            etapa="inicio",
            persistir=persistir,
            dry_run=dry_run,
        )

        # =========================
        # CLIENTE (isolado por telefone normalizado)
        # =========================

        limpar_ultimo_erro_cliente()
        limpar_ultimo_erro_historico()
        cliente_debug_erro = None
        historico_tentou_salvar = False
        historico_erro_dbg = None
        historico_coluna_meta = diagnostico_coluna_historico()
        historico_essencial = bool(historico_coluna_meta.get("historico_coluna_existe"))

        try:
            cliente = buscar_cliente(numero)
        except Exception as exc:
            cliente = None
            cliente_debug_erro = registrar_erro_cliente("buscar_cliente", exc)
            log_seguro(
                "cliente_busca_nao_encontrado",
                telefone=numero,
                message_id=msg_id or "-",
                erro=type(exc).__name__,
                detalhe=str(exc)[:120],
            )

        if cliente and cliente.get("id") and not str(cliente.get("id")).startswith("ephemeral-"):
            etapas["cliente_ok"] = True
            tel_norm = numero
            if str(cliente.get("telefone") or "") == tel_norm:
                origem_cliente = "telefone"
            elif str(cliente.get("celular") or "") == tel_norm:
                origem_cliente = "celular"
            else:
                origem_cliente = "telefone"
        elif persistir:
            cliente = _tentar_persistir(
                "criar_cliente",
                lambda: criar_cliente(numero, nome=nome_cliente),
                essencial=True,
                etapa_flag="cliente_ok",
            )
            if not cliente:
                cliente_debug_erro = obter_ultimo_erro_cliente() or cliente_debug_erro
            if cliente and cliente.get("id") and not str(cliente.get("id")).startswith("ephemeral-"):
                origem_cliente = "criado"
                etapas["cliente_ok"] = True
            else:
                # Insert sem retorno / race: rebusca antes de ephemeral
                try:
                    cliente = buscar_cliente(numero)
                except Exception as exc:
                    cliente = None
                    cliente_debug_erro = registrar_erro_cliente("rebusca", exc)
                if cliente and cliente.get("id") and not str(cliente.get("id")).startswith("ephemeral-"):
                    origem_cliente = "rebuscado"
                    etapas["cliente_ok"] = True
                    log_seguro("cliente_novo", telefone=numero, message_id=msg_id or "-")
                else:
                    # Garante erro estruturado (nunca string vazia)
                    cliente_debug_erro = erro_cliente_para_debug("criar_cliente")
                    # Probe extra em dry_run para capturar causa real (RLS/schema/rede)
                    if dry_run:
                        try:
                            probe = diagnosticar_persistencia_cliente(numero)
                            if probe.get("erro"):
                                cliente_debug_erro = {
                                    "etapa": str(probe["erro"].get("etapa") or "probe"),
                                    "erro_codigo": str(probe["erro"].get("erro_codigo") or ""),
                                    "erro_tipo": str(probe["erro"].get("erro_tipo") or ""),
                                    "erro_resumido": str(probe["erro"].get("erro_resumido") or "")[:160],
                                }
                                registrar_erro_cliente(
                                    f"probe_{cliente_debug_erro['etapa']}",
                                    codigo=cliente_debug_erro["erro_codigo"],
                                    tipo=cliente_debug_erro["erro_tipo"],
                                    resumo=cliente_debug_erro["erro_resumido"],
                                )
                            elif not probe.get("insert_ok"):
                                cliente_debug_erro = {
                                    "etapa": "probe_insert",
                                    "erro_codigo": "PROBE_FAIL",
                                    "erro_tipo": "PERSISTENCIA",
                                    "erro_resumido": "probe não conseguiu inserir em clientes",
                                }
                        except Exception as probe_exc:
                            cliente_debug_erro = registrar_erro_cliente("probe", probe_exc)
                    cliente = {
                        "id": f"ephemeral-{numero}",
                        "telefone": numero,
                        "nome": nome_cliente,
                        "contexto_venda": {},
                    }
                    origem_cliente = "ephemeral"
                    # Nunca deixar historico/contexto “ok” por valor inicial quando caiu em fallback
                    etapas["cliente_ok"] = False
                    etapas["contexto_ok"] = False
                    etapas["historico_ok"] = False
                    etapas["thread_ok"] = False
                    etapas["message_log_ok"] = False
                    persistencia_ok = False
                    contexto_salvo_em = "fallback"
                    historico_salvo_em = "fallback"
        else:
            cliente = {
                "id": f"ephemeral-{numero}",
                "telefone": numero,
                "nome": nome_cliente,
                "contexto_venda": {},
            }
            origem_cliente = "ephemeral"
            log_seguro("cliente_ephemeral", telefone=numero, message_id=msg_id or "-")

        # Update de nome é opcional — nunca derruba cliente_ok
        if (
            cliente
            and not str(cliente.get("id") or "").startswith("ephemeral-")
            and nome_cliente
            and cliente.get("nome") != nome_cliente
        ):
            if persistir:
                _tentar_persistir(
                    "atualizar_nome",
                    lambda: atualizar_cliente(cliente_id=cliente["id"], nome=nome_cliente),
                    essencial=False,
                )
            cliente["nome"] = nome_cliente

        cliente_id = cliente["id"]
        cliente_real = bool(
            persistir
            and cliente_id
            and not str(cliente_id).startswith("ephemeral-")
        )
        if cliente_real:
            etapas["cliente_ok"] = True

        if dry_run or persistir:
            log_seguro(
                "cliente_resolvido",
                telefone=numero,
                message_id=msg_id or "-",
                cliente_ok=etapas.get("cliente_ok"),
                tem_cliente_id=cliente_real,
                origem_cliente=origem_cliente,
                contexto_salvo_em=contexto_salvo_em,
                historico_salvo_em=historico_salvo_em,
            )

        # =========================
        # SALVA MENSAGEM (histórico se coluna existir; thread opcional)
        # =========================

        if persistir and not str(cliente_id).startswith("ephemeral-"):
            if historico_essencial:
                historico_tentou_salvar = True
                _tentar_persistir(
                    "salvar_mensagem_cliente",
                    lambda: salvar_mensagem(
                        cliente_id,
                        "cliente",
                        mensagem,
                        message_id=msg_id or None,
                        telefone=numero,
                        nome=nome_cliente,
                    ),
                    essencial=True,
                    etapa_flag="historico_ok",
                )
                if etapas.get("historico_ok"):
                    historico_salvo_em = "banco"
                else:
                    historico_erro_dbg = obter_ultimo_erro_historico()
                    historico_salvo_em = "nenhum"
                    # Se a coluna sumiu no meio do caminho, deixa de ser essencial
                    if not clientes_tem_historico():
                        historico_essencial = False
                        etapas["historico_ok"] = True
                        historico_salvo_em = "nenhum"
            else:
                # Sem coluna historico: não essencial — contexto_venda cobre a sessão
                etapas["historico_ok"] = True
                historico_salvo_em = "nenhum"
                historico_tentou_salvar = False

            # Thread PulseDesk — opcional
            _tentar_persistir(
                "atualizar_thread",
                lambda: atualizar_thread_conversa(
                    numero,
                    nome_cliente,
                    mensagem,
                    message_id=msg_id or None,
                    inbound=True,
                ),
                ok_se_truthy=True,
                essencial=False,
                etapa_flag="thread_ok",
            )
            # Bridge PulseDesk só em tráfego real (não dry_run de /chat)
            if dry_run:
                etapas["message_log_ok"] = True  # bridge não aplicável em dry_run
            elif not dry_run:
                try:
                    espelhar_mensagem_cliente(numero, nome_cliente, mensagem)
                    etapas["message_log_ok"] = True
                except Exception as exc:
                    etapas["message_log_ok"] = False
                    log_seguro(
                        "chat_aviso_persistencia",
                        telefone=numero,
                        message_id=msg_id or "-",
                        etapa="espelhar_cliente",
                        erro=type(exc).__name__,
                    )
            if historico_essencial:
                _tentar_persistir(
                    "atualizar_historico_json",
                    lambda: atualizar_historico_json(cliente_id),
                    essencial=False,
                )

        # =========================
        # HISTÓRICO
        # =========================

        if str(cliente_id).startswith("ephemeral-"):
            historico = []
        else:
            historico = buscar_historico(cliente_id)

        historico_texto = ""
        ultima_resposta_ia = ""

        for msg in historico:

            if msg["tipo"] == "cliente":
                historico_texto += f"Cliente: {msg['mensagem']}\n"
            else:
                historico_texto += f"IA: {msg['mensagem']}\n"
                ultima_resposta_ia = msg["mensagem"]

        # Em modo sem persistir, inclui a mensagem atual (ainda não está no banco)
        if not persistir:
            historico_texto += f"Cliente: {mensagem}\n"

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
            if persistir:
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

        # =========================
        # ETAPA 3 — classificação de intenção (não responde ao cliente)
        # =========================
        intent = classificar_intencao(
            mensagem,
            historico_texto=historico_venda,
            contexto_venda=sessao,
            produto_ativo=str(sessao.get("produto_ativo") or ""),
            categoria_ativa=str(sessao.get("categoria_interesse") or ""),
            ultima_pergunta_agente=str(sessao.get("ultima_pergunta_agente") or ""),
        )
        sessao["ultima_intencao"] = intent.get("intent") or "INDEFINIDO"
        if intent.get("category") and not sessao.get("categoria_interesse"):
            sessao["categoria_interesse"] = intent["category"]
        contexto_venda.memoria = sessao
        if persistir and not str(cliente_id).startswith('ephemeral-'):
            _tentar_persistir(
                'atualizar_contexto',
                lambda: persistir_sessao(str(cliente_id), sessao),
                ok_se_truthy=True,
                essencial=False,
            )

        log_seguro(
            "intent_classificada",
            telefone=numero,
            message_id=msg_id or "-",
            intent=intent.get("intent"),
            confidence=intent.get("confidence"),
            needs_catalog=intent.get("needs_catalog"),
            needs_human=intent.get("needs_human"),
            category=intent.get("category") or "-",
            reason=intent.get("reason") or "-",
        )

        # =========================
        # ETAPA 4 — Product Service (antes da resposta comercial)
        # =========================
        resultado_produtos = None
        intent_nome = (intent.get("intent") or "").upper()
        if (
            not pular_catalogo
            and not pedido_encerrado
            and intent_nome
            in (
                "BUSCA_PRODUTO",
                "CATALOGO_GERAL",
                "PRODUTOS_DISPONIVEIS",
                "MAIS_OPCOES",
                "PRECO",
                "COMPARACAO",
                "COMPRA",
                "DUVIDA_PRODUTO",
            )
        ):
            resultado_produtos = buscar_por_intencao(
                mensagem=mensagem,
                intent=intent_nome,
                historico_texto=historico_venda,
                categoria_ativa=str(
                    sessao.get("categoria_interesse") or intent.get("category") or ""
                ),
                produto_ativo=str(sessao.get("produto_ativo") or ""),
                product_query=str(intent.get("product_query") or mensagem),
            )
            aplicar_resultado_no_contexto(contexto_venda, resultado_produtos)
            produtos = contexto_venda.produtos
            catalogo = contexto_venda.catalogo
            if resultado_produtos.get("category") and not sessao.get("categoria_interesse"):
                sessao["categoria_interesse"] = resultado_produtos["category"]
            if resultado_produtos.get("found") and produtos:
                p0 = produtos[0]
                if p0.get("name"):
                    sessao["produto_ativo"] = p0["name"]
                    sessao["produto_mencionado"] = p0["name"]
                if p0.get("price") is not None:
                    sessao["preco_cotado"] = p0["price"]
            contexto_venda.memoria = sessao
            if persistir and not str(cliente_id).startswith("ephemeral-"):
                _tentar_persistir(
                    "atualizar_contexto",
                    lambda: persistir_sessao(str(cliente_id), sessao),
                    ok_se_truthy=True,
                    essencial=False,
                )
            log_seguro(
                "product_service",
                telefone=numero,
                message_id=msg_id or "-",
                found=resultado_produtos.get("found"),
                qtd=len(resultado_produtos.get("products") or []),
                category=resultado_produtos.get("category") or "-",
                msg=(resultado_produtos.get("message") or "")[:80],
            )

        # Briefing leve para a OpenAI com a intenção (sem responder no classificador)
        if intent.get("intent") and intent["intent"] != "INDEFINIDO":
            contexto_venda.briefing = (
                (contexto_venda.briefing or "")
                + f"\nINTENÇÃO DETECTADA: {intent['intent']} "
                f"(confiança {intent.get('confidence')}). "
                "Use para conduzir o fluxo; não mencione a classificação ao cliente. "
                "Só fale de produtos que vieram do PRODUCT SERVICE / CATÁLOGO."
            ).strip()

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
                if persistir and not str(cliente_id).startswith("ephemeral-"):
                    _tentar_persistir(
                        "atualizar_contexto",
                        lambda: persistir_sessao(str(cliente_id), sessao),
                        ok_se_truthy=True,
                        essencial=False,
                    )
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

        if persistir and not str(cliente_id).startswith("ephemeral-"):
            try:
                resultado_lead = processar_lead_e_notificar(
                    cliente_id=cliente_id,
                    numero_cliente=numero,
                    nome_cliente=nome_cliente,
                    mensagem=mensagem,
                    produtos=produtos,
                )
                if resultado_lead.get("notificado"):
                    print("VENDEDOR NOTIFICADO:", resultado_lead["interesse"])
            except Exception as exc:
                persistencia_ok = False
                log_seguro(
                    "chat_erro_persistencia",
                    telefone=numero,
                    message_id=msg_id or "-",
                    etapa="lead",
                    erro=type(exc).__name__,
                    detalhe=str(exc)[:120],
                )
        elif not persistir:
            log_seguro("lead_pulado", telefone=numero, message_id=msg_id or "-", motivo="persistir=false")

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
                pedido_registrado = None
                if not ja_encerrado and (fechamento or alteracao_pagamento):
                    # Etapa 5 — checkout seguro (respeita dry_run / persistir / flags)
                    checkout_out = processar_checkout_turno(
                        mensagem=mensagem,
                        sessao=sessao,
                        produtos=produtos,
                        intent=intent_nome or "COMPRA",
                        nome_cliente=nome_conversa,
                        historico_texto=historico_venda,
                        cliente_supabase=cliente,
                        telefone=numero,
                        pushname=nome_cliente,
                        ultima_resposta_ia=ultima_resposta_ia,
                        frete_estimado=frete_estimado,
                        nova_venda=nova_venda,
                        dry_run=dry_run,
                        persistir=persistir,
                        tentar_criar=True,
                    )
                    if checkout_out.get("sessao"):
                        sessao.update(checkout_out["sessao"])
                        contexto_venda.memoria = sessao
                        if persistir and not str(cliente_id).startswith("ephemeral-"):
                            _tentar_persistir(
                                "atualizar_contexto",
                                lambda: persistir_sessao(str(cliente_id), sessao),
                                ok_se_truthy=True,
                                essencial=False,
                            )

                    pedido_registrado = checkout_out.get("pedido")
                    if pedido_registrado and pedido_registrado.get("pedido_id"):
                        print("CHECKOUT PEDIDO CRIADO:", pedido_registrado.get("pedido_id"))
                        try:
                            if pedido_registrado.get("cliente_id"):
                                cliente_mercos_id = int(pedido_registrado["cliente_id"])
                                atualizar_cliente(
                                    cliente["id"],
                                    mercos_cliente_id=cliente_mercos_id,
                                )
                                cliente["mercos_cliente_id"] = cliente_mercos_id
                        except Exception as exc:
                            print("AVISO: falha ao salvar mercos_cliente_id:", exc)
                    elif dry_run or not persistir:
                        print("CHECKOUT: dry_run/persistir=false — pedido não criado")
                    elif checkout_out.get("needs_human"):
                        print("CHECKOUT: humano necessário —", checkout_out.get("reason"))

                    # Resposta: se checkout conduziu coleta, usa reply; senão script legado
                    if checkout_out.get("reply") and (
                        not checkout_out.get("ready")
                        or checkout_out.get("needs_human")
                        or dry_run
                        or not persistir
                        or not checkout_criar_pedido_habilitado()
                    ):
                        # Sem pedido real: nunca usar texto de "pedido criado" do script legado
                        if pedido_registrado and pedido_registrado.get("pedido_id"):
                            resposta_ia = resposta_fechamento_pedido(
                                historico_venda,
                                nome_cliente,
                                frete_estimado,
                                mensagem_atual=mensagem,
                                ultima_resposta_ia=ultima_resposta_ia,
                                mercos_pedido=pedido_registrado,
                            )
                        else:
                            resposta_ia = checkout_out["reply"]
                    else:
                        resposta_ia = resposta_fechamento_pedido(
                            historico_venda,
                            nome_cliente,
                            frete_estimado,
                            mensagem_atual=mensagem,
                            ultima_resposta_ia=ultima_resposta_ia,
                            mercos_pedido=pedido_registrado,
                        )
                else:
                    resposta_ia = resposta_fechamento_pedido(
                        historico_venda,
                        nome_cliente,
                        frete_estimado,
                        mensagem_atual=mensagem,
                        ultima_resposta_ia=ultima_resposta_ia,
                        mercos_pedido=pedido_registrado,
                    )

                resultado_fechamento = buscar_produtos_para_atendimento(historico_venda)
                if persistir and vendedor_configurado() and (
                    pedido_registrado and pedido_registrado.get("pedido_id")
                ):
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
        elif (
            checkout_habilitado()
            and intent_e_checkout(intent.get("intent") or "")
            and not pedido_encerrado
        ):
            # Etapa 5 — condução de compra (COMPRA / PAGAMENTO / ENTREGA)
            checkout_out = processar_checkout_turno(
                mensagem=mensagem,
                sessao=sessao,
                produtos=produtos,
                intent=intent.get("intent") or "",
                nome_cliente=nome_conversa,
                historico_texto=historico_venda,
                cliente_supabase=cliente,
                telefone=numero,
                pushname=nome_cliente,
                ultima_resposta_ia=ultima_resposta_ia,
                dry_run=dry_run,
                persistir=persistir,
                tentar_criar=False,
            )
            if checkout_out.get("sessao"):
                sessao.update(checkout_out["sessao"])
                contexto_venda.memoria = sessao
                if persistir and not str(cliente_id).startswith("ephemeral-"):
                    _tentar_persistir(
                        "atualizar_contexto",
                        lambda: persistir_sessao(str(cliente_id), sessao),
                        ok_se_truthy=True,
                        essencial=False,
                    )
            resposta_ia = checkout_out.get("reply") or (
                "Posso te passar o próximo passo para compra."
            )
            log_seguro(
                "fluxo_checkout",
                intent=intent.get("intent"),
                reason=checkout_out.get("reason") or "-",
                telefone=numero,
            )
        elif intent.get("intent") == "ATENDIMENTO_HUMANO":
            resposta_ia = resposta_atendimento_humano(nome_conversa)
            log_seguro("fluxo_intent", intent="ATENDIMENTO_HUMANO", telefone=numero)
        elif intent.get("intent") == "SAC":
            resposta_ia = resposta_sac(nome_conversa)
            log_seguro("fluxo_intent", intent="SAC", telefone=numero)
        elif intent.get("intent") == "FORA_DO_ESCOPO":
            resposta_ia = resposta_fora_do_escopo(nome_conversa)
            log_seguro("fluxo_intent", intent="FORA_DO_ESCOPO", telefone=numero)
        elif saudacao or intent.get("intent") == "SAUDACAO":
            resposta_ia = resposta_saudacao(nome_conversa)
        elif (
            intent.get("intent") == "MAIS_OPCOES"
            or cliente_pediu_mais_opcoes(mensagem)
        ) and not pedido_encerrado:
            # Fluxo especial MAIS_OPCOES — Product Service por baixo
            produtos_op = produtos
            if resultado_produtos and resultado_produtos.get("products"):
                produtos_op = resultado_produtos["products"]
            elif not produtos_op:
                cat_geral = montar_catalogo_geral()
                produtos_op = cat_geral.get("produtos") or []
            resposta_ia = resposta_mais_opcoes(
                nome_cliente=nome_conversa,
                historico_texto=historico_venda,
                produtos=produtos_op,
                categoria=str(
                    sessao.get("categoria_interesse")
                    or (resultado_produtos or {}).get("category")
                    or ""
                ),
            )
            print("MAIS OPCOES: resposta consultiva (Product Service)")
        elif (
            intent.get("intent") in ("CATALOGO_GERAL", "PRODUTOS_DISPONIVEIS")
            or cliente_quer_ver_catalogo(mensagem, ultima_resposta_ia)
        ) and not pedido_encerrado:
            produtos_cat = []
            if resultado_produtos and resultado_produtos.get("products"):
                produtos_cat = resultado_produtos["products"]
            if not produtos_cat:
                cat_geral = montar_catalogo_geral(limite=8)
                produtos_cat = cat_geral.get("produtos") or []
                catalogo = cat_geral.get("catalogo") or catalogo
            produtos = produtos_cat
            resposta_ia = resposta_mostrar_catalogo(nome_conversa, produtos_cat)
            print("CATALOGO GERAL: lista de produtos reais")
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
        elif (
            intent.get("intent") == "PRECO" or cliente_perguntou_preco(mensagem)
        ) and not pedido_encerrado:
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

        stock_ok = False
        if produtos:
            p0 = produtos[0] or {}
            qty = p0.get("stock_quantity")
            stock_ok = bool(
                p0.get("stock_confirmed")
                and qty is not None
                and float(qty) > 0
            )
        resposta_ia = sanitizar_frases_comerciais(
            resposta_ia, stock_confirmed=stock_ok
        )
        pedido_real = bool(sessao.get("pedido_id"))
        resposta_ia = sanitizar_claims_checkout(
            resposta_ia,
            pedido_criado=pedido_real,
            pix_gerado=False,
        )
        from services.texto_seguro import garantir_espacos_whatsapp, reparar_mojibake

        resposta_ia = garantir_espacos_whatsapp(reparar_mojibake(resposta_ia or ""))

        log_seguro(
            "resposta_pronta",
            telefone=numero,
            message_id=msg_id or "-",
            chars=len(resposta_ia or ""),
        )

        # =========================
        # SALVA RESPOSTA IA
        # =========================

        if persistir and not str(cliente_id).startswith("ephemeral-"):
            if historico_essencial and clientes_tem_historico():
                historico_tentou_salvar = True
                _tentar_persistir(
                    "salvar_mensagem_ia",
                    lambda: salvar_mensagem(
                        cliente_id,
                        "ia",
                        resposta_ia,
                        telefone=numero,
                        nome=nome_cliente,
                    ),
                    essencial=True,
                    etapa_flag="historico_ok",
                )
                if etapas.get("historico_ok"):
                    historico_salvo_em = "banco"
                else:
                    historico_erro_dbg = obter_ultimo_erro_historico() or historico_erro_dbg
                    if not clientes_tem_historico():
                        historico_essencial = False
                        etapas["historico_ok"] = True
                        historico_salvo_em = "nenhum"
            elif not historico_essencial:
                etapas["historico_ok"] = True

            if dry_run:
                etapas["message_log_ok"] = True
            else:
                try:
                    espelhar_mensagem_agente(numero, nome_cliente, resposta_ia)
                except Exception as exc:
                    etapas["message_log_ok"] = False
                    log_seguro(
                        "chat_aviso_persistencia",
                        telefone=numero,
                        message_id=msg_id or "-",
                        etapa="espelhar_agente",
                        erro=type(exc).__name__,
                    )
            _tentar_persistir(
                "atualizar_thread_ia",
                lambda: atualizar_thread_conversa(
                    numero,
                    nome_cliente,
                    resposta_ia or "",
                    inbound=False,
                ),
                ok_se_truthy=True,
                essencial=False,
                etapa_flag="thread_ok",
            )
            if historico_essencial and clientes_tem_historico():
                _tentar_persistir(
                    "atualizar_historico_json",
                    lambda: atualizar_historico_json(cliente_id),
                    essencial=False,
                )

            # Atualiza última pergunta do agente na sessão
            from services.historico_service import extrair_ultima_pergunta_ia

            sessao["ultima_pergunta_agente"] = extrair_ultima_pergunta_ia(
                historico_venda + f"\nIA: {resposta_ia}\n"
            ) or sessao.get("ultima_pergunta_agente") or ""
            _tentar_persistir(
                "atualizar_contexto",
                lambda: persistir_sessao(str(cliente_id), sessao),
                ok_se_truthy=True,
                essencial=True,
                etapa_flag="contexto_ok",
            )
            if etapas.get("contexto_ok"):
                contexto_salvo_em = "banco"
            else:
                contexto_salvo_em = "fallback"
        elif persistir:
            # ephemeral: só cache local — NÃO marca contexto/historico como ok de banco
            try:
                from services.vendas.memoria import persistir_sessao as _ps

                _ps(str(cliente_id), sessao)
            except Exception:
                pass
            etapas["contexto_ok"] = False
            etapas["historico_ok"] = False
            etapas["cliente_ok"] = False
            contexto_salvo_em = "fallback"
            historico_salvo_em = "fallback"
            persistencia_ok = False

        # =========================
        # ENVIA WHATSAPP
        # =========================

        enviar_wa = (not dry_run) and persistir

        # Snapshot ANTES da reconciliação final (detecta flag antiga/errada)
        cliente_ok_antes = bool(etapas.get("cliente_ok"))
        tem_cliente_id = bool(
            cliente_id and not str(cliente_id).startswith("ephemeral-")
        )

        # Essenciais: cliente + contexto (+ historico só se a coluna existir)
        # thread_ok e message_log_ok são opcionais
        if persistir and tem_cliente_id:
            etapas["cliente_ok"] = True
            if not historico_essencial:
                etapas["historico_ok"] = True
            persistencia_ok = bool(
                etapas.get("cliente_ok")
                and etapas.get("contexto_ok")
                and (etapas.get("historico_ok") if historico_essencial else True)
            )
        elif persistir:
            etapas["cliente_ok"] = False
            etapas["contexto_ok"] = False
            if historico_essencial:
                etapas["historico_ok"] = False
            contexto_salvo_em = "fallback"
            historico_salvo_em = "fallback"
            persistencia_ok = False

        historico_debug = None
        cliente_debug = None
        if dry_run:
            if origem_cliente == "ephemeral" or not tem_cliente_id:
                dbg_erro = cliente_debug_erro or erro_cliente_para_debug("criar_cliente")
            else:
                dbg_erro = cliente_debug_erro or obter_ultimo_erro_cliente()
            cliente_debug = {
                "tem_cliente_id": tem_cliente_id if persistir else False,
                "origem_cliente": origem_cliente,
                "cliente_ok_antes": cliente_ok_antes,
                "cliente_ok_final": bool(etapas.get("cliente_ok")),
                "contexto_salvo_em": contexto_salvo_em,
                "historico_salvo_em": historico_salvo_em,
                "supabase_key_source": __import__(
                    "database.supabase", fromlist=["supabase_key_source"]
                ).supabase_key_source(),
            }
            if dbg_erro:
                cliente_debug["cliente_debug_erro"] = {
                    "etapa": str(dbg_erro.get("etapa") or ""),
                    "erro_codigo": str(dbg_erro.get("erro_codigo") or ""),
                    "erro_tipo": str(dbg_erro.get("erro_tipo") or ""),
                    "erro_resumido": str(dbg_erro.get("erro_resumido") or "")[:160],
                }
            elif origem_cliente == "ephemeral":
                cliente_debug["cliente_debug_erro"] = erro_cliente_para_debug("criar_cliente")

            hist_meta = diagnostico_coluna_historico()
            hist_err = historico_erro_dbg or obter_ultimo_erro_historico()
            historico_debug = {
                "historico_coluna_existe": bool(hist_meta.get("historico_coluna_existe")),
                "historico_tipo": str(hist_meta.get("historico_tipo") or "desconhecido"),
                "historico_tentou_salvar": bool(historico_tentou_salvar),
                "historico_salvo_em": historico_salvo_em,
                "historico_essencial": bool(historico_essencial),
                "historico_erro": {
                    "codigo": str((hist_err or {}).get("codigo") or ""),
                    "tipo": str((hist_err or {}).get("tipo") or ""),
                    "resumo": str((hist_err or {}).get("resumo") or "")[:160],
                },
            }
            log_seguro(
                "cliente_resolvido",
                telefone=numero,
                message_id=msg_id or "-",
                cliente_ok=etapas.get("cliente_ok"),
                tem_cliente_id=tem_cliente_id,
                origem_cliente=origem_cliente,
                contexto_salvo_em=contexto_salvo_em,
                historico_salvo_em=historico_salvo_em,
                historico_coluna=hist_meta.get("historico_coluna_existe"),
                erro_tipo=(cliente_debug.get("cliente_debug_erro") or {}).get("erro_tipo") or "-",
            )

        # =========================
        # FORMATADOR FINAL (última camada antes de retornar/enviar)
        # =========================
        from services.texto_seguro import aplicar_formatador_final

        resposta_ia, formatacao_debug = aplicar_formatador_final(resposta_ia or "")

        resultado_final = _montar_resultado(
            resposta_ia,
            persistencia_ok,
            persistencia_etapas=etapas if dry_run else None,
            cliente_debug=cliente_debug,
            historico_debug=historico_debug,
            formatacao_debug=formatacao_debug if dry_run else None,
        )
        log_seguro(
            "chat_resposta_final",
            telefone=numero,
            message_id=msg_id or "-",
            persistencia_ok=persistencia_ok,
            chars=len(resposta_ia or ""),
            dry_run=dry_run,
            persistir=persistir,
            cliente_ok=etapas.get("cliente_ok"),
            contexto_ok=etapas.get("contexto_ok"),
            historico_ok=etapas.get("historico_ok"),
            thread_ok=etapas.get("thread_ok"),
            formatador_final=True,
            tinha_colado=formatacao_debug.get("tinha_espaco_colado_antes"),
        )

        if not enviar_wa:
            log_seguro(
                "processamento_fim",
                telefone=numero,
                message_id=msg_id or "-",
                etapa="dry_run" if dry_run else "sem_persistir",
                ms=int((__import__("time").time() - inicio) * 1000),
            )
            finalizar_mensagem(data, sucesso=True)
            return resultado_final

        # Reaplica imediatamente antes do envio WhatsApp (nada passa sem filtro)
        resposta_ia, formatacao_debug = aplicar_formatador_final(resposta_ia or "")
        resultado_final["resposta"] = resposta_ia
        if dry_run:
            resultado_final["formatacao_debug"] = formatacao_debug

        envio = enviar_mensagem(
            numero,
            resposta_ia
        )
        if isinstance(envio, dict) and not envio.get("ok"):
            print("FALHA ENVIO WHATSAPP:", {k: v for k, v in envio.items() if k != "token"})
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
        return resultado_final

    except Exception as e:
        print("ERRO:")
        print(type(e).__name__, str(e)[:200])
        traceback.print_exc()
        finalizar_mensagem(data, sucesso=False)
        # Se já havia resposta comercial, devolve mesmo com falha
        if resposta_ia:
            from services.texto_seguro import aplicar_formatador_final

            resposta_ia, _fmt = aplicar_formatador_final(resposta_ia or "")
            log_seguro(
                "chat_erro_persistencia",
                telefone=numero,
                message_id=msg_id or "-",
                etapa="exception_apos_resposta",
                erro=type(e).__name__,
                detalhe=str(e)[:120],
            )
            log_seguro(
                "chat_resposta_final",
                telefone=numero,
                message_id=msg_id or "-",
                persistencia_ok=False,
                chars=len(resposta_ia or ""),
            )
            return _montar_resultado(resposta_ia, persistencia_ok=False)
        return _montar_resultado(None, persistencia_ok=False)


def _log_webhook_recebido(data: dict, diag: dict | None = None) -> None:
    """Log seguro — nunca imprime payload completo, tokens ou telefone."""
    from services.webhook_normalizer import _detectar_provider

    evento = data.get("data") if isinstance(data, dict) else {}
    if isinstance(evento, str):
        try:
            import json as _json

            evento = _json.loads(evento)
        except Exception:
            evento = {}
    if not isinstance(evento, dict):
        evento = {}

    provider = (diag or {}).get("provider_detectado") or _detectar_provider(
        data if isinstance(data, dict) else {}
    )
    msg_id = ""
    if isinstance(data, dict):
        msg_id = (
            str(data.get("messageId") or data.get("id") or "")
            or str(evento.get("id") or evento.get("messageId") or "")
        )
    tel_raw = str(
        (data.get("phone") if isinstance(data, dict) else None)
        or evento.get("from")
        or evento.get("phone")
        or ""
    )
    tipo = (
        (diag or {}).get("tipo_evento")
        or (data.get("event_type") if isinstance(data, dict) else None)
        or (data.get("type") if isinstance(data, dict) else None)
        or evento.get("type")
        or "-"
    )
    log_seguro(
        "webhook_recebido",
        provider=provider,
        provider_detectado=provider,
        message_id=msg_id or "-",
        telefone=tel_raw or "-",
        tipo=tipo,
        tipo_evento=tipo,
        tem_texto=bool((diag or {}).get("tem_texto")),
        from_me=bool((diag or {}).get("from_me")),
        eh_grupo=bool((diag or {}).get("eh_grupo")),
        parse_ok=bool((diag or {}).get("parse_ok")),
    )


async def receber_webhook(data: dict, background_tasks: BackgroundTasks | None = None):
    from services.webhook_normalizer import analisar_webhook

    diag = analisar_webhook(data if isinstance(data, dict) else {})
    _log_webhook_recebido(data if isinstance(data, dict) else {}, diag)

    if not diag.get("ok") or not diag.get("payload"):
        motivo = diag.get("motivo_ignorado") or "formato_ou_evento_descartado"
        log_seguro(
            "webhook_ignorado",
            motivo=motivo,
            provider_detectado=diag.get("provider_detectado") or "-",
            tipo_evento=diag.get("tipo_evento") or "-",
            tem_texto=bool(diag.get("tem_texto")),
            from_me=bool(diag.get("from_me")),
            eh_grupo=bool(diag.get("eh_grupo")),
            parse_ok=bool(diag.get("parse_ok")),
            motivo_ignorado=motivo,
        )
        return {"status": "ok", "ignorado": True, "motivo": motivo}

    payload = diag["payload"]
    log_seguro(
        "webhook_aceito",
        provider_detectado=diag.get("provider_detectado") or payload.get("provider"),
        tipo_evento=diag.get("tipo_evento") or "message_received",
        tem_texto=True,
        from_me=False,
        eh_grupo=False,
        parse_ok=True,
    )

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
        "mensagem": "POST aqui para receber mensagens WhatsApp (UltraMsg ou Z-API)",
        "url": "https://agent-ia-xnamai.onrender.com/webhook",
        "provider": provider_nome(),
        "code_version": CODE_VERSION,
        "aceita": [
            "ultramsg message_received (privado @c.us)",
            "zapi ReceivedCallback",
        ],
        "ignora": [
            "grupos @g.us",
            "fromMe=true",
            "sem texto",
        ],
    }


@router.post("/webhook")
async def webhook(data: dict, background_tasks: BackgroundTasks):
    return await receber_webhook(data, background_tasks)


@router.post("/chat")
async def chat_teste(payload: dict):
    """
    Teste local do agente.

    Body:
      {
        "telefone": "5543999999999",
        "mensagem": "tem mais opções?",
        "nome": "Arthur",
        "dry_run": true,
        "persistir": false
      }

    - dry_run (default true): não envia WhatsApp.
    - persistir (default true se omitido): grava no Supabase (comportamento atual).
      Com persistir=false: não salva mensagem, histórico, lead nem WhatsApp.
    """
    telefone = normalizar_telefone(
        str(payload.get("telefone") or payload.get("phone") or "")
    )
    from services.texto_seguro import reparar_mojibake

    mensagem = reparar_mojibake(
        str(payload.get("mensagem") or payload.get("message") or "").strip()
    )
    nome = reparar_mojibake(
        str(payload.get("nome") or payload.get("name") or "Cliente").strip()
    )

    dry_run_raw = payload.get("dry_run", True)
    if isinstance(dry_run_raw, str):
        dry_run = dry_run_raw.strip().lower() in ("1", "true", "sim", "yes")
    else:
        dry_run = bool(dry_run_raw)

    # Default True = comportamento atual (grava mesmo em dry_run)
    if "persistir" in payload:
        persistir_raw = payload.get("persistir")
        if isinstance(persistir_raw, str):
            persistir = persistir_raw.strip().lower() in ("1", "true", "sim", "yes")
        else:
            persistir = bool(persistir_raw)
    else:
        persistir = True

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
    resultado = await loop.run_in_executor(
        None,
        lambda: processar_mensagem(data, dry_run=dry_run, persistir=persistir),
    )
    if not isinstance(resultado, dict):
        resultado = {
            "resposta": resultado if isinstance(resultado, str) else "",
            "persistencia_ok": False,
        }

    persistencia_ok = bool(resultado.get("persistencia_ok", False))
    etapas = resultado.get("persistencia_etapas") if dry_run else None
    cliente_debug = resultado.get("cliente_debug") if dry_run else None
    historico_debug = resultado.get("historico_debug") if dry_run else None

    # =========================================================
    # ÚLTIMO PONTO antes do return — atualiza resultado["resposta"]
    # Debug é calculado SOBRE a string que vai no JSON.
    # =========================================================
    from services.texto_seguro import (
        aplicar_formatador_final,
        corrigir_mojibake_exibicao,
        tem_espaco_colado,
    )

    resposta_bruta = str(resultado.get("resposta") or "")
    tinha_antes = tem_espaco_colado(resposta_bruta)
    resposta_final = corrigir_mojibake_exibicao(resposta_bruta)
    resposta_final, fmt_chat = aplicar_formatador_final(resposta_final)
    # Garante que o dict e o JSON usam EXATAMENTE a mesma string
    resultado["resposta"] = resposta_final

    formatacao_debug = {
        "formatador_final_aplicado": True,
        "formatador_final_chat": True,
        "tinha_espaco_colado_antes": bool(tinha_antes or fmt_chat.get("tinha_espaco_colado_antes")),
        "tem_espaco_colado_depois": bool(tem_espaco_colado(resultado["resposta"])),
        "amostra_resposta_final": (resultado.get("resposta") or "")[:120],
    }

    out = {
        "status": "ok" if resultado.get("resposta") else "erro",
        "telefone": telefone,
        "mensagem": mensagem,
        "resposta": resultado["resposta"],
        "dry_run": dry_run,
        "persistir": persistir,
        "persistencia_ok": persistencia_ok if resultado.get("resposta") else False,
        "code_version": CODE_VERSION,
    }
    if etapas is not None:
        out["persistencia_etapas"] = etapas
    if cliente_debug is not None:
        out["cliente_debug"] = cliente_debug
    if historico_debug is not None:
        out["historico_debug"] = historico_debug
    if dry_run:
        out["formatacao_debug"] = formatacao_debug
    return out


@router.get("/status")
async def status():
    supabase_diag = diagnosticar_supabase_status()
    return {
        "status": "online",
        "whatsapp_provider": provider_nome(),
        "whatsapp_configurado": whatsapp_configurado(),
        "ultramsg_configurado": ultramsg_svc.ultramsg_configurado(),
        "zapi_configurado": zapi_svc.zapi_configurado(),
        "vendedor_configurado": vendedor_configurado(),
        "produtos_fonte": os.getenv("PRODUTOS_FONTE", "auto"),
        "mercos_configurado": mercos_configurado(),
        "mercos_sandbox": mercos_ambiente_sandbox(),
        "mercos_criar_pedido": mercos_criar_pedido_habilitado(),
        "pulsedesk_pedidos": pulsedesk_pedidos_habilitado(),
        "checkout_enabled": checkout_habilitado(),
        "checkout_create_order": checkout_criar_pedido_habilitado(),
        "mercos_base_url": os.getenv("MERCOS_BASE_URL", ""),
        "vendas_consultivas": True,
        "code_version": CODE_VERSION,
        "pulsedesk_bridge": os.getenv("PULSEDESK_BRIDGE_ENABLED", "true"),
        "mcp_enabled": os.getenv("MCP_ENABLED", "true"),
        "mcp_server_enabled": os.getenv("MCP_SERVER_ENABLED", "false"),
        "tabelas": tabelas_configuradas(),
        "tabelas_validacao": status_validacao(),
        "schema_persistencia": diagnosticar_schema_persistencia(),
        "supabase_key_source": supabase_diag.get("supabase_key_source"),
        "supabase_key_kind": supabase_diag.get("supabase_key_kind"),
        "supabase_url_configurada": supabase_diag.get("supabase_url_configurada"),
        "supabase_client_ready": supabase_diag.get("supabase_client_ready"),
        "supabase_clientes_select_ok": supabase_diag.get("clientes_select_ok"),
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
        prov = provider_nome()
        msg = (
            "Configure ULTRAMSG_INSTANCE_ID e ULTRAMSG_TOKEN no Render"
            if prov == "ultramsg"
            else "Configure ZAPI_INSTANCE_ID e ZAPI_TOKEN no Render"
        )
        return {
            "status": "erro",
            "mensagem": msg,
            "provider": prov,
        }

    resposta = enviar_mensagem(
        tel,
        f"Teste do agente Xnamai ({provider_nome()}). Se chegou, o WhatsApp está ok.",
    )

    ok = isinstance(resposta, dict) and resposta.get("ok")
    if not ok and isinstance(resposta, str) and resposta:
        ok = True
    safe_resp = resposta
    if isinstance(resposta, dict):
        safe_resp = {k: v for k, v in resposta.items() if "token" not in k.lower()}
    return {
        "status": "ok" if ok else "erro",
        "provider": provider_nome(),
        "zapi_client_token_configurado": bool(os.getenv("ZAPI_CLIENT_TOKEN", "").strip()),
        "ultramsg_configurado": ultramsg_svc.ultramsg_configurado(),
        "resposta_whatsapp": safe_resp,
    }