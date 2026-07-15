"""Rotas HTTP locais para homologação beta Mercos.

Protegidas por SYNC_TOKEN (mesmo padrão dos diagnósticos).
Não ligam pedido automático do agente.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from services import mercos_homolog_service as homolog
from services.mercos_api_client import MercosApiError
from services.mercos_service import mercos_ambiente_sandbox, mercos_configurado

router = APIRouter(prefix="/mercos", tags=["mercos-homologacao"])

_QUERY_NAO_REPASSAR_TIPOS = frozenset({"token", "max_paginas", "nocache", "pagina"})


def _params_mercos_da_request(request: Request) -> dict[str, str]:
    """Repassa query params à Mercos, exceto controles locais da rota."""
    out: dict[str, str] = {}
    for chave, valor in request.query_params.multi_items():
        if chave.lower() in _QUERY_NAO_REPASSAR_TIPOS:
            continue
        texto = (valor or "").strip()
        if not texto:
            continue
        out[chave] = texto
    return out


def _bloqueio(token: str = "") -> None:
    abertos = os.getenv("DIAGNOSTICOS_ABERTOS", "false").strip().lower() in (
        "1",
        "true",
        "sim",
        "yes",
    )
    if abertos:
        return
    sync_token = os.getenv("SYNC_TOKEN", "").strip()
    if not sync_token:
        raise HTTPException(
            status_code=403,
            detail="Diagnósticos fechados. Defina SYNC_TOKEN ou DIAGNOSTICOS_ABERTOS=true",
        )
    if token != sync_token:
        raise HTTPException(status_code=403, detail="Token inválido")


def _http(exc: MercosApiError) -> HTTPException:
    code = int(exc.status_code or 502)
    if code < 400 or code > 599:
        code = 502
    return HTTPException(status_code=code, detail=str(exc.message))


def _params_paginacao(
    pagina: int,
    max_paginas: int,
) -> dict[str, int]:
    return {
        "pagina_inicial": max(1, pagina),
        "max_paginas": max(1, min(max_paginas, 50)),
    }


@router.get("/homologacao")
def mercos_homologacao_status(token: str = ""):
    """Inventário das rotas da ata + flags de ambiente (sem tokens)."""
    _bloqueio(token)
    return {
        "status": "ok",
        "checkout_create_order_agente": os.getenv("CHECKOUT_CREATE_ORDER", "false"),
        "mercos_configurado": mercos_configurado(),
        "mercos_sandbox": mercos_ambiente_sandbox(),
        "mercos_base_url_host": (
            "sandbox" if mercos_ambiente_sandbox() else "producao_ou_outro"
        ),
        **homolog.inventario_homologacao(),
    }


def _get_lista(fn, token: str, pagina: int, max_paginas: int) -> dict[str, Any]:
    _bloqueio(token)
    try:
        return fn(**_params_paginacao(pagina, max_paginas))
    except MercosApiError as exc:
        raise _http(exc) from exc


@router.get("/categorias")
def get_categorias(
    token: str = "",
    pagina: int = Query(1, ge=1),
    max_paginas: int = Query(5, ge=1, le=50),
):
    return _get_lista(homolog.listar_categorias, token, pagina, max_paginas)


@router.get("/clientes")
def get_clientes(
    token: str = "",
    pagina: int = Query(1, ge=1),
    max_paginas: int = Query(5, ge=1, le=50),
):
    return _get_lista(homolog.listar_clientes, token, pagina, max_paginas)


@router.post("/clientes")
def post_clientes(token: str = "", body: dict = Body(...)):
    _bloqueio(token)
    try:
        return homolog.criar_cliente(body)
    except MercosApiError as exc:
        raise _http(exc) from exc


@router.put("/clientes/{cliente_id}")
def put_clientes(cliente_id: str, token: str = "", body: dict = Body(...)):
    _bloqueio(token)
    try:
        return homolog.alterar_cliente(cliente_id, body)
    except MercosApiError as exc:
        raise _http(exc) from exc


@router.get("/condicoes-pagamento")
def get_condicoes(
    token: str = "",
    pagina: int = Query(1, ge=1),
    max_paginas: int = Query(5, ge=1, le=50),
):
    return _get_lista(homolog.listar_condicoes_pagamento, token, pagina, max_paginas)


@router.get("/produtos")
def get_produtos(
    token: str = "",
    pagina: int = Query(1, ge=1),
    max_paginas: int = Query(5, ge=1, le=50),
    alterado_apos: str = Query(""),
):
    """Lista produtos; repassa alterado_apos à Mercos (query, sem filtro local)."""
    _bloqueio(token)
    try:
        return homolog.listar_produtos(
            alterado_apos=(alterado_apos or "").strip() or None,
            **_params_paginacao(pagina, max_paginas),
        )
    except MercosApiError as exc:
        raise _http(exc) from exc


@router.get("/segmentos")
def get_segmentos(
    token: str = "",
    pagina: int = Query(1, ge=1),
    max_paginas: int = Query(5, ge=1, le=50),
):
    return _get_lista(homolog.listar_segmentos, token, pagina, max_paginas)


@router.get("/tabelas-preco")
def get_tabelas_preco(
    token: str = "",
    pagina: int = Query(1, ge=1),
    max_paginas: int = Query(5, ge=1, le=50),
):
    return _get_lista(homolog.listar_tabelas_preco, token, pagina, max_paginas)


@router.get("/tabelas-preco-produtos")
def get_tabelas_preco_produtos(
    token: str = "",
    pagina: int = Query(1, ge=1),
    max_paginas: int = Query(5, ge=1, le=50),
):
    """Listagem global — exige path Mercos válido (ver MERCOS_PATH_TABELAS_PRECO_PRODUTO)."""
    return _get_lista(homolog.listar_tabelas_preco_produto, token, pagina, max_paginas)


@router.get("/tabelas-preco/{tabela_id}/produtos")
def get_produtos_da_tabela(
    tabela_id: str,
    token: str = "",
    pagina: int = Query(1, ge=1),
    max_paginas: int = Query(5, ge=1, le=50),
):
    """Tabelas de preço por produto via nested path."""
    _bloqueio(token)
    try:
        return homolog.listar_produtos_da_tabela_preco(
            tabela_id, **_params_paginacao(pagina, max_paginas)
        )
    except MercosApiError as exc:
        raise _http(exc) from exc


@router.get("/tipos-pedido")
def get_tipos_pedido(
    request: Request,
    token: str = "",
    pagina: int = Query(1, ge=1),
    max_paginas: int = Query(5, ge=1, le=50),
):
    """Lista tipos de pedido; repassa query params à Mercos (sem filtro local).

    Controles locais não repassados: token, max_paginas, nocache, pagina.
    """
    _bloqueio(token)
    try:
        return homolog.listar_tipos_pedido(
            params_mercos=_params_mercos_da_request(request),
            **_params_paginacao(pagina, max_paginas),
        )
    except MercosApiError as exc:
        raise _http(exc) from exc


@router.get("/usuarios")
def get_usuarios(
    token: str = "",
    pagina: int = Query(1, ge=1),
    max_paginas: int = Query(5, ge=1, le=50),
):
    return _get_lista(homolog.listar_usuarios, token, pagina, max_paginas)


@router.post("/pedidos")
def post_pedidos(token: str = "", body: dict = Body(...)):
    _bloqueio(token)
    try:
        return homolog.criar_pedido(body)
    except MercosApiError as exc:
        raise _http(exc) from exc


@router.put("/pedidos/{pedido_id}")
def put_pedidos(pedido_id: str, token: str = "", body: dict = Body(...)):
    _bloqueio(token)
    try:
        return homolog.alterar_pedido(pedido_id, body)
    except MercosApiError as exc:
        raise _http(exc) from exc


@router.post("/titulos")
def post_titulos(token: str = "", body: dict = Body(...)):
    _bloqueio(token)
    try:
        return homolog.criar_titulo(body)
    except MercosApiError as exc:
        raise _http(exc) from exc


@router.put("/titulos/{titulo_id}")
def put_titulos(titulo_id: str, token: str = "", body: dict = Body(...)):
    _bloqueio(token)
    try:
        return homolog.alterar_titulo(titulo_id, body)
    except MercosApiError as exc:
        raise _http(exc) from exc
