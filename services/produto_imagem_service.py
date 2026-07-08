import re
import unicodedata

from services.supabase_service import buscar_produtos
from services.whatsapp_service import enviar_imagem

PALAVRAS_FOTO = (
    "foto",
    "imagem",
    "picture",
    "manda foto",
    "manda a foto",
    "tem foto",
    "ver foto",
    "mostra foto",
    "envia foto",
    "me manda foto",
)


def _normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


def cliente_pediu_foto(mensagem: str) -> bool:
    texto = _normalizar_texto(mensagem)
    return any(palavra in texto for palavra in PALAVRAS_FOTO)


def extrair_imagem_url(produto: dict) -> str:
    for campo in ("imagem_url", "imagem", "foto_url", "url_imagem"):
        url = str(produto.get(campo) or "").strip()
        if url.startswith("http"):
            return url
    return ""


def _legenda_produto(produto: dict) -> str:
    nome = produto.get("nome", "Produto")
    preco = produto.get("preco")
    if preco is not None and preco != "":
        return f"{nome} — R$ {preco}"
    return nome


def enriquecer_imagens_supabase(produtos: list[dict]) -> list[dict]:
    """Completa imagem_url do Supabase quando o produto veio da Mercos."""
    if not produtos:
        return produtos

    catalogo_supabase = buscar_produtos()
    if not catalogo_supabase:
        return produtos

    por_nome = {
        _normalizar_texto(p.get("nome", "")): p
        for p in catalogo_supabase
        if p.get("nome")
    }

    enriquecidos = []

    for produto in produtos:
        copia = dict(produto)

        if extrair_imagem_url(copia):
            enriquecidos.append(copia)
            continue

        nome = _normalizar_texto(copia.get("nome", ""))
        supabase_produto = por_nome.get(nome)

        if not supabase_produto and nome:
            for nome_sb, item in por_nome.items():
                if nome in nome_sb or nome_sb in nome:
                    supabase_produto = item
                    break

        if supabase_produto:
            url = extrair_imagem_url(supabase_produto)
            if url:
                copia["imagem_url"] = url

        enriquecidos.append(copia)

    return enriquecidos


def selecionar_produtos_com_foto(produtos: list[dict], mensagem: str) -> list[dict]:
    produtos = enriquecer_imagens_supabase(produtos)
    com_imagem = [p for p in produtos if extrair_imagem_url(p)]

    if not com_imagem:
        return []

    if cliente_pediu_foto(mensagem):
        return com_imagem[:2]

    if len(com_imagem) == 1:
        return com_imagem[:1]

    return []


def enviar_fotos_produtos(numero: str, produtos: list[dict], mensagem: str) -> int:
    selecionados = selecionar_produtos_com_foto(produtos, mensagem)
    enviadas = 0

    for produto in selecionados:
        url = extrair_imagem_url(produto)
        if not url:
            continue

        if enviar_imagem(numero, url, _legenda_produto(produto)):
            enviadas += 1

    return enviadas


def produtos_com_foto_disponivel(produtos: list[dict], mensagem: str) -> list[dict]:
    return selecionar_produtos_com_foto(produtos, mensagem)


def extrair_busca_do_historico(historico_texto: str) -> str:
    """Usa mensagens recentes do cliente quando ele só pede foto."""
    linhas = historico_texto.strip().split("\n")
    mensagens_cliente = [
        linha.replace("Cliente:", "").strip()
        for linha in linhas
        if linha.startswith("Cliente:")
    ]
    return " ".join(mensagens_cliente[-4:])
