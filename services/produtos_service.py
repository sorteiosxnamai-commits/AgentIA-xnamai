import os
import re
import unicodedata

from dotenv import load_dotenv

from services.mercos_service import (
    _extrair_termos,
    buscar_produtos_mercos as listar_todos_mercos,
    buscar_produtos_para_atendimento as buscar_produtos_mercos,
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


def _fonte_configurada() -> str:
    return os.getenv("PRODUTOS_FONTE", "auto").strip().lower()


def _normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


PADROES_SAUDACAO = (
    r"^(oi|ola|olá|hey|eae|e ai|eai|bom dia|boa tarde|boa noite|hello|hi)\b",
    r"^(tudo bem|td bem|blz|beleza)\b",
)


def _eh_saudacao(mensagem: str) -> bool:
    texto = _normalizar_texto(mensagem.strip())
    if not texto:
        return False
    return any(re.search(padrao, texto) for padrao in PADROES_SAUDACAO)


def _catalogo_inicial() -> tuple[list[dict], str, str | None]:
    erro_mercos = None

    if mercos_configurado():
        try:
            produtos = [
                normalizar_produto(p)
                for p in listar_todos_mercos()[:LIMITE_CATALOGO]
            ]
            if produtos:
                return produtos, "mercos", None
        except Exception as e:
            erro_mercos = str(e)

    produtos = buscar_produtos()[:LIMITE_CATALOGO]
    return produtos, "supabase", erro_mercos


def _consulta_catalogo(mensagem: str) -> bool:
    texto = _normalizar_texto(mensagem)
    return any(re.search(padrao, texto) for padrao in PADROES_CATALOGO)


def _filtrar_produtos(produtos: list[dict], mensagem: str) -> list[dict]:
    termos = _extrair_termos(mensagem)

    if not termos:
        return produtos[:LIMITE_CATALOGO]

    encontrados = []
    for produto in produtos:
        texto = " ".join(
            str(produto.get(campo, "") or "")
            for campo in ("nome", "codigo", "categoria", "descricao")
        ).lower()

        if any(termo in texto for termo in termos):
            encontrados.append(produto)

    return encontrados[:LIMITE_CATALOGO]


def _buscar_supabase(mensagem: str) -> list[dict]:
    produtos = buscar_produtos()
    if not produtos:
        return []

    if _consulta_catalogo(mensagem):
        return produtos[:LIMITE_CATALOGO]

    termos = _extrair_termos(mensagem)
    if not termos:
        return []

    filtrados = _filtrar_produtos(produtos, mensagem)
    if filtrados:
        return filtrados

    return produtos[:LIMITE_CATALOGO]


def buscar_produtos_para_atendimento(mensagem: str) -> dict:
    fonte = _fonte_configurada()
    erro_mercos = None

    if _consulta_catalogo(mensagem) or _eh_saudacao(mensagem):
        produtos, fonte_cat, erro_mercos = _catalogo_inicial()
        return {
            "produtos": produtos,
            "fonte": fonte_cat,
            "erro_mercos": erro_mercos,
        }

    termos = _extrair_termos(mensagem)
    if not termos:
        produtos, fonte_cat, erro_mercos = _catalogo_inicial()
        return {
            "produtos": produtos,
            "fonte": fonte_cat,
            "erro_mercos": erro_mercos,
        }

    if fonte in ("mercos", "auto"):
        try:
            produtos = buscar_produtos_mercos(mensagem)
            if produtos:
                return {
                    "produtos": produtos,
                    "fonte": "mercos",
                    "erro_mercos": None,
                }
        except Exception as e:
            erro_mercos = str(e)
            if fonte == "mercos":
                raise

    produtos = _buscar_supabase(mensagem)
    return {
        "produtos": produtos,
        "fonte": "supabase",
        "erro_mercos": erro_mercos,
    }
