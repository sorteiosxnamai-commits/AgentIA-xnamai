import os
import re
import unicodedata

from dotenv import load_dotenv

from services.mercos_service import (
    _extrair_termos,
    buscar_produtos_para_atendimento as buscar_produtos_mercos,
    montar_catalogo_texto,
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
)


def _fonte_configurada() -> str:
    return os.getenv("PRODUTOS_FONTE", "auto").strip().lower()


def _normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


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

    if _consulta_catalogo(mensagem):
        return produtos[:LIMITE_CATALOGO]

    termos = _extrair_termos(mensagem)
    if not termos:
        return []

    filtrados = _filtrar_produtos(produtos, mensagem)
    return filtrados


def buscar_produtos_para_atendimento(mensagem: str) -> dict:
    fonte = _fonte_configurada()
    erro_mercos = None

    if _consulta_catalogo(mensagem):
        produtos = buscar_produtos()[:LIMITE_CATALOGO]
        return {
            "produtos": produtos,
            "fonte": "supabase",
            "erro_mercos": None,
        }

    termos = _extrair_termos(mensagem)
    if not termos:
        return {
            "produtos": [],
            "fonte": "nenhum",
            "erro_mercos": None,
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
