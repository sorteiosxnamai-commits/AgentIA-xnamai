import unicodedata
import os

from services.env_loader import carregar_env

from services.mercos_service import (
    _extrair_termos,
    buscar_produtos_mercos,
    buscar_produtos_para_atendimento as buscar_mercos_por_mensagem,
    mercos_configurado,
    montar_catalogo_texto,
    normalizar_produto,
)
from services.supabase_service import buscar_produtos, _normalizar_produto

carregar_env()

LIMITE_CATALOGO = 20


def _fonte_produtos() -> str:
    return os.getenv("PRODUTOS_FONTE", "supabase").strip().lower()


def _usar_somente_supabase() -> bool:
    """ETL PulseDesk alimenta Supabase — agente não consulta Mercos por mensagem."""
    return _fonte_produtos() in ("supabase", "local", "etl", "pulsedesk")

PADROES_CATALOGO = (
    r"o que (mais )?(voce|voces|vc|vcs) tem",
    r"o que (voce|voces|vc|vcs) (tem|vende|oferece|oferecem)",
    r"o que (voce|voces|vc|vcs) vendem",
    r"quais (produtos|opcoes|opções)",
    r"(mostra|manda|mande|passa|envia|envie) (o |as |os )?(catalogo|produtos|opcoes|opções)",
    r"me (manda|mande|passa|mostra|envia) (o |as |os )?(catalogo|produtos|opcoes|opções)",
    r"catalogo|produtos disponiveis",
    r"tem (o )?catalogo",
    r"lista (os )?produtos",
    r"tem algo disponivel",
    r"o que mais",
    r"oferecer|oferece|oferecem",
    r"tem ai|tem pra vender|tem disponivel",
    r"lista de produtos",
    r"me mostra",
    r"conferiu|conferir|verificou|checou",
    r"algo mais|mais alguma",
    # Pedidos genéricos de opções — NÃO são nome de produto
    r"tem\s+mais\s+(opcoes|opções|produtos|itens)",
    r"mais\s+(opcoes|opções)\s+(de\s+)?produtos?",
    r"(outras|mais)\s+(opcoes|opções)",
    r"tem\s+(outras|mais)\s+(opcoes|opções)",
    r"quais\s+(outras\s+)?(opcoes|opções)",
    r"tem\s+opcoes|tem\s+opções",
    r"me\s+passa\s+(as\s+)?(opcoes|opções)",
)


def _norm_list(produtos: list[dict]) -> list[dict]:
    return [_normalizar_produto(p) for p in produtos]


def _tem_categoria_especifica(mensagem: str) -> bool:
    """True se o cliente citou categoria/produto concreto (ex.: notebook, adaptador)."""
    from services.vendas.respostas import mensagem_tem_produto_especifico

    return mensagem_tem_produto_especifico(mensagem)


def _consulta_catalogo(mensagem: str) -> bool:
    import re

    # "Quais opções" + categoria específica = busca filtrada, não catálogo geral
    if _tem_categoria_especifica(mensagem):
        return False
    texto = _normalizar(mensagem)
    return any(re.search(padrao, texto) for padrao in PADROES_CATALOGO)

COMPLEMENTOS_CATEGORIA = {
    "fone": ("carregador", "cabo", "capa"),
    "caixa": ("cabo", "carregador", "fone"),
    "carregador": ("cabo", "fone"),
    "cabo": ("carregador", "fone"),
    "notebook": ("mouse", "carregador", "cabo"),
    "celular": ("capa", "carregador", "fone"),
    "smartwatch": ("carregador", "cabo"),
}


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


def _chave_produto(produto: dict) -> str:
    return _normalizar(produto.get("nome") or "")


def _deduplicar(produtos: list[dict]) -> list[dict]:
    vistos: set[str] = set()
    resultado = []
    for produto in produtos:
        chave = _chave_produto(produto)
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(produto)
    return resultado


TERMOS_ESTETICOS = {
    "vermelha", "vermelho", "azul", "preto", "branco", "rosa", "verde", "amarelo",
    "linda", "lindo", "bonita", "bonito", "fica", "ficou", "show", "perfeito",
    "rosto", "banho", "conjunto", "queria", "quero", "pra", "pro",
}

