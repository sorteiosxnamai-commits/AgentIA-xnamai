"""Roteiro de atendimento Xnamai (scripts comerciais do time de vendas)."""

from __future__ import annotations

import os
import re
import unicodedata

PEDIDO_MINIMO = float(os.getenv("XNAMAI_PEDIDO_MINIMO", "800") or "800")
# false no sandbox (produtos de teste baratos); true em produção Xnamai
PEDIDO_MINIMO_ATIVO = os.getenv("XNAMAI_PEDIDO_MINIMO_ATIVO", "false").strip().lower() in (
    "1",
    "true",
    "sim",
    "yes",
)
CONSULTORA = (os.getenv("XNAMAI_CONSULTORA", "Ana") or "Ana").strip()
NOME_MARCA = "xNaMai"


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().strip()


def extrair_preferencia_nf(historico_texto: str, mensagem: str = "") -> str | None:
    """Retorna 'sem_nf', 'com_nf' ou None se ainda não informado."""
    textos = []
    if mensagem:
        textos.append(mensagem)
    for linha in reversed((historico_texto or "").split("\n")):
        if linha.startswith("Cliente:"):
            textos.append(linha.replace("Cliente:", "").strip())
        if len(textos) >= 8:
            break

    for texto in textos:
        t = _normalizar(texto)
        if re.search(r"\bsem\s*nf\b|\bnão\s*(quero|preciso)\s*nf\b|\bnao\s*(quero|preciso)\s*nf\b|\bsem\s*nota\b", t):
            return "sem_nf"
        if re.search(r"\bcom\s*nf\b|\bprecisa(rei)?\s*(de\s*)?nf\b|\bnota\s*fiscal\b|\bnf\s*\d", t):
            return "com_nf"
        if re.search(r"\bnf\b", t) and re.search(r"\b(sim|quero|preciso|pode)\b", t):
            return "com_nf"
        if re.search(r"\bnf\b", t) and re.search(r"\b(nao|não|sem)\b", t):
            return "sem_nf"
    return None


def extrair_forma_envio(historico_texto: str, mensagem: str = "") -> str | None:
    from services.conversa_service import extrair_endereco

    padrao_retirada = (
        r"\bretirada\b|\bretirar\b|\bretiro\b|\bbuscar\b|\bpego\b|\bretiro no local\b"
    )
    padrao_envio = (
        r"\benvio\b|\benviar\b|\bfrete\b|\bcorreios\b|\btransportadora\b|"
        r"\bentrega\b|\bmandar\b"
    )

    if mensagem:
        t = _normalizar(mensagem)
        if re.search(padrao_retirada, t):
            return "retirada"
        if re.search(padrao_envio, t):
            return "envio"

    for linha in reversed((historico_texto or "").split("\n")):
        if not linha.startswith("Cliente:"):
            continue
        t = _normalizar(linha)
        if re.search(padrao_retirada, t):
            return "retirada"
        if re.search(padrao_envio, t):
            return "envio"

    # Só usa endereço real (rua/av) — nunca pergunta antiga de produto
    end = extrair_endereco(historico_texto)
    if end:
        return end
    return None


def alinhamento_completo(historico_texto: str, mensagem: str = "") -> bool:
    return (
        extrair_preferencia_nf(historico_texto, mensagem) is not None
        and extrair_forma_envio(historico_texto, mensagem) is not None
    )


def ia_pediu_alinhamento(ultima_resposta_ia: str) -> bool:
    t = _normalizar(ultima_resposta_ia or "")
    return any(
        p in t
        for p in (
            "precisara de nf",
            "precisará de nf",
            "precisa de nf",
            "forma de envio",
            "envio ou retirada",
            "alinhamento",
            "para finalizarmos o seu pedido",
        )
    )


def resposta_saudacao_xnamai(nome_cliente: str = "") -> str:
    if nome_cliente:
        return (
            f"Olá, {nome_cliente}! Como vai?\n\n"
            f"Sou a {CONSULTORA}, do time de vendas da {NOME_MARCA}. "
            "No que posso te ajudar hoje?"
        )
    return (
        f"Olá! Como vai?\n\n"
        f"Sou a {CONSULTORA}, do time de vendas da {NOME_MARCA}. "
        "No que posso te ajudar hoje?"
    )


def resposta_abrir_espaco_pedido(nome_cliente: str = "") -> str:
    """Cliente quer pedir, mas ainda não disse o produto — não empurrar catálogo."""
    if nome_cliente:
        return (
            f"Perfeito, {nome_cliente}! Pode me contar o que você está procurando?\n\n"
            "Fico à disposição pra te ajudar com calma."
        )
    return (
        "Perfeito! Pode me contar o que você está procurando?\n\n"
        "Fico à disposição pra te ajudar com calma."
    )


def resposta_alinhamento_pedido(nome_cliente: str = "") -> str:
    nome = nome_cliente or "Cliente"
    return (
        f"Perfeito, {nome}! Para finalizarmos o seu pedido, poderia me confirmar:\n\n"
        "1) Vai precisar de NF? Se sim, qual a %?\n"
        "2) Forma de envio ou retirada?\n\n"
        "Trabalhamos com pagamento antecipado para agilizar separação e despacho "
        "(não é obrigatório). ST/frete, se houver, avisamos depois com transparência."
    )


def resposta_pedido_minimo(nome_cliente: str = "", valor_atual: float | None = None) -> str:
    nome = nome_cliente or "Cliente"
    valor_fmt = f"R$ {PEDIDO_MINIMO:.2f}".replace(".", ",")
    atual = ""
    if valor_atual is not None and valor_atual > 0:
        atual = f" Seu pedido está em R$ {valor_atual:.2f}.".replace(".", ",")
    return (
        f"Bom dia, {nome}! Tudo bem?\n\n"
        f"Para prosseguirmos, o valor mínimo do pedido é {valor_fmt} em produtos.{atual}\n\n"
        "Se quiser, te ajudo a complementar com itens do catálogo."
    )


