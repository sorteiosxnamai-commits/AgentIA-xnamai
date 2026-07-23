"""Montagem de contexto, intenções e estágio de venda (xNamai)."""

from __future__ import annotations

from typing import Any

from .guardrails import (
    detect_compare,
    detect_delivery_question,
    detect_human_support_request,
    detect_negotiation,
    detect_order_inquiry,
    detect_payment_question,
    detect_price_inquiry,
    detect_product_inquiry,
    detect_promotion_inquiry,
    detect_purchase_intent,
    detect_saudacao,
    detect_stock_inquiry,
    extract_budget,
    extract_quantity,
)
from .models import IncomingMessage
from .sales_knowledge import NOME_EMPRESA, SITE_URL

SALES_STAGES = (
    "descoberta",
    "busca_produto",
    "comparacao",
    "negociacao",
    "intencao_compra",
    "checkout",
    "atendimento_humano",
    "pos_venda",
)

INTENT_PRIORITY = (
    "atendimento_humano",
    "intencao_compra",
    "negociacao",
    "consultar_estoque",
    "consultar_preco",
    "comparar_produtos",
    "consultar_promocao",
    "consultar_pedido",
    "duvida_entrega",
    "duvida_pagamento",
    "buscar_produto",
    "pos_venda",
    "saudacao",
    "geral",
)


def detect_customer_intents(text: str | None) -> list[str]:
    normalized = text or ""
    intents: list[str] = []
    if detect_human_support_request(normalized):
        intents.append("atendimento_humano")
    if detect_purchase_intent(normalized):
        intents.append("intencao_compra")
    if detect_negotiation(normalized):
        intents.append("negociacao")
    if detect_stock_inquiry(normalized):
        intents.append("consultar_estoque")
    if detect_price_inquiry(normalized):
        intents.append("consultar_preco")
    if detect_compare(normalized):
        intents.append("comparar_produtos")
    if detect_promotion_inquiry(normalized):
        intents.append("consultar_promocao")
    if detect_order_inquiry(normalized):
        intents.append("consultar_pedido")
    if detect_delivery_question(normalized):
        intents.append("duvida_entrega")
    if detect_payment_question(normalized):
        intents.append("duvida_pagamento")
    if detect_product_inquiry(normalized):
        intents.append("buscar_produto")
    if detect_saudacao(normalized):
        intents.append("saudacao")
    if not intents:
        intents.append("geral")
    return intents


def _primary_intent(intents: list[str]) -> str:
    for candidate in INTENT_PRIORITY:
        if candidate in intents:
            return candidate
    return intents[0] if intents else "geral"


def infer_sales_stage(primary_intent: str, memoria: dict[str, Any] | None = None) -> str:
    mem = memoria or {}
    atual = str(mem.get("etapa") or mem.get("sales_stage") or "descoberta")
    mapping = {
        "saudacao": "descoberta",
        "buscar_produto": "busca_produto" if mem.get("orcamento") or mem.get("produto_mencionado") else "descoberta",
        "consultar_preco": "busca_produto",
        "consultar_estoque": "busca_produto",
        "comparar_produtos": "comparacao",
        "consultar_promocao": "negociacao",
        "negociacao": "negociacao",
        "intencao_compra": "intencao_compra",
        "duvida_pagamento": "checkout",
        "duvida_entrega": "checkout" if atual in ("intencao_compra", "checkout") else "descoberta",
        "consultar_pedido": "pos_venda",
        "atendimento_humano": "atendimento_humano",
        "pos_venda": "pos_venda",
        "geral": atual if atual in SALES_STAGES else "descoberta",
    }
    return mapping.get(primary_intent, atual if atual in SALES_STAGES else "descoberta")


def gather_customer_facts(
    message: IncomingMessage,
    customer_context: dict[str, Any],
) -> dict[str, Any]:
    text = message.text or ""
    mem = customer_context.get("memoria_sessao") or {}
    if not isinstance(mem, dict):
        mem = {}
    intents = detect_customer_intents(text)
    primary = _primary_intent(intents)
    budget = extract_budget(text) or mem.get("orcamento")
    qty = extract_quantity(text) or mem.get("quantidade")
    stage = infer_sales_stage(primary, {**mem, "orcamento": budget, "produto_mencionado": mem.get("produto_mencionado")})

    produtos_ctx = customer_context.get("produtos_contexto") or mem.get("produtos_contexto") or []
    if not isinstance(produtos_ctx, list):
        produtos_ctx = []
    catalogo = str(customer_context.get("catalogo") or "").strip()
    fonte = str(
        customer_context.get("fonte_produtos")
        or mem.get("fonte_produtos")
        or ""
    ).strip()

    facts: dict[str, Any] = {
        "primary_intent": primary,
        "intents": intents,
        "input_modality": message.input_modality,
        "display_name": customer_context.get("display_name")
        or customer_context.get("name")
        or mem.get("nome")
        or message.sender_name,
        "phone_present": bool(message.sender_phone),
        "empresa": NOME_EMPRESA,
        "site_url": SITE_URL or None,
        "orcamento": budget,
        "quantidade": qty,
        "sales_stage": stage,
        "produto_mencionado": mem.get("produto_mencionado") or customer_context.get("produto_mencionado"),
        "ultimo_produto": mem.get("ultimo_produto") or customer_context.get("ultimo_produto"),
        "ultima_pergunta": mem.get("ultima_pergunta"),
        "interesse_atual": mem.get("interesse_atual"),
        "catalogo": catalogo,
        "fonte_produtos": fonte or None,
        "produtos_precarregados": [p for p in produtos_ctx if isinstance(p, dict)],
    }

    if facts["produtos_precarregados"] and not facts.get("produto_mencionado"):
        p0 = facts["produtos_precarregados"][0]
        nome_p = p0.get("name") or p0.get("nome")
        if nome_p:
            facts["produto_mencionado"] = nome_p
            facts["ultimo_produto"] = nome_p

    # Respostas curtas dependem do contexto
    short = (text or "").strip().lower()
    if short in {"sim", "não", "nao", "esse", "o outro", "pode ser", "ok", "quero"}:
        facts["resposta_curta"] = short
        facts["precisa_contexto"] = True
    return facts


