"""Cliente HTTP Mercos para homologação beta.

Reutiliza autenticação/env de mercos_service.
Não loga tokens. Trata 429 com retry limitado. Paginação com teto.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from services.mercos_service import (
    BASE_URL,
    _application_tokens,
    mercos_ambiente_sandbox,
    mercos_configurado,
)
from services import mercos_throttle
import os

# Teto de segurança para listagens
MAX_PAGINAS_DEFAULT = 20
PAGE_SLEEP_SEGUNDOS = 0.35
MAX_RETRIES_429 = 3


class MercosApiError(Exception):
    """Erro seguro da API Mercos (sem token)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
        pagina: int | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.retry_after = retry_after
        self.pagina = pagina


def _headers(application_token: str) -> dict[str, str]:
    return {
        "ApplicationToken": application_token,
        "CompanyToken": os.getenv("MERCOS_COMPANY_TOKEN", "").strip(),
        "Content-Type": "application/json",
    }


def _mensagem_segura(status: int, body: str) -> str:
    trecho = (body or "").strip().replace("\n", " ")[:180]
    # Nunca ecoar padrões óbvios de token
    lower = trecho.lower()
    for bad in ("companytoken", "applicationtoken", "bearer ", "token="):
        if bad in lower:
            trecho = "(corpo omitido)"
            break
    return f"Mercos HTTP {status}: {trecho or 'sem detalhe'}"


def request_mercos(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | list | None = None,
    timeout: int | float = 30,
    max_retries_429: int = MAX_RETRIES_429,
    intervalo_minimo: float | None = None,
) -> requests.Response:
    """GET/POST/PUT na Mercos com retry de 429 (configurável).

    ``json_body`` aceita dict (maioria das entidades) ou list quando a API exigir.
    ``intervalo_minimo`` opcional sobrepõe o piso desta chamada no throttle
    global (ex.: homologação de ajuste de estoque com piso maior).
    """
    if not mercos_configurado():
        raise MercosApiError(
            "Mercos não configurada. Defina MERCOS_APPLICATION_TOKEN e MERCOS_COMPANY_TOKEN.",
            status_code=503,
        )
    company = os.getenv("MERCOS_COMPANY_TOKEN", "").strip()
    if not company:
        raise MercosApiError("MERCOS_COMPANY_TOKEN não configurado.", status_code=503)

    url = f"{BASE_URL.rstrip('/')}{path}"
    ultimo_401 = ""
    retries_cfg = int(max_retries_429)
    # max_retries_429<=0 → 1 tentativa (sem retry). Default 3 = comportamento histórico.
    max_attempts = 1 if retries_cfg <= 0 else retries_cfg

    for application_token in _application_tokens():
        for tentativa in range(max_attempts):
            # Throttling GLOBAL e persistente por CompanyToken: antes de QUALQUER
            # requisição (GET/POST/PUT, páginas extras e retentativas) aguarda o
            # intervalo mínimo desde a última chamada persistida (sobrevive a
            # reinícios e a chamadas de outros processos/rotas) e registra
            # atomicamente o novo início, mantendo o lock de arquivo durante o
            # envio para serializar processos locais.
            try:
                resp, _throttle_info = mercos_throttle.executar(
                    method,
                    path,
                    lambda: requests.request(
                        method.upper(),
                        url,
                        headers=_headers(application_token),
                        params=params,
                        json=json_body,
                        timeout=timeout,
                    ),
                    intervalo_minimo=intervalo_minimo,
                )
            except requests.Timeout as exc:
                raise MercosApiError(
                    "Timeout na chamada à Mercos.",
                    status_code=504,
                ) from exc
            except requests.RequestException as exc:
                raise MercosApiError(
                    "Falha de rede ao chamar a Mercos.",
                    status_code=502,
                ) from exc
            if resp.status_code in (200, 201, 204):
                return resp
            if resp.status_code == 429:
                retry_raw = (resp.headers.get("Retry-After") or "").strip()
                retry_val: float | None = None
                if retry_raw:
                    try:
                        retry_val = float(retry_raw)
                    except (TypeError, ValueError):
                        retry_val = None
                if tentativa < max_attempts - 1:
                    if retry_val is not None:
                        # Reagenda no limiter global: a próxima tentativa aguarda
                        # o Retry-After sem nunca reduzir o piso de intervalo.
                        mercos_throttle.aplicar_retry_after(retry_val)
                    else:
                        time.sleep(max(0.0, 10.0 * (tentativa + 1)))
                    continue
                raise MercosApiError(
                    "Mercos retornou 429 (throttling). Aguarde e tente novamente.",
                    status_code=429,
                    retry_after=retry_val,
                )
            if resp.status_code == 401:
                ultimo_401 = (resp.text or "")[:120]
                break  # tenta próximo application token
            raise MercosApiError(
                _mensagem_segura(resp.status_code, resp.text),
                status_code=resp.status_code,
            )

    raise MercosApiError(
        "Mercos retornou 401 (não autorizado). Verifique MERCOS_COMPANY_TOKEN.",
        status_code=401,
    )


