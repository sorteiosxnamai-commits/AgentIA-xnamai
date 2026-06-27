import unicodedata

from dotenv import load_dotenv

from services.mercos_service import (
    _extrair_termos,
    buscar_produtos_mercos,
    buscar_produtos_para_atendimento as buscar_mercos_por_mensagem,
    mercos_configurado,
    montar_catalogo_texto,
    normalizar_produto,
)
from services.supabase_service import buscar_produtos

load_dotenv(override=True)

LIMITE_CATALOGO = 20

PADROES_CATALOGO = (
    r"o que (mais )?(voce|voces|vc|vcs) tem",
    r"o que (voce|voces|vc|vcs) (tem|vende|oferece|oferecem)",
    r"quais (produtos|opcoes|opções)",
    r"(mostra|manda|passa|envia) (o )?(catalogo|produtos)",
    r"catalogo|produtos disponiveis",
    r"o que mais",
    r"oferecer|oferece|oferecem",
    r"tem ai|tem pra vender|tem disponivel",
    r"lista de produtos",
    r"me mostra",
    r"conferiu|conferir|verificou|checou",
    r"algo mais|mais alguma",
    r"disponivel|estoque",
)


def _consulta_catalogo(mensagem: str) -> bool:
    import re

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


def _termos_do_cliente(mensagem: str, historico_texto: str = "") -> list[str]:
    """Termos da mensagem atual ou das últimas falas do cliente — nunca do histórico completo."""
    termos = _extrair_termos(mensagem)
    if termos:
        return termos

    if not historico_texto:
        return []

    linhas_cliente = [
        linha.replace("Cliente:", "").strip()
        for linha in historico_texto.split("\n")
        if linha.startswith("Cliente:")
    ]
    for linha in reversed(linhas_cliente[-6:]):
        termos = _extrair_termos(linha)
        if termos:
            return termos

    return []


def _mensagem_busca(mensagem: str, historico_texto: str = "") -> str:
    termos = _termos_do_cliente(mensagem, historico_texto)
    if termos:
        return " ".join(termos)
    return mensagem.strip()


def _buscar_mercos(mensagem: str, historico_texto: str = "") -> tuple[list[dict], str | None]:
    if not mercos_configurado():
        return [], "Mercos não configurada"

    try:
        if _consulta_catalogo(mensagem):
            brutos = buscar_produtos_mercos()[:LIMITE_CATALOGO]
            return [normalizar_produto(p) for p in brutos], None

        busca = _mensagem_busca(mensagem, historico_texto)
        termos = _extrair_termos(busca)
        if not termos:
            return [], None

        produtos = buscar_mercos_por_mensagem(busca)
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

    busca = _mensagem_busca(mensagem, historico_texto)
    termos = _extrair_termos(busca)
    if not termos:
        return []

    encontrados = []
    for produto in produtos:
        texto = " ".join(
            str(produto.get(c, "") or "")
            for c in ("nome", "codigo", "categoria", "descricao")
        ).lower()
        if any(t in texto for t in termos):
            encontrados.append(produto)

    return encontrados[:LIMITE_CATALOGO]


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


def _catalogo_completo_mercos() -> list[dict]:
    if not mercos_configurado():
        return []
    try:
        return [normalizar_produto(p) for p in buscar_produtos_mercos()]
    except Exception:
        return []


def montar_contexto_catalogo(mensagem: str, historico_texto: str = "") -> dict:
    """Consulta Mercos primeiro; Supabase só como fallback. Sem match = catálogo vazio."""
    consulta_ampla = _consulta_catalogo(mensagem)
    termos_cliente = _termos_do_cliente(mensagem, historico_texto)
    consulta_especifica = bool(termos_cliente) and not consulta_ampla

    produtos, erro_mercos = _buscar_mercos(mensagem, historico_texto)
    fonte = "mercos" if produtos else ""

    if not produtos:
        produtos = _buscar_supabase(mensagem, historico_texto)
        if produtos:
            fonte = "supabase"

    produtos = _deduplicar(produtos)[:LIMITE_CATALOGO]
    catalogo_base = _catalogo_completo_mercos() or buscar_produtos()

    principal = produtos[0] if produtos else None
    similares: list[dict] = []
    upsell: list[dict] = []
    complementos: list[dict] = []

    if principal and catalogo_base:
        similares = _similares(principal, catalogo_base)
        upsell = _upsell(principal, catalogo_base)
        complementos = _complementos(principal, catalogo_base)

    def bloco(titulo: str, itens: list[dict]) -> str:
        if not itens:
            return ""
        return f"\n=== {titulo} ===\n{montar_catalogo_texto(itens)}"

    if not produtos:
        busca = " ".join(termos_cliente) if termos_cliente else mensagem.strip()
        catalogo_texto = (
            f"Nenhum produto encontrado para: {busca or 'esta consulta'}.\n"
            "O cliente pediu algo que NÃO está no catálogo.\n"
            "NÃO ofereça produto aleatório ou de outra categoria.\n"
            "Seja honesto, diga que não temos no momento e pergunte se quer "
            "ver outra categoria do catálogo ou ser avisado quando chegar."
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
        "termos_cliente": termos_cliente,
        "sem_match": consulta_especifica and not produtos,
    }
