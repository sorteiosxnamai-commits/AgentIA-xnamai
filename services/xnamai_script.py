"""Roteiro de atendimento Xnamai (scripts comerciais do time de vendas)."""

from __future__ import annotations

import hashlib
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


def _variante(chave: str, opcoes: list[str]) -> str:
    """Escolha estável por conversa (testável, não aleatória pura)."""
    if not opcoes:
        return ""
    digest = hashlib.md5((chave or "x").encode("utf-8")).hexdigest()
    return opcoes[int(digest[:8], 16) % len(opcoes)]


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
    chave = nome_cliente or "anon"
    if nome_cliente:
        return _variante(
            f"saudacao:{chave}",
            [
                (
                    f"Olá, {nome_cliente}! Como vai?\n\n"
                    f"Sou a {CONSULTORA}, do time de vendas da {NOME_MARCA}. "
                    "No que posso te ajudar hoje?"
                ),
                (
                    f"Oi, {nome_cliente}! Tudo bem?\n\n"
                    f"Aqui é a {CONSULTORA}, do time de vendas da {NOME_MARCA}. "
                    "Me conta o que você precisa?"
                ),
                (
                    f"Oi, {nome_cliente}!\n\n"
                    f"Sou a {CONSULTORA}, consultora de vendas da {NOME_MARCA}. "
                    "Como posso te ajudar?"
                ),
            ],
        )
    return _variante(
        "saudacao:anon",
        [
            (
                f"Olá! Como vai?\n\n"
                f"Sou a {CONSULTORA}, do time de vendas da {NOME_MARCA}. "
                "No que posso te ajudar hoje?"
            ),
            (
                f"Oi! Tudo bem?\n\n"
                f"Aqui é a {CONSULTORA}, do time de vendas da {NOME_MARCA}. "
                "Me conta o que você precisa?"
            ),
        ],
    )


def resposta_abrir_espaco_pedido(nome_cliente: str = "") -> str:
    """Cliente quer pedir, mas ainda não disse o produto — não empurrar catálogo."""
    chave = nome_cliente or "anon"
    if nome_cliente:
        return _variante(
            f"abrir:{chave}",
            [
                (
                    f"Perfeito, {nome_cliente}! Pode me contar o que você está procurando?\n\n"
                    "Fico à disposição pra te ajudar com calma."
                ),
                (
                    f"Combinado, {nome_cliente}! O que você tem em mente?\n\n"
                    "Pode ser o produto ou o uso que você precisa."
                ),
                (
                    f"Beleza, {nome_cliente}! Me fala o que você busca "
                    "que eu te ajudo a achar a melhor opção."
                ),
            ],
        )
    return _variante(
        "abrir:anon",
        [
            (
                "Perfeito! Pode me contar o que você está procurando?\n\n"
                "Fico à disposição pra te ajudar com calma."
            ),
            "Combinado! O que você tem em mente? Produto ou o uso que precisa.",
        ],
    )


def resposta_alinhamento_pedido(nome_cliente: str = "") -> str:
    nome = nome_cliente or "Cliente"
    return _variante(
        f"alinhamento:{nome}",
        [
            (
                f"Perfeito, {nome}! Para finalizarmos o seu pedido, poderia me confirmar:\n\n"
                "1) Vai precisar de NF? Se sim, qual a %?\n"
                "2) Forma de envio ou retirada?\n\n"
                "Trabalhamos com pagamento antecipado para agilizar separação e despacho "
                "(não é obrigatório). ST/frete, se houver, avisamos depois com transparência."
            ),
            (
                f"Fechado, {nome}! Antes de registrar, só confirmo com você:\n\n"
                "• Precisa de NF (e qual %)?\n"
                "• Prefere envio ou retirada?\n\n"
                "Pagamento antecipado ajuda a agilizar a separação — sem obrigatoriedade. "
                "Frete/ST a gente confirma depois, com transparência."
            ),
        ],
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
        f"Posso verificar a disponibilidade para você, {nome}. "
        "Me diga o produto (ou me confirma o que estávamos vendo) que eu checo e te retorno."
    )


def cliente_perguntou_estoque(mensagem: str) -> bool:
    """Pergunta de estoque/disponibilidade de um item — não catálogo geral."""
    from services.vendas.respostas import cliente_quer_ver_catalogo

    # "quais produtos tem disponível" = catálogo, não estoque unitário
    if cliente_quer_ver_catalogo(mensagem):
        return False
    t = _normalizar(mensagem)
    if re.search(
        r"\b(quais|lista|catalogo|produtos|vende|vendem|opcoes|opções)\b",
        t,
    ) and re.search(r"\b(disponivel|disponível)\b", t):
        return False
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
    from services.vendas.respostas import cliente_quer_ver_catalogo, query_apenas_generica

    t = _normalizar(mensagem).rstrip("!?.,")
    if not t:
        return True
    if cliente_quer_ver_catalogo(mensagem) or query_apenas_generica(mensagem):
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
    # Confirmação / reação curta — não é busca
    if re.match(
        r"^(eu\s+)?sei(\s+que\s+(nao|não))?$|^(ok|beleza|entendi|certo|ta|tá)$",
        t,
    ):
        return True
    # Pergunta genérica de preço (sem nome de produto)
    if re.match(
        r"^(qual|quanto)\s+(e|é|eh)?\s*(o\s+)?(valor|preco|preço)"
        r"(\s+(dele|dela|disso))?$|^quanto\s+(custa|fica|sai)$|^valor\??$",
        t,
    ):
        return True
    # Pedido genérico de opções — não é busca de produto inexistente
    if re.search(
        r"mais\s+(opcoes|opções|modelos|alternativas)"
        r"|outras\s+(opcoes|opções|alternativas)"
        r"|tem\s+mais\s+(produtos|alguma)"
        r"|outra\s+marca"
        r"|mais\s+barato|algum\s+melhor"
        r"|me\s+mostra\s+outros",
        t,
    ) and not re.search(
        r"\b(nao|não)\s+(quero|precisa)\b.*\b(opcoes|opções|outros)\b"
        r"|opcoes?\s+de\s+cor",
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
