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
import os

# Teto de segurança para listagens
MAX_PAGINAS_DEFAULT = 20
PAGE_SLEEP_SEGUNDOS = 0.35
MAX_RETRIES_429 = 3


class MercosApiError(Exception):
    """Erro seguro da API Mercos (sem token)."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


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
    json_body: dict | None = None,
    timeout: int = 30,
) -> requests.Response:
    """GET/POST/PUT na Mercos com retry de 429 (máx 3)."""
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

    for application_token in _application_tokens():
        for tentativa in range(MAX_RETRIES_429):
            resp = requests.request(
                method.upper(),
                url,
                headers=_headers(application_token),
                params=params,
                json=json_body,
                timeout=timeout,
            )
            if resp.status_code in (200, 201, 204):
                return resp
            if resp.status_code == 429:
                if tentativa < MAX_RETRIES_429 - 1:
                    retry_after = (resp.headers.get("Retry-After") or "").strip()
                    try:
                        espera = float(retry_after)
                    except (TypeError, ValueError):
                        espera = 10.0 * (tentativa + 1)
                    time.sleep(max(0.0, espera))
                    continue
                raise MercosApiError(
                    "Mercos retornou 429 (throttling). Aguarde e tente novamente.",
                    status_code=429,
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


def get_json(path: str, *, params: dict | None = None) -> Any:
    resp = request_mercos("GET", path, params=params)
    if resp.status_code == 204 or not (resp.text or "").strip():
        return []
    try:
        return resp.json()
    except Exception as exc:
        raise MercosApiError(f"Resposta Mercos inválida em GET {path}.", status_code=502) from exc


def listar_paginado(
    path: str,
    *,
    pagina_inicial: int = 1,
    max_paginas: int = MAX_PAGINAS_DEFAULT,
    page_size_hint: int = 50,
    params_extra: dict | None = None,
) -> dict[str, Any]:
    """Lista recursos com paginação segura (teto de páginas)."""
    pagina = max(1, int(pagina_inicial or 1))
    limite = max(1, min(int(max_paginas or MAX_PAGINAS_DEFAULT), 100))
    itens: list = []
    paginas_lidas = 0

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
        if len(lote) < page_size_hint:
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
    }


def put_json(path: str, body: dict) -> dict[str, Any]:
    resp = request_mercos("PUT", path, json_body=body or {})
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
    }