def resposta_estoque_disponibilidade(nome_cliente: str = "") -> str:
    nome = nome_cliente or "Cliente"
    return (
        f"A princípio temos os itens em estoque, sim, {nome}!\n\n"
        "Como o pedido ainda passa pela fila de separação, pode acontecer de algum item "
        "ficar indisponível na conferência. Nesse caso fazemos crédito ou estorno no mesmo dia.\n\n"
        "Para iniciarmos a separação, o pagamento antecipado é a etapa inicial do processo "
        "(sem obrigatoriedade)."
    )


def cliente_perguntou_estoque(mensagem: str) -> bool:
    t = _normalizar(mensagem)
    return bool(
        re.search(
            r"\b(tem\s+todos|vai\s+ter\s+tudo|estoque|disponivel|disponível|falta)\b",
            t,
        )
    )


def cliente_perguntou_como_trabalham(mensagem: str) -> bool:
    """Pergunta institucional — NÃO é busca de produto."""
    t = _normalizar(mensagem)
    padroes = (
        r"como\s+(voces|vocês|vcs|vc|voce|você)?\s*trabalh",
        r"como\s+funciona",
        r"qual\s+(o\s+)?(processo|fluxo|procedimento)",
        r"forma\s+de\s+(trabalho|atendimento|pagamento)",
        r"trabalham\s+como",
        r"quero\s+saber\s+como",
        r"queria\s+saber\s+como",
        r"me\s+explica\s+como",
        r"politica\s+de\s+(venda|pagamento|envio)",
        r"pagamento\s+antecipado",
        r"preciso\s+de\s+nf\??$",
        r"emitem\s+nf",
        r"valor\s+minimo",
        r"pedido\s+minimo",
    )
    return any(re.search(p, t) for p in padroes)


def mensagem_nao_e_busca_produto(mensagem: str) -> bool:
    """Saudação, processo, estoque, envio/retirada — não dispara 'fora do catálogo'."""
    t = _normalizar(mensagem).rstrip("!?.,")
    if not t:
        return True
    if cliente_perguntou_como_trabalham(mensagem):
        return True
    if cliente_perguntou_estoque(mensagem) and not re.search(
        r"\b(headset|cabo|hdmi|mouse|monitor|notebook|webcam|ssd|hub)\b", t
    ):
        return True
    if re.match(
        r"^(oi|ola|olá|opa|eai|eae|bom dia|boa tarde|boa noite|tudo bem|td bem)$",
        t,
    ):
        return True
    if re.search(
        r"\b(quero|queria|gostaria)\s+(fazer\s+)?(um\s+)?(pedido|compra)\b",
        t,
    ) and not re.search(
        r"\b(headset|cabo|hdmi|mouse|monitor|notebook|webcam|ssd|hub|fone)\b",
        t,
    ):
        return True
    # Respostas de alinhamento (NF / envio / retirada)
    if re.search(
        r"\b(retirada|retirar|retiro|envio|enviar|sem\s*nf|com\s*nf|nota\s*fiscal)\b",
        t,
    ) and not re.search(
        r"\b(headset|cabo|hdmi|mouse|monitor|notebook|webcam|ssd|hub|fone)\b",
        t,
    ):
        return True
    return False


def resposta_como_trabalham(nome_cliente: str = "") -> str:
    nome = nome_cliente or "Cliente"
    return (
        f"Claro, {nome}! Te explico rapidinho como trabalhamos:\n\n"
        "• Você me conta o que precisa e eu te ajudo com os produtos\n"
        "• Alinhamos NF (se precisar) e forma de envio ou retirada\n"
        "• Preferimos pagamento antecipado pra agilizar separação e despacho "
        "(não é obrigatório)\n"
        "• Se na separação faltar algum item, fazemos crédito ou estorno no mesmo dia\n\n"
        "O que você está procurando?"
    )


def valor_pedido_historico(historico_texto: str) -> float | None:
    from services.conversa_service import _extrair_preco_historico

    return _extrair_preco_historico(historico_texto)


def precisa_avisar_pedido_minimo(historico_texto: str) -> bool:
    if not PEDIDO_MINIMO_ATIVO or PEDIDO_MINIMO <= 0:
        return False
    valor = valor_pedido_historico(historico_texto)
    if valor is None:
        return False
    return valor < PEDIDO_MINIMO


def enriquecer_resumo_fechamento(
    linhas: list[str],
    historico_texto: str,
    mensagem_atual: str = "",
) -> list[str]:
    """Acrescenta NF/envio/pagamento antecipado no resumo final."""
    nf = extrair_preferencia_nf(historico_texto, mensagem_atual)
    envio = extrair_forma_envio(historico_texto, mensagem_atual)

    if nf == "com_nf":
        linhas.append("🧾 NF: sim (equipe confirma %)")
    elif nf == "sem_nf":
        linhas.append("🧾 NF: não")

    if envio:
        if envio == "retirada":
            linhas.append("🚚 Forma: retirada")
        elif envio == "envio":
            linhas.append("🚚 Forma: envio (frete a confirmar)")
        else:
            linhas.append(f"🚚 Envio/entrega: {envio}")

    linhas.append(
        "💳 Preferência: pagamento antecipado para agilizar separação "
        "(ajustes de ST/frete, se houver, avisamos depois)."
    )
    return linhas
