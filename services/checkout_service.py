"""Etapa 5 — fluxo seguro de fechamento / checkout.

Conduz a compra sem inventar pedido, Pix, reserva ou estoque.
Integra Mercos/PulseDesk somente via funções existentes e flags explícitas.
"""

from __future__ import annotations

import os
import re
import unicodedata
from copy import deepcopy
from typing import Any

from services.env_loader import carregar_env
from services.webhook_guard import log_seguro

carregar_env()

CHECKOUT_STATUS = (
    "nao_iniciado",
    "coletando_dados",
    "pronto_para_pedido",
    "pedido_criado",
    "humano_necessario",
)

CAMPOS_CHECKOUT_SESSAO = (
    "checkout_status",
    "produto_checkout",
    "quantidade",
    "forma_entrega",
    "cidade",
    "endereco",
    "forma_pagamento",
    "pedido_id",
    "checkout_resumo",
)


def checkout_habilitado() -> bool:
    return os.getenv("CHECKOUT_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "sim",
        "yes",
    )


def checkout_criar_pedido_habilitado() -> bool:
    """Gate explícito — padrão false (não cria pedido automático)."""
    return os.getenv("CHECKOUT_CREATE_ORDER", "false").strip().lower() in (
        "1",
        "true",
        "sim",
        "yes",
    )


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().strip()


def _fmt_preco(valor: Any) -> str | None:
    if valor is None or valor == "":
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _produto_ativo(
    sessao: dict | None,
    produtos: list | None = None,
) -> dict:
    """Normaliza produto ativo a partir do Product Service ou sessão."""
    sessao = sessao or {}
    p0: dict = {}
    if produtos:
        raw = produtos[0] or {}
        price = raw.get("price")
        if price is None:
            price = raw.get("preco")
        if price is None:
            price = raw.get("preco_tabela")
        stock_q = raw.get("stock_quantity")
        if stock_q is None and "estoque" in raw:
            stock_q = raw.get("estoque")
        p0 = {
            "id": str(raw.get("id") or raw.get("mercos_id") or ""),
            "name": str(raw.get("name") or raw.get("nome") or ""),
            "price": price,
            "stock_quantity": stock_q,
            "stock_confirmed": bool(raw.get("stock_confirmed")),
        }

    nome = p0.get("name") or str(
        sessao.get("produto_checkout") or sessao.get("produto_ativo") or ""
    )
    preco = p0.get("price")
    if preco is None:
        preco = sessao.get("preco_cotado")

    return {
        "id": str(p0.get("id") or ""),
        "name": nome,
        "price": preco,
        "stock_quantity": p0.get("stock_quantity"),
        "stock_confirmed": bool(p0.get("stock_confirmed")) if p0 else False,
    }


def estoque_ok_para_afirmar(produto: dict) -> bool:
    """Só True com stock_confirmed e quantity > 0."""
    if not produto:
        return False
    qty = produto.get("stock_quantity")
    if not produto.get("stock_confirmed") or qty is None:
        return False
    try:
        return float(qty) > 0
    except (TypeError, ValueError):
        return False


def _extrair_quantidade(mensagem: str) -> int | None:
    t = _normalizar(mensagem)
    m = re.search(
        r"\b(\d{1,3})\s*(unidades?|un\.?|pcs?|pecas?|peças?)?\b",
        t,
    )
    if m:
        q = int(m.group(1))
        if 1 <= q <= 99:
            # Evita capturar preços tipo "249"
            if q >= 100:
                return None
            # Se a mensagem é só número ou "quero 2" / "2 unidades"
            if re.search(r"\b(quero|leva|levar|unidade|un\b|pcs?|pecas?|peças?)\b", t) or len(
                t.split()
            ) <= 3:
                return q
            if m.group(2):
                return q
    m2 = re.search(r"\b(uma|um)\s+(unidade|peca|peça)\b", t)
    if m2:
        return 1
    return None


def _extrair_forma_entrega(mensagem: str, sessao: dict | None = None) -> str:
    from services.xnamai_script import extrair_forma_envio

    envio = extrair_forma_envio("", mensagem) if mensagem else None
    if envio == "retirada":
        return "retirada"
    if envio == "envio":
        return "entrega"
    # Sessão legada usa "envio"
    atual = (sessao or {}).get("forma_entrega") or (sessao or {}).get("envio")
    if atual in ("retirada", "entrega"):
        return str(atual)
    if atual == "envio":
        return "entrega"
    return ""


