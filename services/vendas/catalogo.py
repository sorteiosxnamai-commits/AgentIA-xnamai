import unicodedata
import os

from dotenv import load_dotenv

from services.mercos_service import (
    _extrair_termos,
    buscar_produtos_mercos,
    buscar_produtos_para_atendimento as buscar_mercos_por_mensagem,
    mercos_configurado,
    montar_catalogo_texto,
    normalizar_produto,
)
from services.supabase_service import buscar_produtos, _normalizar_produto

load_dotenv(override=True)

LIMITE_CATALOGO = 20


def _fonte_produtos() -> str:
    return os.getenv("PRODUTOS_FONTE", "supabase").strip().lower()


def _usar_somente_supabase() -> bool:
    """ETL PulseDesk alimenta Supabase — agente não consulta Mercos por mensagem."""
    return _fonte_produtos() in ("supabase", "local", "etl", "pulsedesk")

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


def _norm_list(produtos: list[dict]) -> list[dict]:
    return [_normalizar_produto(p) for p in produtos]


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
    """Termos da mensagem atual + produto citado nas falas recentes do cliente."""
    termos_atual = _extrair_termos(mensagem)

    linhas_cliente: list[str] = []
    if historico_texto:
        linhas_cliente = [
            linha.replace("Cliente:", "").strip()
            for linha in historico_texto.split("\n")
            if linha.startswith("Cliente:")
        ]

    termos_hist: list[str] = []
    for linha in linhas_cliente[-8:]:
        for termo in _extrair_termos(linha):
            if termo not in termos_hist:
                termos_hist.append(termo)

    produto_hist = [t for t in termos_hist if t not in TERMOS_ESTETICOS]

    if termos_atual and all(t in TERMOS_ESTETICOS for t in termos_atual):
        return produto_hist or termos_atual

    combinados: list[str] = []
    for termo in produto_hist + termos_atual:
        if termo not in combinados:
            combinados.append(termo)

    return combinados or termos_hist


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


def _mensagem_busca(mensagem: str, historico_texto: str = "") -> str:
    termos = _expandir_aliases(_termos_do_cliente(mensagem, historico_texto))
    if termos:
        return " ".join(termos)
    return mensagem.strip()


def _score_produto(produto: dict, termos: list[str]) -> int:
    """Pontua match: nome > codigo > categoria/descricao."""
    nome = _normalizar(str(produto.get("nome") or ""))
    codigo = _normalizar(str(produto.get("codigo") or ""))
    resto = _normalizar(
        f"{produto.get('categoria') or ''} {produto.get('descricao') or ''}"
    )
    score = 0
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
            ranqueados = sorted(
                produtos, key=lambda p: _score_produto(p, termos), reverse=True
            )
            return [p for p in ranqueados if _score_produto(p, termos) > 0] or ranqueados, None
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
    termos = _expandir_aliases(
        termos_produto_relevantes(_extrair_termos(busca)) or _extrair_termos(busca)
    )
    if not termos:
        return []

    pontuados = []
    for produto in produtos:
        score = _score_produto(produto, termos)
        if score > 0:
            pontuados.append((score, produto))

    pontuados.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in pontuados[:LIMITE_CATALOGO]]


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
    consulta_especifica = bool(termos_cliente) and not consulta_ampla

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
        "termos_cliente": termos_cliente,
        "sem_match": consulta_especifica
        and not produtos
        and bool(termos_produto_relevantes(termos_cliente)),
        "amostra_disponivel": _amostra_produtos_reais()
        if consulta_especifica and not produtos
        else [],
    }
