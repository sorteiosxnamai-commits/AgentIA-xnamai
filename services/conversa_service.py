import re
import unicodedata

from services.pix_service import montar_mensagem_pix_exemplo

# Confirmações fracas: só fecham se a IA pediu fechamento explicitamente
CONFIRMACOES_FRACAS = (
    "beleza",
    "blz",
    "ok",
    "okay",
    "show",
    "perfeito",
    "pode ser",
    "isso",
    "sim",
    "certo",
    "combinado",
)

# Confirmações fortes: intenção clara de fechar
CONFIRMACOES_FORTES = (
    "fechado",
    "confirmo",
    "fechou",
    "fechamos",
    "fechamos sim",
    "vamos fechar",
    "pode fechar",
    "pode separar",
    "separar",
    "quero fechar",
    "fecha",
    "fechado sim",
)

CONFIRMACOES = CONFIRMACOES_FRACAS + CONFIRMACOES_FORTES

PADROES_CONFIRMACAO_FORTE = (
    r"\bfechou\b",
    r"\bfechado\b",
    r"\bfechamos\b",
    r"\bfechar\b",
    r"\bconfirmo\b",
    r"\bpode separar\b",
    r"\bvou levar\b",
    r"\bvamos fechar\b",
    r"\bpode fechar\b",
)

PADROES_CONFIRMACAO_MSG = PADROES_CONFIRMACAO_FORTE + (
    r"\bcombinado\b",
    r"\bpaguei\b",
    r"\bfiz pagamento\b",
    r"\bpagamento\b",
    r"\bpix\b",
    r"\bsim\b",
    r"\bok\b",
    r"\bbeleza\b",
    r"\bshow\b",
    r"\bperfeito\b",
)

PADROES_IA_PEDIU_FECHAMENTO = (
    r"\bfechamos\b",
    r"\bfecha(mos)?\s+\d+\s+unidade",
    r"\bquer(o)?\s+que\s+eu\s+separe\b",
    r"\bseparo\s+pra\s+voce\b",
    r"\bpra\s+fechar\b",
    r"\bconfirmo\s+o\s+pedido\b",
    r"\bposso\s+fechar\b",
    r"\bfechamos\s+\d",
    r"\bunidade\??\s*$",
)

SAUDACOES_INICIAIS = (
    r"^(oi|ola|olá|hey|eae|e ai|eai|bom dia|boa tarde|boa noite|hello|hi)\b",
    r"^tudo bem\b",
    r"^(fala|salve|opa)\b",
    r"\bcomo (vai|esta|está|vc|voce|você)\b",
)

CONVERSA_CASUAL = (
    r"\btudo bem\b",
    r"\bmeu amor\b",
    r"\bminha vida\b",
    r"\bte amo\b",
    r"\bto bem\b",
    r"\bestou bem\b",
    r"\bobrigad",
    r"\bvaleu\b",
    r"\bkkk+\b",
    r"\bhaha+\b",
)

INDICIOS_ANDAMENTO = (
    "r$",
    "frete",
    "entrega",
    "endereco",
    "endereço",
    "debito",
    "débito",
    "pagamento",
    "caixa de som",
    "fone",
    "produto",
    "separar",
    "fechar",
    "lt800",
    "rua ",
    "avenida",
    "av ",
)

INDICIOS_FECHAMENTO = (
    "frete",
    "entrega",
    "endereco",
    "endereço",
    "debito",
    "débito",
    "pagamento",
    "pix",
    "paguei",
    "separar",
    "fechar",
    "fechou",
    "reservo",
    "na entrega",
    "r$",
)


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().strip()


def conversa_em_andamento(historico_texto: str) -> bool:
    if not historico_texto or historico_texto.strip() == "(primeira mensagem)":
        return False

    linhas = [l for l in historico_texto.split("\n") if l.strip()]
    if len(linhas) > 4:
        return True

    historico = _normalizar(historico_texto)
    return any(indicio in historico for indicio in INDICIOS_ANDAMENTO)


def eh_saudacao_inicial(mensagem: str, historico_texto: str = "") -> bool:
    if conversa_em_andamento(historico_texto):
        return False

    texto = _normalizar(mensagem)
    if not texto:
        return False

    if any(re.search(padrao, texto) for padrao in SAUDACOES_INICIAIS):
        return True

    return eh_conversa_casual(mensagem, historico_texto)


def eh_conversa_casual(mensagem: str, historico_texto: str = "") -> bool:
    if conversa_em_andamento(historico_texto):
        return False

    texto = _normalizar(mensagem)
    if not texto:
        return False

    return any(re.search(padrao, texto) for padrao in CONVERSA_CASUAL)


def _mensagem_tem_confirmacao(mensagem: str) -> bool:
    texto = _normalizar(mensagem).rstrip("!?.,")
    if texto in CONFIRMACOES:
        return True
    return any(re.search(padrao, texto) for padrao in PADROES_CONFIRMACAO_MSG)


def _mensagem_confirmacao_forte(mensagem: str) -> bool:
    texto = _normalizar(mensagem).rstrip("!?.,")
    if texto in CONFIRMACOES_FORTES:
        return True
    return any(re.search(padrao, texto) for padrao in PADROES_CONFIRMACAO_FORTE)