def _extrair_cidade(mensagem: str) -> str:
    t = (mensagem or "").strip()
    tn = _normalizar(t)
    m = re.search(
        r"(?:cidade|moro\s+em|sou\s+de|em)\s+([A-Za-zÀ-ÿ\s]{3,40})$",
        t,
        re.I,
    )
    if m:
        return m.group(1).strip()[:60]
    # Resposta curta só com nome de cidade (quando agente perguntou)
    if len(t.split()) <= 3 and not re.search(
        r"\b(sim|nao|não|ok|pix|retirada|entrega|quero|comprar)\b", tn
    ):
        if re.search(r"^[A-Za-zÀ-ÿ\s\-]+$", t) and len(t) >= 3:
            return t.strip()[:60]
    return ""


def _extrair_pagamento(mensagem: str, sessao: dict | None = None) -> str:
    from services.conversa_service import extrair_pagamento

    pag = extrair_pagamento(mensagem or "", mensagem_atual=mensagem or "")
    if pag and pag != "a combinar":
        return str(pag)
    atual = (sessao or {}).get("forma_pagamento") or (sessao or {}).get("pagamento")
    if atual and atual != "a combinar":
        return str(atual)
    tn = _normalizar(mensagem)
    if "pix" in tn:
        return "PIX"
    if "boleto" in tn:
        return "boleto"
    if "cartao" in tn or "cartão" in tn:
        return "cartão"
    return ""


def atualizar_sessao_checkout(
    sessao: dict,
    *,
    mensagem: str = "",
    produtos: list | None = None,
) -> dict:
    """Atualiza campos de checkout a partir da mensagem / produto ativo."""
    out = deepcopy(sessao) if sessao else {}
    for k in CAMPOS_CHECKOUT_SESSAO:
        out.setdefault(k, None if k == "quantidade" else "")

    prod = _produto_ativo(out, produtos)
    if prod.get("name"):
        out["produto_checkout"] = prod["name"]
        out["produto_ativo"] = prod["name"]
    if prod.get("price") is not None:
        out["preco_cotado"] = prod["price"]

    qty = _extrair_quantidade(mensagem)
    if qty is not None:
        out["quantidade"] = qty

    entrega = _extrair_forma_entrega(mensagem, out)
    if entrega:
        out["forma_entrega"] = entrega
        out["envio"] = "retirada" if entrega == "retirada" else "envio"

    cidade = _extrair_cidade(mensagem)
    if cidade and not out.get("cidade"):
        out["cidade"] = cidade

    # Endereço: só se parece endereço real
    from services.conversa_service import extrair_endereco

    end = extrair_endereco(f"Cliente: {mensagem}") if mensagem else ""
    if end:
        out["endereco"] = end
    elif out.get("forma_entrega") == "entrega" and not out.get("endereco"):
        # Mensagem longa com número pode ser endereço
        if re.search(r"\b(rua|av\.?|avenida|travessa|alameda)\b", _normalizar(mensagem)):
            out["endereco"] = (mensagem or "").strip()[:120]

    pag = _extrair_pagamento(mensagem, out)
    if pag:
        out["forma_pagamento"] = pag
        out["pagamento"] = pag

    if out.get("quantidade") in (None, ""):
        # Default seguro após produto confirmado e entrega escolhida
        if out.get("produto_checkout") and out.get("forma_entrega"):
            out["quantidade"] = 1

    return out


def _campos_faltando(sessao: dict, produto: dict) -> list[str]:
    missing: list[str] = []
    if not (produto.get("name") or "").strip():
        missing.append("produto")
        return missing

    if produto.get("price") is None:
        missing.append("preco")

    if not sessao.get("forma_entrega"):
        missing.append("forma_entrega")
    else:
        if sessao.get("forma_entrega") == "entrega":
            if not sessao.get("cidade"):
                missing.append("cidade")
            if not sessao.get("endereco"):
                missing.append("endereco")

    if sessao.get("quantidade") in (None, ""):
        missing.append("quantidade")

    if not sessao.get("forma_pagamento"):
        missing.append("forma_pagamento")

    return missing


