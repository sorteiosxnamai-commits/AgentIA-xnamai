import os
import re
import time
import unicodedata

import requests
from services import mercos_throttle
from services.env_loader import carregar_env

carregar_env()

def _sanitizar_base_url(url: str) -> str:
    """Remove '=' acidental do Render e sufixo /v1|/v2 (paths já incluem a versão)."""
    limpa = (url or "").strip().lstrip("=").rstrip("/")
    for sufixo in ("/v1", "/v2"):
        if limpa.lower().endswith(sufixo):
            limpa = limpa[: -len(sufixo)]
            break
    return limpa or "https://sandbox.mercos.com/api"


BASE_URL = _sanitizar_base_url(
    os.getenv("MERCOS_BASE_URL", "https://sandbox.mercos.com/api")
)
LIMITE_CATALOGO = 20
SANDBOX_APPLICATION_TOKEN = "7a1540f6-642c-11e8-a500-72dcfa7a7c91"
CACHE_TTL_SEGUNDOS = int(os.getenv("MERCOS_CACHE_SEGUNDOS", "600"))

_cache_produtos: dict = {"dados": None, "expira_em": 0.0, "meta": {}}

STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "e", "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "que", "qual",
    "quais", "quanto", "quero", "preciso", "tem", "têm", "voce", "voces", "vc", "vcs",
    "oi", "ola", "bom", "dia", "tarde", "noite", "favor", "porfavor", "ver", "mostra",
    "manda", "mande", "passa", "envia", "envie", "me", "ta", "está", "esta", "isso",
    "esse", "essa", "aqui", "la", "lá",
    "valor", "preco", "preço", "custa", "sobre", "algum", "alguma",
    "catalogo", "produtos", "produto", "opcoes", "opcao", "lista", "disponivel",
    "vender", "vendem", "vende", "algo", "disponiveis",
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
    _cache_produtos["meta"] = {}


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
            # Passa OBRIGATORIAMENTE pelo throttling global persistente por
            # CompanyToken (mesmo limiter do mercos_api_client): nenhuma chamada
            # Mercos deste cliente direto pode sair fora do controle global.
            resposta, _throttle_info = mercos_throttle.executar(
                method,
                path,
                lambda: requests.request(
                    method,
                    url,
                    headers=_headers(application_token),
                    params=params,
                    json=json_body,
                    timeout=timeout,
                ),
                origem="mercos_service",
            )

            if resposta.status_code in (200, 201):
                return resposta

            if resposta.status_code == 429:
                if tentativa < 2:
                    mercos_throttle.aplicar_retry_after(10 * (tentativa + 1))
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


def _requisicao_produtos(params: dict | None = None) -> requests.Response:
    """GET /v1/produtos — sem ``pagina``; paginação via ``alterado_apos``."""
    return _executar_requisicao_mercos("GET", "/v1/produtos", params=params)


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
        if valor not in (None, ""):
            return valor
    return None


def estoque_confirmado(produto: dict) -> bool:
    """True só quando há quantidade numérica > 0 no catálogo."""
    bruto = _valor_estoque(produto)
    if bruto in (None, ""):
        return False
    try:
        return float(str(bruto).replace(",", ".")) > 0
    except (TypeError, ValueError):
        return False


def _texto_estoque_catalogo(produto: dict) -> str:
    """Nunca afirma disponibilidade sem estoque real."""
    bruto = _valor_estoque(produto)
    if bruto in (None, ""):
        return "não confirmado (verificar disponibilidade)"
    try:
        qtd = float(str(bruto).replace(",", "."))
    except (TypeError, ValueError):
        return "não confirmado (verificar disponibilidade)"
    if qtd > 0:
        if qtd == int(qtd):
            return str(int(qtd))
        return str(qtd)
    return "0 (sem saldo confirmado)"


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


_DEFAULT_ALTERADO_APOS = "2000-01-01T00:00:00"
_HEADER_LIMITOU = "MEUSPEDIDOS_LIMITOU_REGISTROS"
_HEADER_QTDE_TOTAL = "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS"
_HEADER_EXTRAS = "MEUSPEDIDOS_REQUISICOES_EXTRAS"


def _produtos_alterado_apos_inicial() -> str:
    return (
        os.getenv("MERCOS_PRODUTOS_ALTERADO_APOS", _DEFAULT_ALTERADO_APOS).strip()
        or _DEFAULT_ALTERADO_APOS
    )


def _produtos_max_chamadas() -> int:
    try:
        n = int(os.getenv("MERCOS_PRODUTOS_MAX_CHAMADAS", "100"))
    except ValueError:
        n = 100
    return max(1, min(n, 500))