def _mensagem_confirmacao_fraca(mensagem: str) -> bool:
    texto = _normalizar(mensagem).rstrip("!?.,")
    return texto in CONFIRMACOES_FRACAS or bool(
        re.match(r"^(sim|ok|okay|beleza|blz|show|perfeito|certo|isso)$", texto)
    )


def ia_pediu_fechamento(ultima_resposta_ia: str) -> bool:
    """Última mensagem da IA convida a fechar (fechamos? / separo?)."""
    if not ultima_resposta_ia:
        return False
    texto = _normalizar(ultima_resposta_ia)
    if any(re.search(p, texto) for p in PADROES_IA_PEDIU_FECHAMENTO):
        return True
    return "fechamos" in texto or "unidade?" in texto or "separe" in texto


def _historico_tem_negociacao(historico_texto: str) -> bool:
    historico = _normalizar(historico_texto)
    return any(
        sinal in historico
        for sinal in (
            "r$",
            "reservo",
            "pagamento",
            "pix",
            "prefere pagar",
            "endereco",
            "entrega",
            "monitor",
            "mouse",
            "notebook",
            "headset",
            "fone",
            "cabo",
            "produto",
            "separar",
            "preco",
            "fechamos",
            "unidade",
        )
    )


def _ultima_oferta_fechamento_no_historico(historico_texto: str) -> str:
    """Última fala da IA que cotou preço / pediu fechamento (ignora soft pós-venda)."""
    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("IA:"):
            continue
        texto = linha.replace("IA:", "").strip()
        t = _normalizar(texto)
        if "precisa de algo mais" in t and "resumo do pedido" not in t:
            continue
        if "resumo do pedido" in t:
            continue
        if "r$" in t or ia_pediu_fechamento(texto):
            return texto
    return ""


def fechamento_pronto(historico_texto: str, ultima_resposta_ia: str = "") -> bool:
    """Checklist: produto + preço cotados; e (IA pediu fechar OU endereço/pagamento)."""
    nome, preco = _extrair_oferta_ia(historico_texto)
    tem_preco = preco is not None or _extrair_preco_historico(historico_texto) is not None
    tem_produto = bool(nome) or bool(_extrair_nome_produto_historico(historico_texto))
    if not (tem_preco and tem_produto):
        return False

    oferta = ultima_resposta_ia or _ultima_oferta_fechamento_no_historico(historico_texto)
    if ia_pediu_fechamento(oferta):
        return True
    if entrega_ja_informada(historico_texto):
        return True
    if extrair_pagamento(historico_texto) != "a combinar":
        return True
    return False


def resolver_estado_venda(
    historico_texto: str,
    mensagem: str = "",
    ultima_resposta_ia: str = "",
) -> str:
    """Estado da venda atual: nova_venda | pos_venda | fechando | negociando."""
    if cliente_quer_nova_venda(mensagem):
        return "nova_venda"
    if negociacao_nova_apos_fechamento(historico_texto, mensagem):
        historico_venda = historico_desde_ultimo_fechamento(historico_texto)
        if fechamento_pronto(historico_venda, ultima_resposta_ia) and (
            _mensagem_confirmacao_forte(mensagem)
            or (
                _mensagem_confirmacao_fraca(mensagem)
                and ia_pediu_fechamento(ultima_resposta_ia)
            )
        ):
            return "fechando"
        return "negociando"

    soft = bool(ultima_resposta_ia) and (
        "precisa de algo mais" in _normalizar(ultima_resposta_ia)
        and "resumo do pedido" not in _normalizar(ultima_resposta_ia)
    )
    if pedido_ja_encerrado(ultima_resposta_ia, historico_texto) and not soft:
        return "pos_venda"
    if soft and not negociacao_nova_apos_fechamento(historico_texto, mensagem):
        return "pos_venda"

    if fechamento_pronto(historico_texto, ultima_resposta_ia) and (
        _mensagem_confirmacao_forte(mensagem)
        or (
            _mensagem_confirmacao_fraca(mensagem)
            and ia_pediu_fechamento(ultima_resposta_ia)
        )
    ):
        return "fechando"
    return "negociando"


