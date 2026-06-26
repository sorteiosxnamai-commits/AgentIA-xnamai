import re
import unicodedata

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

SAUDACOES_INICIAIS = (
    r"^(oi|ola|olá|hey|eae|e ai|eai|bom dia|boa tarde|boa noite|hello|hi)\b",
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
    "separar",
    "fechar",
    "na entrega",
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

    return any(re.search(padrao, texto) for padrao in SAUDACOES_INICIAIS)


def eh_confirmacao_fechamento(
    mensagem: str,
    historico_texto: str,
    ultima_resposta_ia: str = "",
) -> bool:
    texto = _normalizar(mensagem).rstrip("!?.")
    if texto not in CONFIRMACOES:
        return False

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
    "o",
    "a",
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

    nomes_ia = re.findall(
        r"(?:fechado|perfeito|show|obrigad[oa]|certo|combinado),?\s+([A-Za-zÀ-ÿ]{2,20})",
        historico_texto,
        re.I,
    )
    nomes_validos = [n for n in nomes_ia if _nome_valido(n)]
    if nomes_validos:
        return nomes_validos[-1].strip().title()

    if pushname:
        return pushname.split()[0]

    return "Cliente"


def extrair_endereco(historico_texto: str) -> str:
    for linha in reversed(historico_texto.split("\n")):
        if not linha.startswith("Cliente:"):
            continue
        texto = linha.replace("Cliente:", "").strip()
        if re.search(r"\b(rua|av\.?|avenida|travessa|rodovia)\b", texto, re.I):
            return texto
        if re.search(r"\d{1,5}", texto) and len(texto) > 15:
            return texto
    return ""


def extrair_pagamento(historico_texto: str) -> str:
    historico = _normalizar(historico_texto)
    if "debito" in historico or "débito" in historico.lower():
        return "débito na entrega"
    if "pix" in historico:
        return "PIX"
    if "credito" in historico or "crédito" in historico.lower():
        return "cartão de crédito"
    return "a combinar"


def _extrair_preco_historico(historico_texto: str) -> float | None:
    precos = re.findall(r"r\$\s*([\d.,]+)", historico_texto.lower())
    if not precos:
        return None
    valor = precos[-1].replace(".", "").replace(",", ".")
    try:
        return float(valor)
    except ValueError:
        return None


def _extrair_nome_produto_historico(historico_texto: str) -> str:
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
    historico = _normalizar(historico_texto)
    termos = []
    for termo in re.findall(r"\b(lt\d+|rs\d+|hmaston)\b", historico):
        if termo not in termos:
            termos.append(termo)

    for termo in reversed(termos):
        resultado = buscar_produtos_para_atendimento(termo)
        if resultado.get("produtos"):
            return resultado["produtos"][0]

    resultado = buscar_produtos_para_atendimento(historico_texto)
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
    pagamento = extrair_pagamento(historico_texto)

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

    if pagamento:
        linhas.append(f"💳 Pagamento: {pagamento}")

    linhas.append("Pedido registrado! Em breve nossa equipe finaliza com você.")
    return "\n".join(linhas)
