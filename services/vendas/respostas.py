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
    "produto", "produtos", "opcao", "opcoes", "item", "itens",
    "tipo", "tipos", "categoria", "mais", "outras", "outra", "outro",
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
        r"lista\s+(de\s+)?produtos",
        r"manda\s+(o\s+)?catalogo",
    )
    return any(re.search(p, texto) for p in padroes_diretos)


def cliente_pediu_mais_opcoes(mensagem: str) -> bool:
    """Cliente pede outras opções/alternativas — não é nome de produto.

    Evita falsos positivos como:
    - 'qual é a melhor opção?'
    - 'esse produto tem opções de cor?'
    - 'não quero mais opções'
    """
    texto = _normalizar(mensagem)

    # Negação explícita → não é pedido de mais opções
    if re.search(
        r"\b(nao|não)\s+(quero|preciso|precisa|quero ver|mostra|mostrar)\b"
        r".*\b(mais\s+)?(opcoes|opções|outros|outras)\b"
        r"|\b(nao|não)\s+(quero|precisa)\s+mais\s+(opcoes|opções)\b"
        r"|\bnão\s+precisa\s+mostrar\b"
        r"|\bnao\s+precisa\s+mostrar\b",
        texto,
    ):
        return False

    # Atributos do produto atual (cor/tamanho) — não é catálogo genérico
    if re.search(
        r"opcoes?\s+de\s+(cor|cores|tamanho|tamanhos|voltagem|capacidade)"
        r"|opções?\s+de\s+(cor|cores|tamanho|tamanhos|voltagem|capacidade)",
        texto,
    ):
        return False

    # Pedido de recomendação da opção atual (singular) — não é "mais opções"
    if re.search(
        r"\b(qual|quais)\s+(e|é|eh)?\s*(a\s+)?melhor\s+opcao\b"
        r"|\bmelhor\s+opcao\b(?!\s+(de|entre|dentre))",
        texto,
    ) and not re.search(r"\b(mais|outras|outros|alternativas)\b", texto):
        return False

    # "produto com várias opções" descreve o item — não pede catálogo
    if re.search(r"\b(com|tem)\s+(varias|várias|muitas)\s+opcoes\b", texto):
        return False

    padroes = (
        # opções / alternativas
        r"\b(tem|têm|temos|voce tem|voces tem|vocês têm)\s+(outras|mais)\s+(opcoes|opções|alternativas)\b",
        r"\b(outras|mais)\s+(opcoes|opções|alternativas)\b",
        r"\bquais\s+(outras\s+)?(opcoes|opções|alternativas)\b",
        r"\bquero\s+ver\s+mais\s+(opcoes|opções)\b",
        r"\btem\s+mais\s+(opcoes|opções|produtos|itens)\b",
        r"\bmais\s+(opcoes|opções)(\s+de\s+produtos?)?\b",
        # modelos / marcas / alternativas
        r"\b(tem|têm|temos)\s+(mais\s+)?(modelos|alternativas)\b",
        r"\bmais\s+modelos\b",
        r"\boutras?\s+alternativas?\b",
        r"\b(tem|têm)\s+de\s+outra\s+marca\b",
        r"\boutra\s+marca\b",
        # mais barato / melhor (comparação dentro da linha)
        r"\btem\s+(outro|outra|algum|alguma)\s+(mais\s+)?(barato|barata|bom|boa|melhor)\b",
        r"\btem\s+algum\s+melhor\b",
        r"\btem\s+outro\s+mais\s+barato\b",
        # genéricos
        r"\btem\s+mais\s+alguma\s+coisa\b",
        r"\bmais\s+alguma\s+coisa\b",
        r"\bme\s+mostra\s+outros?\b",
        r"\bmostra\s+outros?\b",
        r"\btem\s+mais\s*\??$",
        r"\bmais\s+produtos\b",
    )
    return any(re.search(p, texto) for p in padroes)


def _categoria_no_historico(historico_texto: str) -> str | None:
    """Detecta categoria/produto já citado no histórico recente."""
    from services.conversa_service import _extrair_oferta_ia

    nome_oferta, _ = _extrair_oferta_ia(historico_texto or "")
    if nome_oferta:
        return nome_oferta

    categorias = (
        "headset", "fone", "cabo", "hdmi", "mouse", "teclado", "monitor",
        "notebook", "webcam", "ssd", "hd", "hub", "carregador", "caixa",
        "celular", "smartphone", "mesa", "cadeira", "movel", "móvel",
    )
    texto = _normalizar(historico_texto or "")
    for cat in categorias:
        if cat in texto:
            return cat
    return None