def _proxima_pergunta(missing: list[str], produto: dict, nome: str = "") -> str:
    tratamento = (nome or "").split()[0] if nome else ""
    prefix = f"{tratamento}, " if tratamento else ""
    if not missing:
        return ""
    campo = missing[0]
    nome_p = produto.get("name") or "esse produto"
    preco = _fmt_preco(produto.get("price"))
    if campo == "produto":
        return "Claro. Qual produto você quer finalizar?"
    if campo == "preco":
        return (
            f"Antes de seguir, preciso confirmar o valor do {nome_p}. "
            "Posso verificar o preço atualizado para você?"
        )
    if campo == "forma_entrega":
        if preco:
            return (
                f"Perfeito{', ' + tratamento if tratamento else ''}. "
                f"Vamos seguir com o {nome_p} de {preco}. "
                "Você prefere retirar ou receber por entrega?"
            ).replace("Perfeito, .", "Perfeito.")
        return f"{prefix}Você prefere retirar ou receber por entrega?".strip()
    if campo == "quantidade":
        return "Para finalizar, qual quantidade você quer?"
    if campo == "cidade":
        return "Para a entrega, qual é a sua cidade?"
    if campo == "endereco":
        return "Me passa o endereço completo com rua e número?"
    if campo == "forma_pagamento":
        return "Qual forma de pagamento você prefere: Pix, boleto ou cartão?"
    return "Posso te passar o próximo passo para compra."


def _resumo(sessao: dict, produto: dict) -> str:
    partes = []
    if produto.get("name"):
        partes.append(produto["name"])
    preco = _fmt_preco(produto.get("price"))
    if preco:
        partes.append(preco)
    if sessao.get("quantidade"):
        partes.append(f"qtd={sessao['quantidade']}")
    if sessao.get("forma_entrega"):
        partes.append(f"entrega={sessao['forma_entrega']}")
    if sessao.get("cidade"):
        partes.append("cidade=ok")
    if sessao.get("endereco"):
        partes.append("endereco=ok")
    if sessao.get("forma_pagamento"):
        partes.append(f"pag={sessao['forma_pagamento']}")
    return "; ".join(partes)