TERMOS_NAO_PRODUTO = TERMOS_ESTETICOS | {
    "sim", "nao", "não", "ok", "tem", "catalogo", "nada", "disponivel",
    "claro", "pode", "hoje", "voce", "voces", "vcs", "vc", "ver",
    "tudo", "bem", "meu", "minha", "amor", "vida", "carinho", "obrigado",
    "obrigada", "valeu", "haha", "kkk", "kkkk", "faz", "nele", "nela",
    "pedido", "pedidos", "venda", "vendas", "fazer", "abrir", "outro",
    "outra", "nova", "novo", "mais", "comprar", "preciso", "quero",
    # Genéricos de catálogo — NUNCA viram "não trabalhamos com X"
    "produto", "produtos", "opcao", "opcoes", "item", "itens",
    "tipo", "tipos", "categoria", "categorias", "linha", "linhas",
    "modelo", "modelos", "variedade", "variedades",
    "mande", "manda", "passa", "envia", "envie", "mostra", "mostrar",
    "lista", "vender", "vendem", "vende", "favor", "porfavor",
    "quais", "algo", "disponiveis", "geral", "completo", "saber",
    # Envio / NF / confirmações — NUNCA tratar como produto
    "retirar", "retirada", "retiro", "buscar", "pego", "envio", "enviar",
    "frete", "correios", "entrega", "entregar", "mandar", "local",
    "nota", "fiscal", "antecipado", "pagamento", "pix", "cartao",
    "sei", "sabe", "acho", "mesmo", "tambem", "também", "ainda",
    "qual", "quanto", "custa", "valor", "preco", "preço",
}

# Alias cliente → termos de busca no catálogo (evita sem_match falso)
ALIASES_PRODUTO = {
    "headset": ("headset", "fone", "gamer"),
    "fone": ("fone", "headset"),
    "hdmi": ("hdmi", "cabo"),
    "cabo": ("cabo", "hdmi"),
    "ssd": ("ssd",),
    "hd": ("hd", "externo"),
    "externo": ("externo", "hd"),
    "mouse": ("mouse",),
    "teclado": ("teclado",),
    "monitor": ("monitor", "led"),
    "notebook": ("notebook",),
    "webcam": ("webcam",),
    "hub": ("hub", "usb"),
    "usb": ("usb", "hub"),
}


def termos_produto_relevantes(termos: list[str]) -> list[str]:
    return [t for t in termos if t not in TERMOS_NAO_PRODUTO and len(t) >= 3]


def _termos_do_cliente(mensagem: str, historico_texto: str = "") -> list[str]:
    """Termos da mensagem atual + produto citado nas falas recentes do cliente.

    Histórico só entra com termos de produto reais — nunca envio/NF/confirmação.
    """
    termos_atual = [
        t for t in _extrair_termos(mensagem) if t not in TERMOS_NAO_PRODUTO
    ]

    linhas_cliente: list[str] = []
    if historico_texto:
        linhas_cliente = [
            linha.replace("Cliente:", "").strip()
            for linha in historico_texto.split("\n")
            if linha.startswith("Cliente:")
        ]

    produto_hist: list[str] = []
    for linha in linhas_cliente[-8:]:
        for termo in _extrair_termos(linha):
            if termo in TERMOS_NAO_PRODUTO or termo in produto_hist:
                continue
            produto_hist.append(termo)

    # Mensagem só com estética/confirmação → usa produto do histórico
    if not termos_atual:
        return produto_hist

    if all(t in TERMOS_ESTETICOS for t in termos_atual):
        return produto_hist or termos_atual

    combinados: list[str] = []
    for termo in produto_hist + termos_atual:
        if termo not in combinados:
            combinados.append(termo)

    return combinados


def _expandir_aliases(termos: list[str]) -> list[str]:
    expandidos: list[str] = []
    for termo in termos:
        t = _normalizar(termo)
        if t not in expandidos:
            expandidos.append(t)
        for alias in ALIASES_PRODUTO.get(t, ()):
            if alias not in expandidos:
                expandidos.append(alias)
    return expandidos


