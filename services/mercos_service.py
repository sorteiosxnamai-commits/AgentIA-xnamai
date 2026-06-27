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
CACHE_TTL_SEGUNDOS = int(os.getenv("MERCOS_CACHE_SEGUNDOS", "600"))

_cache_produtos: dict = {"dados": None, "expira_em": 0.0}

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


def mercos_ambiente_sandbox() -> bool:
    return "sandbox" in BASE_URL.lower()


def invalidar_cache_produtos_mercos() -> None:
    _cache_produtos["dados"] = None
    _cache_produtos["expira_em"] = 0.0


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


def _executar_requisicao_mercos(
    method: str,
    path: str,
    params: dict | None = None,
    json_body: dict | None = None,
    timeout: int = 15,
) -> requests.Response:
    company_token = os.getenv("MERCOS_COMPANY_TOKEN", "").strip()

    if not company_token:
        raise ValueError("MERCOS_COMPANY_TOKEN não configurado no .env")

    ultimo_erro = None
    url = f"{BASE_URL}{path}"

    for application_token in _application_tokens():
        for tentativa in range(3):
            resposta = requests.request(
                method,
                url,
                headers=_headers(application_token),
                params=params,
                json=json_body,
                timeout=timeout,
            )

            if resposta.status_code in (200, 201):
                return resposta

            if resposta.status_code == 429:
                if tentativa < 2:
                    time.sleep(10 * (tentativa + 1))
                    continue

                raise ValueError(
                    "Mercos retornou 429 (muitas requisições). "
                    "Aguarde 1 minuto e tente novamente."
                )

            if resposta.status_code == 401:
                ultimo_erro = resposta.text.strip() or "não autorizado"
                break

            return resposta

    raise ValueError(
        "Mercos retornou 401 (não autorizado). Verifique MERCOS_COMPANY_TOKEN. "
        f"Detalhe: {ultimo_erro}"
    )


def _requisicao_mercos(pagina: int) -> requests.Response:
    return _executar_requisicao_mercos(
        "GET",
        "/v1/produtos",
        params={"pagina": pagina},
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


def ocultar_produtos_exemplo() -> bool:
    return os.getenv("MERCOS_OCULTAR_EXEMPLOS", "true").strip().lower() in (
        "1",
        "true",
        "sim",
        "yes",
    )


def eh_produto_exemplo(produto: dict) -> bool:
    nome = _normalizar_texto(str(produto.get("nome") or ""))
    return "[exemplo]" in nome


def _filtrar_catalogo(produtos: list[dict]) -> list[dict]:
    if not ocultar_produtos_exemplo():
        return produtos
    return [p for p in produtos if not eh_produto_exemplo(p)]


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


def extrair_imagem_mercos(produto: dict) -> str:
    """Extrai URL de imagem se a Mercos enviar no JSON do produto."""
    for campo in (
        "imagem_url",
        "imagem",
        "url_imagem",
        "foto",
        "foto_url",
        "url_foto",
        "link_imagem",
    ):
        url = str(produto.get(campo) or "").strip()
        if url.startswith("http"):
            return url

    for campo in ("imagens", "fotos", "anexos", "arquivos"):
        itens = produto.get(campo)
        if not isinstance(itens, list):
            continue

        for item in itens:
            if isinstance(item, str) and item.startswith("http"):
                return item

            if isinstance(item, dict):
                for chave in ("url", "link", "imagem_url", "arquivo_url", "caminho"):
                    url = str(item.get(chave) or "").strip()
                    if url.startswith("http"):
                        return url

    return ""


def normalizar_produto(produto: dict) -> dict:
    imagem = extrair_imagem_mercos(produto)
    return {
        "nome": produto.get("nome", ""),
        "codigo": produto.get("codigo", ""),
        "categoria": produto.get("categoria_nome") or produto.get("categoria", ""),
        "preco": _valor_preco(produto),
        "estoque": _valor_estoque(produto),
        "descricao": produto.get("observacoes") or produto.get("descricao") or "",
        "imagem_url": imagem,
    }


def buscar_produtos_mercos() -> list[dict]:
    agora = time.time()
    if _cache_produtos["dados"] is not None and agora < _cache_produtos["expira_em"]:
        return _cache_produtos["dados"]

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
        time.sleep(0.3)

    ativos = [p for p in produtos if _produto_ativo(p)]
    ativos = _filtrar_catalogo(ativos)
    _cache_produtos["dados"] = ativos
    _cache_produtos["expira_em"] = agora + CACHE_TTL_SEGUNDOS
    return ativos


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


def buscar_produto_bruto_por_mensagem(mensagem: str) -> dict | None:
    termos = _extrair_termos(mensagem)
    if not termos:
        return None

    for produto in buscar_produtos_mercos():
        if _produto_corresponde(produto, termos):
            return produto

    return None


def criar_cliente_mercos(
    nome: str,
    telefone: str = "",
    observacao: str = "",
) -> int:
    payload = {
        "razao_social": (nome or "Cliente WhatsApp")[:100],
        "nome_fantasia": (nome or "Cliente WhatsApp")[:100],
        "tipo": "F",
        "observacao": observacao[:500] if observacao else "Cliente via WhatsApp Agent IA",
    }

    if telefone:
        payload["telefones"] = [{"numero": telefone}]

    resposta = _executar_requisicao_mercos("POST", "/v1/clientes", json_body=payload)

    if resposta.status_code not in (200, 201):
        raise ValueError(
            f"Erro ao criar cliente Mercos ({resposta.status_code}): {resposta.text[:300]}"
        )

    mercos_id = resposta.headers.get("MeusPedidosID")
    if mercos_id:
        return int(mercos_id)

    dados = resposta.json() if resposta.text.strip() else {}
    if dados.get("id"):
        return int(dados["id"])

    raise ValueError("Cliente criado no Mercos, mas ID não retornado.")


def criar_pedido_mercos(
    cliente_id: int,
    produto_id: int,
    quantidade: float,
    preco_bruto: float,
    condicao_pagamento: str,
    observacoes: str = "",
) -> dict:
    from datetime import date

    payload = {
        "cliente_id": cliente_id,
        "data_emissao": date.today().isoformat(),
        "condicao_pagamento": condicao_pagamento,
        "observacoes": observacoes[:500],
        "itens": [
            {
                "produto_id": produto_id,
                "quantidade": quantidade,
                "preco_bruto": round(float(preco_bruto), 2),
            }
        ],
    }

    resposta = _executar_requisicao_mercos("POST", "/v1/pedidos", json_body=payload)

    if resposta.status_code not in (200, 201):
        raise ValueError(
            f"Erro ao criar pedido Mercos ({resposta.status_code}): {resposta.text[:300]}"
        )

    return resposta.json() if resposta.text.strip() else {}


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