def _familia_categoria(chave: str) -> str:
    """Agrupa termo/produto em família para critério de pergunta."""
    t = _normalizar(chave or "")
    if any(x in t for x in ("headset", "fone", "earbud", "audio", "áudio", "microfone")):
        return "headset"
    if any(x in t for x in ("ssd", "hd ", "hd externo", "externo", "pendrive", "armazen", "disco")):
        return "armazenamento"
    if any(x in t for x in ("celular", "smartphone", "iphone", "galaxy")):
        return "celular"
    if any(x in t for x in ("mesa", "cadeira", "movel", "móvel", "armario", "armário", "estante")):
        return "moveis"
    if any(x in t for x in ("cabo", "hdmi", "carregador", "fonte", "hub", "suporte", "pelicula", "película", "capa")):
        return "simples"
    if any(x in t for x in ("mouse", "teclado", "webcam", "monitor", "notebook")):
        return "periferico"
    if any(x in t for x in ("caixa", "som", "jbl")):
        return "audio_caixa"
    return "geral"


def _atributos_disponiveis_catalogo(produtos: list | None) -> set[str]:
    """Lê só o que existe de fato nos produtos (não inventa atributo)."""
    attrs: set[str] = set()
    itens = produtos or []
    if not itens:
        return attrs

    precos = []
    for p in itens:
        nome = _normalizar(str(p.get("nome") or ""))
        desc = _normalizar(str(p.get("descricao") or ""))
        cat = _normalizar(str(p.get("categoria") or ""))
        texto = f"{nome} {desc} {cat}"
        preco = p.get("preco")
        if preco in (None, ""):
            preco = p.get("preco_tabela")
        try:
            if preco not in (None, ""):
                precos.append(float(preco))
        except (TypeError, ValueError):
            pass

        if re.search(r"\b(gamer|jogo|jogos|rgb)\b", texto):
            attrs.add("uso_jogos")
        if re.search(r"\b(trabalho|escritorio|escritório|home\s*office)\b", texto):
            attrs.add("uso_trabalho")
        if re.search(r"\b(chamada|microfone|mic|call)\b", texto):
            attrs.add("uso_chamadas")
        if re.search(r"\b(\d+\s*(gb|tb)|capacidade)\b", texto):
            attrs.add("capacidade")
        if re.search(r"\b(usb\s*3|nvme|sata|velocidade|rapido|rápido)\b", texto):
            attrs.add("velocidade")
        if re.search(r"\b(portatil|portátil|externo|compacto)\b", texto):
            attrs.add("portabilidade")
        if re.search(r"\b(camera|câmera|mp|megapixel)\b", texto):
            attrs.add("camera")
        if re.search(r"\b(bateria|mah|autonomia)\b", texto):
            attrs.add("bateria")
        if re.search(r"\b(desempenho|ram|processador|snapdragon|helio)\b", texto):
            attrs.add("desempenho")
        if re.search(r"\b(\d+\s*x\s*\d+|cm|medida|largura|altura)\b", texto):
            attrs.add("medidas")
        if re.search(r"\b(madeira|mdp|mdf|metal|tecido|material)\b", texto):
            attrs.add("material")
        if re.search(r"\b(acabamento|verniz|laca|fosco|brilhante)\b", texto):
            attrs.add("acabamento")
        if re.search(r"\b(marca|hmaston|lenovo|jbl|samsung|apple|logitech)\b", texto):
            attrs.add("marca")

    if len(precos) >= 2 and (max(precos) - min(precos)) >= 10:
        attrs.add("preco")
    elif precos:
        attrs.add("preco")

    return attrs


