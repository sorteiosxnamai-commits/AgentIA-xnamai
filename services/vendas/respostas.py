import re
import unicodedata

from services.mercos_service import montar_catalogo_texto

TERMOS_IGNORAR_PEDIDO = {
    "vermelha", "vermelho", "azul", "preto", "branco", "rosa", "verde", "amarelo",
    "linda", "lindo", "bonita", "bonito", "fica", "ficou", "show", "perfeito",
    "rosto", "banho", "conjunto", "queria", "quero", "pra", "pro",
    "sim", "nao", "não", "ok", "tem", "catalogo", "catálogo", "nada",
    "disponivel", "disponível", "hoje", "voce", "voces", "vocês", "claro", "pode",
    "retirar", "retirada", "retiro", "envio", "enviar", "frete", "sei",
}


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().strip()


def _termos_produto(termos: list | None) -> list[str]:
    if not termos:
        return []
    return [
        t for t in termos
        if t not in TERMOS_IGNORAR_PEDIDO and len(t) >= 3
    ]


def ia_ofereceu_catalogo(ultima_resposta_ia: str) -> bool:
    if not ultima_resposta_ia:
        return False
    ultima = _normalizar(ultima_resposta_ia)
    indicadores = (
        "mostrar o que temos",
        "mostrar o que tem",
        "te mostre",
        "te mostro",
        "ver o que temos",
        "o que temos dispon",
        "nosso catálogo",
        "nosso catalogo",
        "quer que eu te mostre",
    )
    return any(ind in ultima for ind in indicadores)


def cliente_quer_ver_catalogo(mensagem: str, ultima_resposta_ia: str = "") -> bool:
    texto = _normalizar(mensagem).rstrip("!?.,")

    if ia_ofereceu_catalogo(ultima_resposta_ia):
        confirmacoes = (
            r"^(sim|quero sim|quero|claro|pode|ok|show|beleza|por favor)$",
            r"^quero ver$",
            r"^pode mostrar$",
            r"^manda$",
            r"^mostra$",
            r"^tem\??$",
        )
        if any(re.match(p, texto) for p in confirmacoes):
            return True

    padroes_diretos = (
        r"mostra(r)? (o )?(catalogo|catálogo|produtos)",
        r"o que\s+.*(voce|voces|vocês|vc|vcs)\s+tem",
        r"quais produtos",
        r"me mostra",
        r"ver (o )?(catalogo|catálogo|produtos)",
        r"produtos?\s+para\s+vender",
        r"mais\s+de\s+produtos",
        r"o\s+que\s+mais",
    )
    return any(re.search(p, texto) for p in padroes_diretos)


def _fmt_preco_item(produto: dict) -> str:
    preco = produto.get("preco")
    if preco in (None, ""):
        preco = produto.get("preco_tabela")
    if preco in (None, ""):
        return ""
    try:
        return f"R$ {float(preco):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return f"R$ {preco}"


def cliente_perguntou_preco(mensagem: str) -> bool:
    """Pergunta genérica de preço — usa o produto em discussão no histórico."""
    t = _normalizar(mensagem).rstrip("!?.,")
    if not t:
        return False
    padroes = (
        r"^(qual|quanto)\s+(e|é|eh)?\s*(o\s+)?(valor|preco|preço)$",
        r"^(qual|quanto)\s+(e|é|eh)?\s*(o\s+)?(valor|preco|preço)\s+(dele|dela|disso|desse|dessa)?$",
        r"^quanto\s+(custa|fica|sai)$",
        r"^qual\s+o\s+valor$",
        r"^e\s+o\s+valor\??$",
        r"^valor\??$",
        r"^preco\??$",
        r"^preço\??$",
    )
    return any(re.match(p, t) for p in padroes)