def avaliar_checkout(
    *,
    mensagem: str = "",
    sessao: dict | None = None,
    produtos: list | None = None,
    intent: str = "",
    nome_cliente: str = "",
    dry_run: bool = False,
    persistir: bool = True,
) -> dict:
    """Avalia prontidão do checkout e próximo passo (sem side effects)."""
    sessao = atualizar_sessao_checkout(dict(sessao or {}), mensagem=mensagem, produtos=produtos)
    produto = _produto_ativo(sessao, produtos)
    intent_u = (intent or "").upper()
    msg_n = _normalizar(mensagem)
    pediu_pix = bool(re.search(r"\bpix\b", msg_n)) or intent_u == "PAGAMENTO"

    # Estoque zero → não segue fechamento
    qty = produto.get("stock_quantity")
    try:
        qty_num = float(qty) if qty is not None else None
    except (TypeError, ValueError):
        qty_num = None
    if produto.get("name") and qty_num == 0:
        resultado = {
            "ready": False,
            "can_create_order": False,
            "needs_human": False,
            "product": produto,
            "missing_fields": ["disponibilidade"],
            "next_question": (
                "No momento não aparece disponibilidade desse produto. "
                "Posso verificar uma alternativa parecida para você?"
            ),
            "summary": _resumo(sessao, produto),
            "reason": "estoque_zero",
            "reply": (
                "No momento não aparece disponibilidade desse produto. "
                "Posso verificar uma alternativa parecida para você?"
            ),
            "sessao": sessao,
            "pedido": None,
        }
        sessao["checkout_status"] = "coletando_dados"
        sessao["checkout_resumo"] = resultado["summary"]
        log_seguro(
            "checkout_dados_faltando",
            reason="estoque_zero",
            produto=(produto.get("name") or "")[:40],
        )
        return resultado

    stock_afirmavel = estoque_ok_para_afirmar(produto)
    missing = _campos_faltando(sessao, produto)

    # Pix / pagamento sem produto
    if pediu_pix and "produto" in missing:
        reply = (
            "Consigo te orientar com o pagamento, mas antes preciso confirmar "
            "qual produto você quer comprar."
        )
        resultado = {
            "ready": False,
            "can_create_order": False,
            "needs_human": False,
            "product": produto,
            "missing_fields": ["produto"],
            "next_question": reply,
            "summary": "",
            "reason": "pix_sem_produto",
            "reply": reply,
            "sessao": sessao,
            "pedido": None,
        }
        sessao["checkout_status"] = "coletando_dados"
        log_seguro("checkout_dados_faltando", reason="pix_sem_produto")
        return resultado

    # Pix com produto: prioriza confirmação de entrega antes do pagamento
    if pediu_pix and produto.get("name") and "forma_entrega" in missing:
        reply = (
            "Antes de te passar o pagamento, vou confirmar os dados do pedido. "
            "Você prefere entrega ou retirada?"
        )
        resultado = {
            "ready": False,
            "can_create_order": False,
            "needs_human": False,
            "product": produto,
            "missing_fields": missing,
            "next_question": reply,
            "summary": _resumo(sessao, produto),
            "reason": "pix_aguarda_entrega",
            "reply": reply,
            "sessao": sessao,
            "pedido": None,
        }
        sessao["checkout_status"] = "coletando_dados"
        sessao["checkout_resumo"] = resultado["summary"]
        log_seguro("checkout_dados_faltando", reason="pix_aguarda_entrega")
        return resultado

    # Estoque não confirmado: avisa quando já teria os dados (ou só falta preço)
    # Não bloqueia a 1ª pergunta de entrega no "quero comprar" (Caso 1).
    if (
        produto.get("name")
        and not stock_afirmavel
        and not missing
    ):
        reply = (
            "Consigo seguir com o atendimento, mas antes preciso verificar "
            "a disponibilidade desse produto."
        )
        resultado = {
            "ready": False,
            "can_create_order": False,
            "needs_human": False,
            "product": produto,
            "missing_fields": ["disponibilidade"],
            "next_question": reply,
            "summary": _resumo(sessao, produto),
            "reason": "estoque_nao_confirmado",
            "reply": reply,
            "sessao": sessao,
            "pedido": None,
        }
        sessao["checkout_status"] = "coletando_dados"
        log_seguro("checkout_dados_faltando", reason="estoque_nao_confirmado")
        return resultado

    next_q = _proxima_pergunta(missing, produto, nome_cliente)
    ready = (not missing) and stock_afirmavel
    summary = _resumo(sessao, produto)

    # Integração segura disponível?
    from services.pedido_mercos_service import mercos_criar_pedido_habilitado
    from services.pedido_pulsedesk_service import pulsedesk_pedidos_habilitado
    from services.mercos_service import mercos_configurado

    integracao_ok = bool(
        (mercos_configurado() and mercos_criar_pedido_habilitado())
        or pulsedesk_pedidos_habilitado()
    )
    create_flag = checkout_criar_pedido_habilitado()
    pode_criar = (
        ready
        and create_flag
        and integracao_ok
        and (not dry_run)
        and persistir
    )
    needs_human = ready and (not integracao_ok or not create_flag)

    if ready:
        status = "pronto_para_pedido"
        if needs_human:
            status = "humano_necessario"
            reason = "humano_sem_integracao" if not integracao_ok else "create_order_desabilitado"
            reply = (
                f"Perfeito. Resumo: {summary}. "
                "Vou te encaminhar para o time finalizar o pedido com segurança."
            )
        else:
            reason = "pronto"
            reply = (
                f"Perfeito. Resumo: {summary}. "
                "Posso te passar o próximo passo para compra."
            )
    else:
        status = "coletando_dados" if produto.get("name") else "nao_iniciado"
        reason = f"faltando:{','.join(missing)}" if missing else "coletando"
        reply = next_q

    sessao["checkout_status"] = status
    sessao["checkout_resumo"] = summary
    if produto.get("name"):
        sessao["produto_checkout"] = produto["name"]

    resultado = {
        "ready": ready,
        "can_create_order": pode_criar,
        "needs_human": needs_human,
        "product": produto,
        "missing_fields": missing,
        "next_question": next_q,
        "summary": summary,
        "reason": reason,
        "reply": reply,
        "sessao": sessao,
        "pedido": None,
    }

    if status == "nao_iniciado" or (intent_u in ("COMPRA", "PAGAMENTO") and status == "coletando_dados"):
        log_seguro(
            "checkout_iniciado",
            intent=intent_u or "-",
            produto=(produto.get("name") or "")[:40] or "-",
            missing=",".join(missing) or "-",
        )
    log_seguro(
        "checkout_validado",
        ready=ready,
        can_create=pode_criar,
        needs_human=needs_human,
        reason=reason,
        missing=",".join(missing) or "-",
    )
    if missing:
        log_seguro("checkout_dados_faltando", missing=",".join(missing))
    if needs_human:
        log_seguro("checkout_humano_necessario", reason=reason)
    if dry_run or not persistir:
        log_seguro(
            "checkout_dry_run",
            dry_run=dry_run,
            persistir=persistir,
            would_create=ready and create_flag and integracao_ok,
        )

    return resultado