def eh_confirmacao_fechamento(
    mensagem: str,
    historico_texto: str,
    ultima_resposta_ia: str = "",
) -> bool:
    if cliente_agradeceu_pos_venda(mensagem):
        return False

    ultima_norm = _normalizar(ultima_resposta_ia or "")
    soft_pos = bool(ultima_norm) and (
        "precisa de algo mais" in ultima_norm
        and "resumo do pedido" not in ultima_norm
    )
    # Fechamento REAL na última resposta → não fecha de novo
    if ultima_norm and _texto_indica_pedido_encerrado(ultima_resposta_ia) and not soft_pos:
        return False
    # Soft pós-venda só bloqueia se NÃO houver nova negociação
    if soft_pos and not negociacao_nova_apos_fechamento(historico_texto, mensagem):
        return False

    historico_venda = historico_texto
    if negociacao_nova_apos_fechamento(historico_texto, mensagem):
        historico_venda = historico_desde_ultimo_fechamento(historico_texto)

    if not _mensagem_tem_confirmacao(mensagem):
        return False
    if not conversa_em_andamento(historico_venda):
        return False

    # ok/sim/beleza só fecham se a IA pediu fechamento
    if _mensagem_confirmacao_fraca(mensagem) and not _mensagem_confirmacao_forte(mensagem):
        oferta = ultima_resposta_ia
        if soft_pos:
            oferta = _ultima_oferta_fechamento_no_historico(historico_venda)
        if not ia_pediu_fechamento(oferta):
            return False

    if not fechamento_pronto(historico_venda, ultima_resposta_ia if not soft_pos else ""):
        # Soft pós-venda: usa oferta anterior no histórico da venda
        if soft_pos and fechamento_pronto(
            historico_venda, _ultima_oferta_fechamento_no_historico(historico_venda)
        ):
            return _mensagem_confirmacao_forte(mensagem) or (
                _mensagem_confirmacao_fraca(mensagem)
                and ia_pediu_fechamento(
                    _ultima_oferta_fechamento_no_historico(historico_venda)
                )
            )
        return False

    return True


NOMES_IGNORAR = {
    "debito",
    "entrega",
    "frete",
    "pix",
    "cliente",
    "sim",
    "na",
    "no",
    "o",
    "a",
    "vermelha",
    "vermelho",
    "azul",
    "preto",
    "branco",
    "rosa",
    "verde",
    "show",
    "toalha",
    "rosto",
    "banho",
}


def _nome_valido(nome: str) -> bool:
    return _normalizar(nome) not in NOMES_IGNORAR and len(nome) >= 2


def extrair_nome_do_historico(historico_texto: str, pushname: str = "") -> str:
    for linha in historico_texto.split("\n"):
        if not linha.startswith("Cliente:"):
            continue
        texto = linha.replace("Cliente:", "").strip()
        match = re.search(r"me chamo\s+([A-Za-zÀ-ÿ]{2,20})", texto, re.I)
        if match and _nome_valido(match.group(1)):
            return match.group(1).strip().title()

    nomes_ia = []
    for linha in historico_texto.split("\n"):
        if not linha.startswith("Cliente:"):
            continue
        for match in re.finditer(
            r"(?:fechado|perfeito|obrigad[oa]|certo|combinado),\s+([A-Za-zÀ-ÿ]{2,20})",
            linha,
            re.I,
        ):
            if _nome_valido(match.group(1)):
                nomes_ia.append(match.group(1))

    if nomes_ia:
        return nomes_ia[-1].strip().title()

    if pushname:
        return pushname.split()[0]

    return "Cliente"


def _parece_endereco_real(texto: str) -> bool:
    """Evita tratar pergunta de produto antiga como endereço de entrega."""
    t = _normalizar(texto)
    if not t or len(t) < 8:
        return False
    if _eh_pergunta_produto(texto) or "?" in texto:
        return False
    if re.search(
        r"\b(monitor|munitor|mouse|headset|cabo|hdmi|notebook|webcam|produto|"
        r"valor|preco|preço|quanto|qual e|qual é|quero|retirar|retirada|envio)\b",
        t,
    ):
        return False
    if re.search(r"\b(rua|av\.?|avenida|travessa|rodovia|bairro|cep)\b", t):
        return True
    # Número + texto longo só conta se parecer endereço (não pergunta)
    if re.search(r"\d{1,5}", texto) and len(texto) > 20 and "valor" not in t:
        return True
    return False


def extrair_endereco(historico_texto: str) -> str:
    match = re.search(r"📍\s*Entrega:\s*(.+)", historico_texto, re.IGNORECASE)
    if match:
        candidato = match.group(1).strip().split("\n")[0]
        if _parece_endereco_real(candidato):
            return candidato

    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("Cliente:"):
            continue
        texto = linha.replace("Cliente:", "").strip()
        if _eh_dado_contato(texto):
            continue
        if _parece_endereco_real(texto):
            return texto
    return ""


def extrair_preferencia_entrega(historico_texto: str) -> str:
    """Data/preferência de entrega — não confundir com pergunta de produto."""
    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("Cliente:"):
            continue
        texto = linha.replace("Cliente:", "").strip()
        if _eh_dado_contato(texto) or _eh_pergunta_produto(texto) or "?" in texto:
            continue
        t = _normalizar(texto)
        if re.search(
            r"\b(monitor|munitor|mouse|headset|cabo|hdmi|notebook|webcam|valor|preco|quanto)\b",
            t,
        ):
            continue
        if re.search(
            r"\b(entregar|entrega|dia\s+\d{1,2}|no dia\s+\d{1,2}|desse mes|deste mes|"
            r"retirada|retiro|envio)\b",
            texto,
            re.I,
        ):
            return texto
    return ""


def entrega_ja_informada(historico_texto: str) -> bool:
    return bool(extrair_endereco(historico_texto) or extrair_preferencia_entrega(historico_texto))


def ia_ja_pediu_endereco(historico_texto: str) -> bool:
    padroes = (
        r"endereco completo",
        r"endereço completo",
        r"me passa o endereco",
        r"me passa o endereço",
        r"rua.*numero",
        r"rua.*número",
    )
    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("IA:"):
            continue
        texto = _normalizar(linha.replace("IA:", ""))
        if any(re.search(padrao, texto) for padrao in padroes):
            return True
    return False


