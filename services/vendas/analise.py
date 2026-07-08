import re
import unicodedata

from services.conversa_service import (
    conversa_em_andamento,
    extrair_endereco,
    extrair_pagamento,
    entrega_ja_informada,
    ia_ja_pediu_endereco,
)

OBJECOES = {
    "preco": (
        r"\bcaro\b|\bcust[ao]\b|\bnao tenho\b|\bnão tenho\b|\bmuito\b.*\b(valor|preco|preço)\b"
        r"|\bconseguir\b.*\bdesconto\b|\bmais barato\b|\bcaba\b.*\borcamento\b"
    ),
    "prazo": (
        r"\bdemora\b|\bquando chega\b|\bprazo\b|\bentrega\b.*\b(quanto|quando)\b"
        r"|\brapido\b|\brápido\b|\burgente\b"
    ),
    "confianca": (
        r"\bconfiavel\b|\bconfiável\b|\bgolpe\b|\bseguro\b|\bconheco\b|\bconheço\b"
        r"|\bprimeira vez\b|\bja compr\b|\bjá compr\b"
    ),
    "decisao": (
        r"\bvou pensar\b|\bdeixa eu ver\b|\bdepois\b|\bmais tarde\b|\bconversar com\b"
        r"|\bver com\b|\bnao sei\b|\bnão sei\b"
    ),
    "comparacao": (
        r"\boutra loja\b|\bmercado livre\b|\bshopee\b|\bamazon\b|\bmais em conta\b"
        r"|\bvi mais barato\b|\bconcorren"
    ),
}

INTENCAO_COMPRA = (
    r"\b(quero|vou)\s+(comprar|fechar|levar|pegar)\b",
    r"\bpode separar\b",
    r"\bseparar\b.*\b(pra|para)\b",
    r"\bfech(o|a|ado|ou)\b",
    r"\bconfirmo\b",
    r"\bmanda\b.*\bpix\b",
    r"\bforma de pagamento\b",
    r"\bcomo (pago|faço o pagamento)\b",
    r"\bquanto fica\b",
    r"\bfazer pedido\b",
    r"\bpode mandar\b",
    r"\bvou levar\b",
    r"\bbeleza\b.*\b(fecha|pedido)\b",
)

NECESSIDADE_USO = (
    r"\bpara\b",
    r"\bpro\b|\bpra\b",
    r"\buso\b",
    r"\bpreciso\b",
    r"\bquero\b",
    r"\bgift\b|\bpresente\b",
    r"\btrabalho\b|\bcasa\b|\bacademia\b|\bviagem\b",
)

INDICIOS_ORCAMENTO = (
    r"\bquanto\b",
    r"\bvalor\b",
    r"\bpreco\b|\bpreço\b",
    r"\bcusta\b",
    r"\borcamento\b|\borçamento\b",
    r"\bat[eé]\s*r?\$?\s*\d",
)

INDICIOS_PRAZO = (
    r"\bhoje\b",
    r"\bamanha\b|\bamanhã\b",
    r"\bessa semana\b",
    r"\burgente\b",
    r"\blogo\b",
    r"\bquando\b",
)


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().strip()


def _buscar_padroes(texto: str, padroes: tuple[str, ...]) -> bool:
    return any(re.search(p, texto) for p in padroes)


def detectar_objecao(mensagem: str, historico_texto: str = "") -> str | None:
    texto = _normalizar(f"{historico_texto}\n{mensagem}")
    for tipo, padrao in OBJECOES.items():
        if re.search(padrao, texto):
            return tipo
    return None


def detectar_intencao_compra(mensagem: str, historico_texto: str = "") -> bool:
    texto = _normalizar(mensagem)
    if _buscar_padroes(texto, INTENCAO_COMPRA):
        return True

    historico = _normalizar(historico_texto)
    return any(
        p in historico
        for p in ("separar", "fechar", "endereco", "endereço", "pagamento", "frete")
    ) and _buscar_padroes(texto, (r"\bsim\b", r"\bok\b", r"\bbeleza\b", r"\bconfirmo\b"))


def analisar_bant(mensagem: str, historico_texto: str) -> dict:
    texto = _normalizar(f"{historico_texto}\n{mensagem}")

    need = _buscar_padroes(texto, NECESSIDADE_USO) or bool(
        re.search(r"\b(fone|caixa|carregador|perfume|vinho|notebook|celular)\b", texto)
    )
    budget = _buscar_padroes(texto, INDICIOS_ORCAMENTO)
    timeline = _buscar_padroes(texto, INDICIOS_PRAZO)
    authority = bool(re.search(r"\b(esposa|marido|chefe|empresa|cnpj|socio|sócio)\b", texto))

    return {
        "need": need,
        "budget": budget,
        "authority": authority,
        "timeline": timeline,
    }


def inferir_estagio_aida(
    mensagem: str,
    historico_texto: str,
    produtos_encontrados: bool,
    pedido_encerrado: bool = False,
) -> str:
    if pedido_encerrado:
        return "pos_venda"

    if not conversa_em_andamento(historico_texto):
        return "atencao"

    texto = _normalizar(f"{historico_texto}\n{mensagem}")
    bant = analisar_bant(mensagem, historico_texto)

    if detectar_intencao_compra(mensagem, historico_texto):
        if entrega_ja_informada(historico_texto) or extrair_pagamento(historico_texto) != "a combinar":
            return "acao"
        return "desejo"

    if detectar_objecao(mensagem, historico_texto):
        return "desejo"

    if produtos_encontrados and (bant["budget"] or "r$" in texto):
        return "desejo"

    if produtos_encontrados or bant["need"]:
        return "interesse"

    return "atencao"


def orientacao_spin(mensagem: str, historico_texto: str, bant: dict) -> str:
    texto = _normalizar(f"{historico_texto}\n{mensagem}")
    linhas = []

    if not bant["need"]:
        linhas.append(
            "Situação: descubra para que o cliente precisa (uso, presente, trabalho) "
            "com UMA pergunta natural."
        )
    elif not re.search(r"\b(problema|dificuldade|nao funciona|não funciona|preciso trocar)\b", texto):
        linhas.append(
            "Problema: entenda a dor ou limitação do que ele usa hoje — "
            "pergunte só se fizer sentido."
        )
    elif bant["budget"] and detectar_objecao(mensagem, historico_texto) == "preco":
        linhas.append(
            "Necessidade: conecte o produto ao benefício concreto para o caso dele, "
            "sem pressionar."
        )
    else:
        linhas.append(
            "Payoff: mostre como o produto resolve o que ele descreveu; "
            "se já entendeu, avance para fechamento suave."
        )

    return " ".join(linhas)


def orientacao_objecao(tipo: str | None) -> str:
    if not tipo:
        return ""

    orientacoes = {
        "preco": (
            "Objeção de preço: valide a preocupação, reforce valor/benefício do catálogo "
            "e, se houver opção mais em conta no catálogo, apresente. Não invente desconto."
        ),
        "prazo": (
            "Objeção de prazo: seja honesto sobre confirmação de frete pela equipe; "
            "não prometa data exata."
        ),
        "confianca": (
            "Objeção de confiança: tom calmo, mencione que a equipe finaliza o pedido "
            "e confirma detalhes. Sem textão."
        ),
        "decisao": (
            "Objeção de decisão: respeite o tempo, deixe porta aberta, "
            "ofereça tirar dúvida específica — uma pergunta só."
        ),
        "comparacao": (
            "Comparação com concorrência: destaque diferencial do produto do catálogo "
            "(preço, categoria, descrição). Não fale mal de outras lojas."
        ),
    }
    return orientacoes.get(tipo, "")