def criar_pedido_se_permitido(
    *,
    resultado: dict,
    historico_texto: str,
    cliente_supabase: dict,
    telefone: str,
    pushname: str = "",
    mensagem_atual: str = "",
    ultima_resposta_ia: str = "",
    frete_estimado: float = 0.0,
    nova_venda: bool = False,
    dry_run: bool = False,
    persistir: bool = True,
) -> dict:
    """Cria pedido real só com flags + dados mínimos + não dry_run."""
    out = dict(resultado or {})
    sessao = dict(out.get("sessao") or {})

    if dry_run or not persistir:
        log_seguro("checkout_dry_run", acao="criar_pedido_bloqueado")
        out["can_create_order"] = False
        out["pedido"] = None
        out["reason"] = "dry_run_ou_sem_persistir"
        out["reply"] = (
            (out.get("reply") or "")
            if out.get("ready")
            else out.get("reply")
        )
        if out.get("ready"):
            out["reply"] = (
                f"Perfeito. Resumo: {out.get('summary') or ''}. "
                "Posso te passar o próximo passo para compra."
            )
        return out

    if not out.get("can_create_order"):
        if out.get("needs_human"):
            log_seguro("checkout_humano_necessario", reason=out.get("reason"))
        return out

    if not checkout_criar_pedido_habilitado():
        out["can_create_order"] = False
        out["needs_human"] = True
        out["reason"] = "create_order_desabilitado"
        sessao["checkout_status"] = "humano_necessario"
        out["sessao"] = sessao
        out["reply"] = (
            f"Perfeito. Resumo: {out.get('summary') or ''}. "
            "Vou te encaminhar para o time finalizar o pedido com segurança."
        )
        log_seguro("checkout_humano_necessario", reason="create_order_desabilitado")
        return out

    pedido = None
    pedido_mercos = None

    try:
        from services.pedido_mercos_service import (
            criar_pedido_fechamento_mercos,
            mercos_criar_pedido_habilitado,
        )
        from services.mercos_service import mercos_configurado

        if mercos_configurado() and mercos_criar_pedido_habilitado():
            pedido_mercos = criar_pedido_fechamento_mercos(
                historico_texto=historico_texto,
                cliente_supabase=cliente_supabase,
                telefone=telefone,
                pushname=pushname,
                mensagem_atual=mensagem_atual,
                ultima_resposta_ia=ultima_resposta_ia,
                frete_estimado=frete_estimado,
            )
            if pedido_mercos and pedido_mercos.get("pedido_id"):
                pedido = pedido_mercos
    except Exception as exc:
        log_seguro("checkout_mercos_erro", erro=type(exc).__name__)
        pedido_mercos = {"erro": type(exc).__name__}

    try:
        from services.pedido_pulsedesk_service import (
            pulsedesk_pedidos_habilitado,
            registrar_venda_pulsedesk,
        )

        if pulsedesk_pedidos_habilitado():
            pedido_pd = registrar_venda_pulsedesk(
                historico_texto=historico_texto,
                cliente_supabase=cliente_supabase,
                telefone=telefone,
                pushname=pushname,
                mensagem_atual=mensagem_atual,
                ultima_resposta_ia=ultima_resposta_ia,
                frete_estimado=frete_estimado,
                nova_venda=nova_venda,
            )
            if pedido_mercos and pedido_mercos.get("pedido_id"):
                pedido = {
                    **(pedido_pd or {}),
                    "pedido_id": pedido_mercos.get("pedido_id"),
                    "numero": pedido_mercos.get("numero") or pedido_mercos.get("pedido_id"),
                    "origem": "mercos+pulsedesk",
                }
            elif pedido_pd and pedido_pd.get("pedido_id"):
                pedido = pedido_pd
    except Exception as exc:
        log_seguro("checkout_pulsedesk_erro", erro=type(exc).__name__)

    if pedido and pedido.get("pedido_id"):
        sessao["pedido_id"] = str(pedido["pedido_id"])
        sessao["checkout_status"] = "pedido_criado"
        out["pedido"] = pedido
        out["sessao"] = sessao
        out["reason"] = "pedido_criado"
        out["reply"] = (
            f"Pedido registrado com sucesso (#{pedido.get('numero') or pedido['pedido_id']}). "
            "Qualquer dúvida, estou por aqui."
        )
        log_seguro(
            "checkout_pedido_criado",
            pedido_id=str(pedido.get("pedido_id"))[:20],
            origem=pedido.get("origem") or "ok",
        )
    else:
        out["pedido"] = pedido
        out["needs_human"] = True
        out["can_create_order"] = False
        sessao["checkout_status"] = "humano_necessario"
        out["sessao"] = sessao
        out["reason"] = "falha_ou_sem_pedido"
        out["reply"] = (
            f"Perfeito. Resumo: {out.get('summary') or ''}. "
            "Vou te encaminhar para o time finalizar o pedido com segurança."
        )
        log_seguro("checkout_humano_necessario", reason="falha_ou_sem_pedido")

    return out