def resposta_entrega_ja_anotada(nome: str, historico_texto: str) -> str:
    tratamento = nome or "Cliente"
    entrega = extrair_endereco(historico_texto) or extrair_preferencia_entrega(historico_texto)
    pagamento = extrair_pagamento(historico_texto)

    if pagamento and pagamento != "a combinar":
        return (
            f"Perfeito, {tratamento}! Anotei a entrega ({entrega}) e pagamento ({pagamento}). "
            "Posso registrar seu pedido?"
        )

    return (
        f"Anotei, {tratamento}! Entrega: {entrega}. "
        "Me diz como prefere pagar — Pix, débito ou cartão na entrega?"
    )


def _eh_dado_contato(texto: str) -> bool:
    return bool(
        re.search(r"@|\bcpf\b|\d{11}", texto, re.I)
        and not re.search(r"\b(rua|av\.?|avenida)\b", texto, re.I)
    )


def extrair_contato(historico_texto: str) -> str:
    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("Cliente:"):
            continue
        texto = linha.replace("Cliente:", "").strip()
        if _eh_dado_contato(texto):
            return texto
    return ""


def _detectar_pagamento_linha(texto: str) -> str | None:
    t = _normalizar(texto)
    if re.search(r"\bpix\b", t) or "via pix" in t or "por pix" in t or "no pix" in t:
        return "PIX na entrega"
    if re.search(r"\bdebito\b", t):
        return "débito na entrega"
    if re.search(r"\bcredito\b|\bcartao\b|\bcartão\b", t):
        return "cartão de crédito na entrega"
    return None


def extrair_pagamento(
    historico_texto: str,
    mensagem_atual: str = "",
    ultima_resposta_ia: str = "",
) -> str:
    if mensagem_atual:
        pagamento = _detectar_pagamento_linha(mensagem_atual)
        if pagamento:
            return pagamento

    if ultima_resposta_ia and "Resumo do pedido" not in ultima_resposta_ia:
        pagamento = _detectar_pagamento_linha(ultima_resposta_ia)
        if pagamento:
            return pagamento

    linhas = [l for l in historico_texto.split("\n") if l.strip()]

    for linha in reversed(linhas):
        if not linha.startswith("Cliente:"):
            continue
        pagamento = _detectar_pagamento_linha(linha.replace("Cliente:", "").strip())
        if pagamento:
            return pagamento

    for linha in reversed(linhas):
        if not linha.startswith("IA:"):
            continue
        texto = linha.replace("IA:", "").strip()
        if "Resumo do pedido" in texto or "Pagamento:" in texto:
            continue
        pagamento = _detectar_pagamento_linha(texto)
        if pagamento:
            return pagamento

    return "a combinar"


def eh_alteracao_pagamento(
    mensagem: str,
    historico_texto: str,
    ultima_resposta_ia: str = "",
) -> bool:
    if pedido_ja_encerrado(ultima_resposta_ia, historico_texto):
        return False
    if not conversa_em_andamento(historico_texto):
        return False
    if _detectar_pagamento_linha(mensagem):
        return True
    texto = _normalizar(mensagem)
    return _historico_tem_negociacao(historico_texto) and bool(
        re.search(r"\b(pix|pagamento|paguei|debito|credito|cartao)\b", texto)
    )


def _texto_indica_pedido_encerrado(texto: str) -> bool:
    t = _normalizar(texto)
    if not t:
        return False
    marcadores = (
        "pedido registrado",
        "pedido ja esta registrado",
        "resumo do pedido",
        "fechado,",
        "precisa de algo mais",
    )
    if any(m in t for m in marcadores):
        return True
    return bool(re.search(r"pedido\s*#wa-", t))


def pedido_ja_encerrado(ultima_resposta_ia: str, historico_texto: str = "") -> bool:
    if ultima_resposta_ia and _texto_indica_pedido_encerrado(ultima_resposta_ia):
        return True

    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("IA:"):
            continue
        if _texto_indica_pedido_encerrado(linha):
            return True

    return False


def _mensagem_so_acolhe_pos_venda(mensagem: str) -> bool:
    texto = _normalizar(mensagem).rstrip("!?.,")
    return texto in (
        "ok",
        "okay",
        "beleza",
        "blz",
        "show",
        "certo",
        "isso",
        "sim",
        "perfeito",
        "combinado",
    )


def cliente_quer_nova_venda(mensagem: str) -> bool:
    """Intenção explícita de abrir outra venda (não é busca de produto)."""
    texto = _normalizar(mensagem).rstrip("!?.,")
    padroes = (
        r"\b(quero|preciso|vamos|bora)\s+(fazer\s+)?(outro|mais\s+um|um\s+novo|novo)\s+pedido\b",
        r"\b(fazer|abrir|iniciar|comecar|começar)\s+(outro|mais\s+um|um\s+novo|novo)\s+pedido\b",
        r"\b(outro|mais\s+um|novo)\s+pedido\b",
        r"\b(nova|outra)\s+venda\b",
        r"\b(quero|preciso)\s+(comprar|pedir)\s+(de\s+novo|novamente|mais)\b",
        r"\bfazer\s+(uma\s+)?nova\s+compra\b",
        r"\bmais\s+um\s+pedido\b",
        r"\bquero\s+pedir\s+(de\s+novo|novamente|outro)\b",
    )
    return any(re.search(p, texto) for p in padroes)


