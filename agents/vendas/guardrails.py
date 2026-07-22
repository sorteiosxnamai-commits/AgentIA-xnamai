"""Guardrails comerciais da xNamai — bloqueia só o perigoso, não vendas normais."""

from __future__ import annotations

import re

HUMAN_SUPPORT_KEYWORDS = (
    "falar com atendente",
    "falar com um atendente",
    "atendente humano",
    "atendimento humano",
    "falar com alguem",
    "falar com alguém",
    "quero um humano",
    "quero atendente",
    "falar com a equipe",
    "preciso de um humano",
)

# Bloquear apenas riscos reais — NÃO bloquear "quero comprar", preço, estoque etc.
BLOCKED_PATTERNS = (
    r"\btoken\b.*(api|supabase|openai|mercos)",
    r"(chave|secret|service.?role).*(supabase|openai)",
    r"dados do(a)? (outro|outra) cliente",
    r"cpf (do|da) (outro|outra)",
    r"\bbomba\b|\bameaça\b|\bameaca\b|\bmat(ar|o)\b",
    r"fraude|golpe financeiro|clonar cart",
)


def _norm(text: str | None) -> str:
    return (text or "").lower()


def detect_human_support_request(text: str) -> bool:
    n = _norm(text)
    return any(k in n for k in HUMAN_SUPPORT_KEYWORDS)


def detect_saudacao(text: str) -> bool:
    n = _norm(text).strip()
    return n in {
        "oi",
        "olá",
        "ola",
        "bom dia",
        "boa tarde",
        "boa noite",
        "hey",
        "eai",
        "e aí",
    } or n.startswith(("oi ", "olá ", "ola ", "bom dia", "boa tarde", "boa noite"))


def detect_product_inquiry(text: str) -> bool:
    n = _norm(text)
    keys = (
        "produto",
        "produtos",
        "quero um",
        "quero uma",
        "procurando",
        "estou procurando",
        "tem ",
        "vende",
        "catalogo",
        "catálogo",
        "notebook",
        "celular",
        "fone",
        "headset",
        "mouse",
        "teclado",
        "cabo",
        "relogio",
        "relógio",
    )
    return any(k in n for k in keys)


def detect_price_inquiry(text: str) -> bool:
    n = _norm(text)
    return any(
        k in n
        for k in (
            "preco",
            "preço",
            "quanto custa",
            "quanto fica",
            "valor",
            "qual o preço",
            "qual o preco",
        )
    )


def detect_stock_inquiry(text: str) -> bool:
    n = _norm(text)
    return any(
        k in n
        for k in (
            "estoque",
            "tem em estoque",
            "disponivel",
            "disponível",
            "tem disponível",
            "tem disponivel",
        )
    )


def detect_promotion_inquiry(text: str) -> bool:
    n = _norm(text)
    return any(k in n for k in ("promocao", "promoção", "desconto", "tem desconto"))


def detect_order_inquiry(text: str) -> bool:
    n = _norm(text)
    return any(k in n for k in ("meu pedido", "status do pedido", "rastreio", "onde está meu pedido"))


def detect_purchase_intent(text: str) -> bool:
    n = _norm(text)
    return any(
        k in n
        for k in (
            "quero esse",
            "quero comprar",
            "quero fazer um pedido",
            "vou querer",
            "pode reservar",
            "quero pagar",
            "como finalizo",
            "fecha pra mim",
        )
    )


def detect_negotiation(text: str) -> bool:
    n = _norm(text)
    return any(k in n for k in ("desconto", "mais barato", "consegue desconto", "melhor preço", "negociar"))


def detect_compare(text: str) -> bool:
    n = _norm(text)
    return any(
        k in n
        for k in (
            "qual desses",
            "qual é melhor",
            "qual e melhor",
            "diferença",
            "comparar",
            "o outro",
            "o mais barato",
        )
    )


def detect_delivery_question(text: str) -> bool:
    n = _norm(text)
    return any(k in n for k in ("entrega", "frete", "prazo de envio", "envia para"))


def detect_payment_question(text: str) -> bool:
    n = _norm(text)
    return any(k in n for k in ("como pago", "pagamento", "pix", "boleto", "cartão", "cartao"))


def detect_blocked_request(text: str) -> str | None:
    n = _norm(text)
    # Frases comerciais normais NUNCA bloqueadas
    for ok in (
        "quero comprar",
        "quero um produto",
        "quero fazer um pedido",
        "tem desconto",
        "qual o preço",
        "quanto custa",
        "tem em estoque",
        "quero dois",
        "pode reservar",
        "qual o mais barato",
        "qual é melhor",
        "quero pagar",
        "como finalizo",
    ):
        if ok in n and not any(
            bad in n for bad in ("token", "service role", "outro cliente", "outra cliente")
        ):
            return None
    for pat in BLOCKED_PATTERNS:
        if re.search(pat, n, flags=re.IGNORECASE):
            return f"blocked:{pat}"
    return None


def default_safe_handoff() -> str:
    from .sales_knowledge import HUMAN_SUPPORT_MESSAGE

    return (
        "Para sua segurança, vou encaminhar esse atendimento para a equipe da xNamai. "
        + HUMAN_SUPPORT_MESSAGE
    )


def extract_budget(text: str) -> str | None:
    m = re.search(
        r"(?:até|ate|maximo|máximo|orcamento|orçamento|faixa)\s*(?:de\s*)?R?\$?\s*([\d\.\,]+)",
        text or "",
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m2 = re.search(r"R\$\s*([\d\.\,]+)", text or "", flags=re.IGNORECASE)
    return m2.group(1) if m2 else None


def extract_quantity(text: str) -> int | None:
    n = _norm(text)
    m = re.search(r"quero\s+(\d+)\b", n)
    if m:
        return int(m.group(1))
    m2 = re.search(r"\b(\d+)\s+unidades?\b", n)
    if m2:
        return int(m2.group(1))
    if "quero dois" in n or "quero 2" in n:
        return 2
    if "quero tres" in n or "quero três" in n or "quero 3" in n:
        return 3
    return None