def criterio_util_por_categoria(
    categoria: str | None,
    produtos: list | None = None,
) -> str | None:
    """
    Próximo critério útil — no máximo UMA pergunta simples (2 opções).
    Nunca lista 3+ critérios na mesma frase.
    """
    familia = _familia_categoria(categoria or "")
    attrs = _atributos_disponiveis_catalogo(produtos)

    if familia == "simples":
        return None

    if familia == "headset":
        usos = {"uso_jogos", "uso_trabalho", "uso_chamadas"} & attrs
        if "uso_jogos" in usos and "uso_chamadas" in usos:
            return "Você pretende usar mais para jogos ou chamadas?"
        if "uso_jogos" in usos and "uso_trabalho" in usos:
            return "Você quer priorizar jogos ou trabalho?"
        if usos:
            return "Você pretende usar mais para jogos ou chamadas?"
        return "Você tem alguma preferência de faixa de preço?"

    if familia == "armazenamento":
        if "capacidade" in attrs and "velocidade" in attrs:
            return "Você prioriza capacidade ou velocidade?"
        if "capacidade" in attrs:
            return "Quer que eu filtre mais por capacidade?"
        if "preco" in attrs:
            return "Prefere algo mais em conta ou com mais desempenho?"
        return "Você tem alguma preferência de capacidade?"

    if familia == "celular":
        if "camera" in attrs and "bateria" in attrs:
            return "O que pesa mais pra você: câmera ou bateria?"
        if "preco" in attrs:
            return "Quer priorizar desempenho ou orçamento?"
        return "Você tem alguma preferência de uso principal?"

    if familia == "moveis":
        if "medidas" in attrs and "material" in attrs:
            return "Quer filtrar por medidas ou material?"
        if "preco" in attrs:
            return "Prefere focar em preço ou acabamento?"
        return None

    if familia in ("periferico", "audio_caixa"):
        if "preco" in attrs:
            return "Quer ver opções mais em conta ou com mais recursos?"
        return "Você tem alguma preferência de marca?"

    return "Você tem alguma preferência de faixa de preço?"


def resposta_mais_opcoes(
    nome_cliente: str = "",
    historico_texto: str = "",
    produtos: list | None = None,
    categoria: str = "",
) -> str:
    """Resposta natural quando o cliente pede mais opções (via Product Service)."""
    from services.product_service import buscar_mais_opcoes, normalizar_produto_servico

    nome = nome_cliente or "Cliente"
    cat = (categoria or _categoria_no_historico(historico_texto) or "").strip()

    if produtos:
        itens = []
        for p in produtos:
            if p.get("name"):
                itens.append(p)
            else:
                np = normalizar_produto_servico(p)
                if np:
                    itens.append(np)
        resultado = {
            "found": bool(itens),
            "category": cat,
            "products": itens,
        }
    else:
        resultado = buscar_mais_opcoes(
            categoria=cat,
            historico_texto=historico_texto,
            mensagem="",
            limite=6,
        )
        cat = resultado.get("category") or cat
        itens = resultado.get("products") or []

    if not cat:
        return (
            f"Temos sim, {nome}. Qual tipo de produto você está procurando? "
            "Assim consigo mostrar opções que realmente façam sentido para você."
        )

    if not resultado.get("found") or not itens:
        return (
            f"{nome}, no momento não encontrei mais opções de {cat} no catálogo. "
            "Quer que eu te mostre outra categoria que trabalhamos?"
        )

    pergunta = criterio_util_por_categoria(cat, itens)
    linhas = [f"Temos sim, {nome}! Olha outras opções de {cat}:"]
    for p in itens[:4]:
        nome_p = p.get("name") or p.get("nome") or "Produto"
        preco = p.get("price")
        if preco is None:
            preco = p.get("preco")
        if preco is not None:
            try:
                preco_fmt = f"R$ {float(preco):.2f}".replace(".", ",")
                linhas.append(f"• {nome_p} — {preco_fmt}")
            except (TypeError, ValueError):
                linhas.append(f"• {nome_p}")
        else:
            linhas.append(f"• {nome_p}")

    if pergunta:
        if pergunta.count("?") > 1:
            pergunta = pergunta.split("?")[0].strip() + "?"
        linhas.append("")
        linhas.append(pergunta)
    return "\n".join(linhas)


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
        from services.xnamai_script import _variante

        return _variante(
            f"preco:{nome}:{nome_prod}:{preco_fmt}",
            [
                (
                    f"{nome}, o {nome_prod} fica {preco_fmt}. "
                    "Quer que eu feche 1 unidade pra você?"
                ),
                (
                    f"{nome}, esse {nome_prod} está {preco_fmt}. "
                    "Te interessa fechar 1 unidade?"
                ),
                (
                    f"{nome_prod} — {preco_fmt}, {nome}. "
                    "Posso separar 1 pra você?"
                ),
            ],
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

    # Sem termo de produto real → não inventar "não trabalhamos com X"
    if not termos_produto:
        return (
            f"{nome}, me diz qual tipo de produto você procura "
            "(ex.: headset, cabo HDMI, mouse) que eu te mostro as opções."
        )

    pedido = " ".join(termos_produto)

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