def _extrair_lista(payload: Any) -> list:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for chave in ("data", "results", "items", "produtos", "clientes", "registros"):
            valor = payload.get(chave)
            if isinstance(valor, list):
                return valor
    return []


def get_json(
    path: str,
    *,
    params: dict | None = None,
    timeout: int | float = 30,
    max_retries_429: int = MAX_RETRIES_429,
) -> Any:
    payload, _headers_resp = get_json_com_headers(
        path,
        params=params,
        timeout=timeout,
        max_retries_429=max_retries_429,
    )
    return payload


def get_json_com_headers(
    path: str,
    *,
    params: dict | None = None,
    timeout: int | float = 30,
    max_retries_429: int = MAX_RETRIES_429,
) -> tuple[Any, dict[str, str]]:
    """GET que retorna (payload, headers) — headers para paginação Mercos
    (MEUSPEDIDOS_LIMITOU_REGISTROS / QTDE_TOTAL_REGISTROS / REQUISICOES_EXTRAS)."""
    resp = request_mercos(
        "GET",
        path,
        params=params,
        timeout=timeout,
        max_retries_429=max_retries_429,
    )
    headers = dict(resp.headers or {})
    if resp.status_code == 204 or not (resp.text or "").strip():
        return [], headers
    try:
        return resp.json(), headers
    except Exception as exc:
        raise MercosApiError(f"Resposta Mercos inválida em GET {path}.", status_code=502) from exc


def listar_paginado(
    path: str,
    *,
    pagina_inicial: int = 1,
    max_paginas: int = MAX_PAGINAS_DEFAULT,
    page_size_hint: int | None = 50,
    params_extra: dict | None = None,
) -> dict[str, Any]:
    """Lista recursos com paginação segura (teto de páginas).

    Para quando o lote vem vazio ou atinge max_paginas.
    Se page_size_hint > 0, também para cedo quando o lote tem menos itens
    que o hint (economiza um request vazio). Use page_size_hint=0/None para
    percorrer até a página vazia (ex.: clientes com página menor que 50).
    """
    pagina = max(1, int(pagina_inicial or 1))
    limite = max(1, min(int(max_paginas or MAX_PAGINAS_DEFAULT), 100))
    itens: list = []
    paginas_lidas = 0
    hint = int(page_size_hint or 0)

    for _ in range(limite):
        params = {"pagina": pagina}
        if params_extra:
            params.update(params_extra)
        payload = get_json(path, params=params)
        lote = _extrair_lista(payload)
        paginas_lidas += 1
        if not lote:
            break
        itens.extend(lote)
        if hint > 0 and len(lote) < hint:
            break
        pagina += 1
        time.sleep(PAGE_SLEEP_SEGUNDOS)

    return {
        "ok": True,
        "path": path,
        "total": len(itens),
        "paginas_lidas": paginas_lidas,
        "sandbox": mercos_ambiente_sandbox(),
        "itens": itens,
    }


def post_json(path: str, body: dict) -> dict[str, Any]:
    resp = request_mercos("POST", path, json_body=body or {})
    # Metadata do throttling DESTA execução (mesma chamada que gravou o estado).
    throttle_info = mercos_throttle.ultima_execucao_info()
    dados: Any = {}
    if (resp.text or "").strip():
        try:
            dados = resp.json()
        except Exception:
            dados = {}
    if not isinstance(dados, dict):
        dados = {"data": dados}
    mercos_id = (
        resp.headers.get("MeusPedidosID")
        or resp.headers.get("meuspedidosid")
        or dados.get("id")
    )
    return {
        "ok": True,
        "status_code": resp.status_code,
        "id": mercos_id,
        "sandbox": mercos_ambiente_sandbox(),
        "dados": dados,
        "throttle": throttle_info,
    }


def put_json(
    path: str,
    body: dict | list | None,
    *,
    max_retries_429: int = MAX_RETRIES_429,
    intervalo_minimo: float | None = None,
) -> dict[str, Any]:
    """PUT na Mercos. Body tipicamente dict; list só se a entidade exigir."""
    if body is None:
        payload: dict | list = {}
    else:
        payload = body
    resp = request_mercos(
        "PUT",
        path,
        json_body=payload,
        max_retries_429=max_retries_429,
        intervalo_minimo=intervalo_minimo,
    )
    throttle_info = mercos_throttle.ultima_execucao_info()
    dados: Any = {}
    if (resp.text or "").strip():
        try:
            dados = resp.json()
        except Exception:
            dados = {}
    if not isinstance(dados, dict):
        dados = {"data": dados}
    return {
        "ok": True,
        "status_code": resp.status_code,
        "sandbox": mercos_ambiente_sandbox(),
        "dados": dados,
        "throttle": throttle_info,
        "path": path,
        "method": "PUT",
    }
