import os
import re
import time
import unicodedata

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_URL = os.getenv("MERCOS_BASE_URL", "https://sandbox.mercos.com/api").rstrip("/")
LIMITE_CATALOGO = 20
SANDBOX_APPLICATION_TOKEN = "7a1540f6-642c-11e8-a500-72dcfa7a7c91"

STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "e", "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "que", "qual",
    "quais", "quanto", "quero", "preciso", "tem", "têm", "voce", "voces", "vc", "vcs",
    "oi", "ola", "bom", "dia", "tarde", "noite", "favor", "porfavor", "ver", "mostra",
    "manda", "me", "ta", "está", "esta", "isso", "esse", "essa", "aqui", "la", "lá",
    "valor", "preco", "preço", "custa", "sobre", "algum", "alguma",
}


def mercos_configurado() -> bool:
    return bool(
        os.getenv("MERCOS_APPLICATION_TOKEN")
        and os.getenv("MERCOS_COMPANY_TOKEN")
    )


def _application_tokens() -> list[str]:
    tokens = []

    for token in (
        os.getenv("MERCOS_APPLICATION_TOKEN", "").strip(),
        os.getenv("MERCOS_APPLICATION_TOKEN_FALLBACK", "").strip(),
        SANDBOX_APPLICATION_TOKEN,
    ):
        if token and token not in tokens:
            tokens.append(token)

    return tokens


def _headers(application_token: str) -> dict:
    return {
        "ApplicationToken": application_token,
        "CompanyToken": os.getenv("MERCOS_COMPANY_TOKEN", "").strip(),
        "Content-Type": "application/json",
    }


def _requisicao_mercos(pagina: int) -> requests.Response:
    company_token = os.getenv("MERCOS_COMPANY_TOKEN", "").strip()

    if not company_token:
        raise ValueError("MERCOS_COMPANY_TOKEN não configurado no .env")

    ultimo_erro = None

    for application_token in _application_tokens():
        for tentativa in range(3):
            resposta = requests.get(
                f"{BASE_URL}/v1/produtos",
                headers=_headers(application_token),
                params={"pagina": pagina},
                timeout=8,
            )

            if resposta.status_code == 200:
                return resposta

            if resposta.status_code == 429:
                if tentativa < 2:
                    time.sleep(10 * (tentativa + 1))
                    continue

                raise ValueError(
                    "Mercos sandbox retornou 429 (muitas requisições). "
                    "Aguarde 1 minuto e tente novamente."
                )

            if resposta.status_code == 401:
                ultimo_erro = resposta.text.strip() or "não autorizado"
                break

            resposta.raise_for_status()

    raise ValueError(
        "Mercos sandbox retornou 401 (não autorizado). "
        "Recopie o Company Token em https://sandbox.mercos.com "
        "(Minha conta → Sistema → Integração). "
        "Use o ApplicationToken da documentação Mercos "
        "(d39001ac-0b14-11f0-8ed7-6e1485be00f2). "
        "Se persistir, fale no chat da Mercos para vincular sua empresa ao aplicativo. "
        f"Detalhe: {ultimo_erro}"
    )


def _normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


def _extrair_termos(mensagem: str) -> list[str]:
    mensagem = _normalizar_texto(mensagem)
    palavras = re.findall(r"[a-z0-9]+", mensagem)
    return [p for p in palavras if len(p) >= 3 and p not in STOPWORDS]


def _produto_ativo(produto: dict) -> bool:
    if produto.get("excluido"):
        return False
    if produto.get("ativo") is False:
        return False
    return True


def _valor_preco(produto: dict):
    for campo in ("preco_tabela", "preco", "preco_venda", "preco_unitario"):
        valor = produto.get(campo)
        if valor is not None:
            return valor
    return 0


def _valor_estoque(produto: dict):
    for campo in ("saldo_estoque", "estoque", "quantidade_estoque", "saldo"):
        valor = produto.get(campo)
        if valor is not None:
            return valor
    return 0


def normalizar_produto(produto: dict) -> dict:
    return {
        "nome": produto.get("nome", ""),
        "codigo": produto.get("codigo", ""),
        "categoria": produto.get("categoria_nome") or produto.get("categoria", ""),
        "preco": _valor_preco(produto),
        "estoque": _valor_estoque(produto),
        "descricao": produto.get("observacoes") or produto.get("descricao") or "",
    }


def buscar_produtos_mercos() -> list[dict]:
    produtos = []
    pagina = 1

    while True:
        resposta = _requisicao_mercos(pagina)
        lote = resposta.json()

        if isinstance(lote, dict):
            lote = lote.get("produtos") or lote.get("data") or lote.get("results") or []

        if not lote:
            break

        produtos.extend(lote)

        if len(lote) < 50:
            break

        pagina += 1

    return [p for p in produtos if _produto_ativo(p)]


def _produto_corresponde(produto: dict, termos: list[str]) -> bool:
    texto = _normalizar_texto(
        " ".join(
            str(produto.get(campo, "") or "")
            for campo in ("nome", "codigo", "observacoes", "descricao", "categoria_nome")
        )
    )
    return any(termo in texto for termo in termos)


def buscar_produtos_por_termo(mensagem: str) -> list[dict]:
    termos = _extrair_termos(mensagem)
    produtos_mercos = buscar_produtos_mercos()

    if not termos:
        return []

    encontrados = [p for p in produtos_mercos if _produto_corresponde(p, termos)]
    return [normalizar_produto(p) for p in encontrados[:LIMITE_CATALOGO]]


def buscar_produtos_para_atendimento(mensagem: str) -> list[dict]:
    if not mercos_configurado():
        raise ValueError(
            "Mercos não configurada. Defina MERCOS_APPLICATION_TOKEN e MERCOS_COMPANY_TOKEN no .env"
        )

    produtos = buscar_produtos_por_termo(mensagem)

    if produtos:
        return produtos

    termos = _extrair_termos(mensagem)
    if termos:
        return []

    return []


def montar_catalogo_texto(produtos: list[dict]) -> str:
    if not produtos:
        return "Nenhum produto encontrado no catálogo para esta consulta.\n"

    catalogo = ""
    for produto in produtos:
        estoque = produto.get("estoque")
        if estoque in (None, "", 0, "0"):
            estoque_texto = "disponível"
        else:
            estoque_texto = str(estoque)

        descricao = produto.get("descricao", "") or ""
        if len(descricao) > 120:
            descricao = descricao[:120] + "..."

        catalogo += (
            f"Nome: {produto['nome']}\n"
            f"Preço: R$ {produto['preco']}\n"
            f"Estoque: {estoque_texto}\n"
            f"Categoria: {produto.get('categoria', '')}\n"
            f"Descrição: {descricao}\n\n"
        )
    return catalogo