def processar_checkout_turno(
    *,
    mensagem: str,
    sessao: dict | None = None,
    produtos: list | None = None,
    intent: str = "",
    nome_cliente: str = "",
    historico_texto: str = "",
    cliente_supabase: dict | None = None,
    telefone: str = "",
    pushname: str = "",
    ultima_resposta_ia: str = "",
    frete_estimado: float = 0.0,
    nova_venda: bool = False,
    dry_run: bool = False,
    persistir: bool = True,
    tentar_criar: bool = False,
) -> dict:
    """Entrada principal do turno de checkout."""
    if not checkout_habilitado():
        return {
            "ready": False,
            "can_create_order": False,
            "needs_human": False,
            "product": _produto_ativo(sessao, produtos),
            "missing_fields": [],
            "next_question": "",
            "summary": "",
            "reason": "checkout_desabilitado",
            "reply": "",
            "sessao": sessao or {},
            "pedido": None,
            "handled": False,
        }

    resultado = avaliar_checkout(
        mensagem=mensagem,
        sessao=sessao,
        produtos=produtos,
        intent=intent,
        nome_cliente=nome_cliente,
        dry_run=dry_run,
        persistir=persistir,
    )
    resultado["handled"] = True

    if tentar_criar and resultado.get("ready"):
        resultado = criar_pedido_se_permitido(
            resultado=resultado,
            historico_texto=historico_texto,
            cliente_supabase=cliente_supabase or {},
            telefone=telefone,
            pushname=pushname,
            mensagem_atual=mensagem,
            ultima_resposta_ia=ultima_resposta_ia,
            frete_estimado=frete_estimado,
            nova_venda=nova_venda,
            dry_run=dry_run,
            persistir=persistir,
        )
        resultado["handled"] = True

    return resultado


def intent_e_checkout(intent: str) -> bool:
    return (intent or "").upper() in (
        "COMPRA",
        "PAGAMENTO",
        "ENTREGA",
    )


def sanitizar_claims_checkout(
    texto: str,
    *,
    pedido_criado: bool = False,
    pix_gerado: bool = False,
) -> str:
    """Remove afirmações falsas de pedido/Pix/reserva."""
    if not (texto or "").strip():
        return texto or ""
    out = texto
    if not pedido_criado:
        out = re.sub(
            r"(?i)\bpedido\s+criado\b[^.!?]*[.!]?",
            "Posso te passar o próximo passo para compra.",
            out,
        )
        out = re.sub(
            r"(?i)\bpedido\s+registrado\s+com\s+sucesso\b[^.!?]*[.!]?",
            "Posso te passar o próximo passo para compra.",
            out,
        )
    if not pix_gerado:
        out = re.sub(
            r"(?i)\bpix\s+gerado\b[^.!?]*[.!]?",
            "Posso te orientar no pagamento depois de confirmar o pedido.",
            out,
        )
        out = re.sub(
            r"(?i)\bpagamento\s+confirmado\b[^.!?]*[.!]?",
            "pagamento a confirmar",
            out,
        )
    out = re.sub(
        r"(?i)\bestoque\s+garantido\b",
        "disponibilidade a confirmar",
        out,
    )
    out = re.sub(
        r"(?i)\bj[aá]\s+separei\s+para\s+voc[eê]\b[^.!?]*[.!]?",
        "Quer seguir com a compra?",
        out,
    )
    out = re.sub(
        r"(?i)\bvou\s+mandar\s+para\s+entrega\b[^.!?]*[.!]?",
        "Quando confirmarmos o endereço, seguimos com a entrega.",
        out,
    )
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out