# Stopwords extras da consulta (além das de _extrair_termos / TERMOS_NAO_PRODUTO)
STOPWORDS_CONSULTA = {
    "de", "da", "do", "das", "dos", "para", "com", "em", "e", "a", "o", "as", "os",
    "um", "uma", "uns", "umas", "no", "na", "nos", "nas", "por", "ao", "aos",
    "pra", "pro", "pelo", "pela", "pelos", "pelas",
}

# Níveis de relevância (menor = melhor)
NIVEL_FRASE = 0          # nome contém a frase completa
NIVEL_TODOS_TERMOS = 1   # nome contém todos os termos relevantes
NIVEL_COMECA = 2         # nome começa com o(s) termo(s) da busca
NIVEL_PARCIAL = 3        # nome contém só parte dos termos
NIVEL_NENHUM = 99


def _mensagem_busca(mensagem: str, historico_texto: str = "") -> str:
    termos = _expandir_aliases(_termos_do_cliente(mensagem, historico_texto))
    if termos:
        return " ".join(termos)
    return mensagem.strip()


def _frase_consulta(mensagem: str) -> str:
    """Frase normalizada (caixa/acentos), espaços colapsados — mantém 'de' etc."""
    return " ".join(_normalizar(mensagem or "").split())


def _termos_consulta_busca(mensagem: str, historico_texto: str = "") -> list[str]:
    """Termos relevantes da consulta (sem stopwords curtas / genéricas)."""
    busca = _mensagem_busca(mensagem, historico_texto)
    brutos = _expandir_aliases(
        termos_produto_relevantes(_extrair_termos(busca)) or _extrair_termos(busca)
    )
    out: list[str] = []
    for t in brutos:
        tn = _normalizar(t)
        if not tn or tn in STOPWORDS_CONSULTA or len(tn) < 3:
            continue
        if tn not in out:
            out.append(tn)
    return out


def _estoque_valor(produto: dict) -> float:
    bruto = produto.get("estoque")
    if bruto in (None, ""):
        bruto = produto.get("saldo_estoque")
    if bruto in (None, ""):
        return 0.0
    try:
        return float(bruto)
    except (TypeError, ValueError):
        return 0.0


def _tem_estoque(produto: dict) -> bool:
    return _estoque_valor(produto) > 0


def _nivel_relevancia_nome(
    nome_norm: str, frase: str, termos: list[str]
) -> int:
    if not nome_norm:
        return NIVEL_NENHUM
    if frase and len(frase) >= 3 and frase in nome_norm:
        return NIVEL_FRASE
    if termos and all(t in nome_norm for t in termos):
        return NIVEL_TODOS_TERMOS
    if termos:
        primeiro = termos[0]
        if nome_norm.startswith(primeiro) or (
            frase and nome_norm.startswith(frase.split()[0] if frase else "")
        ):
            return NIVEL_COMECA
    if termos and any(t in nome_norm for t in termos):
        return NIVEL_PARCIAL
    return NIVEL_NENHUM


def _score_produto(produto: dict, termos: list[str], frase: str = "") -> int:
    """Pontua match: frase/todos os termos >> nome parcial > codigo > categoria."""
    nome = _normalizar(str(produto.get("nome") or ""))
    codigo = _normalizar(str(produto.get("codigo") or ""))
    resto = _normalizar(
        f"{produto.get('categoria') or ''} {produto.get('descricao') or ''}"
    )
    frase_n = _frase_consulta(frase) if frase else ""
    if not frase_n and termos:
        frase_n = " ".join(termos)

    nivel = _nivel_relevancia_nome(nome, frase_n, termos)
    score = 0
    if nivel == NIVEL_FRASE:
        score += 1000
    elif nivel == NIVEL_TODOS_TERMOS:
        score += 500
    elif nivel == NIVEL_COMECA:
        score += 80
    elif nivel == NIVEL_PARCIAL:
        score += 10

    for t in termos:
        if not t:
            continue
        if t in nome:
            score += 10
            if nome.startswith(t) or f" {t}" in f" {nome}":
                score += 3
        if t in codigo:
            score += 6
        if t in resto:
            score += 2
    return score