def _header_int_ci(headers, nome: str) -> int | None:
    if headers is None:
        return None
    alvo = nome.lower()
    try:
        items = headers.items()
    except Exception:
        return None
    for k, v in items:
        if str(k).lower() == alvo:
            try:
                return int(str(v).strip())
            except (TypeError, ValueError):
                return None
    return None


def _maior_ultima_alteracao(itens: list) -> str | None:
    maior: str | None = None
    for item in itens:
        if not isinstance(item, dict):
            continue
        bruto = item.get("ultima_alteracao")
        if bruto is None or bruto == "":
            continue
        texto = str(bruto)
        if maior is None or texto > maior:
            maior = texto
    return maior


def _log_detalhado_produtos() -> bool:
    return os.getenv("SYNC_PRODUTOS_LOG_DETALHADO", "").strip().lower() in (
        "1",
        "true",
        "sim",
        "yes",
    )


def _atualizar_total_informado(atual: int | None, novo: int | None) -> int | None:
    """Preserva o maior QTDE_TOTAL visto (não o residual do último lote)."""
    if novo is None:
        return atual
    if atual is None:
        return novo
    return max(atual, novo)


def buscar_produtos_mercos_detalhado(*, usar_cache: bool = True) -> dict:
    """Busca paginada com metadados (chamadas, totais, filtros).

    Retorna dict com produtos ativos e estatísticas — sem log por item
    ignorado (salvo SYNC_PRODUTOS_LOG_DETALHADO=true).
    """
    from services.webhook_guard import log_seguro

    agora = time.time()
    if (
        usar_cache
        and _cache_produtos["dados"] is not None
        and agora < _cache_produtos["expira_em"]
    ):
        meta = dict(_cache_produtos.get("meta") or {})
        return {
            "produtos": list(_cache_produtos["dados"]),
            **meta,
        }

    cursor = _produtos_alterado_apos_inicial()
    max_chamadas = _produtos_max_chamadas()
    por_id: dict[str, dict] = {}
    chamadas = 0
    total_informado: int | None = None
    extras_atual: int | None = None
    detalhado = _log_detalhado_produtos()

    print("buscar_produtos_mercos: início da consulta", flush=True)

    while chamadas < max_chamadas:
        params = {
            "excluido": "false",
            "alterado_apos": cursor,
        }
        params.pop("pagina", None)

        try:
            resposta = _requisicao_produtos(params)
        except Exception as exc:
            nome = type(exc).__name__
            if "Timeout" in nome or "timeout" in str(exc).lower():
                raise ValueError(
                    "Mercos GET /v1/produtos: timeout na leitura. "
                    "Aumente o timeout ou tente novamente. "
                    f"Detalhe={nome}"
                ) from exc
            raise
        chamadas += 1

        status = getattr(resposta, "status_code", None)
        if status not in (200, 201):
            raise ValueError(
                f"Mercos GET /v1/produtos: HTTP {status} (esperado 200)"
            )

        lote = resposta.json()
        if not isinstance(lote, list):
            print(
                "buscar_produtos_mercos: resposta não é lista "
                f"(tipo={type(lote).__name__})",
                flush=True,
            )
            raise ValueError(
                "Mercos GET /v1/produtos: resposta esperada é lista, "
                f"recebido {type(lote).__name__}"
            )

        headers = getattr(resposta, "headers", None) or {}
        limitou = _header_int_ci(headers, _HEADER_LIMITOU)
        total_lote = _header_int_ci(headers, _HEADER_QTDE_TOTAL)
        total_informado = _atualizar_total_informado(total_informado, total_lote)
        extras_atual = _header_int_ci(headers, _HEADER_EXTRAS)

        novos_no_lote = 0
        for p in lote:
            if not isinstance(p, dict):
                continue
            mid = p.get("id")
            if mid is None or mid == "":
                continue
            chave = str(mid)
            if chave not in por_id:
                por_id[chave] = p
                novos_no_lote += 1

        max_ua = _maior_ultima_alteracao(lote)

        print(
            f"buscar_produtos_mercos: lote={chamadas} "
            f"recebidos_lote={len(lote)} "
            f"acumulado_unico={len(por_id)} "
            f"cursor={cursor} "
            f"total_mercos={total_informado if total_informado is not None else '-'} "
            f"extras={extras_atual if extras_atual is not None else '-'}",
            flush=True,
        )

        if not lote:
            break

        if limitou is None or limitou == 0:
            break

        if extras_atual is not None and extras_atual <= 0:
            break

        if max_ua is None:
            raise ValueError(
                "Mercos GET /v1/produtos: lote limitado sem ultima_alteracao "
                "para avançar o cursor alterado_apos"
            )

        if max_ua == cursor and novos_no_lote == 0:
            raise ValueError(
                "Mercos GET /v1/produtos: cursor alterado_apos sem progresso "
                f"(cursor={cursor}, lote={chamadas}, acumulado={len(por_id)})"
            )

        cursor = max_ua
    else:
        raise ValueError(
            f"Mercos GET /v1/produtos: limite de segurança de {max_chamadas} "
            f"chamadas atingido (acumulado={len(por_id)}, "
            f"total_mercos={total_informado})"
        )

    ocultar_exemplos = ocultar_produtos_exemplo()
    ativos: list[dict] = []
    excluidos = 0
    inativos = 0
    exemplos = 0
    for p in por_id.values():
        mid = p.get("id")
        codigo = str(p.get("codigo") or "")[:40] or "-"
        nome = str(p.get("nome") or "")[:80] or "-"

        if p.get("excluido"):
            excluidos += 1
            if detalhado:
                log_seguro(
                    "sync_produto_ignorado",
                    motivo="excluido",
                    mercos_id=mid if mid is not None else "-",
                    codigo=codigo,
                    nome=nome,
                )
            continue

        if p.get("ativo") is False:
            inativos += 1
            if detalhado:
                log_seguro(
                    "sync_produto_ignorado",
                    motivo="inativo",
                    mercos_id=mid if mid is not None else "-",
                    codigo=codigo,
                    nome=nome,
                )
            continue

        if ocultar_exemplos and eh_produto_exemplo(p):
            exemplos += 1
            if detalhado:
                log_seguro(
                    "sync_produto_ignorado",
                    motivo="produto_exemplo",
                    mercos_id=mid if mid is not None else "-",
                    codigo=codigo,
                    nome=nome,
                )
            continue

        ativos.append(p)

    meta = {
        "chamadas_mercos": chamadas,
        "total_informado_mercos": total_informado,
        "unicos_recebidos": len(por_id),
        "excluidos": excluidos,
        "inativos": inativos,
        "exemplos_ocultos": exemplos,
        "ativos_processados": len(ativos),
    }
    _cache_produtos["dados"] = ativos
    _cache_produtos["expira_em"] = agora + CACHE_TTL_SEGUNDOS
    _cache_produtos["meta"] = meta

    print(
        f"buscar_produtos_mercos: finalização "
        f"chamadas={chamadas} "
        f"unicos={len(por_id)} "
        f"ativos={len(ativos)} "
        f"excluidos={excluidos} "
        f"inativos={inativos} "
        f"total_mercos={total_informado if total_informado is not None else '-'}",
        flush=True,
    )
    return {"produtos": ativos, **meta}


