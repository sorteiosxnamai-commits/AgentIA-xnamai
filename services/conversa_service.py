import re
import unicodedata

from services.pix_service import montar_mensagem_pix_exemplo
from services.produtos_service import buscar_produtos_para_atendimento

CONFIRMACOES = (
    "beleza",
    "blz",
    "ok",
    "okay",
    "show",
    "perfeito",
    "pode ser",
    "isso",
    "fechado",
    "confirmo",
    "sim",
    "certo",
    "combinado",
    "fechou",
)

PADROES_CONFIRMACAO_MSG = (
    r"\bfechou\b",
    r"\bfechado\b",
    r"\bconfirmo\b",
    r"\bcombinado\b",
    r"\bpaguei\b",
    r"\bfiz pagamento\b",
    r"\bpagamento\b",
    r"\bpix\b",
    r"\bobrigad",
    r"\bsim\b",
    r"\bok\b",
    r"\bbeleza\b",
    r"\bshow\b",
    r"\bperfeito\b",
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
            "produto",
            "separar",
            "preco",
        )
    )


def eh_confirmacao_fechamento(
    mensagem: str,
    historico_texto: str,
    ultima_resposta_ia: str = "",
) -> bool:
    if not _mensagem_tem_confirmacao(mensagem):
        return False
    if not conversa_em_andamento(historico_texto):
        return False
    if _historico_tem_negociacao(historico_texto):
        return True

    historico = _normalizar(historico_texto)
    if any(indicio in historico for indicio in INDICIOS_FECHAMENTO):
        return True

    ultima = _normalizar(ultima_resposta_ia)
    promessas = (
        "total com frete",
        "te passo o total",
        "vou calcular",
        "te mando o total",
        "valor total",
        "prefere pagar",
        "endereco de entrega",
        "pra fechar",
        "reservo",
    )
    return any(p in ultima for p in promessas)


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


def extrair_endereco(historico_texto: str) -> str:
    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("Cliente:"):
            continue
        texto = linha.replace("Cliente:", "").strip()
        if _eh_dado_contato(texto):
            continue
        if _eh_pergunta_produto(texto):
            continue
        if re.search(r"\b(rua|av\.?|avenida|travessa|rodovia)\b", texto, re.I):
            return texto
        if re.search(r"\d{1,5}", texto) and len(texto) > 15:
            return texto
    return ""


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


def pedido_ja_encerrado(ultima_resposta_ia: str, historico_texto: str = "") -> bool:
    if ultima_resposta_ia and "pedido registrado" in ultima_resposta_ia.lower():
        return True

    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("IA:"):
            continue
        if "pedido registrado" in linha.lower():
            return True

    return False


def cliente_quer_novo_atendimento(mensagem: str) -> bool:
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
    )
    return any(ind in texto for ind in indicadores)


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
    if not pedido_ja_encerrado(ultima_resposta_ia, historico_texto):
        return None
    if cliente_quer_novo_atendimento(mensagem):
        return None

    if cliente_informou_pagamento(mensagem):
        return resposta_comprovante_ou_pagamento(nome, historico_texto, mensagem)

    if cliente_pergunta_status_pedido(mensagem):
        return resposta_status_pedido(nome, historico_texto)

    if cliente_agradeceu_pos_venda(mensagem):
        return resposta_agradecimento_pos_venda(nome)

    return resposta_pos_fechamento(nome)


def historico_recente(historico_texto: str, max_linhas: int = 24) -> str:
    linhas = [l for l in historico_texto.split("\n") if l.strip()]
    if len(linhas) <= max_linhas:
        return historico_texto
    return "\n".join(linhas[-max_linhas:])


def _parse_preco(valor: str) -> float | None:
    if valor in (None, ""):
        return None
    try:
        return float(str(valor).replace(".", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _extrair_oferta_ia(historico_texto: str) -> tuple[str, float | None]:
    """Última oferta explícita da IA no histórico (nome + preço)."""
    padroes = (
        r"(?:reservo|separo|temos|olha|segue|fica)[^\n]{0,30}?\s*(?:1x\s*)?(.+?)\s+por\s+r\$\s*([\d.,]+)",
        r"(.+?)\s*[—–-]\s*r\$\s*([\d.,]+)",
        r"(.+?)\s+por\s+r\$\s*([\d.,]+)",
    )
    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("IA:"):
            continue
        texto = linha.replace("IA:", "").strip()
        for padrao in padroes:
            match = re.search(padrao, texto, re.I)
            if not match:
                continue
            nome = re.sub(r"^[\W\d]+", "", match.group(1).strip(" .,!-"))
            if 2 < len(nome) < 80:
                return nome, _parse_preco(match.group(2))
    return "", None


def _buscar_produto_por_preco(preco: float) -> dict | None:
    from services.supabase_service import buscar_produtos

    for produto in buscar_produtos():
        bruto = produto.get("preco") or produto.get("preco_tabela")
        try:
            if abs(float(bruto) - preco) < 0.05:
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
        preco = preco.replace(",", ".")
        try:
            preco = float(preco)
        except ValueError:
            return preco
    return f"R$ {preco:.2f}".replace(".", ",")


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
    preco = preco_historico if preco_historico is not None else produto.get("preco")
    preco_fmt = _formatar_preco(preco)

    endereco = extrair_endereco(historico_texto)
    contato = extrair_contato(historico_texto)
    pagamento = extrair_pagamento(
        historico_texto,
        mensagem_atual=mensagem_atual,
        ultima_resposta_ia=ultima_resposta_ia,
    )

    linhas = [f"Fechado, {nome}! Resumo do pedido:"]
    linhas.append(f"📦 {nome_produto}")

    if preco_fmt:
        linhas.append(f"💰 Produto: {preco_fmt}")

    if frete_estimado > 0 and preco is not None:
        try:
            valor_produto = float(str(preco).replace(",", "."))
            total = valor_produto + frete_estimado
            linhas.append(f"🚚 Frete estimado: R$ {frete_estimado:.2f}".replace(".", ","))
            linhas.append(f"✅ Total: R$ {total:.2f}".replace(".", ","))
        except (TypeError, ValueError):
            linhas.append(f"🚚 Frete estimado: R$ {frete_estimado:.2f}".replace(".", ","))
    elif preco_fmt:
        linhas.append(f"✅ Total do produto: {preco_fmt}")
        linhas.append("🚚 Frete: nossa equipe confirma o valor com você.")

    if endereco:
        linhas.append(f"📍 Entrega: {endereco}")
    elif contato:
        linhas.append(f"📋 Dados: {contato}")

    if pagamento:
        linhas.append(f"💳 Pagamento: {pagamento}")

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
        linhas.append(f"🧾 Pedido Mercos #{numero}")

    linhas.append("Pedido registrado! Em breve nossa equipe finaliza com você.")
    return "\n".join(linhas)
