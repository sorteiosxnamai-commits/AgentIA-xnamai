import re
import unicodedata

from services.mercos_service import montar_catalogo_texto

TERMOS_IGNORAR_PEDIDO = {
    "vermelha", "vermelho", "azul", "preto", "branco", "rosa", "verde", "amarelo",
    "linda", "lindo", "bonita", "bonito", "fica", "ficou", "show", "perfeito",
    "rosto", "banho", "conjunto", "queria", "quero", "pra", "pro",
    "sim", "nao", "não", "ok", "tem", "catalogo", "catálogo", "nada",
    "disponivel", "disponível", "hoje", "voce", "voces", "vocês", "claro", "pode",
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

    linhas = [f"Olha o que temos, {nome}:"]
    for produto in itens[:6]:
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
    for produto in itens[:6]:
        nome_p = produto.get("nome", "Produto")
        preco = _fmt_preco_item(produto)
        linhas.append(f"• {nome_p}" + (f" — {preco}" if preco else ""))

    linhas.append("Qual você quer?")
    return "\n".join(linhas)