def cliente_quer_novo_atendimento(mensagem: str) -> bool:
    """Sai do modo pós-venda: nova venda explícita ou interesse em comprar/ver catálogo."""
    if cliente_quer_nova_venda(mensagem):
        return True
    texto = _normalizar(mensagem)
    indicadores = (
        "quero",
        "preciso",
        "comprar",
        "catalogo",
        "produto",
        "tem ",
        "mostra",
        "preco",
        "novo pedido",
        "outro",
        "mais um",
    )
    return any(ind in texto for ind in indicadores)


def historico_desde_ultimo_fechamento(historico_texto: str) -> str:
    """Corta só após fechamento REAL (resumo), não após mensagem soft de pós-venda."""
    linhas = historico_texto.split("\n")
    inicio = 0
    for indice, linha in enumerate(linhas):
        if not linha.startswith("IA:"):
            continue
        texto = linha.lower()
        # Soft pós-venda: "já está registrado" / "precisa de algo mais" — NÃO corta
        if "precisa de algo mais" in texto and "resumo do pedido" not in texto:
            continue
        if "resumo do pedido" in texto or "pedido #" in texto:
            inicio = indice + 1
            continue
        # Fechamento completo: "Pedido registrado!" com produto no resumo
        if "pedido registrado" in texto and (
            "resumo" in texto or "📦" in linha or "total" in texto
        ):
            inicio = indice + 1
    if inicio > 0:
        return "\n".join(linhas[inicio:])
    return historico_texto


def negociacao_nova_apos_fechamento(historico_texto: str, mensagem: str = "") -> bool:
    if cliente_quer_nova_venda(mensagem):
        return True
    if cliente_quer_novo_atendimento(mensagem) and not _mensagem_so_acolhe_pos_venda(mensagem):
        # "quero headset" etc. — só conta se já houve fechamento antes
        if pedido_ja_encerrado("", historico_texto):
            return True
    trecho = historico_desde_ultimo_fechamento(historico_texto)
    if trecho == historico_texto:
        return False
    texto = _normalizar(trecho)
    return bool(re.search(r"\b(quero|preciso|comprar|outro|novo|mais|headset|cabo|monitor)\b", texto))


def resposta_pos_fechamento(nome: str = "") -> str:
    tratamento = nome or "Cliente"
    return (
        f"Oi, {tratamento}! Seu pedido já está registrado e nossa equipe "
        "finaliza com você em breve. Precisa de algo mais?"
    )


PADROES_PAGAMENTO_INFORMADO = (
    r"\bpaguei\b",
    r"\bpagamento feito\b",
    r"\bja paguei\b",
    r"\bjá paguei\b",
    r"\btransferi\b",
    r"\bcomprovante\b",
    r"\benviei o pix\b",
    r"\bfiz o pix\b",
    r"\bfiz pagamento\b",
)

PADROES_CONSULTA_STATUS = (
    r"\bstatus\b",
    r"\bconfirmad",
    r"\bpendente\b",
    r"\bpago ou pendente\b",
    r"\bja estava pago\b",
    r"\bjá estava pago\b",
    r"\bfoi pago\b",
    r"\bpagou\b",
    r"\besta pago\b",
    r"\bestá pago\b",
)


def cliente_informou_pagamento(mensagem: str) -> bool:
    texto = _normalizar(mensagem)
    return any(re.search(padrao, texto) for padrao in PADROES_PAGAMENTO_INFORMADO)


def cliente_pergunta_status_pedido(mensagem: str) -> bool:
    texto = _normalizar(mensagem)
    if any(re.search(padrao, texto) for padrao in PADROES_CONSULTA_STATUS):
        return True
    return bool(re.search(r"\bpago\b", texto) and re.search(r"\b(pendente|status|pedido)\b", texto))


def cliente_agradeceu_pos_venda(mensagem: str) -> bool:
    texto = _normalizar(mensagem).rstrip("!?.,")
    if re.search(r"\bobrigad", texto):
        return True
    return bool(re.match(r"^(valeu|obg|brigadao|brigada|thanks)\b", texto))


def pagamento_ja_informado_no_historico(historico_texto: str) -> bool:
    apos_fechamento = False
    for linha in historico_texto.split("\n"):
        if linha.startswith("IA:") and "pedido registrado" in linha.lower():
            apos_fechamento = True
            continue
        if apos_fechamento and linha.startswith("Cliente:"):
            msg = linha.replace("Cliente:", "").strip()
            if cliente_informou_pagamento(msg):
                return True
    return False


def _extrair_pagamento_do_resumo(historico_texto: str) -> str:
    match = re.search(r"Pagamento:\s*(.+)", historico_texto, re.IGNORECASE)
    if match:
        return match.group(1).strip().split("\n")[0]
    return extrair_pagamento(historico_texto)