def _ranquear_produtos_por_consulta(
    produtos: list[dict],
    mensagem: str,
    historico_texto: str = "",
    *,
    limite: int | None = None,
) -> list[dict]:
    """Ranqueia catálogo local pela consulta.

    Prioridade: frase completa → todos os termos → começa com termo → parcial.
    Com matches fortes (frase/todos), exclui parciais fracos (ex.: só 'tomada').
    No mesmo nível, saldo_estoque > 0 vem antes.
    """
    if not produtos:
        return []

    frase = _frase_consulta(mensagem)
    # Frase sem stopwords (para match de "adaptador tomada" se o nome omitir "de")
    termos = _termos_consulta_busca(mensagem, historico_texto)
    if not termos and not frase:
        return []

    frase_termos = " ".join(termos) if termos else frase
    pontuados: list[tuple[int, int, int, dict]] = []
    for produto in produtos:
        nome = _normalizar(str(produto.get("nome") or ""))
        nivel = _nivel_relevancia_nome(nome, frase, termos)
        if nivel == NIVEL_NENHUM and frase_termos and frase_termos != frase:
            nivel = _nivel_relevancia_nome(nome, frase_termos, termos)
        if nivel == NIVEL_NENHUM:
            # Último recurso: match só em codigo/categoria (parcial fraco)
            score_extra = _score_produto(produto, termos, frase=frase)
            if score_extra <= 0:
                continue
            nivel = NIVEL_PARCIAL
        sem_estoque = 0 if _tem_estoque(produto) else 1
        score = _score_produto(produto, termos, frase=frase)
        pontuados.append((nivel, sem_estoque, -score, produto))

    if not pontuados:
        return []

    tem_forte = any(n <= NIVEL_TODOS_TERMOS for n, *_ in pontuados)
    if tem_forte:
        pontuados = [item for item in pontuados if item[0] <= NIVEL_TODOS_TERMOS]
    else:
        tem_comeca = any(n <= NIVEL_COMECA for n, *_ in pontuados)
        if tem_comeca:
            pontuados = [item for item in pontuados if item[0] <= NIVEL_COMECA]

    pontuados.sort(key=lambda x: (x[0], x[1], x[2]))
    lim = LIMITE_CATALOGO if limite is None else max(1, int(limite))
    return [p for *_, p in pontuados[:lim]]


def _buscar_mercos(mensagem: str, historico_texto: str = "") -> tuple[list[dict], str | None]:
    if not mercos_configurado():
        return [], "Mercos não configurada"

    try:
        if _consulta_catalogo(mensagem):
            brutos = buscar_produtos_mercos()[:LIMITE_CATALOGO]
            return [normalizar_produto(p) for p in brutos], None

        busca = _mensagem_busca(mensagem, historico_texto)
        termos = _expandir_aliases(_extrair_termos(busca))
        if not termos:
            return [], None

        produtos = buscar_mercos_por_mensagem(busca)
        if produtos:
            return (
                _ranquear_produtos_por_consulta(
                    produtos, mensagem, historico_texto, limite=LIMITE_CATALOGO
                )
                or produtos[:LIMITE_CATALOGO],
                None,
            )
        return produtos, None
    except Exception as e:
        return [], str(e)


def _filtrar_produtos_locais(produtos: list[dict]) -> list[dict]:
    from services.mercos_service import eh_produto_exemplo, ocultar_produtos_exemplo

    if not ocultar_produtos_exemplo():
        return produtos
    return [p for p in produtos if not eh_produto_exemplo(p)]


def _buscar_supabase(mensagem: str, historico_texto: str = "") -> list[dict]:
    produtos = _filtrar_produtos_locais(buscar_produtos())
    if not produtos:
        return []

    if _consulta_catalogo(mensagem):
        return produtos[:LIMITE_CATALOGO]

    return _ranquear_produtos_por_consulta(
        produtos, mensagem, historico_texto, limite=LIMITE_CATALOGO
    )