def buscar_produtos_mercos() -> list[dict]:
    """Lista produtos Mercos ativos (compatível com catálogo/agente)."""
    return list(buscar_produtos_mercos_detalhado().get("produtos") or [])


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
        "condicao_pagamento": condicao_pagamento or "a vista",
        "observacoes": observacoes[:500],
        "itens": [
            {
                "produto_id": produto_id,
                "quantidade": quantidade,
                "preco_tabela": round(float(preco_bruto), 2),
            }
        ],
    }

    # API v2 (mesma usada no PulseDesk / homologação)
    resposta = _executar_requisicao_mercos("POST", "/v2/pedidos", json_body=payload)

    if resposta.status_code not in (200, 201):
        raise ValueError(
            f"Erro ao criar pedido Mercos ({resposta.status_code}): {resposta.text[:300]}"
        )

    body = resposta.json() if resposta.text.strip() else {}
    pedido_id = (
        body.get("id")
        or resposta.headers.get("meuspedidosid")
        or resposta.headers.get("MeusPedidosID")
    )
    if pedido_id is not None and "id" not in body:
        body["id"] = int(pedido_id) if str(pedido_id).isdigit() else pedido_id
    return body


def montar_catalogo_texto(produtos: list[dict]) -> str:
    if not produtos:
        return "Nenhum produto encontrado no catálogo para esta consulta.\n"

    catalogo = ""
    for produto in produtos:
        estoque_texto = _texto_estoque_catalogo(produto)

        descricao = produto.get("descricao", "") or produto.get("observacoes", "") or ""
        if len(descricao) > 120:
            descricao = descricao[:120] + "..."

        catalogo += (
            f"Nome: {produto.get('nome', '')}\n"
            f"Preço: R$ {_valor_preco(produto)}\n"
            f"Estoque: {estoque_texto}\n"
            f"Categoria: {produto.get('categoria', '') or produto.get('categoria_nome', '')}\n"
            f"Descrição: {descricao}\n\n"
        )
    return catalogo