def resposta_comprovante_ou_pagamento(
    nome: str,
    historico_texto: str,
    mensagem_atual: str = "",
) -> str:
    tratamento = nome or "Cliente"
    pagamento = _extrair_pagamento_do_resumo(historico_texto)
    pagamento_lower = (pagamento or "").lower()
    ja_informou = pagamento_ja_informado_no_historico(historico_texto)

    if ja_informou and not cliente_informou_pagamento(mensagem_atual):
        return resposta_status_pedido(tratamento, historico_texto)

    if "na entrega" in pagamento_lower:
        return (
            f"Perfeito, {tratamento}! Anotei aqui. "
            f"Pagamento combinado: {pagamento}. "
            "Seu pedido está confirmado e segue para separação — te avisamos sobre a entrega."
        )

    return (
        f"Recebi, {tratamento}! Pagamento informado — nossa equipe confirma em breve. "
        "Se ainda não enviou, pode mandar o comprovante aqui no chat."
    )


def resposta_status_pedido(nome: str, historico_texto: str) -> str:
    tratamento = nome or "Cliente"
    pagamento = _extrair_pagamento_do_resumo(historico_texto)
    pagamento_lower = (pagamento or "").lower()
    pago_informado = pagamento_ja_informado_no_historico(historico_texto)

    if pago_informado:
        if "na entrega" in pagamento_lower:
            return (
                f"{tratamento}, seu pedido está confirmado. "
                f"Pagamento: {pagamento}. Status: aguardando entrega — equipe separando."
            )
        return (
            f"{tratamento}, registramos seu pagamento. "
            "Status: em confirmação pela equipe — te avisamos assim que validarmos."
        )

    if "na entrega" in pagamento_lower:
        return (
            f"{tratamento}, pedido confirmado. "
            f"Pagamento: {pagamento}. Status: aguardando entrega."
        )

    return (
        f"{tratamento}, pedido registrado. "
        "Status: pagamento pendente — envie o comprovante aqui quando pagar."
    )


def resposta_agradecimento_pos_venda(nome: str = "") -> str:
    tratamento = nome or "Cliente"
    return f"Por nada, {tratamento}! Qualquer coisa estamos por aqui. 😊"


def resolver_resposta_pos_pedido(
    mensagem: str,
    historico_texto: str,
    ultima_resposta_ia: str,
    nome: str,
) -> str | None:
    from services.vendas.respostas import cliente_quer_ver_catalogo

    if cliente_quer_ver_catalogo(mensagem, ultima_resposta_ia):
        return None
    if cliente_quer_novo_atendimento(mensagem):
        return None

    # Já há negociação nova após o último fechamento — não engolir "fechamos"
    # com a mensagem genérica de pós-venda do pedido antigo.
    if negociacao_nova_apos_fechamento(historico_texto, mensagem):
        return None

    if not pedido_ja_encerrado(ultima_resposta_ia, historico_texto):
        return None

    if cliente_informou_pagamento(mensagem):
        return resposta_comprovante_ou_pagamento(nome, historico_texto, mensagem)

    if cliente_pergunta_status_pedido(mensagem):
        return resposta_status_pedido(nome, historico_texto)

    if cliente_agradeceu_pos_venda(mensagem):
        return resposta_agradecimento_pos_venda(nome)

    if _mensagem_so_acolhe_pos_venda(mensagem):
        return resposta_agradecimento_pos_venda(nome)

    if _texto_indica_pedido_encerrado(ultima_resposta_ia):
        return resposta_agradecimento_pos_venda(nome)

    return resposta_pos_fechamento(nome)


def historico_recente(historico_texto: str, max_linhas: int = 24) -> str:
    linhas = [l for l in historico_texto.split("\n") if l.strip()]
    if len(linhas) <= max_linhas:
        return historico_texto
    return "\n".join(linhas[-max_linhas:])


def _parse_preco(valor: str) -> float | None:
    """Aceita 249.9, 249,90, 3.499, 1.249,90 e 1,249.90.

    BR milhar sem centavos (3.499) vira 3499; decimal curto (249.9) permanece.
    """
    if valor in (None, ""):
        return None
    texto = str(valor).strip().rstrip(".,;:!?)")
    if not texto:
        return None
    try:
        if "," in texto and "." in texto:
            # BR: 1.249,90  |  US: 1,249.90
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                texto = texto.replace(",", "")
        elif "," in texto:
            # 249,9 ou 249,90
            texto = texto.replace(",", ".")
        elif "." in texto:
            # 249.9 / 249.90 = decimal; 3.499 ou 1.249 = milhar BR (3 dígitos)
            partes = texto.split(".")
            if (
                len(partes) >= 2
                and all(p.isdigit() for p in partes)
                and all(len(p) == 3 for p in partes[1:])
            ):
                texto = "".join(partes)
            # senão: decimal (1–2 casas) — manter
        return float(texto)
    except (TypeError, ValueError):
        return None