def _categoria_chave(produto: dict) -> str:
    cat = _normalizar(produto.get("categoria") or "")
    nome = _normalizar(produto.get("nome") or "")

    for chave in COMPLEMENTOS_CATEGORIA:
        if chave in cat or chave in nome:
            return chave
    return cat or nome.split()[0] if nome else ""


def _preco_float(produto: dict) -> float:
    preco = produto.get("preco")
    if preco in (None, ""):
        preco = produto.get("preco_tabela")
    if preco in (None, ""):
        return 0.0
    try:
        return float(str(preco).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _similares(produto_ref: dict, catalogo: list[dict], limite: int = 3) -> list[dict]:
    cat_ref = _normalizar(produto_ref.get("categoria") or "")
    nome_ref = _normalizar(produto_ref.get("nome") or "")
    chave_ref = _chave_produto(produto_ref)

    candidatos = []
    for produto in catalogo:
        if _chave_produto(produto) == chave_ref:
            continue

        cat = _normalizar(produto.get("categoria") or "")
        nome = _normalizar(produto.get("nome") or "")

        mesmo_grupo = (
            (cat_ref and cat_ref in cat)
            or (cat and cat in cat_ref)
            or any(p in nome for p in _extrair_termos(nome_ref)[:2])
        )
        if mesmo_grupo:
            candidatos.append(produto)

    return _deduplicar(candidatos)[:limite]


def _upsell(produto_ref: dict, catalogo: list[dict], limite: int = 2) -> list[dict]:
    preco_ref = _preco_float(produto_ref)
    if preco_ref <= 0:
        return []

    cat_ref = _categoria_chave(produto_ref)
    candidatos = []

    for produto in catalogo:
        if _chave_produto(produto) == _chave_produto(produto_ref):
            continue
        if _categoria_chave(produto) != cat_ref:
            continue
        preco = _preco_float(produto)
        if preco > preco_ref:
            candidatos.append((preco, produto))

    candidatos.sort(key=lambda x: x[0])
    return [p for _, p in candidatos[:limite]]


def _complementos(produto_ref: dict, catalogo: list[dict], limite: int = 2) -> list[dict]:
    chave_cat = _categoria_chave(produto_ref)
    termos_comp = COMPLEMENTOS_CATEGORIA.get(chave_cat, ())

    if not termos_comp:
        return []

    chave_ref = _chave_produto(produto_ref)
    candidatos = []

    for produto in catalogo:
        if _chave_produto(produto) == chave_ref:
            continue
        texto = _normalizar(
            f"{produto.get('nome', '')} {produto.get('categoria', '')}"
        )
        if any(t in texto for t in termos_comp):
            candidatos.append(produto)

    return _deduplicar(candidatos)[:limite]


def _amostra_produtos_reais(limite: int = 4) -> list[dict]:
    """Produtos reais do catálogo para redirecionar quando o pedido não existe."""
    if not _usar_somente_supabase() and mercos_configurado():
        try:
            brutos = buscar_produtos_mercos()[:limite]
            return [normalizar_produto(p) for p in brutos]
        except Exception:
            pass
    return _filtrar_produtos_locais(buscar_produtos())[:limite]


def _catalogo_completo_mercos() -> list[dict]:
    if _usar_somente_supabase() or not mercos_configurado():
        return []
    try:
        return [normalizar_produto(p) for p in buscar_produtos_mercos()]
    except Exception:
        return []


def montar_catalogo_geral(limite: int = LIMITE_CATALOGO) -> dict:
    """Catálogo completo — quando o cliente pede para ver o que temos."""
    if _usar_somente_supabase():
        todos = _filtrar_produtos_locais(buscar_produtos())
        fonte = "supabase"
    else:
        todos = _catalogo_completo_mercos() or _filtrar_produtos_locais(buscar_produtos())
        fonte = "mercos" if mercos_configurado() and _catalogo_completo_mercos() else "supabase"

    produtos = _deduplicar(todos)[:limite]

    return {
        "produtos": produtos,
        "similares": [],
        "upsell": [],
        "complementos": [],
        "catalogo": montar_catalogo_texto(produtos),
        "fonte": fonte,
        "erro_mercos": None,
        "consulta_especifica": False,
        "termos_cliente": [],
        "sem_match": False,
        "amostra_disponivel": produtos,
    }


def montar_contexto_catalogo(mensagem: str, historico_texto: str = "") -> dict:
    """Com PRODUTOS_FONTE=supabase lê só o ETL; senão Mercos primeiro."""
    consulta_ampla = _consulta_catalogo(mensagem)
    termos_cliente = _termos_do_cliente(mensagem, historico_texto)
    # Fora do catálogo só se a MENSAGEM ATUAL pedir produto inexistente
    termos_msg = termos_produto_relevantes(_extrair_termos(mensagem))
    consulta_especifica = bool(termos_msg) and not consulta_ampla

    if _usar_somente_supabase():
        produtos = _buscar_supabase(mensagem, historico_texto)
        fonte = "supabase"
        erro_mercos = None
    else:
        produtos, erro_mercos = _buscar_mercos(mensagem, historico_texto)
        fonte = "mercos" if produtos else ""
        if not produtos:
            produtos = _buscar_supabase(mensagem, historico_texto)
            if produtos:
                fonte = "supabase"

    produtos = _deduplicar(produtos)[:LIMITE_CATALOGO]
    produtos = _norm_list(produtos)
    if _usar_somente_supabase():
        catalogo_base = _norm_list(_filtrar_produtos_locais(buscar_produtos()))
    else:
        catalogo_base = _norm_list(_catalogo_completo_mercos() or buscar_produtos())

    principal = produtos[0] if produtos else None
    similares: list[dict] = []
    upsell: list[dict] = []
    complementos: list[dict] = []

    if principal and catalogo_base:
        similares = _similares(principal, catalogo_base)
        upsell = _upsell(principal, catalogo_base)
        # Acessórios só como follow-up — não misturar na 1ª busca por categoria
        if not (_tem_categoria_especifica(mensagem) or consulta_especifica):
            complementos = _complementos(principal, catalogo_base)

    def bloco(titulo: str, itens: list[dict]) -> str:
        if not itens:
            return ""
        return f"\n=== {titulo} ===\n{montar_catalogo_texto(itens)}"

    if not produtos:
        busca = " ".join(termos_cliente) if termos_cliente else mensagem.strip()
        amostra = _amostra_produtos_reais()
        catalogo_texto = (
            f"Nenhum produto encontrado para: {busca or 'esta consulta'}.\n"
            "A Xnamai NÃO vende esta categoria/produto — não está no catálogo.\n"
            "PROIBIDO: perguntar cor, tamanho ou modelo desse item; prometer avisar quando chegar;\n"
            "finja que temos essa linha em falta (ex.: 'não tenho vermelha' implica que vendemos toalha).\n"
            "CORRETO: dizer que não trabalhamos com isso e, se fizer sentido, citar o que vendemos.\n"
        )
        if amostra:
            catalogo_texto += (
                "\n=== O QUE VENDEMOS (cite só estes para redirecionar) ===\n"
                + montar_catalogo_texto(amostra)
            )
    else:
        catalogo_texto = montar_catalogo_texto(produtos)
        if similares:
            catalogo_texto += bloco(
                "OPÇÕES SEMELHANTES (só se relacionadas ao que o cliente pediu)", similares
            )
        if upsell:
            catalogo_texto += bloco(
                "UPSELL — versão superior (só na mesma linha do interesse)", upsell
            )
        if complementos:
            catalogo_texto += bloco(
                "COMPLEMENTOS — cross-sell natural (só se combinar com o pedido)", complementos
            )

    return {
        "produtos": produtos,
        "similares": similares,
        "upsell": upsell,
        "complementos": complementos,
        "catalogo": catalogo_texto,
        "fonte": fonte or "nenhum",
        "erro_mercos": erro_mercos,
        "consulta_especifica": consulta_especifica,
        "termos_cliente": termos_msg or termos_produto_relevantes(termos_cliente),
        "sem_match": consulta_especifica and not produtos and bool(termos_msg),
        "amostra_disponivel": _amostra_produtos_reais()
        if consulta_especifica and not produtos
        else [],
    }