def resposta_preco_em_discussao(
    historico_texto: str,
    nome_cliente: str = "",
    produtos: list | None = None,
) -> str | None:
    """Responde preço do item em discussão; None se não houver contexto."""
    from services.conversa_service import (
        _extrair_oferta_ia,
        _extrair_preco_historico,
        _formatar_preco,
        _parse_preco,
    )

    nome = nome_cliente or "Cliente"
    # Prioriza a última oferta da IA (evita trocar Headset por outro item de mesmo preço)
    nome_oferta, preco_oferta = _extrair_oferta_ia(historico_texto)
    nome_prod = nome_oferta or ""
    preco = preco_oferta

    if produtos and produtos[0].get("nome") and not nome_prod:
        nome_prod = str(produtos[0].get("nome") or "")
        bruto = produtos[0].get("preco") or produtos[0].get("preco_tabela")
        if bruto not in (None, "") and preco is None:
            preco = _parse_preco(str(bruto))

    if preco is None:
        preco = _extrair_preco_historico(historico_texto)

    preco_fmt = _formatar_preco(preco) if preco is not None else None
    if nome_prod and preco_fmt:
        return (
            f"{nome}, o {nome_prod} fica {preco_fmt}. "
            "Quer que eu feche 1 unidade pra você?"
        )
    if preco_fmt:
        return f"{nome}, fica {preco_fmt}. Quer fechar?"
    if nome_prod:
        return (
            f"{nome}, sobre o {nome_prod}: me confirma o modelo/código "
            "que eu te passo o valor certinho?"
        )
    return (
        f"{nome}, me diz qual produto você quer o valor "
        "(ex.: headset, cabo HDMI, monitor) que eu te passo."
    )


def resposta_fora_catalogo(
    nome_cliente: str = "",
    termos: list | None = None,
    amostra: list | None = None,
) -> str:
    """Quando o cliente pede algo que a loja não vende."""
    nome = nome_cliente or "Cliente"
    termos_produto = _termos_produto(termos)
    pedido = " ".join(termos_produto) if termos_produto else "isso"

    if amostra:
        exemplos = [p.get("nome", "") for p in amostra[:3] if p.get("nome")]
        if len(exemplos) == 1:
            linha_cat = f"Temos {exemplos[0]}, por exemplo."
        elif exemplos:
            linha_cat = f"Temos {exemplos[0]} e {exemplos[1]}, entre outros."
        else:
            linha_cat = ""
    else:
        linha_cat = ""

    partes = [f"{nome}, não trabalhamos com {pedido}."]
    if linha_cat:
        partes.append(linha_cat)
    partes.append("Quer ver o catálogo?")
    return " ".join(partes)


def resposta_mostrar_catalogo(
    nome_cliente: str = "",
    produtos: list | None = None,
) -> str:
    """Lista produtos reais quando o cliente aceita ver o catálogo."""
    nome = nome_cliente or "Cliente"
    itens = produtos or []

    if not itens:
        return f"{nome}, me diz o que você procura que eu te ajudo."

    # Lista o catálogo completo (WhatsApp aguenta bem ~20–30 itens)
    linhas = [f"Olha o que temos, {nome}:"]
    for produto in itens:
        nome_p = produto.get("nome", "Produto")
        preco = _fmt_preco_item(produto)
        linhas.append(f"• {nome_p}" + (f" — {preco}" if preco else ""))

    linhas.append("Qual te interessa?")
    return "\n".join(linhas)


def resposta_abrir_nova_venda(
    nome_cliente: str = "",
    produtos: list | None = None,
) -> str:
    """Abre nova venda após pedido fechado — não trata a frase como nome de produto."""
    nome = nome_cliente or "Cliente"
    itens = produtos or []

    if not itens:
        return f"Bora, {nome}! O que você quer pedir agora?"

    linhas = [f"Bora, {nome}! Olha o que temos:"]
    for produto in itens:
        nome_p = produto.get("nome", "Produto")
        preco = _fmt_preco_item(produto)
        linhas.append(f"• {nome_p}" + (f" — {preco}" if preco else ""))

    linhas.append("Qual você quer?")
    return "\n".join(linhas)