def _extrair_oferta_ia(historico_texto: str) -> tuple[str, float | None]:
    """Última oferta explícita da IA no histórico (nome + preço)."""
    padroes = (
        r"(?:reservo|separo|temos|olha|segue|fica)[^\n]{0,40}?\s*(?:1x\s*)?(.+?)\s+por\s+r\$\s*([\d]+(?:[.,]\d+)?)",
        r"(.+?)\s*[—–-]\s*r\$\s*([\d]+(?:[.,]\d+)?)",
        r"(.+?)\s+por\s+r\$\s*([\d]+(?:[.,]\d+)?)",
        r"(.+?)\s+sai\s+por\s+r\$\s*([\d]+(?:[.,]\d+)?)",
        r"(.+?)\s+fica\s+(?:por\s+)?r\$\s*([\d]+(?:[.,]\d+)?)",
        # "Notebook Intel i5 (R$ 3.499)" / "Notebook Intel i5 R$ 3.499"
        r"(.+?)\s*\(?\s*r\$\s*([\d]+(?:[.,]\d+)?)\s*\)?",
        r"preco\s+(?:do|da|de)\s+(.+?)\s*[:=]?\s*r\$\s*([\d]+(?:[.,]\d+)?)",
        r"\b(headset\s+gamer|cabo\s+hdmi(?:\s*\d+m)?|hd\s+externo(?:\s*\d+\s*tb)?|"
        r"monitor\s+led(?:\s*\d+)?|mouse\s+[^\n,]{0,30}|teclado\s+[^\n,]{0,30}|"
        r"notebook\s+[^\n,]{0,40}|hub\s+usb[^\n,]{0,20}|ssd\s+[^\n,]{0,20}|"
        r"webcam\s+[^\n,]{0,30})\b[^\n]{0,40}?r\$\s*([\d]+(?:[.,]\d+)?)",
    )
    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("IA:"):
            continue
        texto = linha.replace("IA:", "").strip()
        t = _normalizar(texto)
        if "precisa de algo mais" in t and "resumo do pedido" not in t:
            continue
        for padrao in padroes:
            match = re.search(padrao, texto, re.I)
            if not match:
                continue
            nome = re.sub(r"^[\W\d]+", "", match.group(1).strip(" .,!-"))
            # Evita capturar frases longas demais
            if "—" in nome:
                nome = nome.split("—")[0].strip()
            if 2 < len(nome) < 80:
                return nome, _parse_preco(match.group(2))
    return "", None


def _buscar_produto_por_preco(preco: float) -> dict | None:
    from services.supabase_service import buscar_produtos

    for produto in buscar_produtos():
        bruto = produto.get("preco") or produto.get("preco_tabela")
        try:
            valor = _parse_preco(str(bruto))
            if valor is not None and abs(valor - preco) < 0.05:
                return produto
        except (TypeError, ValueError):
            continue
    return None


def _linhas_cliente_recentes(historico_texto: str, limite: int = 6) -> list[str]:
    linhas = [
        linha.replace("Cliente:", "").strip()
        for linha in historico_texto.split("\n")
        if linha.startswith("Cliente:")
    ]
    return linhas[-limite:]


def _eh_pergunta_produto(texto: str) -> bool:
    t = _normalizar(texto)
    if "?" in texto:
        return True
    indicadores = (
        "valor", "preco", "preço", "quanto", "custa", "tem ", "quero", "preciso",
        "monitor", "mouse", "teclado", "notebook", "cabo", "fone", "produto",
    )
    return any(ind in t for ind in indicadores) and not re.search(
        r"\b(rua|av\.?|avenida|travessa|rodovia|cep)\b", t, re.I
    )


def _extrair_preco_historico(historico_texto: str) -> float | None:
    nome_oferta, preco_oferta = _extrair_oferta_ia(historico_texto)
    if preco_oferta is not None:
        return preco_oferta
    precos = re.findall(r"r\$\s*([\d.,]+)", historico_texto.lower())
    if not precos:
        return None
    return _parse_preco(precos[-1])


def _extrair_nome_produto_historico(historico_texto: str) -> str:
    nome_oferta, _ = _extrair_oferta_ia(historico_texto)
    if nome_oferta:
        return nome_oferta

    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("IA:"):
            continue
        texto = linha.replace("IA:", "")
        match = re.search(r"\b(LT\d+|RS\d+)\b", texto, re.I)
        if match:
            return f"Caixa de Som Bluetooth {match.group(1).upper()}"
        match = re.search(r"caixa de som[^.\n]{0,40}", texto, re.I)
        if match:
            return match.group(0).strip().title()

    historico = _normalizar(historico_texto)
    if "lt800" in historico:
        return "Caixa de Som Bluetooth LT800"
    return ""


def _buscar_produto_do_historico(historico_texto: str) -> dict | None:
    nome_oferta, preco_oferta = _extrair_oferta_ia(historico_texto)
    if preco_oferta is not None:
        por_preco = _buscar_produto_por_preco(preco_oferta)
        if por_preco:
            return por_preco

    from services.produtos_service import buscar_produtos_para_atendimento

    if nome_oferta:
        resultado = buscar_produtos_para_atendimento(nome_oferta, historico_texto)
        if resultado.get("produtos"):
            return resultado["produtos"][0]

    preco_hist = _extrair_preco_historico(historico_texto)
    if preco_hist is not None:
        por_preco = _buscar_produto_por_preco(preco_hist)
        if por_preco:
            return por_preco

    historico = _normalizar(historico_texto)
    termos = []
    for termo in re.findall(r"\b(lt\d+|rs\d+|hmaston)\b", historico):
        if termo not in termos:
            termos.append(termo)

    for termo in reversed(termos):
        resultado = buscar_produtos_para_atendimento(termo)
        if resultado.get("produtos"):
            return resultado["produtos"][0]

    linhas_cliente = [
        linha for linha in _linhas_cliente_recentes(historico_texto)
        if not _eh_pergunta_produto(linha) and not _detectar_pagamento_linha(linha)
    ]
    if linhas_cliente:
        busca = " ".join(linhas_cliente[-3:])
        resultado = buscar_produtos_para_atendimento(busca, historico_texto)
        if resultado.get("produtos"):
            return resultado["produtos"][0]

    return None


