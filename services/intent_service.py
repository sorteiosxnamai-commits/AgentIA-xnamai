"""Classificação estruturada de intenção (Etapa 3).

Não responde ao cliente — só decide o fluxo.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from services.vendas.respostas import cliente_pediu_mais_opcoes

INTENTS = (
    "SAUDACAO",
    "BUSCA_PRODUTO",
    "MAIS_OPCOES",
    "DUVIDA_PRODUTO",
    "PRECO",
    "COMPARACAO",
    "COMPRA",
    "OBJECAO",
    "SAC",
    "ENTREGA",
    "PAGAMENTO",
    "GARANTIA",
    "FORA_DO_ESCOPO",
    "ATENDIMENTO_HUMANO",
    "INDEFINIDO",
)

CONFIDENCE_MIN = 0.55

_CATEGORIAS = (
    "headset",
    "fone",
    "cabo",
    "hdmi",
    "mouse",
    "teclado",
    "monitor",
    "notebook",
    "webcam",
    "ssd",
    "hd",
    "hub",
    "carregador",
    "celular",
    "smartphone",
    "mesa",
    "cadeira",
)


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.lower()).strip()


def _resultado(
    intent: str,
    confidence: float,
    *,
    in_scope: bool = True,
    needs_catalog: bool = False,
    needs_human: bool = False,
    product_query: str = "",
    category: str = "",
    reason: str = "",
) -> dict[str, Any]:
    if confidence < CONFIDENCE_MIN and intent != "INDEFINIDO":
        return {
            "intent": "INDEFINIDO",
            "confidence": round(float(confidence), 2),
            "in_scope": True,
            "needs_catalog": False,
            "needs_human": False,
            "product_query": product_query or "",
            "category": category or "",
            "reason": f"baixa_confianca:{intent}:{reason}",
        }
    return {
        "intent": intent if intent in INTENTS else "INDEFINIDO",
        "confidence": round(float(min(1.0, max(0.0, confidence))), 2),
        "in_scope": bool(in_scope),
        "needs_catalog": bool(needs_catalog),
        "needs_human": bool(needs_human),
        "product_query": (product_query or "").strip(),
        "category": (category or "").strip(),
        "reason": (reason or "").strip(),
    }


def _extrair_categoria(texto: str, contexto: dict | None = None) -> str:
    ctx = contexto or {}
    for cat in _CATEGORIAS:
        if re.search(rf"\b{re.escape(cat)}\b", texto):
            if cat in ("ssd", "hd"):
                return "armazenamento"
            if cat in ("fone",):
                return "headset"
            if cat in ("smartphone",):
                return "celular"
            return cat
    return str(ctx.get("categoria_interesse") or ctx.get("category") or "")


def _extrair_product_query(mensagem: str, categoria: str) -> str:
    t = (mensagem or "").strip()
    if not t:
        return categoria or ""
    # Mantém curto
    if len(t) <= 80:
        return t
    return (categoria or t)[:80]


def classificar_intencao(
    mensagem: str,
    *,
    historico_texto: str = "",
    contexto_venda: dict | None = None,
    produto_ativo: str = "",
    categoria_ativa: str = "",
    ultima_pergunta_agente: str = "",
) -> dict[str, Any]:
    """
    Classifica a intenção da mensagem atual.

    Considera mensagem, histórico útil, contexto_venda, produto/categoria ativos
    e última pergunta do agente. Nunca gera resposta ao cliente.
    """
    msg = (mensagem or "").strip()
    t = _normalizar(msg)
    ctx = dict(contexto_venda or {})
    produto = (produto_ativo or ctx.get("produto_ativo") or ctx.get("produto_mencionado") or "").strip()
    categoria = (categoria_ativa or ctx.get("categoria_interesse") or "").strip()
    ultima_perg = _normalizar(
        ultima_pergunta_agente or ctx.get("ultima_pergunta_agente") or ""
    )
    hist = _normalizar(historico_texto or "")

    if not t:
        return _resultado("INDEFINIDO", 0.2, reason="mensagem_vazia")

    # --- ATENDIMENTO HUMANO ---
    if re.search(
        r"\b(atendente|humano|pessoa\s+real|falar\s+com\s+(alguem|alguém|vendedor|atendente))"
        r"|\b(quero|preciso)\s+(de\s+)?(um\s+)?(atendente|humano)"
        r"|\bpassa\s+(pro|para\s+o)\s+(vendedor|atendente)"
        r"|\bme\s+passa\s+(um\s+)?(humano|atendente)\b",
        t,
    ):
        return _resultado(
            "ATENDIMENTO_HUMANO",
            0.95,
            needs_human=True,
            reason="pedido_humano",
        )

    # --- SAC / reclamação ---
    if re.search(
        r"\b(reclam|problema|defeito|quebr|estrag|troca|devolver|devolucao|devolução|"
        r"atraso|atrasado|nao\s+recebi|não\s+recebi|suporte|sac|garantia\s+do\s+pedido|"
        r"pedido\s+errado|veio\s+errado|cobranca|cobrança\s+indevida)\b",
        t,
    ):
        # "tem garantia?" sozinho é GARANTIA, não SAC
        if re.search(r"\b(tem|qual|como\s+funciona)\s+(a\s+)?garantia\b", t) and not re.search(
            r"\b(reclam|problema|defeito|troca|devolver|atraso)\b", t
        ):
            pass
        else:
            return _resultado(
                "SAC",
                0.9,
                needs_human=True,
                reason="reclamacao_ou_suporte",
            )

    # --- FORA DO ESCOPO ---
    if re.search(
        r"\b(receita|bolo|pizza|futebol|politica|política|eleicao|eleição|"
        r"namoro|horoscopo|horóscopo|piada|chatgpt|openai|"
        r"previsao\s+do\s+tempo|previsão\s+do\s+tempo|cotacao\s+do\s+dolar|cotação\s+do\s+dólar)\b",
        t,
    ) or re.search(
        r"\b(me\s+ensina|como\s+fazer)\s+(um\s+)?(bolo|codigo|código)\b",
        t,
    ):
        return _resultado(
            "FORA_DO_ESCOPO",
            0.92,
            in_scope=False,
            reason="assunto_fora_empresa",
        )

    # --- SAUDAÇÃO ---
    if re.match(
        r"^(oi|ola|olá|opa|eai|eae|hey|bom dia|boa tarde|boa noite|"
        r"tudo bem|td bem|oie|oii+)[!?.]*$",
        t,
    ):
        return _resultado("SAUDACAO", 0.95, reason="saudacao_simples")

    # --- MAIS OPÇÕES (reusa detector existente — não quebrar fluxo) ---
    if cliente_pediu_mais_opcoes(msg):
        cat = _extrair_categoria(t, ctx) or categoria or _extrair_categoria(hist, ctx)
        return _resultado(
            "MAIS_OPCOES",
            0.93,
            needs_catalog=True,
            product_query=_extrair_product_query(msg, cat),
            category=cat,
            reason="pedido_mais_opcoes",
        )

    # --- PREÇO ---
    if re.search(
        r"\b(preco|preço|valor|quanto\s+(custa|fica|sai|e|é)|qual\s+(o\s+)?(preco|preço|valor)|"
        r"fica\s+em\s+quanto|custa\s+quanto)\b",
        t,
    ):
        cat = _extrair_categoria(t, ctx) or categoria
        return _resultado(
            "PRECO",
            0.9,
            needs_catalog=True,
            product_query=produto or _extrair_product_query(msg, cat),
            category=cat,
            reason="pergunta_preco",
        )

    # --- COMPARAÇÃO ---
    if re.search(
        r"\b(compar|diferenca|diferença|qual\s+(e|é)\s+melhor|melhor\s+entre|"
        r"ou\s+o\s+outro|vs\.?|versus)\b",
        t,
    ) or (
        " ou " in f" {t} "
        and re.search(r"\b(headset|fone|cabo|mouse|ssd|hd|monitor)\b", t)
        and t.count(" ou ") >= 1
        and len(t.split()) <= 12
    ):
        cat = _extrair_categoria(t, ctx) or categoria
        return _resultado(
            "COMPARACAO",
            0.85,
            needs_catalog=True,
            product_query=_extrair_product_query(msg, cat),
            category=cat,
            reason="comparacao_produtos",
        )

    # --- GARANTIA ---
    if re.search(r"\bgarantia\b", t):
        return _resultado(
            "GARANTIA",
            0.9,
            product_query=produto,
            category=categoria or _extrair_categoria(t, ctx),
            reason="pergunta_garantia",
        )

    # --- ENTREGA ---
    if re.search(
        r"\b(entrega|frete|prazo\s+de\s+entrega|envio|sedex|correios|"
        r"quanto\s+tempo\s+(pra|para)\s+(chegar|entregar)|retirada|retirar)\b",
        t,
    ):
        return _resultado("ENTREGA", 0.88, reason="pergunta_entrega")

    # --- PAGAMENTO ---
    if re.search(
        r"\b(pagamento|pagar|pix|boleto|cartao|cartão|parcel|forma\s+de\s+pag|"
        r"aceita\s+pix|como\s+pago)\b",
        t,
    ):
        return _resultado("PAGAMENTO", 0.88, reason="pergunta_pagamento")

    # --- COMPRA / fechamento ---
    if re.search(
        r"\b(quero\s+comprar|vou\s+levar|fechamos|fecha\s+pra\s+mim|pode\s+fechar|"
        r"quero\s+esse|quero\s+essa|fechado|manda\s+o\s+pix|pode\s+mandar\s+o\s+pix|"
        r"quero\s+fechar|vamos\s+fechar)\b",
        t,
    ):
        return _resultado(
            "COMPRA",
            0.9,
            needs_catalog=bool(produto or categoria),
            product_query=produto or _extrair_product_query(msg, categoria),
            category=categoria or _extrair_categoria(t, ctx),
            reason="intencao_compra",
        )

    # --- OBJEÇÃO ---
    if re.search(
        r"\b(muito\s+caro|ta\s+caro|está\s+caro|achei\s+caro|sem\s+grana|"
        r"nao\s+tenho\s+dinheiro|não\s+tenho\s+dinheiro|depois\s+eu\s+vejo|"
        r"vou\s+pensar|deixa\s+pra\s+la|deixa\s+para\s+la|nao\s+quero\s+mais|"
        r"não\s+quero\s+mais|desisto)\b",
        t,
    ):
        return _resultado(
            "OBJECAO",
            0.85,
            product_query=produto,
            category=categoria,
            reason="objecao_preco_ou_adiamento",
        )

    # Resposta a orçamento pedido pelo agente
    if re.search(r"(orcamento|orçamento|faixa|ate|até)\s*.{0,10}r?\$?\s*[\d.,]+", t) or (
        ultima_perg
        and re.search(r"orcamento|orçamento|faixa|preco|preço", ultima_perg)
        and re.search(r"\d", t)
        and len(t.split()) <= 12
    ):
        cat = categoria or _extrair_categoria(hist, ctx)
        return _resultado(
            "BUSCA_PRODUTO",
            0.8,
            needs_catalog=True,
            product_query=produto or cat,
            category=cat,
            reason="resposta_orcamento",
        )

    # --- DÚVIDA SOBRE PRODUTO ATIVO ---
    if produto and (
        re.search(
            r"\b(esse|essa|desse|dessa|dele|dela|tem\s+preto|tem\s+branco|"
            r"funciona|serve|compativel|compatível|detalhe|especific|"
            r"como\s+e|como\s+é|qual\s+a\s+cor)\b",
            t,
        )
        or (len(t.split()) <= 6 and t.endswith("?"))
    ):
        return _resultado(
            "DUVIDA_PRODUTO",
            0.82,
            needs_catalog=True,
            product_query=produto,
            category=categoria or _extrair_categoria(t, ctx),
            reason="duvida_produto_ativo",
        )

    # --- BUSCA DE PRODUTO ---
    cat_msg = _extrair_categoria(t, ctx)
    if re.search(
        r"\b(quero|queria|procuro|preciso|tem|têm|voces\s+tem|vocês\s+têm|"
        r"busca|looking|me\s+indica|indica|recomend|para\s+jogos|pra\s+jogos|"
        r"gamer)\b",
        t,
    ) and (
        cat_msg
        or re.search(
            r"\b(produto|item|modelo|aparelho)\b",
            t,
        )
    ):
        return _resultado(
            "BUSCA_PRODUTO",
            0.88,
            needs_catalog=True,
            product_query=_extrair_product_query(msg, cat_msg or categoria),
            category=cat_msg or categoria,
            reason="busca_produto",
        )

    if cat_msg and re.search(r"\b(quero|tem|procuro|preciso|indica)\b", t):
        return _resultado(
            "BUSCA_PRODUTO",
            0.86,
            needs_catalog=True,
            product_query=_extrair_product_query(msg, cat_msg),
            category=cat_msg,
            reason="categoria_na_mensagem",
        )

    # Mudança de assunto: nova categoria diferente da ativa
    if cat_msg and categoria and cat_msg != categoria and re.search(
        r"\b(na\s+verdade|melhor|agora|troca|muda|quero\s+um|quero\s+uma)\b",
        t,
    ):
        return _resultado(
            "BUSCA_PRODUTO",
            0.84,
            needs_catalog=True,
            product_query=_extrair_product_query(msg, cat_msg),
            category=cat_msg,
            reason="mudanca_assunto",
        )

    # Ambíguo / curto sem sinal claro
    if len(t.split()) <= 3 and not cat_msg:
        return _resultado(
            "INDEFINIDO",
            0.4,
            product_query=produto,
            category=categoria,
            reason="mensagem_ambigua",
        )

    return _resultado(
        "INDEFINIDO",
        0.45,
        product_query=produto,
        category=categoria or cat_msg,
        reason="sem_padrao_forte",
    )


def intent_precisa_catalogo(intent_result: dict | None) -> bool:
    return bool((intent_result or {}).get("needs_catalog"))


def intent_precisa_humano(intent_result: dict | None) -> bool:
    return bool((intent_result or {}).get("needs_human"))


def resposta_atendimento_humano(nome_cliente: str = "") -> str:
    nome = nome_cliente or "Cliente"
    return (
        f"Claro, {nome}! Vou te encaminhar para um atendimento humano. "
        "Um momento que já te conecto com alguém da equipe."
    )


def resposta_sac(nome_cliente: str = "") -> str:
    nome = nome_cliente or "Cliente"
    return (
        f"Sinto muito pelo transtorno, {nome}. "
        "Vou priorizar seu caso com o suporte. Me conta o número do pedido "
        "ou o que aconteceu, se puder, para agilizar."
    )


def resposta_fora_do_escopo(nome_cliente: str = "") -> str:
    nome = nome_cliente or "Cliente"
    return (
        f"Posso te ajudar com produtos e pedidos da xNaMai, {nome}. "
        "Sobre esse outro assunto não consigo orientar — "
        "mas se quiser headset, cabos, armazenamento ou periféricos, é só falar."
    )


# Frases comerciais a evitar na resposta final
FRASES_PROIBIDAS = (
    "a princípio temos em estoque",
    "a principio temos em estoque",
    "sujeito à separação",
    "sujeito a separacao",
    "sujeito à separacao",
    "aqui no chat não tenho foto",
    "aqui no chat nao tenho foto",
    "não trabalhamos com opções produtos",
    "nao trabalhamos com opcoes produtos",
    "quer ver o catálogo?",
    "quer ver o catalogo?",
    "disponível para envio",
    "disponivel para envio",
    "pronta entrega",
    "disponibilidade confirmada",
    "posso separar",
    "posso reservar",
    "já reservei",
    "deixo separado",
)


def sanitizar_frases_comerciais(
    texto: str,
    *,
    stock_confirmed: bool = False,
) -> str:
    """Remove/substitui frases ruins sem inventar estoque/reserva.

    Se stock_confirmed=True, permite falar de estoque real.
    Se False, remove afirmações de disponibilidade.
    """
    if not (texto or "").strip():
        return texto or ""
    out = texto
    substituicoes = [
        (
            r"(?i)a\s+princ[ií]pio\s+temos\s+(os\s+itens\s+)?em\s+estoque[^.!?]*[.!]?",
            "Posso verificar a disponibilidade para você. ",
        ),
        (
            r"(?i)\(?\s*sujeito\s+[àa]\s+separa[cç][aã]o\s*\)?[^.!?]*[.!]?",
            "",
        ),
        (
            r"(?i)aqui\s+no\s+chat\s+n[aã]o\s+tenho\s+foto[^.!?]*[.!]?",
            "",
        ),
        (
            r"(?i)ainda\s+n[aã]o\s+tenho\s+foto\s+d[oe]\s+[^.]+aqui\.?",
            "",
        ),
        (
            r"(?i)n[aã]o\s+trabalhamos\s+com\s+op[cç][oõ]es\s+produtos[^.!?]*[.!]?",
            "Posso te mostrar outras opções do que trabalhamos. ",
        ),
        (
            r"(?i)quer\s+ver\s+o\s+cat[aá]logo\?",
            "Quer que eu te mostre algumas opções?",
        ),
        (
            r"(?i)\bposso\s+separar\b[^.!?]*[.!]?",
            "Quer seguir com a compra?",
        ),
        (
            r"(?i)\bposso\s+reservar\b[^.!?]*[.!]?",
            "Quer seguir com a compra?",
        ),
        (
            r"(?i)\bj[aá]\s+reservei\b[^.!?]*[.!]?",
            "Quer seguir com a compra?",
        ),
        (
            r"(?i)\bdeixo\s+separado\b[^.!?]*[.!]?",
            "Quer seguir com a compra?",
        ),
        (
            r"(?i)\bseparar\s+1\b[^.!?]*[.!]?",
            "Quer seguir com a compra?",
        ),
    ]
    if not stock_confirmed:
        substituicoes.extend(
            [
                (
                    r"(?i),?\s*dispon[ií]vel\s+para\s+envio\.?",
                    ". Posso verificar a disponibilidade para você.",
                ),
                (
                    r"(?i)\bpronta\s+entrega\b",
                    "disponibilidade a confirmar",
                ),
                (
                    r"(?i)\b(temos|esta|está)\s+dispon[ií]vel\b(?!\s+\d)",
                    "Posso verificar a disponibilidade",
                ),
                (
                    r"(?i),?\s*com\s+disponibilidade\s+confirmada[^.!?]*[.!]?",
                    ". Posso verificar a disponibilidade para você.",
                ),
                (
                    r"(?i)\bdisponibilidade\s+confirmada\b",
                    "disponibilidade a confirmar",
                ),
                (
                    r"(?i)\bem\s+estoque\b",
                    "com disponibilidade a confirmar",
                ),
                (
                    r"(?i)\bdispon[ií]vel\b(?!\s+a\s+confirmar)",
                    "com disponibilidade a confirmar",
                ),
            ]
        )
    for padrao, repl in substituicoes:
        out = re.sub(padrao, repl, out)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+\.", ".", out)
    out = re.sub(r"\.{2,}", ".", out).strip()
    return out