def format_facts_for_prompt(facts: dict[str, Any]) -> str:
    linhas = [
        f"- Intenção principal: {facts.get('primary_intent')}",
        f"- Estágio da venda: {facts.get('sales_stage')}",
        f"- Nome: {facts.get('display_name') or 'não informado'}",
        f"- Orçamento: {facts.get('orcamento') or 'não informado'}",
        f"- Quantidade: {facts.get('quantidade') or 'não informada'}",
        f"- Produto mencionado: {facts.get('produto_mencionado') or 'não informado'}",
        f"- Último produto: {facts.get('ultimo_produto') or 'não informado'}",
    ]
    if facts.get("fonte_produtos"):
        linhas.append(f"- Fonte do catálogo (Product Service): {facts['fonte_produtos']}")
    if facts.get("resposta_curta"):
        linhas.append(f"- Resposta curta do cliente: {facts['resposta_curta']} (use o contexto)")

    produtos = facts.get("produtos_precarregados") or []
    if produtos:
        linhas.append(
            "- CATÁLOGO PRÉ-CARREGADO (já consultado pelo Product Service — "
            "NÃO chame search_products / get_product / check_inventory / get_product_price):"
        )
        for p in produtos[:8]:
            if not isinstance(p, dict):
                continue
            nome = p.get("name") or p.get("nome") or ""
            preco = p.get("price") if p.get("price") is not None else p.get("preco")
            estoque = p.get("stock_quantity")
            if estoque is None:
                estoque = p.get("estoque")
            pedaco = f"  • {nome}"
            if preco not in (None, ""):
                pedaco += f" | R$ {preco}"
            if estoque not in (None, ""):
                pedaco += f" | estoque={estoque}"
            linhas.append(pedaco)
    elif facts.get("catalogo"):
        linhas.append("- CATÁLOGO PRÉ-CARREGADO (texto):")
        linhas.append(str(facts["catalogo"])[:2500])

    return "Contexto comercial:\n" + "\n".join(linhas)


def reply_from_preloaded_products(facts: dict[str, Any]) -> str | None:
    """Resposta segura a partir dos produtos já encontrados pelo Product Service."""
    produtos = facts.get("produtos_precarregados") or []
    if not produtos:
        catalogo = str(facts.get("catalogo") or "").strip()
        if catalogo:
            return (
                "Encontrei estas opções no catálogo:\n"
                + catalogo[:700]
                + "\nQual delas te interessa?"
            )
        return None
    nome = facts.get("display_name")
    prefixo = f"{nome}, encontrei estas opções:\n" if nome else "Encontrei estas opções:\n"
    linhas = []
    for p in produtos[:3]:
        if not isinstance(p, dict):
            continue
        item = p.get("name") or p.get("nome") or ""
        if not item:
            continue
        preco = p.get("price") if p.get("price") is not None else p.get("preco")
        if preco not in (None, ""):
            item += f" — R$ {preco}"
        linhas.append(f"• {item}")
    if not linhas:
        return None
    return prefixo + "\n".join(linhas) + "\nQual dessas faz mais sentido para você?"


def build_template_fallback(message: IncomingMessage, facts: dict[str, Any]) -> str | None:
    from .sales_knowledge import APRESENTACAO, HUMAN_SUPPORT_MESSAGE

    intent = facts.get("primary_intent")
    nome = facts.get("display_name")
    if intent == "saudacao":
        if nome:
            return f"Olá, {nome}! Sou o assistente de vendas da xNamai. Como posso ajudar hoje?"
        return APRESENTACAO
    if intent == "atendimento_humano":
        return HUMAN_SUPPORT_MESSAGE

    preloaded = reply_from_preloaded_products(facts)
    if preloaded and intent in (
        "buscar_produto",
        "consultar_preco",
        "consultar_estoque",
        "comparar_produtos",
        "negociacao",
        "intencao_compra",
        "geral",
    ):
        return preloaded

    if intent == "buscar_produto":
        return (
            "Claro! Você já tem alguma marca ou modelo em mente, "
            "ou prefere que eu procure opções dentro de uma faixa de preço?"
        )
    if intent in ("consultar_preco", "consultar_estoque") and facts.get("produto_mencionado"):
        return (
            f"Vou verificar isso sobre {facts['produto_mencionado']} para você. "
            "Um instante — se preferir, me diga o código ou o nome exato."
        )
    return None