def _formatar_preco(preco) -> str | None:
    if preco in (None, ""):
        return None
    if isinstance(preco, str):
        parsed = _parse_preco(preco)
        if parsed is None:
            return preco
        preco = parsed
    try:
        return f"R$ {float(preco):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(preco)


def resposta_fechamento_pedido(
    historico_texto: str,
    pushname: str = "",
    frete_estimado: float = 0,
    mensagem_atual: str = "",
    ultima_resposta_ia: str = "",
    mercos_pedido: dict | None = None,
) -> str:
    nome = extrair_nome_do_historico(historico_texto, pushname)
    produto = _buscar_produto_do_historico(historico_texto) or {}
    preco_historico = _extrair_preco_historico(historico_texto)
    nome_produto = (
        _extrair_nome_produto_historico(historico_texto)
        or produto.get("nome")
        or "produto"
    )
    preco_bruto = (
        preco_historico
        if preco_historico is not None
        else produto.get("preco") or produto.get("preco_tabela")
    )
    preco = _parse_preco(str(preco_bruto)) if preco_bruto not in (None, "") else None
    if preco is None and isinstance(preco_bruto, (int, float)):
        preco = float(preco_bruto)
    preco_fmt = _formatar_preco(preco)

    endereco = extrair_endereco(historico_texto)
    contato = extrair_contato(historico_texto)
    pagamento = extrair_pagamento(
        historico_texto,
        mensagem_atual=mensagem_atual,
        ultima_resposta_ia=ultima_resposta_ia,
    )

    # Se nome bate com catálogo e preço do histórico diverge, usa o do catálogo
    preco_cat = produto.get("preco") or produto.get("preco_tabela")
    if preco_cat not in (None, "") and produto.get("nome"):
        preco_cat_f = _parse_preco(str(preco_cat))
        nome_cat = _normalizar(str(produto.get("nome")))
        nome_hist = _normalizar(nome_produto)
        nomes_batem = bool(nome_cat and nome_hist) and (
            nome_cat in nome_hist or nome_hist in nome_cat
        )
        if preco_cat_f is not None and nomes_batem:
            if preco is None or abs(preco_cat_f - float(preco)) > 1:
                preco = preco_cat_f
                preco_fmt = _formatar_preco(preco)

    linhas = [f"Fechado, {nome}! Resumo do pedido:"]
    linhas.append(f"📦 {nome_produto}")

    if preco_fmt:
        linhas.append(f"💰 Produto: {preco_fmt}")

    if frete_estimado > 0 and preco is not None:
        try:
            valor_produto = float(preco)
            total = valor_produto + frete_estimado
            linhas.append(f"🚚 Frete estimado: R$ {frete_estimado:.2f}".replace(".", ","))
            linhas.append(f"✅ Total: R$ {total:.2f}".replace(".", ","))
        except (TypeError, ValueError):
            linhas.append(f"🚚 Frete estimado: R$ {frete_estimado:.2f}".replace(".", ","))
    elif preco_fmt:
        linhas.append(f"✅ Total do produto: {preco_fmt}")
        linhas.append("🚚 Frete: nossa equipe confirma o valor com você.")

    if endereco and _parece_endereco_real(endereco):
        linhas.append(f"📍 Entrega: {endereco}")
    elif contato and not _eh_pergunta_produto(contato):
        linhas.append(f"📋 Dados: {contato}")

    if pagamento and pagamento != "a combinar":
        linhas.append(f"💳 Pagamento: {pagamento}")

    from services.xnamai_script import enriquecer_resumo_fechamento

    linhas = enriquecer_resumo_fechamento(linhas, historico_texto, mensagem_atual)

    if pagamento and "pix" in pagamento.lower():
        try:
            valor_pix = float(str(preco).replace(",", ".")) if preco is not None else None
            if frete_estimado > 0 and valor_pix is not None:
                valor_pix += frete_estimado
        except (TypeError, ValueError):
            valor_pix = None
        linhas.append(montar_mensagem_pix_exemplo(valor=valor_pix))

    if mercos_pedido and mercos_pedido.get("pedido_id"):
        numero = mercos_pedido.get("numero") or mercos_pedido["pedido_id"]
        if isinstance(numero, float) and numero.is_integer():
            numero = int(numero)
        linhas.append(f"🧾 Pedido #{numero}")

    linhas.append(
        "Pedido registrado! Em breve nossa equipe finaliza com você "
        "(separação após confirmação do pagamento)."
    )
    return "\n".join(linhas)
