"""UI visual isolada para evidências de homologação Mercos (prints).

Não altera rotas JSON /mercos/produtos|clientes|pedidos|titulos.
Não cria recursos na abertura da página — só nos POSTs de ação.
"""

from __future__ import annotations

import base64
import html
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from services import mercos_homolog_service as homolog
from services import mercos_clientes_catalogo as catalogo_clientes
from services import mercos_produtos_catalogo as catalogo_produtos
from services import mercos_usuarios_catalogo as catalogo_usuarios
from services import mercos_pedidos_catalogo as catalogo_pedidos
from services import mercos_tipos_pedido_catalogo as catalogo_tipos_pedido
from services import mercos_pagamentos_catalogo as catalogo_pagamentos
from services import mercos_condicoes_pagamento_catalogo as catalogo_condicoes
from services.mercos_api_client import MercosApiError
from services.mercos_service import mercos_ambiente_sandbox, mercos_configurado

router = APIRouter(prefix="/mercos", tags=["mercos-homologacao-ui"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_COOKIE = "mercos_homolog_ui"
_COOKIE_MAX_AGE = 60 * 60 * 8
_COOKIE_PRODUTOS_CURSOR = "mercos_produtos_cursor"
_COOKIE_PRODUTOS_SESSAO = "mercos_produtos_sessao"
_COOKIE_CLIENTES_CURSOR = "mercos_clientes_cursor"
_COOKIE_CLIENTES_SESSAO = "mercos_clientes_sessao"
_COOKIE_USUARIOS_CURSOR = "mercos_usuarios_cursor"
_COOKIE_USUARIOS_SESSAO = "mercos_usuarios_sessao"
_COOKIE_PEDIDOS_CURSOR = "mercos_pedidos_cursor"
_COOKIE_PEDIDOS_SESSAO = "mercos_pedidos_sessao"
_COOKIE_TIPOS_CURSOR = "mercos_tipos_pedido_cursor"
_COOKIE_TIPOS_SESSAO = "mercos_tipos_pedido_sessao"
_COOKIE_PAGAMENTOS_CURSOR = "mercos_pagamentos_cursor"
_COOKIE_PAGAMENTOS_SESSAO = "mercos_pagamentos_sessao"
_COOKIE_CONDICOES_CURSOR = "mercos_condicoes_pagamento_cursor"
_COOKIE_CONDICOES_SESSAO = "mercos_condicoes_pagamento_sessao"
_CURSOR_MAX_AGE = 60 * 60 * 24 * 30
_SESSAO_MAX_AGE = 60 * 60 * 24 * 30


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


def _token_request(
    request: Request,
    token: str = "",
    token_form: str = "",
) -> str:
    return (
        (token or "").strip()
        or (token_form or "").strip()
        or (request.cookies.get(_COOKIE) or "").strip()
        or (request.query_params.get("token") or "").strip()
    )


def _esc(valor: Any) -> str:
    if valor is None:
        return "—"
    return html.escape(str(valor))


def _agora_br() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M:%S")


def _status_visual() -> tuple[str, str]:
    """Retorna (rótulo, classe css)."""
    if not mercos_configurado():
        return "Erro", "erro"
    if mercos_ambiente_sandbox():
        return "Aprovado", "aprovado"
    return "Pendente", "pendente"


def _campo(item: dict, *chaves: str, default: str = "—") -> Any:
    for chave in chaves:
        if chave in item and item[chave] not in (None, ""):
            return item[chave]
    return default


def _fmt_bool(valor: Any) -> str:
    if valor is True or str(valor).lower() in ("1", "true", "sim", "s"):
        return "Sim"
    if valor is False or str(valor).lower() in ("0", "false", "nao", "não", "n"):
        return "Não"
    if valor in (None, "", "—"):
        return "—"
    return str(valor)


def _table(
    headers: list[str],
    rows: list[list[Any]],
    empty_msg: str = "Sem registros.",
    row_classes: list[str] | None = None,
) -> str:
    if not rows:
        return f'<p class="empty">{_esc(empty_msg)}</p>'
    thead = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = []
    for idx, row in enumerate(rows):
        cells = "".join(f"<td>{_esc(c)}</td>" for c in row)
        cls = ""
        if row_classes and idx < len(row_classes) and row_classes[idx]:
            cls = f' class="{html.escape(row_classes[idx])}"'
        body.append(f"<tr{cls}>{cells}</tr>")
    return (
        f'<div class="table-wrap"><table><thead><tr>{thead}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def _card(titulo: str, linhas: list[tuple[str, Any]], *, status_label: str = "", css: str = "ok") -> str:
    meta = f'<div class="badge {css}">{_esc(status_label)}</div>' if status_label else ""
    items = "".join(
        f"<li><span>{_esc(k)}</span><strong>{_esc(v)}</strong></li>" for k, v in linhas
    )
    return (
        f'<div class="result-card {css}" data-status="{_esc(css)}">'
        f"<h4>{_esc(titulo)}</h4>{meta}<ul>{items}</ul></div>"
    )


def _erro_html(exc: Exception) -> str:
    if isinstance(exc, MercosApiError):
        code = exc.status_code or "—"
        return _card(
            "Falha na operação",
            [("HTTP", code), ("Mensagem", exc.message)],
            status_label=f"Erro {code}",
            css="erro",
        )
    return _card(
        "Falha na operação",
        [("Mensagem", str(exc)[:240])],
        status_label="Erro",
        css="erro",
    )


def _wrap_result(
    inner: str,
    *,
    entity: str = "",
    entity_id: str = "",
    extra_attrs: dict[str, str] | None = None,
) -> HTMLResponse:
    attrs = []
    if entity:
        attrs.append(f'data-entity="{html.escape(entity)}"')
    if entity_id:
        attrs.append(f'data-id="{html.escape(str(entity_id))}"')
    for chave, valor in (extra_attrs or {}).items():
        if valor is None:
            continue
        attrs.append(f'data-{html.escape(chave)}="{html.escape(str(valor))}"')
    attr = (" " + " ".join(attrs)) if attrs else ""
    return HTMLResponse(f'<div class="acao-resultado"{attr}>{inner}</div>')


# ---------------------------------------------------------------------------
# Página principal
# ---------------------------------------------------------------------------


@router.get("/homologacao-ui", response_class=HTMLResponse)
def homologacao_ui(
    request: Request,
    token: str = Query(""),
):
    """Tela ERP de homologação. Não executa POST/PUT Mercos na abertura."""
    _bloqueio(token)

    rotulo, classe = _status_visual()
    origem = "Mercos Sandbox" if mercos_ambiente_sandbox() else "Mercos"
    response = templates.TemplateResponse(
        request,
        "homologacao_mercos.html",
        {
            "titulo": "Xnamai ERP - Homologação Mercos Sandbox",
            "ambiente": "Sandbox" if mercos_ambiente_sandbox() else "Produção",
            "data_hora": _agora_br(),
            "status_label": rotulo,
            "status_class": classe,
            "origem_dados": origem,
        },
    )
    # Cookie HttpOnly: POSTs autenticados sem exibir o token na tela
    if token:
        response.set_cookie(
            key=_COOKIE,
            value=token,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            path="/mercos",
        )
    return response


def _auth(request: Request, token: str = "") -> None:
    _bloqueio(_token_request(request, token_form=token))


# ---------------------------------------------------------------------------
# Ações (somente no clique)
# ---------------------------------------------------------------------------


_NOMES_PRODUTO_DESTAQUE = frozenset(
    {
        "4c2e97e74c634ea4",
        "87109c4efa4b4f3f",
        "5db65d7102b54a98",
    }
)


def _cursor_produtos(request: Request, cursor_form: str = "") -> str:
    """Cursor: form (localStorage) tem prioridade; depois cookie do servidor."""
    form = (cursor_form or "").strip()
    if form:
        return form
    raw = (request.cookies.get(_COOKIE_PRODUTOS_CURSOR) or "").strip().strip('"')
    if not raw:
        return ""
    try:
        return unquote(raw)
    except Exception:
        return raw


def _set_cursor_cookie(resp: HTMLResponse, cursor: str | None) -> HTMLResponse:
    valor = (cursor or "").strip()
    if valor:
        resp.set_cookie(
            key=_COOKIE_PRODUTOS_CURSOR,
            value=quote(valor, safe=""),
            httponly=False,
            max_age=_CURSOR_MAX_AGE,
            samesite="lax",
        )
    else:
        resp.delete_cookie(_COOKIE_PRODUTOS_CURSOR)
    return resp


def _sessao_produtos(request: Request) -> str:
    return (request.cookies.get(_COOKIE_PRODUTOS_SESSAO) or "").strip()


def _garantir_sessao_cookie(resp: HTMLResponse, sessao_id: str) -> HTMLResponse:
    resp.set_cookie(
        key=_COOKIE_PRODUTOS_SESSAO,
        value=sessao_id,
        httponly=False,
        max_age=_SESSAO_MAX_AGE,
        samesite="lax",
    )
    return resp


def _obter_ou_criar_sessao(request: Request) -> str:
    existente = _sessao_produtos(request)
    if existente:
        return existente
    return uuid.uuid4().hex


def _hidratar_catalogo_form(sessao_id: str, catalogo_json: str = "") -> None:
    """Recupera catálogo do localStorage (form) se a memória do servidor estiver vazia."""
    catalogo_produtos.hidratar_se_vazio(sessao_id, catalogo_json or "")


def _html_patch_catalogo(sessao_id: str) -> str:
    snap = catalogo_produtos.snapshot_cliente(sessao_id)
    blob = html.escape(json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    return (
        f'<textarea class="mercos-catalogo-blob" hidden readonly '
        f'aria-hidden="true">{blob}</textarea>'
    )


def _linhas_ultima_sync(estado: dict[str, Any] | None) -> list[tuple[str, Any]]:
    sync = (estado or {}).get("ultima_sync") or {}
    tipo = sync.get("tipo")
    tipo_label = (
        "Completa"
        if tipo == "completa"
        else ("Incremental" if tipo == "incremental" else (tipo or "—"))
    )
    return [
        ("Tipo da busca", tipo_label),
        ("Cursor base", sync.get("cursor_base") or "—"),
        ("Alterado após enviado", sync.get("alterado_apos_enviado") or "—"),
        ("Novo cursor salvo", sync.get("novo_cursor") or "—"),
    ]


def _linhas_ciclo(sessao_id: str, estado: dict[str, Any] | None = None) -> list[tuple[str, Any]]:
    estado = estado or catalogo_produtos.obter(sessao_id)
    ciclo = catalogo_produtos.obter_ciclo(sessao_id)
    sync = (estado or {}).get("ultima_sync") or {}
    tipo = sync.get("tipo")
    tipo_label = (
        "Completa"
        if tipo == "completa"
        else ("Incremental" if tipo == "incremental" else (tipo or "—"))
    )
    etapa = int(ciclo.get("etapa_interna") or 0)
    return [
        ("Etapa interna", f"{etapa}/3"),
        ("Tipo da última busca", tipo_label),
        ("Cursor base", sync.get("cursor_base") or "—"),
        ("alterado_apos enviado", sync.get("alterado_apos_enviado") or "—"),
        ("Novo cursor", sync.get("novo_cursor") or "—"),
        ("Produtos no catálogo acumulado", len((estado or {}).get("produtos") or {})),
        ("Chamadas completas no ciclo", ciclo.get("chamadas_completas") or 0),
        ("Chamadas incrementais no ciclo", ciclo.get("chamadas_incrementais") or 0),
    ]


def _attrs_ciclo(sessao_id: str) -> dict[str, str]:
    ciclo = catalogo_produtos.obter_ciclo(sessao_id)
    return {
        "ciclo-ativo": "1" if ciclo.get("ativo") else "0",
        "etapa-interna": str(ciclo.get("etapa_interna") or 0),
        "chamadas-completas": str(ciclo.get("chamadas_completas") or 0),
        "chamadas-incrementais": str(ciclo.get("chamadas_incrementais") or 0),
        "bloquear-busca-completa": "1" if ciclo.get("ativo") else "0",
    }


def _html_tabela_produtos(itens: list) -> str:
    rows = []
    classes: list[str] = []
    for item in itens or []:
        nome = _campo(item, "nome", "nome_produto")
        nome_str = "" if nome == "—" else str(nome)
        ativo = _fmt_bool(_campo(item, "ativo", default=None))
        if "excluido" in item and "ativo" not in item:
            ativo = "Não" if item.get("excluido") else "Sim"
        preco = item.get("preco_tabela")
        if preco is None or preco == "":
            preco = "—"
        rows.append(
            [
                _campo(item, "id"),
                nome_str or "—",
                _campo(item, "codigo", "codigo_sku", "sku"),
                preco,
                _campo(item, "estoque", "saldo_estoque", "quantidade_estoque"),
                ativo,
                item.get("ultima_alteracao")
                if item.get("ultima_alteracao") not in (None, "")
                else "—",
            ]
        )
        nome_l = nome_str.lower()
        classes.append(
            "destaque-homolog"
            if nome_l in _NOMES_PRODUTO_DESTAQUE
            or any(nome_l.startswith(n) for n in _NOMES_PRODUTO_DESTAQUE)
            else ""
        )
    return _table(
        ["ID", "Nome", "Código", "Preço", "Estoque", "Ativo", "Última alteração"],
        rows,
        row_classes=classes,
    )


def _ativo_produto(item: dict) -> str:
    if "ativo" in item:
        return _fmt_bool(item.get("ativo"))
    if "excluido" in item:
        return "Não" if item.get("excluido") else "Sim"
    return "—"


def _cursor_clientes(request: Request, cursor_form: str = "") -> str:
    form = (cursor_form or "").strip()
    if form:
        return form
    raw = (request.cookies.get(_COOKIE_CLIENTES_CURSOR) or "").strip().strip('"')
    if not raw:
        return ""
    try:
        return unquote(raw)
    except Exception:
        return raw


def _set_cursor_clientes_cookie(resp: HTMLResponse, cursor: str | None) -> HTMLResponse:
    valor = (cursor or "").strip()
    if valor:
        resp.set_cookie(
            key=_COOKIE_CLIENTES_CURSOR,
            value=quote(valor, safe=""),
            httponly=False,
            max_age=_CURSOR_MAX_AGE,
            samesite="lax",
        )
    else:
        resp.delete_cookie(_COOKIE_CLIENTES_CURSOR)
    return resp


def _sessao_clientes(request: Request) -> str:
    return (request.cookies.get(_COOKIE_CLIENTES_SESSAO) or "").strip()


def _garantir_sessao_clientes_cookie(resp: HTMLResponse, sessao_id: str) -> HTMLResponse:
    resp.set_cookie(
        key=_COOKIE_CLIENTES_SESSAO,
        value=sessao_id,
        httponly=False,
        max_age=_SESSAO_MAX_AGE,
        samesite="lax",
    )
    return resp


def _obter_ou_criar_sessao_clientes(request: Request) -> str:
    existente = _sessao_clientes(request)
    if existente:
        return existente
    return uuid.uuid4().hex


def _hidratar_catalogo_clientes_form(sessao_id: str, catalogo_json: str = "") -> None:
    catalogo_clientes.hidratar_se_vazio(sessao_id, catalogo_json or "")


def _html_patch_catalogo_clientes(sessao_id: str) -> str:
    snap = catalogo_clientes.snapshot_sessao(sessao_id)
    blob = html.escape(json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    return (
        f'<textarea class="mercos-clientes-catalogo-blob" hidden readonly '
        f'aria-hidden="true">{blob}</textarea>'
    )


def _linhas_ciclo_clientes(
    sessao_id: str, estado: dict[str, Any] | None = None
) -> list[tuple[str, Any]]:
    estado = estado or catalogo_clientes.obter(sessao_id)
    ciclo = catalogo_clientes.obter_ciclo(sessao_id)
    sync = (estado or {}).get("ultima_sync") or {}
    tipo = sync.get("tipo")
    tipo_label = (
        "Completa"
        if tipo == "completa"
        else ("Incremental" if tipo == "incremental" else (tipo or "—"))
    )
    etapa = int(ciclo.get("etapa_interna") or 0)

    def _num(chave: str) -> Any:
        valor = sync.get(chave)
        return valor if valor is not None else "—"

    return [
        ("Etapa interna", f"{etapa}/3"),
        ("Tipo da última busca", tipo_label),
        ("Cursor base", sync.get("cursor_base") or "—"),
        ("alterado_apos enviado", sync.get("alterado_apos_enviado") or "—"),
        ("Novo cursor", sync.get("novo_cursor") or "—"),
        ("Total de páginas consultadas", sync.get("paginas_lidas") or "—"),
        ("Requisições extras informadas pela Mercos", _num("requisicoes_extras")),
        ("Requisições previstas", _num("requisicoes_previstas")),
        ("Requisições executadas", _num("requisicoes_executadas")),
        ("Total retornado em todas as páginas", sync.get("total_lote") or 0),
        ("Total de clientes", len((estado or {}).get("clientes") or {})),
        ("Motivo da parada", sync.get("motivo_parada") or "—"),
        ("Status da sincronização", sync.get("status_sync") or "—"),
        ("Chamadas completas no ciclo", ciclo.get("chamadas_completas") or 0),
        ("Chamadas incrementais no ciclo", ciclo.get("chamadas_incrementais") or 0),
    ]


def _attrs_ciclo_clientes(sessao_id: str) -> dict[str, str]:
    ciclo = catalogo_clientes.obter_ciclo(sessao_id)
    return {
        "ciclo-ativo": "1" if ciclo.get("ativo") else "0",
        "etapa-interna": str(ciclo.get("etapa_interna") or 0),
        "chamadas-completas": str(ciclo.get("chamadas_completas") or 0),
        "chamadas-incrementais": str(ciclo.get("chamadas_incrementais") or 0),
        "bloquear-busca-completa": "1" if ciclo.get("ativo") else "0",
    }


def _cursor_usuarios(request: Request, cursor_form: str = "") -> str:
    form = (cursor_form or "").strip()
    if form:
        return form
    raw = (request.cookies.get(_COOKIE_USUARIOS_CURSOR) or "").strip().strip('"')
    if not raw:
        return ""
    try:
        return unquote(raw)
    except Exception:
        return raw


def _set_cursor_usuarios_cookie(resp: HTMLResponse, cursor: str | None) -> HTMLResponse:
    valor = (cursor or "").strip()
    if valor:
        resp.set_cookie(
            key=_COOKIE_USUARIOS_CURSOR,
            value=quote(valor, safe=""),
            httponly=False,
            max_age=_CURSOR_MAX_AGE,
            samesite="lax",
        )
    else:
        resp.delete_cookie(_COOKIE_USUARIOS_CURSOR)
    return resp


def _obter_ou_criar_sessao_usuarios(request: Request) -> str:
    existente = (request.cookies.get(_COOKIE_USUARIOS_SESSAO) or "").strip()
    if existente:
        return existente
    return uuid.uuid4().hex


def _garantir_sessao_usuarios_cookie(resp: HTMLResponse, sessao_id: str) -> HTMLResponse:
    resp.set_cookie(
        key=_COOKIE_USUARIOS_SESSAO,
        value=sessao_id,
        httponly=False,
        max_age=_SESSAO_MAX_AGE,
        samesite="lax",
    )
    return resp


def _hidratar_catalogo_usuarios_form(sessao_id: str, catalogo_json: str = "") -> None:
    catalogo_usuarios.hidratar_se_vazio(sessao_id, catalogo_json or "")


def _html_patch_catalogo_usuarios(sessao_id: str) -> str:
    snap = catalogo_usuarios.snapshot_sessao(sessao_id)
    blob = html.escape(json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    return (
        f'<textarea class="mercos-usuarios-catalogo-blob" hidden readonly '
        f'aria-hidden="true">{blob}</textarea>'
    )


def _linhas_ciclo_usuarios(
    sessao_id: str, estado: dict[str, Any] | None = None
) -> list[tuple[str, Any]]:
    estado = estado or catalogo_usuarios.obter(sessao_id)
    ciclo = catalogo_usuarios.obter_ciclo(sessao_id)
    sync = (estado or {}).get("ultima_sync") or {}
    tipo = sync.get("tipo")
    tipo_label = (
        "Completa"
        if tipo == "completa"
        else ("Incremental" if tipo == "incremental" else (tipo or "—"))
    )
    etapa = int(ciclo.get("etapa_interna") or 0)

    def _num(chave: str) -> Any:
        valor = sync.get(chave)
        return valor if valor is not None else "—"

    return [
        ("Etapa interna", f"{etapa}/3"),
        ("Tipo da última busca", tipo_label),
        ("Cursor base", sync.get("cursor_base") or "—"),
        ("alterado_apos enviado", sync.get("alterado_apos_enviado") or "—"),
        ("Novo cursor", sync.get("novo_cursor") or "—"),
        ("Total de páginas consultadas", sync.get("paginas_lidas") or "—"),
        ("Requisições extras informadas pela Mercos", _num("requisicoes_extras")),
        ("Requisições previstas", _num("requisicoes_previstas")),
        ("Requisições executadas", _num("requisicoes_executadas")),
        ("Total retornado em todas as páginas", sync.get("total_lote") or 0),
        ("Total de usuários", len((estado or {}).get("usuarios") or {})),
        ("Motivo da parada", sync.get("motivo_parada") or "—"),
        ("Status da sincronização", sync.get("status_sync") or "—"),
        ("Chamadas completas no ciclo", ciclo.get("chamadas_completas") or 0),
        ("Chamadas incrementais no ciclo", ciclo.get("chamadas_incrementais") or 0),
    ]


def _attrs_ciclo_usuarios(sessao_id: str) -> dict[str, str]:
    ciclo = catalogo_usuarios.obter_ciclo(sessao_id)
    return {
        "ciclo-ativo": "1" if ciclo.get("ativo") else "0",
        "etapa-interna": str(ciclo.get("etapa_interna") or 0),
        "chamadas-completas": str(ciclo.get("chamadas_completas") or 0),
        "chamadas-incrementais": str(ciclo.get("chamadas_incrementais") or 0),
        "bloquear-busca-completa": "1" if ciclo.get("ativo") else "0",
    }


def _ativo_usuario(item: dict) -> str:
    if "ativo" in item:
        return _fmt_bool(item.get("ativo"))
    if "excluido" in item:
        return "Não" if item.get("excluido") else "Sim"
    return "—"


def _html_tabela_usuarios(itens: list) -> str:
    rows = []
    for item in itens or []:
        rows.append(
            [
                _campo(item, "id"),
                _campo(item, "nome", "name"),
                _campo(item, "email"),
                _fmt_bool(_campo(item, "administrador", "admin", default="—")),
                _ativo_usuario(item) if isinstance(item, dict) else "—",
                item.get("ultima_alteracao")
                if isinstance(item, dict)
                and item.get("ultima_alteracao") not in (None, "")
                else "—",
            ]
        )
    return _table(
        ["ID", "Nome", "E-mail", "Administrador", "Ativo", "Última alteração"],
        rows,
    )


def _cursor_tipos(request: Request, cursor_form: str = "") -> str:
    form = (cursor_form or "").strip()
    if form:
        return form
    raw = (request.cookies.get(_COOKIE_TIPOS_CURSOR) or "").strip().strip('"')
    if not raw:
        return ""
    try:
        return unquote(raw)
    except Exception:
        return raw


def _set_cursor_tipos_cookie(resp: HTMLResponse, cursor: str | None) -> HTMLResponse:
    valor = (cursor or "").strip()
    if valor:
        resp.set_cookie(
            key=_COOKIE_TIPOS_CURSOR,
            value=quote(valor, safe=""),
            httponly=False,
            max_age=_CURSOR_MAX_AGE,
            samesite="lax",
        )
    else:
        resp.delete_cookie(_COOKIE_TIPOS_CURSOR)
    return resp


def _obter_ou_criar_sessao_tipos(request: Request) -> str:
    existente = (request.cookies.get(_COOKIE_TIPOS_SESSAO) or "").strip()
    if existente:
        return existente
    return uuid.uuid4().hex


def _garantir_sessao_tipos_cookie(resp: HTMLResponse, sessao_id: str) -> HTMLResponse:
    resp.set_cookie(
        key=_COOKIE_TIPOS_SESSAO,
        value=sessao_id,
        httponly=False,
        max_age=_SESSAO_MAX_AGE,
        samesite="lax",
    )
    return resp


def _hidratar_catalogo_tipos_form(sessao_id: str, catalogo_json: str = "") -> None:
    catalogo_tipos_pedido.hidratar_se_vazio(sessao_id, catalogo_json or "")


def _html_patch_catalogo_tipos(sessao_id: str) -> str:
    snap = catalogo_tipos_pedido.snapshot_sessao(sessao_id)
    blob = html.escape(json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    return (
        f'<textarea class="mercos-tipos-catalogo-blob" hidden readonly '
        f'aria-hidden="true">{blob}</textarea>'
    )


def _linhas_ciclo_tipos(
    sessao_id: str, estado: dict[str, Any] | None = None
) -> list[tuple[str, Any]]:
    estado = estado or catalogo_tipos_pedido.obter(sessao_id)
    ciclo = catalogo_tipos_pedido.obter_ciclo(sessao_id)
    sync = (estado or {}).get("ultima_sync") or {}
    tipo = sync.get("tipo")
    tipo_label = (
        "Completa"
        if tipo == "completa"
        else ("Incremental" if tipo == "incremental" else (tipo or "—"))
    )
    etapa = int(ciclo.get("etapa_interna") or 0)

    def _num(chave: str) -> Any:
        valor = sync.get(chave)
        return valor if valor is not None else "—"

    return [
        ("Etapa interna", f"{etapa}/3"),
        ("Tipo da última busca", tipo_label),
        ("Cursor base", sync.get("cursor_base") or "—"),
        ("alterado_apos enviado", sync.get("alterado_apos_enviado") or "—"),
        ("Novo cursor", sync.get("novo_cursor") or "—"),
        ("Total de páginas consultadas", sync.get("paginas_lidas") or "—"),
        ("Requisições extras informadas pela Mercos", _num("requisicoes_extras")),
        ("Requisições previstas", _num("requisicoes_previstas")),
        ("Requisições executadas", _num("requisicoes_executadas")),
        ("Total retornado em todas as páginas", sync.get("total_lote") or 0),
        ("Total no catálogo", len((estado or {}).get("tipos") or {})),
        ("Motivo da parada", sync.get("motivo_parada") or "—"),
        ("Status da sincronização", sync.get("status_sync") or "—"),
        ("Chamadas completas no ciclo", ciclo.get("chamadas_completas") or 0),
        ("Chamadas incrementais no ciclo", ciclo.get("chamadas_incrementais") or 0),
    ]


def _attrs_ciclo_tipos(sessao_id: str) -> dict[str, str]:
    ciclo = catalogo_tipos_pedido.obter_ciclo(sessao_id)
    return {
        "ciclo-ativo": "1" if ciclo.get("ativo") else "0",
        "etapa-interna": str(ciclo.get("etapa_interna") or 0),
        "chamadas-completas": str(ciclo.get("chamadas_completas") or 0),
        "chamadas-incrementais": str(ciclo.get("chamadas_incrementais") or 0),
        "bloquear-busca-completa": "1" if ciclo.get("ativo") else "0",
    }


def _html_tabela_tipos(itens: list) -> str:
    rows = []
    for item in itens or []:
        rows.append(
            [
                _campo(item, "id"),
                _campo(item, "nome", "name"),
                _fmt_bool(_campo(item, "excluido", default=False)),
                item.get("ultima_alteracao")
                if isinstance(item, dict)
                and item.get("ultima_alteracao") not in (None, "")
                else "—",
            ]
        )
    return _table(["ID", "Nome", "Excluído", "Última alteração"], rows)


def _cursor_condicoes(request: Request, cursor_form: str = "") -> str:
    form = (cursor_form or "").strip()
    if form:
        return form
    raw = (request.cookies.get(_COOKIE_CONDICOES_CURSOR) or "").strip().strip('"')
    if not raw:
        return ""
    try:
        return unquote(raw)
    except Exception:
        return raw


def _set_cursor_condicoes_cookie(resp: HTMLResponse, cursor: str | None) -> HTMLResponse:
    valor = (cursor or "").strip()
    if valor:
        resp.set_cookie(
            key=_COOKIE_CONDICOES_CURSOR,
            value=quote(valor, safe=""),
            httponly=False,
            max_age=_CURSOR_MAX_AGE,
            samesite="lax",
        )
    else:
        resp.delete_cookie(_COOKIE_CONDICOES_CURSOR)
    return resp


def _obter_ou_criar_sessao_condicoes(request: Request) -> str:
    existente = (request.cookies.get(_COOKIE_CONDICOES_SESSAO) or "").strip()
    if existente:
        return existente
    return uuid.uuid4().hex


def _garantir_sessao_condicoes_cookie(resp: HTMLResponse, sessao_id: str) -> HTMLResponse:
    resp.set_cookie(
        key=_COOKIE_CONDICOES_SESSAO,
        value=sessao_id,
        httponly=False,
        max_age=_SESSAO_MAX_AGE,
        samesite="lax",
    )
    return resp


def _hidratar_catalogo_condicoes_form(sessao_id: str, catalogo_json: str = "") -> None:
    catalogo_condicoes.hidratar_se_vazio(sessao_id, catalogo_json or "")


def _html_patch_catalogo_condicoes(sessao_id: str) -> str:
    snap = catalogo_condicoes.snapshot_sessao(sessao_id)
    blob = html.escape(json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    return (
        f'<textarea class="mercos-condicoes-catalogo-blob" hidden readonly '
        f'aria-hidden="true">{blob}</textarea>'
    )


def _linhas_ciclo_condicoes(
    sessao_id: str, estado: dict[str, Any] | None = None
) -> list[tuple[str, Any]]:
    estado = estado or catalogo_condicoes.obter(sessao_id)
    ciclo = catalogo_condicoes.obter_ciclo(sessao_id)
    sync = (estado or {}).get("ultima_sync") or {}
    tipo = sync.get("tipo")
    tipo_label = (
        "Completa"
        if tipo == "completa"
        else ("Incremental" if tipo == "incremental" else (tipo or "—"))
    )
    etapa = int(ciclo.get("etapa_interna") or 0)

    def _num(chave: str) -> Any:
        valor = sync.get(chave)
        return valor if valor is not None else "—"

    return [
        ("Etapa interna", f"{etapa}/3"),
        ("Tipo da última busca", tipo_label),
        ("Cursor base", sync.get("cursor_base") or "—"),
        ("alterado_apos enviado", sync.get("alterado_apos_enviado") or "—"),
        ("Novo cursor", sync.get("novo_cursor") or "—"),
        ("Total de páginas consultadas", sync.get("paginas_lidas") or "—"),
        ("Requisições extras informadas pela Mercos", _num("requisicoes_extras")),
        ("Requisições previstas", _num("requisicoes_previstas")),
        ("Requisições executadas", _num("requisicoes_executadas")),
        ("Total retornado em todas as páginas", sync.get("total_lote") or 0),
        ("Total no catálogo", len((estado or {}).get("condicoes") or {})),
        ("Motivo da parada", sync.get("motivo_parada") or "—"),
        ("Status da sincronização", sync.get("status_sync") or "—"),
        ("Chamadas completas no ciclo", ciclo.get("chamadas_completas") or 0),
        ("Chamadas incrementais no ciclo", ciclo.get("chamadas_incrementais") or 0),
    ]


def _attrs_ciclo_condicoes(sessao_id: str) -> dict[str, str]:
    ciclo = catalogo_condicoes.obter_ciclo(sessao_id)
    return {
        "ciclo-ativo": "1" if ciclo.get("ativo") else "0",
        "etapa-interna": str(ciclo.get("etapa_interna") or 0),
        "chamadas-completas": str(ciclo.get("chamadas_completas") or 0),
        "chamadas-incrementais": str(ciclo.get("chamadas_incrementais") or 0),
        "bloquear-busca-completa": "1" if ciclo.get("ativo") else "0",
    }


def _fmt_valor_minimo(valor: Any) -> str:
    if valor is None or valor == "":
        return "—"
    try:
        return f"{float(valor):.2f}"
    except (TypeError, ValueError):
        return str(valor)


def _html_tabela_condicoes(itens: list) -> str:
    rows = []
    for item in itens or []:
        rows.append(
            [
                _campo(item, "id"),
                _campo(item, "nome", "name"),
                _fmt_valor_minimo(item.get("valor_minimo") if isinstance(item, dict) else None),
                _fmt_bool(_campo(item, "disponivel_b2b", "b2b", default="—")),
                _fmt_bool(_campo(item, "excluido", default=False)),
                item.get("ultima_alteracao")
                if isinstance(item, dict)
                and item.get("ultima_alteracao") not in (None, "")
                else "—",
            ]
        )
    return _table(
        ["ID", "Nome", "Valor mínimo", "Disponível B2B", "Excluído", "Última alteração"],
        rows,
    )


def _cursor_pedidos(request: Request, cursor_form: str = "") -> str:
    form = (cursor_form or "").strip()
    if form:
        return form
    raw = (request.cookies.get(_COOKIE_PEDIDOS_CURSOR) or "").strip().strip('"')
    if not raw:
        return ""
    try:
        return unquote(raw)
    except Exception:
        return raw


def _set_cursor_pedidos_cookie(resp: HTMLResponse, cursor: str | None) -> HTMLResponse:
    valor = (cursor or "").strip()
    if valor:
        resp.set_cookie(
            key=_COOKIE_PEDIDOS_CURSOR,
            value=quote(valor, safe=""),
            httponly=False,
            max_age=_CURSOR_MAX_AGE,
            samesite="lax",
        )
    else:
        resp.delete_cookie(_COOKIE_PEDIDOS_CURSOR)
    return resp


def _obter_ou_criar_sessao_pedidos(request: Request) -> str:
    existente = (request.cookies.get(_COOKIE_PEDIDOS_SESSAO) or "").strip()
    if existente:
        return existente
    return uuid.uuid4().hex


def _garantir_sessao_pedidos_cookie(resp: HTMLResponse, sessao_id: str) -> HTMLResponse:
    resp.set_cookie(
        key=_COOKIE_PEDIDOS_SESSAO,
        value=sessao_id,
        httponly=False,
        max_age=_SESSAO_MAX_AGE,
        samesite="lax",
    )
    return resp


def _hidratar_catalogo_pedidos_form(sessao_id: str, catalogo_json: str = "") -> None:
    catalogo_pedidos.hidratar_se_vazio(sessao_id, catalogo_json or "")


def _html_patch_catalogo_pedidos(sessao_id: str) -> str:
    snap = catalogo_pedidos.snapshot_sessao(sessao_id)
    blob = html.escape(json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    return (
        f'<textarea class="mercos-pedidos-catalogo-blob" hidden readonly '
        f'aria-hidden="true">{blob}</textarea>'
    )


def _linhas_ciclo_pedidos(
    sessao_id: str, estado: dict[str, Any] | None = None
) -> list[tuple[str, Any]]:
    estado = estado or catalogo_pedidos.obter(sessao_id)
    ciclo = catalogo_pedidos.obter_ciclo(sessao_id)
    sync = (estado or {}).get("ultima_sync") or {}
    tipo = sync.get("tipo")
    tipo_label = (
        "Completa"
        if tipo == "completa"
        else ("Incremental" if tipo == "incremental" else (tipo or "—"))
    )
    etapa = int(ciclo.get("etapa_interna") or 0)

    def _num(chave: str) -> Any:
        valor = sync.get(chave)
        return valor if valor is not None else "—"

    def _seg(chave: str) -> str:
        valor = sync.get(chave)
        if valor is None:
            return "—"
        try:
            return f"{float(valor):.1f}s"
        except (TypeError, ValueError):
            return str(valor)

    throttling = sync.get("throttling_respeitado")
    throttling_label = "—" if throttling is None else ("Sim" if throttling else "Não")

    return [
        ("Etapa interna", f"{etapa}/2"),
        ("Tipo da última busca", tipo_label),
        ("Cursor base", sync.get("cursor_base") or "—"),
        ("alterado_apos enviado", sync.get("alterado_apos_enviado") or "—"),
        ("Novo cursor", sync.get("novo_cursor") or "—"),
        ("Total de páginas consultadas", sync.get("paginas_lidas") or "—"),
        ("Requisições extras informadas pela Mercos", _num("requisicoes_extras")),
        ("Requisições previstas", _num("requisicoes_previstas")),
        ("Requisições executadas", _num("requisicoes_executadas")),
        ("Intervalo mínimo aplicado", _seg("intervalo_minimo_aplicado")),
        ("Menor intervalo real entre chamadas", _seg("menor_intervalo_real")),
        ("Throttling respeitado", throttling_label),
        ("Total retornado em todas as páginas", sync.get("total_lote") or 0),
        ("Total de pedidos", len((estado or {}).get("pedidos") or {})),
        ("Motivo da parada", sync.get("motivo_parada") or "—"),
        ("Status da sincronização", sync.get("status_sync") or "—"),
        ("Chamadas completas no ciclo", ciclo.get("chamadas_completas") or 0),
        ("Chamadas incrementais no ciclo", ciclo.get("chamadas_incrementais") or 0),
    ]


def _attrs_ciclo_pedidos(sessao_id: str) -> dict[str, str]:
    ciclo = catalogo_pedidos.obter_ciclo(sessao_id)
    return {
        "ciclo-ativo": "1" if ciclo.get("ativo") else "0",
        "etapa-interna": str(ciclo.get("etapa_interna") or 0),
        "chamadas-completas": str(ciclo.get("chamadas_completas") or 0),
        "chamadas-incrementais": str(ciclo.get("chamadas_incrementais") or 0),
        "bloquear-busca-completa": "1" if ciclo.get("ativo") else "0",
    }


def _cursor_pagamentos(request: Request, cursor_form: str = "") -> str:
    form = (cursor_form or "").strip()
    if form:
        return form
    raw = (request.cookies.get(_COOKIE_PAGAMENTOS_CURSOR) or "").strip().strip('"')
    if not raw:
        return ""
    try:
        return unquote(raw)
    except Exception:
        return raw


def _set_cursor_pagamentos_cookie(resp: HTMLResponse, cursor: str | None) -> HTMLResponse:
    valor = (cursor or "").strip()
    if valor:
        resp.set_cookie(
            key=_COOKIE_PAGAMENTOS_CURSOR,
            value=quote(valor, safe=""),
            httponly=False,
            max_age=_CURSOR_MAX_AGE,
            samesite="lax",
        )
    else:
        resp.delete_cookie(_COOKIE_PAGAMENTOS_CURSOR)
    return resp


def _obter_ou_criar_sessao_pagamentos(request: Request) -> str:
    existente = (request.cookies.get(_COOKIE_PAGAMENTOS_SESSAO) or "").strip()
    if existente:
        return existente
    return uuid.uuid4().hex


def _garantir_sessao_pagamentos_cookie(resp: HTMLResponse, sessao_id: str) -> HTMLResponse:
    resp.set_cookie(
        key=_COOKIE_PAGAMENTOS_SESSAO,
        value=sessao_id,
        httponly=False,
        max_age=_SESSAO_MAX_AGE,
        samesite="lax",
    )
    return resp


def _hidratar_catalogo_pagamentos_form(sessao_id: str, catalogo_json: str = "") -> None:
    catalogo_pagamentos.hidratar_se_vazio(sessao_id, catalogo_json or "")


def _html_patch_catalogo_pagamentos(sessao_id: str) -> str:
    snap = catalogo_pagamentos.snapshot_sessao(sessao_id)
    blob = html.escape(json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    return (
        f'<textarea class="mercos-pagamentos-catalogo-blob" hidden readonly '
        f'aria-hidden="true">{blob}</textarea>'
    )


def _linhas_ciclo_pagamentos(
    sessao_id: str, estado: dict[str, Any] | None = None
) -> list[tuple[str, Any]]:
    estado = estado or catalogo_pagamentos.obter(sessao_id)
    ciclo = catalogo_pagamentos.obter_ciclo(sessao_id)
    sync = (estado or {}).get("ultima_sync") or {}
    tipo = sync.get("tipo")
    tipo_label = (
        "Completa"
        if tipo == "completa"
        else ("Incremental" if tipo == "incremental" else (tipo or "—"))
    )
    etapa = int(ciclo.get("etapa_interna") or 0)

    def _num(chave: str) -> Any:
        valor = sync.get(chave)
        return valor if valor is not None else "—"

    return [
        ("Etapa interna", f"{etapa}/2"),
        ("Tipo da última busca", tipo_label),
        ("Cursor base", sync.get("cursor_base") or "—"),
        ("alterado_apos enviado", sync.get("alterado_apos_enviado") or "—"),
        ("Novo cursor", sync.get("novo_cursor") or "—"),
        ("Total de páginas consultadas", sync.get("paginas_lidas") or "—"),
        ("Requisições extras informadas pela Mercos", _num("requisicoes_extras")),
        ("Requisições previstas", _num("requisicoes_previstas")),
        ("Requisições executadas", _num("requisicoes_executadas")),
        ("Total retornado em todas as páginas", sync.get("total_lote") or 0),
        ("Total no catálogo", len((estado or {}).get("pagamentos") or {})),
        ("Motivo da parada", sync.get("motivo_parada") or "—"),
        ("Status da sincronização", sync.get("status_sync") or "—"),
        ("Chamadas completas no ciclo", ciclo.get("chamadas_completas") or 0),
        ("Chamadas incrementais no ciclo", ciclo.get("chamadas_incrementais") or 0),
    ]


def _attrs_ciclo_pagamentos(sessao_id: str) -> dict[str, str]:
    ciclo = catalogo_pagamentos.obter_ciclo(sessao_id)
    return {
        "ciclo-ativo": "1" if ciclo.get("ativo") else "0",
        "etapa-interna": str(ciclo.get("etapa_interna") or 0),
        "chamadas-completas": str(ciclo.get("chamadas_completas") or 0),
        "chamadas-incrementais": str(ciclo.get("chamadas_incrementais") or 0),
        "bloquear-busca-completa": "1" if ciclo.get("ativo") else "0",
    }


def _fmt_valor_pagamento(valor: Any) -> str:
    if valor in (None, ""):
        return "—"
    try:
        return f"{float(valor):.2f}"
    except (TypeError, ValueError):
        return str(valor)


def _relacionado_pagamento(item: dict) -> str:
    partes: list[str] = []
    if item.get("pedido_id") not in (None, ""):
        partes.append(f"Pedido {item.get('pedido_id')}")
    if item.get("titulo_id") not in (None, ""):
        partes.append(f"Título {item.get('titulo_id')}")
    if item.get("cliente_id") not in (None, ""):
        partes.append(f"Cliente {item.get('cliente_id')}")
    return " · ".join(partes) if partes else "—"


def _html_tabela_pagamentos(itens: list) -> str:
    rows = []
    for item in itens or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            [
                _campo(item, "id"),
                _fmt_valor_pagamento(item.get("valor")),
                _relacionado_pagamento(item),
                item.get("data_criacao")
                if item.get("data_criacao") not in (None, "")
                else "—",
                _fmt_bool(item.get("excluido", False)),
                item.get("ultima_alteracao")
                if item.get("ultima_alteracao") not in (None, "")
                else "—",
            ]
        )
    return _table(
        ["ID", "Valor", "Relacionado", "Data", "Excluído", "Última alteração"],
        rows,
    )


def _fmt_total_pedido(valor: Any) -> str:
    if valor in (None, ""):
        return "—"
    try:
        return f"{float(valor):.2f}"
    except (TypeError, ValueError):
        return str(valor)


def _html_tabela_pedidos(itens: list) -> str:
    rows = []
    for item in itens or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            [
                _campo(item, "id"),
                _campo(item, "cliente_id"),
                _campo(item, "cliente_razao_social", "razao_social"),
                _fmt_total_pedido(item.get("total")),
                _campo(item, "status", "situacao"),
                _campo(item, "data_emissao"),
                item.get("ultima_alteracao")
                if item.get("ultima_alteracao") not in (None, "")
                else "—",
            ]
        )
    return _table(
        [
            "ID",
            "Cliente (ID)",
            "Razão social",
            "Total",
            "Status",
            "Emissão",
            "Última alteração",
        ],
        rows,
    )


def _razoes_clientes_por_id(request: Request) -> dict[str, str]:
    """Mapa cliente_id -> razão social do catálogo local de clientes (sem chamar Mercos)."""
    sessao_cli = (request.cookies.get(_COOKIE_CLIENTES_SESSAO) or "").strip()
    if not sessao_cli:
        return {}
    estado = catalogo_clientes.obter(sessao_cli)
    mapa: dict[str, str] = {}
    for cid, cli in (estado.get("clientes") or {}).items():
        if isinstance(cli, dict) and cli.get("razao_social"):
            mapa[str(cid)] = str(cli.get("razao_social"))
    return mapa


def _html_tabela_clientes(itens: list) -> str:
    rows = []
    for item in itens or []:
        ativo = _ativo_produto(item) if isinstance(item, dict) else "—"
        rows.append(
            [
                _campo(item, "id"),
                _campo(item, "razao_social", "nome"),
                _campo(item, "nome_fantasia", "fantasia"),
                _campo(item, "cnpj"),
                _campo(item, "email"),
                ativo,
                item.get("ultima_alteracao")
                if isinstance(item, dict)
                and item.get("ultima_alteracao") not in (None, "")
                else "—",
            ]
        )
    return _table(
        [
            "ID",
            "Razão social",
            "Nome fantasia",
            "CNPJ",
            "E-mail",
            "Ativo",
            "Última alteração",
        ],
        rows,
    )


@router.post("/homologacao-ui/acoes/produtos", response_class=HTMLResponse)
def acao_produtos(
    request: Request,
    token: str = Form(""),
    alterado_apos: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Busca simples — bloqueada durante ciclo ativo de homologação."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao(request)
    _hidratar_catalogo_form(sessao, catalogo_json)
    if catalogo_produtos.ciclo_ativo(sessao):
        resp = _wrap_result(
            _card(
                "Busca completa bloqueada durante a homologação",
                [
                    (
                        "Mensagem",
                        "Use apenas «Sincronizar próxima etapa» durante o ciclo ativo.",
                    )
                ]
                + _linhas_ciclo(sessao),
                status_label="Bloqueado",
                css="erro",
            ),
            extra_attrs={
                "status-sync": "bloqueado",
                **_attrs_ciclo(sessao),
            },
        )
        return _garantir_sessao_cookie(resp, sessao)

    filtro = (alterado_apos or "").strip()
    try:
        data = homolog.listar_produtos(
            pagina_inicial=1,
            max_paginas=5,
            alterado_apos=filtro or None,
        )
        table = _html_tabela_produtos(data.get("itens") or [])
        head_parts = [
            "Status: <strong>200</strong>",
            f'Total: <strong>{_esc(data.get("total", 0))}</strong>',
        ]
        if filtro:
            head_parts.append(
                f'Filtro usado: alterado_apos = <strong>{_esc(filtro)}</strong>'
            )
        head = f'<p class="meta">{" · ".join(head_parts)}</p>'
        resp = _wrap_result(head + table, extra_attrs=_attrs_ciclo(sessao))
        return _garantir_sessao_cookie(resp, sessao)
    except Exception as exc:
        resp = _wrap_result(_erro_html(exc))
        return _garantir_sessao_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/produtos-reiniciar", response_class=HTMLResponse)
def acao_produtos_reiniciar(
    request: Request,
    token: str = Form(""),
):
    """Apaga cursor e catálogo, inicia ciclo na etapa 0 — sem chamar a Mercos."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao(request)
    catalogo_produtos.iniciar_ciclo(sessao)
    estado = catalogo_produtos.obter(sessao)
    mensagem = (
        '<div class="result-card ok">'
        "<h4>Ciclo de sincronização reiniciado</h4>"
        "<p>Cursor e catálogo anteriores apagados. Novo ciclo ativo na etapa 0. "
        "Use «Sincronizar próxima etapa» para a busca completa.</p>"
        "</div>"
    )
    resumo = _card(
        "Estado do ciclo",
        _linhas_ciclo(sessao, estado),
        status_label="Ciclo ativo",
        css="ok",
    )
    resp = _wrap_result(
        mensagem + resumo + _html_patch_catalogo(sessao),
        extra_attrs={
            "novo-cursor": "",
            "cursor-limpo": "1",
            "catalogo-limpo": "1",
            "status-sync": "reiniciado",
            "catalogo-total": "0",
            **_attrs_ciclo(sessao),
        },
    )
    resp = _set_cursor_cookie(resp, None)
    return _garantir_sessao_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/produtos-sincronizar", response_class=HTMLResponse)
def acao_produtos_sincronizar(
    request: Request,
    token: str = Form(""),
    cursor: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Única ação que chama a Mercos no ciclo: etapa 0 completa; 1 e 2 incrementais."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao(request)
    _hidratar_catalogo_form(sessao, catalogo_json)
    ciclo = catalogo_produtos.obter_ciclo(sessao)
    if not ciclo.get("ativo"):
        catalogo_produtos.iniciar_ciclo(sessao)
        ciclo = catalogo_produtos.obter_ciclo(sessao)

    etapa = int(ciclo.get("etapa_interna") or 0)
    cursor_form = _cursor_produtos(request, cursor)

    # Etapa 0 → completa (ignora cursor residual). Etapas 1+ → incremental obrigatório.
    if etapa == 0:
        cursor_para_sync = None
        tipo_esperado = "completa"
    else:
        if not cursor_form:
            resp = _wrap_result(
                _card(
                    "Cursor ausente",
                    [
                        (
                            "Mensagem",
                            "Etapa incremental exige cursor salvo. Reinicie o ciclo se necessário.",
                        )
                    ]
                    + _linhas_ciclo(sessao),
                    status_label="Erro",
                    css="erro",
                ),
                extra_attrs={"status-sync": "erro", **_attrs_ciclo(sessao)},
            )
            return _garantir_sessao_cookie(resp, sessao)
        cursor_para_sync = cursor_form
        tipo_esperado = "incremental"

    try:
        data = homolog.sincronizar_produtos(cursor_para_sync, max_paginas=50)
        tipo_real = data.get("tipo") or tipo_esperado
        if etapa >= 1 and tipo_real == "completa":
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [("Mensagem", "A etapa atual exige busca incremental com alterado_apos.")]
                    + _linhas_ciclo(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo(sessao)},
            )
            return _garantir_sessao_cookie(resp, sessao)
        if etapa >= 1 and not data.get("alterado_apos_enviado"):
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [("Mensagem", "alterado_apos não foi enviado na etapa incremental.")]
                    + _linhas_ciclo(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo(sessao)},
            )
            return _garantir_sessao_cookie(resp, sessao)

        meta = {
            "tipo": tipo_real,
            "cursor_base": data.get("cursor_base"),
            "alterado_apos_enviado": data.get("alterado_apos_enviado"),
            "novo_cursor": data.get("novo_cursor"),
            "total_lote": data.get("total", 0),
        }
        # Completa substitui; incremental faz upsert (preserva catálogo)
        if tipo_real == "completa":
            catalogo_produtos.substituir_completo(
                sessao, data.get("itens") or [], meta=meta
            )
        else:
            catalogo_produtos.upsert_incremental(
                sessao, data.get("itens") or [], meta=meta
            )
        try:
            catalogo_produtos.registrar_sync_ciclo(sessao, tipo=tipo_real)
        except ValueError as exc:
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [("Mensagem", str(exc))] + _linhas_ciclo(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo(sessao)},
            )
            return _garantir_sessao_cookie(resp, sessao)

        estado = catalogo_produtos.obter(sessao)
        total = data.get("total", 0)
        resumo = _card(
            "Sincronização de produtos",
            [
                ("Status da sincronização", "Concluída"),
            ]
            + _linhas_ciclo(sessao, estado)
            + [("Total retornado no lote", total)],
            status_label="Status 200",
            css="ok",
        )
        table = _html_tabela_produtos(data.get("itens") or [])
        resp = _wrap_result(
            resumo + table + _html_patch_catalogo(sessao),
            extra_attrs={
                "novo-cursor": data.get("novo_cursor") or "",
                "cursor-anterior": data.get("cursor_anterior") or "",
                "cursor-base": data.get("cursor_base") or "",
                "alterado-apos-enviado": data.get("alterado_apos_enviado") or "",
                "tipo-busca": tipo_real,
                "total": str(total),
                "catalogo-total": str(len(estado.get("produtos") or {})),
                "catalogo-modo": "replace" if tipo_real == "completa" else "upsert",
                "status-sync": "concluida",
                **_attrs_ciclo(sessao),
            },
        )
        resp = _set_cursor_cookie(resp, data.get("novo_cursor"))
        return _garantir_sessao_cookie(resp, sessao)
    except MercosApiError as exc:
        html_erro = _erro_html(exc)
        resp = _wrap_result(
            html_erro,
            extra_attrs={
                "status-sync": "erro",
                "http-status": str(exc.status_code or ""),
                **_attrs_ciclo(sessao),
            },
        )
        if exc.status_code == 429:
            resp.status_code = 429
            resp.headers["Retry-After"] = "10"
        elif exc.status_code == 409:
            resp.status_code = 409
        return _garantir_sessao_cookie(resp, sessao)
    except Exception as exc:
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={"status-sync": "erro", **_attrs_ciclo(sessao)},
        )
        return _garantir_sessao_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/produtos-localizar", response_class=HTMLResponse)
def acao_produtos_localizar(
    request: Request,
    token: str = Form(""),
    nome: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Localiza pelo nome exato no catálogo local. Não chama Mercos nem altera cursor/etapa."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao(request)
    _hidratar_catalogo_form(sessao, catalogo_json)
    ciclo_antes = catalogo_produtos.obter_ciclo(sessao)
    nome_busca = (nome or "").strip()
    if not nome_busca:
        return _garantir_sessao_cookie(
            _wrap_result(
                _card(
                    "Localizar produto",
                    [("Mensagem", "Informe o nome exato do produto.")],
                    status_label="Atenção",
                    css="erro",
                )
            ),
            sessao,
        )

    encontrado, no_ultimo_lote, estado = catalogo_produtos.buscar_por_nome(
        sessao, nome_busca
    )
    if not encontrado:
        return _garantir_sessao_cookie(
            _wrap_result(
                _card(
                    "Produto não encontrado",
                    [
                        ("Nome buscado", nome_busca),
                        ("Produtos no catálogo local", catalogo_produtos.total(sessao)),
                    ]
                    + _linhas_ciclo(sessao, estado),
                    status_label="Não encontrado",
                    css="erro",
                ),
                extra_attrs={"cursor-fixo": "1", **_attrs_ciclo(sessao)},
            ),
            sessao,
        )

    preco = encontrado.get("preco_tabela")
    if preco is None or preco == "":
        preco = "—"
    ultima = encontrado.get("ultima_alteracao")
    if ultima is None or ultima == "":
        ultima = "—"
    linhas: list[tuple[str, Any]] = [
        ("ID", encontrado.get("id")),
        ("Nome", encontrado.get("nome")),
        ("Preço tabela", preco),
        ("Última alteração", ultima),
        ("Ativo", _ativo_produto(encontrado)),
        ("Origem", "Catálogo local sincronizado"),
    ]
    linhas.extend(_linhas_ciclo(sessao, estado))
    nota = ""
    if not no_ultimo_lote:
        nota = (
            '<p class="hint">Produto localizado no catálogo do ERP; '
            "não veio no último lote incremental.</p>"
        )
    card = _card(
        "Produto localizado",
        linhas,
        status_label="Encontrado",
        css="ok",
    )
    # Garantir que etapa/ciclo não mudaram
    ciclo_depois = catalogo_produtos.obter_ciclo(sessao)
    if ciclo_antes.get("etapa_interna") != ciclo_depois.get("etapa_interna"):
        catalogo_produtos._salvar_ciclo(sessao, ciclo_antes)
    resp = _wrap_result(
        nota + card + _html_patch_catalogo(sessao),
        extra_attrs={
            "status-sync": "localizado",
            "no-ultimo-lote": "1" if no_ultimo_lote else "0",
            "cursor-fixo": "1",
            "catalogo-total": str(catalogo_produtos.total(sessao)),
            **_attrs_ciclo(sessao),
        },
    )
    return _garantir_sessao_cookie(resp, sessao)


def _bool_form(valor: str, default: bool = True) -> bool:
    texto = (valor or "").strip().lower()
    if not texto:
        return default
    if texto in ("1", "true", "sim", "s", "yes", "ativo"):
        return True
    if texto in ("0", "false", "nao", "não", "n", "no", "inativo"):
        return False
    return default


def _float_form(valor: str) -> float | None:
    texto = (valor or "").strip().replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


@router.post("/homologacao-ui/acoes/produtos-criar", response_class=HTMLResponse)
def acao_produtos_criar(
    request: Request,
    token: str = Form(""),
    nome: str = Form(""),
    codigo: str = Form(""),
    preco_tabela: str = Form(""),
    saldo_estoque: str = Form(""),
    ativo: str = Form("true"),
    unidade: str = Form(""),
    observacoes: str = Form(""),
):
    """Cadastro operacional de produto — independente do ciclo GET incremental."""
    _auth(request, token)
    nome_txt = (nome or "").strip()
    codigo_txt = (codigo or "").strip()
    if not nome_txt or not codigo_txt:
        return _wrap_result(
            _card(
                "Dados incompletos",
                [
                    ("Mensagem", "Informe nome e código do produto (obrigatórios)."),
                ],
                status_label="Validação",
                css="erro",
            )
        )
    body: dict[str, Any] = {
        "nome": nome_txt[:300],
        "codigo": codigo_txt[:30],
        "ativo": _bool_form(ativo, True),
    }
    preco = _float_form(preco_tabela)
    if preco is not None:
        body["preco_tabela"] = preco
    estoque = _float_form(saldo_estoque)
    if estoque is not None:
        body["saldo_estoque"] = estoque
    if (unidade or "").strip():
        body["unidade"] = (unidade or "").strip()[:5]
    if (observacoes or "").strip():
        body["observacoes"] = (observacoes or "").strip()[:5000]
    try:
        out = homolog.criar_produto(body)
        dados = out.get("dados") if isinstance(out.get("dados"), dict) else {}
        pid = out.get("id") or dados.get("id")
        card = _card(
            "Produto cadastrado",
            [
                ("Status HTTP", out.get("status_code") or 201),
                ("ID", pid),
                ("Nome", dados.get("nome") if dados.get("nome") not in (None, "") else body["nome"]),
                (
                    "Código",
                    dados.get("codigo")
                    if dados.get("codigo") not in (None, "")
                    else body["codigo"],
                ),
                (
                    "Preço tabela",
                    dados.get("preco_tabela")
                    if dados.get("preco_tabela") not in (None, "")
                    else body.get("preco_tabela", "—"),
                ),
                (
                    "Estoque",
                    dados.get("saldo_estoque")
                    if dados.get("saldo_estoque") not in (None, "")
                    else body.get("saldo_estoque", "—"),
                ),
                (
                    "Ativo",
                    _fmt_bool(
                        dados.get("ativo")
                        if "ativo" in dados
                        else body.get("ativo")
                    ),
                ),
                (
                    "Última alteração",
                    dados.get("ultima_alteracao")
                    or dados.get("data_criacao")
                    or "—",
                ),
            ],
            status_label=f"Status {out.get('status_code') or 201}",
            css="ok",
        )
        return _wrap_result(card, entity="produto", entity_id=str(pid or ""))
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/produtos-alterar", response_class=HTMLResponse)
def acao_produtos_alterar(
    request: Request,
    token: str = Form(""),
    produto_id: str = Form(""),
    nome: str = Form(""),
    codigo: str = Form(""),
    preco_tabela: str = Form(""),
    saldo_estoque: str = Form(""),
    ativo: str = Form(""),
    unidade: str = Form(""),
    excluido: str = Form(""),
):
    """Alteração operacional de produto (inclui exclusão lógica via excluido=true)."""
    _auth(request, token)
    pid_txt = (produto_id or "").strip()
    if not pid_txt:
        return _wrap_result(
            _card(
                "Produto não informado",
                [("Mensagem", "Informe o ID do produto que será alterado.")],
                status_label="Validação",
                css="erro",
            )
        )

    # Só entram no corpo os campos preenchidos (Mercos aceita atualização parcial)
    body: dict[str, Any] = {}
    if (nome or "").strip():
        body["nome"] = (nome or "").strip()[:300]
    if (codigo or "").strip():
        body["codigo"] = (codigo or "").strip()[:30]
    preco = _float_form(preco_tabela)
    if preco is not None:
        body["preco_tabela"] = preco
    estoque = _float_form(saldo_estoque)
    if estoque is not None:
        body["saldo_estoque"] = estoque
    ativo_txt = (ativo or "").strip().lower()
    if ativo_txt in ("true", "false"):
        body["ativo"] = ativo_txt == "true"
    if (unidade or "").strip():
        body["unidade"] = (unidade or "").strip()[:5]
    excluido_txt = (excluido or "").strip().lower()
    if excluido_txt in ("true", "false"):
        body["excluido"] = excluido_txt == "true"  # exclusão lógica, nunca DELETE

    if not body:
        return _wrap_result(
            _card(
                "Nada para alterar",
                [("Mensagem", "Preencha ao menos um campo para atualizar o produto.")],
                status_label="Validação",
                css="erro",
            )
        )

    try:
        out = homolog.alterar_produto(pid_txt, body)
        dados = out.get("dados") if isinstance(out.get("dados"), dict) else {}

        def _mostra(chave: str) -> Any:
            valor = dados.get(chave)
            if valor not in (None, ""):
                return valor
            return body.get(chave, "—")

        ativo_final = dados.get("ativo") if "ativo" in dados else body.get("ativo")
        excluido_final = (
            dados.get("excluido") if "excluido" in dados else body.get("excluido")
        )
        titulo_card = (
            "Produto excluído logicamente"
            if body.get("excluido") is True
            else "Produto alterado"
        )
        card = _card(
            titulo_card,
            [
                ("Status HTTP", out.get("status_code") or 200),
                ("ID", pid_txt),
                ("Nome", _mostra("nome")),
                ("Código", _mostra("codigo")),
                ("Preço tabela", _mostra("preco_tabela")),
                ("Estoque", _mostra("saldo_estoque")),
                (
                    "Excluído",
                    _fmt_bool(excluido_final) if excluido_final is not None else "—",
                ),
                ("Ativo", _fmt_bool(ativo_final) if ativo_final is not None else "—"),
                ("Última alteração", dados.get("ultima_alteracao") or "—"),
            ],
            status_label=f"Status {out.get('status_code') or 200}",
            css="ok",
        )
        return _wrap_result(card, entity="produto", entity_id=pid_txt)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


_NOME_PRODUTO_IMAGEM_DESTAQUE = "988c59d30ae54204"


@router.post("/homologacao-ui/acoes/produto-imagens", response_class=HTMLResponse)
def acao_produto_imagens(
    request: Request,
    token: str = Form(""),
    nome: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Imagens do produto pelo nome: localiza no catálogo local e faz UMA chamada
    de imagens à Mercos. Não altera cursor nem ciclo do Produto GET."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao(request)
    _hidratar_catalogo_form(sessao, catalogo_json)
    ciclo_antes = catalogo_produtos.obter_ciclo(sessao)
    nome_busca = (nome or "").strip()
    attrs_fixos = {"cursor-fixo": "1", **_attrs_ciclo(sessao)}
    if not nome_busca:
        return _garantir_sessao_cookie(
            _wrap_result(
                _card(
                    "Imagem do produto",
                    [("Mensagem", "Informe o nome exato do produto.")],
                    status_label="Atenção",
                    css="erro",
                ),
                extra_attrs=attrs_fixos,
            ),
            sessao,
        )

    encontrado, _no_lote, _estado = catalogo_produtos.buscar_por_nome(
        sessao, nome_busca
    )
    origem_produto = "Catálogo local sincronizado"
    if not encontrado:
        # Consulta controlada (1 requisição, sem paginação): não altera
        # catálogo, cursor nem ciclo do Produto GET.
        try:
            encontrado = homolog.localizar_produto_por_nome(nome_busca)
            origem_produto = "Consulta controlada na Mercos"
        except MercosApiError as exc:
            return _garantir_sessao_cookie(
                _wrap_result(_erro_html(exc), extra_attrs=attrs_fixos), sessao
            )
    if not encontrado:
        return _garantir_sessao_cookie(
            _wrap_result(
                _card(
                    "Produto não encontrado",
                    [
                        ("Nome buscado", nome_busca),
                        ("Produtos no catálogo local", catalogo_produtos.total(sessao)),
                        ("Mensagem", "Sincronize o Produto GET ou confira o nome exato."),
                    ],
                    status_label="Não encontrado",
                    css="erro",
                ),
                extra_attrs=attrs_fixos,
            ),
            sessao,
        )

    pid = encontrado.get("id")
    nome_produto = str(encontrado.get("nome") or nome_busca)
    destaque = nome_produto.strip().lower() == _NOME_PRODUTO_IMAGEM_DESTAQUE
    try:
        out = homolog.listar_imagens_produto(pid)
    except MercosApiError as exc:
        if exc.status_code == 429:
            segundos = exc.retry_after if exc.retry_after is not None else 10
            try:
                segundos = max(0, int(float(segundos)))
            except (TypeError, ValueError):
                segundos = 10
            resp = _wrap_result(
                _card(
                    "Aguardando limite da Mercos",
                    [
                        ("Mensagem", "Aguardando limite da Mercos"),
                        ("Segundos restantes", segundos),
                        ("Produto", nome_produto),
                    ],
                    status_label="Aguardando",
                    css="pendente",
                ),
                extra_attrs=attrs_fixos,
            )
            resp.headers["Retry-After"] = str(segundos)
            return _garantir_sessao_cookie(resp, sessao)
        if exc.status_code == 404:
            return _garantir_sessao_cookie(
                _wrap_result(
                    _card(
                        "Imagens não encontradas",
                        [
                            ("ID do produto", pid),
                            ("Nome do produto", nome_produto),
                            ("Status HTTP", 404),
                            ("Mensagem", "A Mercos não encontrou imagens para este produto."),
                        ],
                        status_label="Erro 404",
                        css="erro",
                    ),
                    extra_attrs=attrs_fixos,
                ),
                sessao,
            )
        return _garantir_sessao_cookie(
            _wrap_result(_erro_html(exc), extra_attrs=attrs_fixos), sessao
        )
    except Exception as exc:
        return _garantir_sessao_cookie(
            _wrap_result(_erro_html(exc), extra_attrs=attrs_fixos), sessao
        )

    imagens = out.get("imagens") or []
    linhas: list[tuple[str, Any]] = [
        ("ID do produto", pid),
        ("Nome do produto", nome_produto),
        ("Status HTTP", out.get("status_code") or 200),
        ("Total de imagens", len(imagens)),
        ("Origem do produto", origem_produto),
        ("Origem", "Mercos Sandbox" if out.get("sandbox") else "Mercos"),
    ]
    if len(imagens) == 1:
        linhas.insert(2, ("Hash da imagem", imagens[0].get("hash")))
    card = _card(
        "Imagens do produto" if imagens else "Produto sem imagem",
        linhas
        if imagens
        else linhas + [("Mensagem", "A Mercos não retornou imagens para este produto.")],
        status_label="Encontrado" if imagens else "Sem imagem",
        css="ok" if imagens else "pendente",
    )
    tabela = ""
    if imagens:
        tem_url = any(img.get("url") not in (None, "") for img in imagens)
        headers = ["ID da imagem", "Hash da imagem"] + (["URL/arquivo"] if tem_url else [])
        rows = []
        classes = []
        for img in imagens:
            row = [
                img.get("id") if img.get("id") not in (None, "") else "—",
                img.get("hash"),  # exatamente como retornado pela Mercos
            ]
            if tem_url:
                row.append(img.get("url") if img.get("url") not in (None, "") else "—")
            rows.append(row)
            classes.append("destaque-homolog" if destaque else "")
        tabela = _table(headers, rows, row_classes=classes)
    ciclo_depois = catalogo_produtos.obter_ciclo(sessao)
    if ciclo_antes.get("etapa_interna") != ciclo_depois.get("etapa_interna"):
        catalogo_produtos._salvar_ciclo(sessao, ciclo_antes)
    return _garantir_sessao_cookie(
        _wrap_result(
            card + tabela,
            entity="produto",
            entity_id=str(pid or ""),
            extra_attrs={**attrs_fixos, "status-sync": "imagens"},
        ),
        sessao,
    )


def _card_erro_imagem(titulo: str, linhas: list[tuple[str, Any]], status: Any) -> HTMLResponse:
    return _wrap_result(
        _card(titulo, linhas, status_label=f"Erro {status}", css="erro"),
        extra_attrs={"cursor-fixo": "1"},
    )


@router.post("/homologacao-ui/acoes/produto-imagem-adicionar", response_class=HTMLResponse)
async def acao_produto_imagem_adicionar(
    request: Request,
    token: str = Form(""),
    produto_id: str = Form(""),
    nome: str = Form(""),
    ordem: str = Form(""),
    imagem_url: str = Form(""),
    imagem: UploadFile | None = File(None),
):
    """Adiciona imagem ao produto via POST /v1/imagens_produto (URL ou Base64).

    Não toca em catálogo, cursor nem ciclo do Produto GET; uma chamada de envio
    por clique (+1 consulta de hash após sucesso, pois o POST não retorna hash)."""
    _auth(request, token)
    attrs_fixos = {"cursor-fixo": "1"}
    pid = (produto_id or "").strip()
    nome_produto = (nome or "").strip() or "—"
    if not pid.isdigit():
        return _card_erro_imagem(
            "Imagem do produto",
            [("Mensagem", "Informe o ID numérico do produto Mercos.")],
            422,
        )

    url_informada = (imagem_url or "").strip()
    b64 = ""
    nome_arquivo = ""
    if imagem is not None and (imagem.filename or "").strip():
        nome_arquivo = imagem.filename.strip()
        extensao = os.path.splitext(nome_arquivo)[1].lower()
        if extensao not in homolog.FORMATOS_IMAGEM_PRODUTO:
            return _card_erro_imagem(
                "Arquivo inválido",
                [
                    ("Arquivo", nome_arquivo),
                    ("Mensagem", "Formato não aceito pela Mercos. Use PNG ou JPG."),
                ],
                422,
            )
        conteudo = await imagem.read()
        if not conteudo:
            return _card_erro_imagem(
                "Arquivo inválido",
                [("Arquivo", nome_arquivo), ("Mensagem", "O arquivo está vazio.")],
                422,
            )
        if len(conteudo) > homolog.IMAGEM_PRODUTO_MAX_BYTES:
            mb = homolog.IMAGEM_PRODUTO_MAX_BYTES // (1024 * 1024)
            return _card_erro_imagem(
                "Imagem muito grande",
                [
                    ("Arquivo", nome_arquivo),
                    ("Tamanho", f"{len(conteudo) / (1024 * 1024):.1f} MB"),
                    ("Mensagem", f"Envie uma imagem de até {mb} MB."),
                ],
                413,
            )
        b64 = base64.b64encode(conteudo).decode("ascii")

    if not b64 and not url_informada:
        return _card_erro_imagem(
            "Imagem do produto",
            [("Mensagem", "Selecione um arquivo PNG/JPG ou informe a URL da imagem.")],
            422,
        )

    try:
        # Doc Mercos: se URL e Base64 forem enviados juntos, só a URL vale —
        # por isso enviamos apenas um dos dois (arquivo tem prioridade aqui).
        out = homolog.criar_imagem_produto(
            pid,
            imagem_url=None if b64 else url_informada,
            imagem_base64=b64 or None,
            ordem=ordem,
        )
    except MercosApiError as exc:
        if exc.status_code == 429:
            segundos = exc.retry_after if exc.retry_after is not None else 10
            try:
                segundos = max(0, int(float(segundos)))
            except (TypeError, ValueError):
                segundos = 10
            resp = _wrap_result(
                _card(
                    "Aguardando limite da Mercos",
                    [
                        ("Mensagem", "Aguardando limite da Mercos"),
                        ("Segundos restantes", segundos),
                        ("Produto", f"{pid} — {nome_produto}"),
                    ],
                    status_label="Aguardando",
                    css="pendente",
                ),
                extra_attrs=attrs_fixos,
            )
            resp.headers["Retry-After"] = str(segundos)
            return resp
        if exc.status_code == 404:
            return _card_erro_imagem(
                "Produto não encontrado",
                [
                    ("ID do produto", pid),
                    ("Mensagem", "A Mercos não encontrou este produto (HTTP 404)."),
                ],
                404,
            )
        if exc.status_code in (400, 412, 422):
            return _card_erro_imagem(
                "Dados recusados pela Mercos",
                [("ID do produto", pid), ("Mensagem", exc.message)],
                exc.status_code,
            )
        return _wrap_result(_erro_html(exc), extra_attrs=attrs_fixos)
    except Exception as exc:
        return _wrap_result(_erro_html(exc), extra_attrs=attrs_fixos)

    # POST não devolve o hash: uma consulta de hashes após o sucesso.
    hashes: list[str] = []
    hash_novo = "—"
    try:
        consulta = homolog.listar_imagens_produto(pid)
        hashes = [
            str(img.get("hash"))
            for img in consulta.get("imagens") or []
            if img.get("hash") not in (None, "")
        ]
        if hashes:
            hash_novo = hashes[-1]
    except Exception:
        pass

    status_http = out.get("status_code") or 201
    linhas: list[tuple[str, Any]] = [
        ("Status HTTP", status_http),
        ("ID do produto", pid),
        ("Nome do produto", nome_produto),
        ("Hash retornado", hash_novo),
        ("Quantidade de imagens", len(hashes)),
    ]
    if nome_arquivo:
        linhas.append(("Arquivo", nome_arquivo))
    if out.get("id") not in (None, ""):
        linhas.append(("ID da imagem (MeusPedidosID)", out.get("id")))
    linhas.append(("Origem", "Mercos Sandbox" if out.get("sandbox") else "Mercos"))
    if hash_novo == "—":
        linhas.append(
            ("Observação", "A Mercos ainda não retornou o hash; consulte novamente em instantes.")
        )
    tabela = ""
    if len(hashes) > 1:
        tabela = _table(
            ["#", "Hash da imagem"],
            [[i + 1, h] for i, h in enumerate(hashes)],
        )
    return _wrap_result(
        _card(
            "Imagem adicionada ao produto",
            linhas,
            status_label="Enviado",
            css="ok",
        )
        + tabela,
        entity="produto",
        entity_id=pid,
        extra_attrs={**attrs_fixos, "status-sync": "imagem-post"},
    )


@router.post("/homologacao-ui/acoes/categorias", response_class=HTMLResponse)
def acao_categorias(request: Request, token: str = Form("")):
    _auth(request, token)
    try:
        data = homolog.listar_categorias(pagina_inicial=1, max_paginas=3)
        rows = [
            [
                _campo(i, "id"),
                _campo(i, "nome"),
                _fmt_bool(_campo(i, "excluido", default=False)),
            ]
            for i in (data.get("itens") or [])
        ]
        table = _table(["ID", "Nome", "Excluído"], rows)
        head = f'<p class="meta">Total: <strong>{_esc(data.get("total", 0))}</strong> · Status: <strong>200</strong></p>'
        return _wrap_result(head + table)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/clientes-buscar", response_class=HTMLResponse)
def acao_clientes_buscar(
    request: Request,
    token: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Busca simples — bloqueada durante ciclo ativo de homologação."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_clientes(request)
    _hidratar_catalogo_clientes_form(sessao, catalogo_json)
    if catalogo_clientes.ciclo_ativo(sessao):
        resp = _wrap_result(
            _card(
                "Busca completa bloqueada durante a homologação",
                [
                    (
                        "Mensagem",
                        "Use apenas «Sincronizar próxima etapa» durante o ciclo ativo.",
                    )
                ]
                + _linhas_ciclo_clientes(sessao),
                status_label="Bloqueado",
                css="erro",
            ),
            extra_attrs={
                "status-sync": "bloqueado",
                **_attrs_ciclo_clientes(sessao),
            },
        )
        return _garantir_sessao_clientes_cookie(resp, sessao)
    try:
        data = homolog.listar_clientes(pagina_inicial=1, max_paginas=3)
        table = _html_tabela_clientes(data.get("itens") or [])
        head = (
            f'<p class="meta">Total: <strong>{_esc(data.get("total", 0))}</strong>'
            " · Status: <strong>200</strong></p>"
        )
        resp = _wrap_result(head + table, extra_attrs=_attrs_ciclo_clientes(sessao))
        return _garantir_sessao_clientes_cookie(resp, sessao)
    except Exception as exc:
        resp = _wrap_result(_erro_html(exc))
        return _garantir_sessao_clientes_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/clientes-reiniciar", response_class=HTMLResponse)
def acao_clientes_reiniciar(
    request: Request,
    token: str = Form(""),
):
    """Apaga cursor e catálogo de clientes, inicia ciclo na etapa 0 — sem chamar a Mercos."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_clientes(request)
    catalogo_clientes.iniciar_ciclo(sessao)
    homolog._limpar_resumes_da_sessao(sessao)
    estado = catalogo_clientes.obter(sessao)
    mensagem = (
        '<div class="result-card ok">'
        "<h4>Ciclo de sincronização reiniciado</h4>"
        "<p>Cursor e catálogo anteriores apagados. Novo ciclo ativo na etapa 0. "
        "Use «Sincronizar próxima etapa» para a busca completa.</p>"
        "</div>"
    )
    resumo = _card(
        "Estado do ciclo",
        _linhas_ciclo_clientes(sessao, estado),
        status_label="Ciclo ativo",
        css="ok",
    )
    resp = _wrap_result(
        mensagem + resumo + _html_patch_catalogo_clientes(sessao),
        extra_attrs={
            "novo-cursor": "",
            "cursor-limpo": "1",
            "catalogo-limpo": "1",
            "status-sync": "reiniciado",
            "catalogo-total": "0",
            **_attrs_ciclo_clientes(sessao),
        },
    )
    resp = _set_cursor_clientes_cookie(resp, None)
    return _garantir_sessao_clientes_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/clientes-sincronizar", response_class=HTMLResponse)
def acao_clientes_sincronizar(
    request: Request,
    token: str = Form(""),
    cursor: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Única ação que chama a Mercos no ciclo: etapa 0 completa; 1 e 2 incrementais."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_clientes(request)
    _hidratar_catalogo_clientes_form(sessao, catalogo_json)
    ciclo = catalogo_clientes.obter_ciclo(sessao)
    if not ciclo.get("ativo"):
        catalogo_clientes.iniciar_ciclo(sessao)
        ciclo = catalogo_clientes.obter_ciclo(sessao)

    etapa = int(ciclo.get("etapa_interna") or 0)
    cursor_form = _cursor_clientes(request, cursor)

    if etapa == 0:
        cursor_para_sync = None
        tipo_esperado = "completa"
    else:
        if not cursor_form:
            resp = _wrap_result(
                _card(
                    "Cursor ausente",
                    [
                        (
                            "Mensagem",
                            "Etapa incremental exige cursor salvo. Reinicie o ciclo se necessário.",
                        )
                    ]
                    + _linhas_ciclo_clientes(sessao),
                    status_label="Erro",
                    css="erro",
                ),
                extra_attrs={"status-sync": "erro", **_attrs_ciclo_clientes(sessao)},
            )
            return _garantir_sessao_clientes_cookie(resp, sessao)
        cursor_para_sync = cursor_form
        tipo_esperado = "incremental"

    try:
        data = homolog.sincronizar_clientes(
            cursor_para_sync, max_paginas=20, sessao_id=sessao
        )
        tipo_real = data.get("tipo") or tipo_esperado
        if etapa >= 1 and tipo_real == "completa":
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [
                        (
                            "Mensagem",
                            "A etapa atual exige busca incremental com alterado_apos.",
                        )
                    ]
                    + _linhas_ciclo_clientes(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_clientes(sessao)},
            )
            return _garantir_sessao_clientes_cookie(resp, sessao)
        if etapa >= 1 and not data.get("alterado_apos_enviado"):
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [
                        (
                            "Mensagem",
                            "alterado_apos não foi enviado na etapa incremental.",
                        )
                    ]
                    + _linhas_ciclo_clientes(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_clientes(sessao)},
            )
            return _garantir_sessao_clientes_cookie(resp, sessao)

        status_sync = data.get("status") or "concluida"
        motivo = data.get("motivo_parada") or ""
        status_label = (
            "Timeout"
            if status_sync == "timeout"
            else "Concluída"
        )
        meta = {
            "tipo": tipo_real,
            "cursor_base": data.get("cursor_base"),
            "alterado_apos_enviado": data.get("alterado_apos_enviado"),
            "novo_cursor": data.get("novo_cursor"),
            "total_lote": data.get("total", 0),
            "paginas_lidas": data.get("paginas_lidas") or 0,
            "motivo_parada": motivo,
            "status_sync": status_label,
            "requisicoes_extras": data.get("requisicoes_extras"),
            "requisicoes_previstas": data.get("requisicoes_previstas"),
            "requisicoes_executadas": data.get("requisicoes_executadas"),
        }
        if tipo_real == "completa":
            catalogo_clientes.substituir_completo(
                sessao, data.get("itens") or [], meta=meta
            )
        else:
            catalogo_clientes.upsert_incremental(
                sessao, data.get("itens") or [], meta=meta
            )
        try:
            catalogo_clientes.registrar_sync_ciclo(sessao, tipo=tipo_real)
        except ValueError as exc:
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [("Mensagem", str(exc))] + _linhas_ciclo_clientes(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_clientes(sessao)},
            )
            return _garantir_sessao_clientes_cookie(resp, sessao)

        estado = catalogo_clientes.obter(sessao)
        total = data.get("total", 0)
        paginas = data.get("paginas_lidas") or 0
        css = "pendente" if status_sync == "timeout" else "ok"
        resumo = _card(
            "Sincronização de clientes",
            [
                ("Status da sincronização", status_label),
                ("Motivo da parada", motivo or "—"),
            ]
            + _linhas_ciclo_clientes(sessao, estado),
            status_label=status_label,
            css=css,
        )
        table = _html_tabela_clientes(data.get("itens") or [])
        resp = _wrap_result(
            resumo + table + _html_patch_catalogo_clientes(sessao),
            extra_attrs={
                "novo-cursor": data.get("novo_cursor") or "",
                "cursor-anterior": data.get("cursor_anterior") or "",
                "cursor-base": data.get("cursor_base") or "",
                "alterado-apos-enviado": data.get("alterado_apos_enviado") or "",
                "tipo-busca": tipo_real,
                "total": str(total),
                "paginas-lidas": str(paginas),
                "requisicoes-extras": str(data.get("requisicoes_extras") if data.get("requisicoes_extras") is not None else ""),
                "requisicoes-previstas": str(data.get("requisicoes_previstas") if data.get("requisicoes_previstas") is not None else ""),
                "requisicoes-executadas": str(data.get("requisicoes_executadas") or 0),
                "motivo-parada": motivo,
                "catalogo-total": str(len(estado.get("clientes") or {})),
                "catalogo-modo": "replace" if tipo_real == "completa" else "upsert",
                "status-sync": status_sync,
                **_attrs_ciclo_clientes(sessao),
            },
        )
        resp = _set_cursor_clientes_cookie(resp, data.get("novo_cursor"))
        return _garantir_sessao_clientes_cookie(resp, sessao)
    except MercosApiError as exc:
        if exc.status_code == 429:
            segundos = exc.retry_after
            if segundos is None:
                segundos = 10
            try:
                segundos = max(0, int(float(segundos)))
            except (TypeError, ValueError):
                segundos = 10
            pagina_atual = exc.pagina if exc.pagina is not None else "—"
            html_429 = _card(
                "Aguardando limite da Mercos",
                [
                    ("Mensagem", "Aguardando limite da Mercos"),
                    ("Segundos restantes", segundos),
                    ("Página atual", pagina_atual),
                ],
                status_label="Aguardando",
                css="pendente",
            )
            resp = _wrap_result(
                html_429,
                extra_attrs={
                    "status-sync": "aguardando-429",
                    "aguardando-mercos": "1",
                    "segundos-espera": str(segundos),
                    "pagina-atual": str(pagina_atual),
                    "http-status": "429",
                    **_attrs_ciclo_clientes(sessao),
                },
            )
            resp.status_code = 429
            resp.headers["Retry-After"] = str(segundos)
            resp.headers["X-Mercos-Pagina"] = str(pagina_atual)
            return _garantir_sessao_clientes_cookie(resp, sessao)
        html_erro = _erro_html(exc)
        resp = _wrap_result(
            html_erro,
            extra_attrs={
                "status-sync": "erro",
                "http-status": str(exc.status_code or ""),
                **_attrs_ciclo_clientes(sessao),
            },
        )
        if exc.status_code == 409:
            resp.status_code = 409
        elif exc.status_code == 504:
            resp.status_code = 504
        return _garantir_sessao_clientes_cookie(resp, sessao)
    except Exception as exc:
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={"status-sync": "erro", **_attrs_ciclo_clientes(sessao)},
        )
        return _garantir_sessao_clientes_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/clientes-localizar", response_class=HTMLResponse)
def acao_clientes_localizar(
    request: Request,
    token: str = Form(""),
    razao_social: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Localiza pela razão social exata no catálogo local. Não chama Mercos nem altera cursor."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_clientes(request)
    _hidratar_catalogo_clientes_form(sessao, catalogo_json)
    ciclo_antes = catalogo_clientes.obter_ciclo(sessao)
    busca = (razao_social or "").strip()
    if not busca:
        return _garantir_sessao_clientes_cookie(
            _wrap_result(
                _card(
                    "Localizar cliente",
                    [("Mensagem", "Informe a razão social exata do cliente.")],
                    status_label="Atenção",
                    css="erro",
                )
            ),
            sessao,
        )

    encontrado, no_ultimo_lote, estado = catalogo_clientes.buscar_por_razao_social(
        sessao, busca
    )
    if not encontrado:
        return _garantir_sessao_clientes_cookie(
            _wrap_result(
                _card(
                    "Cliente não encontrado",
                    [
                        ("Razão social buscada", busca),
                        ("Clientes no catálogo local", catalogo_clientes.total(sessao)),
                    ]
                    + _linhas_ciclo_clientes(sessao, estado),
                    status_label="Não encontrado",
                    css="erro",
                ),
                extra_attrs={"cursor-fixo": "1", **_attrs_ciclo_clientes(sessao)},
            ),
            sessao,
        )

    ultima = encontrado.get("ultima_alteracao")
    if ultima is None or ultima == "":
        ultima = "—"
    linhas: list[tuple[str, Any]] = [
        ("ID", encontrado.get("id")),
        ("Razão social", encontrado.get("razao_social")),
        ("Nome fantasia", encontrado.get("nome_fantasia") or "—"),
        ("CNPJ", encontrado.get("cnpj") or "—"),
        ("E-mail", encontrado.get("email") or "—"),
        ("Ativo", _ativo_produto(encontrado)),
        ("Última alteração", ultima),
        ("Origem", "Catálogo local sincronizado"),
    ]
    linhas.extend(_linhas_ciclo_clientes(sessao, estado))
    nota = ""
    if not no_ultimo_lote:
        nota = (
            '<p class="hint">Cliente localizado no catálogo do ERP; '
            "não veio no último lote incremental.</p>"
        )
    card = _card(
        "Cliente localizado",
        linhas,
        status_label="Encontrado",
        css="ok",
    )
    ciclo_depois = catalogo_clientes.obter_ciclo(sessao)
    if ciclo_antes.get("etapa_interna") != ciclo_depois.get("etapa_interna"):
        catalogo_clientes._salvar_ciclo(sessao, ciclo_antes)
    resp = _wrap_result(
        nota + card + _html_patch_catalogo_clientes(sessao),
        extra_attrs={
            "status-sync": "localizado",
            "cursor-fixo": "1",
            **_attrs_ciclo_clientes(sessao),
        },
    )
    return _garantir_sessao_clientes_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/clientes-criar", response_class=HTMLResponse)
def acao_clientes_criar(
    request: Request,
    token: str = Form(""),
    tipo: str = Form("J"),
    razao_social: str = Form(""),
    nome_fantasia: str = Form(""),
    cnpj: str = Form(""),
    email: str = Form(""),
    ativo: str = Form("true"),
):
    """Envia exatamente os valores do formulário — nada é gerado automaticamente."""
    _auth(request, token)
    tipo_val = (tipo or "").strip().upper() or "J"
    if tipo_val not in ("J", "F"):
        tipo_val = "J"
    razao_val = (razao_social or "").strip()
    fantasia_val = (nome_fantasia or "").strip()
    cnpj_val = (cnpj or "").strip()
    email_val = (email or "").strip()
    ativo_val = (ativo or "true").strip().lower() != "false"

    faltando = [
        rotulo
        for rotulo, valor in (
            ("Razão social", razao_val),
            ("Nome fantasia", fantasia_val),
            ("CNPJ/CPF", cnpj_val),
        )
        if not valor
    ]
    if faltando:
        return _wrap_result(
            _card(
                "Campos obrigatórios ausentes",
                [("Preencha", ", ".join(faltando))],
                status_label="Pendente",
                css="pendente",
            )
        )

    body = {
        "tipo": tipo_val,
        "razao_social": razao_val,
        "nome_fantasia": fantasia_val,
        "cnpj": cnpj_val,  # enviado exatamente como digitado, sem formatação
        "ativo": ativo_val,
    }
    if email_val:
        body["email"] = email_val
    try:
        out = homolog.criar_cliente(body)
        dados = out.get("dados") or {}
        cid = out.get("id") or dados.get("id")

        def _retornado_ou_enviado(chave: str, enviado: Any) -> Any:
            valor = dados.get(chave)
            if valor in (None, ""):
                return enviado
            return valor

        ativo_final = _retornado_ou_enviado("ativo", ativo_val)
        card = _card(
            "Cliente criado",
            [
                ("Status HTTP", out.get("status_code") or 201),
                ("ID criado", cid or "—"),
                ("Tipo", _retornado_ou_enviado("tipo", tipo_val)),
                ("Razão social", _retornado_ou_enviado("razao_social", razao_val)),
                ("Nome fantasia", _retornado_ou_enviado("nome_fantasia", fantasia_val)),
                ("CNPJ", _retornado_ou_enviado("cnpj", cnpj_val)),
                ("E-mail", _retornado_ou_enviado("email", email_val or "—")),
                ("Ativo", _fmt_bool(ativo_final)),
                ("Última alteração", dados.get("ultima_alteracao") or "—"),
            ],
            status_label=f"Status {out.get('status_code') or 201}",
            css="ok",
        )
        return _wrap_result(card, entity="cliente", entity_id=str(cid or ""))
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/clientes-alterar", response_class=HTMLResponse)
def acao_clientes_alterar(
    request: Request,
    token: str = Form(""),
    cliente_id: str = Form(""),
    tipo: str = Form(""),
    razao_social: str = Form(""),
    nome_fantasia: str = Form(""),
    cnpj: str = Form(""),
    email: str = Form(""),
    ativo: str = Form(""),
    excluido: str = Form(""),
):
    """Envia exatamente os valores preenchidos ao PUT — nada é gerado
    automaticamente; campos vazios não entram no corpo; id só na URL.
    Exclusão lógica: excluido=true via PUT (sem DELETE, nada é apagado)."""
    _auth(request, token)
    cid = (cliente_id or "").strip()
    if not cid:
        return _wrap_result(
            _card(
                "Cliente não informado",
                [("Ação", "Informe o ID do cliente que será alterado.")],
                status_label="Pendente",
                css="pendente",
            )
        )

    tipo_val = (tipo or "").strip().upper()
    razao_val = (razao_social or "").strip()
    fantasia_val = (nome_fantasia or "").strip()
    cnpj_val = (cnpj or "").strip()
    email_val = (email or "").strip()
    ativo_val = (ativo or "").strip().lower()
    excluido_val = (excluido or "").strip().lower()

    body: dict[str, Any] = {}
    if tipo_val in ("J", "F"):
        body["tipo"] = tipo_val
    if razao_val:
        body["razao_social"] = razao_val
    if fantasia_val:
        body["nome_fantasia"] = fantasia_val
    if cnpj_val:
        body["cnpj"] = cnpj_val  # enviado exatamente como digitado, sem formatação
    if email_val:
        body["email"] = email_val
    if ativo_val in ("true", "false"):
        body["ativo"] = ativo_val == "true"
    if excluido_val in ("true", "false"):
        body["excluido"] = excluido_val == "true"

    if not body:
        return _wrap_result(
            _card(
                "Nenhum campo para alterar",
                [("Ação", "Preencha ao menos um campo além do ID.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        out = homolog.alterar_cliente(cid, body)
        dados = out.get("dados") or {}

        def _retornado_ou_enviado(chave: str, enviado: Any) -> Any:
            valor = dados.get(chave)
            if valor in (None, ""):
                return enviado
            return valor

        ativo_final = _retornado_ou_enviado("ativo", body.get("ativo"))
        excluido_final = _retornado_ou_enviado("excluido", body.get("excluido"))
        exclusao_logica = body.get("excluido") is True
        linhas = [
            ("Status HTTP", out.get("status_code") or 200),
            ("ID", cid),
            ("Tipo", _retornado_ou_enviado("tipo", body.get("tipo") or "—")),
            (
                "Razão social",
                _retornado_ou_enviado("razao_social", body.get("razao_social") or "—"),
            ),
            (
                "Nome fantasia",
                _retornado_ou_enviado("nome_fantasia", body.get("nome_fantasia") or "—"),
            ),
            ("CNPJ", _retornado_ou_enviado("cnpj", body.get("cnpj") or "—")),
            ("E-mail", _retornado_ou_enviado("email", body.get("email") or "—")),
            ("Ativo", _fmt_bool(ativo_final) if ativo_final is not None else "—"),
            (
                "Excluído",
                _fmt_bool(excluido_final) if excluido_final is not None else "—",
            ),
            ("Última alteração", dados.get("ultima_alteracao") or "—"),
        ]
        card = _card(
            "Cliente excluído logicamente" if exclusao_logica else "Cliente alterado",
            linhas,
            status_label=f"Status {out.get('status_code') or 200}",
            css="ok",
        )
        return _wrap_result(card, entity="cliente", entity_id=cid)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/condicoes", response_class=HTMLResponse)
def acao_condicoes(request: Request, token: str = Form("")):
    _auth(request, token)
    bloqueio = _bloqueio_condicoes_ciclo_ativo(request)
    if bloqueio is not None:
        return bloqueio
    try:
        data = homolog.listar_condicoes_pagamento(pagina_inicial=1, max_paginas=3)
        rows = [
            [
                _campo(i, "id"),
                _campo(i, "nome"),
                _campo(i, "valor_minimo", "valor_minimo_pedido"),
                _fmt_bool(_campo(i, "disponivel_b2b", "b2b", default="—")),
                _fmt_bool(_campo(i, "excluido", default=False)),
            ]
            for i in (data.get("itens") or [])
        ]
        table = _table(
            ["ID", "Nome", "Valor mínimo", "Disponível B2B", "Excluído"],
            rows,
        )
        head = f'<p class="meta">Total: <strong>{_esc(data.get("total", 0))}</strong> · Status: <strong>200</strong></p>'
        return _wrap_result(head + table)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/condicoes-criar", response_class=HTMLResponse)
def acao_condicoes_criar(
    request: Request,
    token: str = Form(""),
    nome: str = Form(""),
    valor_minimo: str = Form(""),
    disponivel_b2b: str = Form(""),
    considerar_limite_credito: str = Form(""),
    ativo: str = Form("sim"),
):
    """POST /v1/condicoes_pagamento — um único envio à Mercos por clique.

    Entidade Condição de Pagamento (não confundir com Forma de Pagamento,
    Pagamento ou Faturamento). Contrato oficial: nome obrigatório; opcionais
    valor_minimo, disponivel_b2b, considerar_limite_credito, excluido.
    Ativo=Sim vira excluido=false. Não altera o ciclo GET.
    """
    _auth(request, token)
    nome_limpo = (nome or "").strip()
    if not nome_limpo:
        return _wrap_result(
            _card(
                "Campos obrigatórios",
                [("Ação", "Informe o nome da condição de pagamento.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    ativo_bool = (ativo or "sim").strip().lower() != "nao"
    body: dict[str, Any] = {"nome": nome_limpo, "excluido": not ativo_bool}

    vm = (valor_minimo or "").strip()
    if vm:
        body["valor_minimo"] = vm

    b2b = (disponivel_b2b or "").strip().lower()
    if b2b in ("sim", "true", "1"):
        body["disponivel_b2b"] = True
    elif b2b in ("nao", "não", "false", "0"):
        body["disponivel_b2b"] = False

    limite = (considerar_limite_credito or "").strip().lower()
    if limite in ("sim", "true", "1"):
        body["considerar_limite_credito"] = True
    elif limite in ("nao", "não", "false", "0"):
        body["considerar_limite_credito"] = False

    try:
        out = homolog.criar_condicao_pagamento(body)
        status = out.get("status_code") or 201
        cid = out.get("id") or (out.get("dados") or {}).get("id") or "—"
        linhas: list[tuple[str, Any]] = [
            ("Status HTTP", status),
            ("ID criado", cid),
            ("Nome", nome_limpo),
        ]
        if "valor_minimo" in body:
            linhas.append(("Valor mínimo", _fmt_valor_minimo(body["valor_minimo"])))
        if "disponivel_b2b" in body:
            linhas.append(("Disponível B2B", _fmt_bool(body["disponivel_b2b"])))
        if "considerar_limite_credito" in body:
            linhas.append(
                ("Considerar limite de crédito", _fmt_bool(body["considerar_limite_credito"]))
            )
        linhas.append(("Ativo", "Sim" if ativo_bool else "Não"))
        linhas.append(("Excluído", _fmt_bool(not ativo_bool)))
        linhas.append(("Origem", "Mercos Sandbox"))
        card = _card(
            "Condição de pagamento criada",
            linhas,
            status_label=f"Status {status}",
            css="ok",
        )
        return _wrap_result(card, entity="condicao_pagamento", entity_id=str(cid or ""))
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/condicoes-alterar", response_class=HTMLResponse)
def acao_condicoes_alterar(
    request: Request,
    token: str = Form(""),
    condicao_id: str = Form(""),
    nome: str = Form(""),
    valor_minimo: str = Form(""),
    disponivel_b2b: str = Form(""),
    considerar_limite_credito: str = Form(""),
    ativo: str = Form(""),
    excluido: str = Form(""),
):
    """PUT /v1/condicoes_pagamento/{id} — um único PUT por clique, id só na URL.

    Contrato oficial: nome obrigatório; opcionais valor_minimo, disponivel_b2b,
    considerar_limite_credito, excluido. Ativo=Sim vira excluido=false; o
    campo Excluído=Sim (ou o botão «Excluir logicamente») envia excluido=true
    junto com o nome. Sem DELETE. Não altera GET/POST.
    """
    _auth(request, token)
    cid = (condicao_id or "").strip()
    nome_limpo = (nome or "").strip()
    if not cid or not nome_limpo:
        return _wrap_result(
            _card(
                "Campos obrigatórios",
                [("Ação", "Informe o ID e o nome da condição de pagamento.")],
                status_label="Pendente",
                css="pendente",
            )
        )

    excluido_bool: bool | None = None
    exc_form = (excluido or "").strip().lower()
    if exc_form in ("true", "sim"):
        excluido_bool = True
    elif exc_form in ("false", "nao", "não"):
        excluido_bool = False
    else:
        ativo_form = (ativo or "").strip().lower()
        if ativo_form in ("sim", "true"):
            excluido_bool = False
        elif ativo_form in ("nao", "não", "false"):
            excluido_bool = True

    body: dict[str, Any] = {"nome": nome_limpo}
    if excluido_bool is not None:
        body["excluido"] = excluido_bool

    vm = (valor_minimo or "").strip()
    if vm:
        body["valor_minimo"] = vm

    b2b = (disponivel_b2b or "").strip().lower()
    if b2b in ("sim", "true", "1"):
        body["disponivel_b2b"] = True
    elif b2b in ("nao", "não", "false", "0"):
        body["disponivel_b2b"] = False

    limite = (considerar_limite_credito or "").strip().lower()
    if limite in ("sim", "true", "1"):
        body["considerar_limite_credito"] = True
    elif limite in ("nao", "não", "false", "0"):
        body["considerar_limite_credito"] = False

    try:
        out = homolog.alterar_condicao_pagamento(cid, body)
        status = out.get("status_code") or 201
        if excluido_bool is None:
            ativo_label = "—"
            excluido_label = "Não alterado"
        else:
            ativo_label = "Não" if excluido_bool else "Sim"
            excluido_label = "Sim" if excluido_bool else "Não"
        linhas: list[tuple[str, Any]] = [
            ("Status HTTP", status),
            ("ID", cid),
            ("Nome", nome_limpo),
        ]
        if "valor_minimo" in body:
            linhas.append(("Valor mínimo", _fmt_valor_minimo(body["valor_minimo"])))
        if "disponivel_b2b" in body:
            linhas.append(("Disponível B2B", _fmt_bool(body["disponivel_b2b"])))
        if "considerar_limite_credito" in body:
            linhas.append(
                ("Considerar limite de crédito", _fmt_bool(body["considerar_limite_credito"]))
            )
        linhas.extend(
            [
                ("Ativo", ativo_label),
                ("Excluído", excluido_label),
                ("Origem", "Mercos Sandbox"),
            ]
        )
        card = _card(
            "Condição de pagamento alterada",
            linhas,
            status_label=f"Status {status}",
            css="ok",
        )
        return _wrap_result(card, entity="condicao_pagamento", entity_id=cid)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/formas-pagamento-criar", response_class=HTMLResponse)
def acao_formas_pagamento_criar(
    request: Request,
    token: str = Form(""),
    nome: str = Form(""),
    ativo: str = Form("sim"),
):
    """POST /v1/formas_pagamento — um único envio à Mercos por clique.

    Entidade Formas de Pagamento (não confundir com Condições de Pagamento).
    Contrato oficial aceita nome (obrigatório) e excluido (opcional): Ativo=Sim
    vira excluido=false.
    """
    _auth(request, token)
    nome_limpo = (nome or "").strip()
    if not nome_limpo:
        return _wrap_result(
            _card(
                "Campos obrigatórios",
                [("Ação", "Informe o nome da forma de pagamento.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    ativo_bool = (ativo or "sim").strip().lower() != "nao"
    try:
        out = homolog.criar_forma_pagamento(
            {"nome": nome_limpo, "excluido": not ativo_bool}
        )
        status = out.get("status_code") or 201
        fid = out.get("id") or (out.get("dados") or {}).get("id") or "—"
        card = _card(
            "Forma de pagamento criada",
            [
                ("Status HTTP", status),
                ("ID criado", fid),
                ("Nome", nome_limpo),
                ("Ativo", "Sim" if ativo_bool else "Não"),
                ("Origem", "Mercos Sandbox"),
            ],
            status_label=f"Status {status}",
            css="ok",
        )
        return _wrap_result(card, entity="forma_pagamento", entity_id=str(fid or ""))
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/formas-pagamento-alterar", response_class=HTMLResponse)
def acao_formas_pagamento_alterar(
    request: Request,
    token: str = Form(""),
    forma_id: str = Form(""),
    nome: str = Form(""),
    ativo: str = Form(""),
    excluido: str = Form(""),
):
    """PUT /v1/formas_pagamento/{id} — um único PUT por clique, id só na URL.

    Contrato oficial aceita nome (obrigatório) e excluido. Ativo=Sim vira
    excluido=false; o campo Excluído=Sim (ou o botão "Excluir logicamente")
    envia excluido=true junto com o nome obrigatório. Sem DELETE.
    """
    _auth(request, token)
    fid = (forma_id or "").strip()
    nome_limpo = (nome or "").strip()
    if not fid or not nome_limpo:
        return _wrap_result(
            _card(
                "Campos obrigatórios",
                [("Ação", "Informe o ID e o nome da forma de pagamento.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    excluido_bool: bool | None = None
    exc_form = (excluido or "").strip().lower()
    if exc_form in ("true", "sim"):
        excluido_bool = True
    elif exc_form in ("false", "nao", "não"):
        excluido_bool = False
    else:
        ativo_form = (ativo or "").strip().lower()
        if ativo_form in ("sim", "true"):
            excluido_bool = False
        elif ativo_form in ("nao", "não", "false"):
            excluido_bool = True
    try:
        body: dict[str, Any] = {"nome": nome_limpo}
        if excluido_bool is not None:
            body["excluido"] = excluido_bool
        out = homolog.alterar_forma_pagamento(fid, body)
        status = out.get("status_code") or 200
        if excluido_bool is None:
            ativo_label = "—"
            excluido_label = "Não alterado"
        else:
            ativo_label = "Não" if excluido_bool else "Sim"
            excluido_label = "Sim" if excluido_bool else "Não"
        card = _card(
            "Forma de pagamento alterada",
            [
                ("Status HTTP", status),
                ("ID", fid),
                ("Nome", nome_limpo),
                ("Ativo", ativo_label),
                ("Excluído", excluido_label),
                ("Origem", "Mercos Sandbox"),
            ],
            status_label=f"Status {status}",
            css="ok",
        )
        return _wrap_result(card, entity="forma_pagamento", entity_id=fid)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/segmentos", response_class=HTMLResponse)
def acao_segmentos(request: Request, token: str = Form("")):
    _auth(request, token)
    try:
        data = homolog.listar_segmentos(pagina_inicial=1, max_paginas=3)
        total = int(data.get("total") or 0)
        if total == 0:
            msg = (
                '<div class="result-card pendente">'
                "<h4>Segmentos de clientes</h4>"
                "<p>Nenhum segmento cadastrado no ambiente atual.</p>"
                '<p class="meta">Total: <strong>0</strong></p>'
                "</div>"
            )
            return _wrap_result(msg)
        rows = [
            [_campo(i, "id"), _campo(i, "nome"), _fmt_bool(_campo(i, "excluido", default=False))]
            for i in (data.get("itens") or [])
        ]
        head = f'<p class="meta">Total encontrado: <strong>{total}</strong> · Status: <strong>200</strong></p>'
        return _wrap_result(head + _table(["ID", "Nome", "Excluído"], rows))
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/tabelas-preco-criar", response_class=HTMLResponse)
def acao_tabelas_preco_criar(
    request: Request,
    token: str = Form(""),
    tipo: str = Form(""),
    nome: str = Form(""),
    acrescimo: str = Form(""),
    desconto: str = Form(""),
    ativo: str = Form("sim"),
):
    """POST /v1/tabelas_preco — um único envio à Mercos por clique.

    Entidade Tabela de Preço (não confundir com Pedido, Condição de Pagamento
    ou preço de produto). Contrato: nome e tipo obrigatórios no POST
    (P/A/D); opcionais acrescimo, desconto e excluido. Ativo=Sim vira
    excluido=false. Não vincula cliente nem cria pedido. Não altera o GET.
    """
    _auth(request, token)
    tipo_limpo = (tipo or "").strip().upper()
    nome_limpo = (nome or "").strip()
    faltando = []
    if not tipo_limpo:
        faltando.append("tipo")
    if not nome_limpo:
        faltando.append("nome")
    if faltando:
        return _wrap_result(
            _card(
                "Campos obrigatórios",
                [("Ação", f"Informe: {', '.join(faltando)}.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    ativo_bool = (ativo or "sim").strip().lower() != "nao"
    body: dict[str, Any] = {
        "tipo": tipo_limpo,
        "nome": nome_limpo,
        "excluido": not ativo_bool,
    }
    acr = (acrescimo or "").strip()
    if acr:
        body["acrescimo"] = acr
    desc = (desconto or "").strip()
    if desc:
        body["desconto"] = desc
    try:
        out = homolog.criar_tabela_preco(body)
        status = out.get("status_code") or 201
        tid = out.get("id") or (out.get("dados") or {}).get("id") or "—"
        tipo_label = {
            "P": "P (preço livre)",
            "A": "A (acréscimo)",
            "D": "D (desconto)",
        }.get(tipo_limpo, tipo_limpo)
        linhas: list[tuple[str, Any]] = [
            ("Status HTTP", status),
            ("ID criado", tid),
            ("Tipo", tipo_label),
            ("Nome", nome_limpo),
            ("Ativo", "Sim" if ativo_bool else "Não"),
            ("Excluído", _fmt_bool(not ativo_bool)),
            ("Origem", "Mercos Sandbox"),
        ]
        card = _card(
            "Tabela de preço criada",
            linhas,
            status_label=f"Status {status}",
            css="ok",
        )
        return _wrap_result(card, entity="tabela_preco", entity_id=str(tid or ""))
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/tabelas-preco", response_class=HTMLResponse)
def acao_tabelas_preco(request: Request, token: str = Form("")):
    _auth(request, token)
    try:
        data = homolog.listar_tabelas_preco(pagina_inicial=1, max_paginas=3)
        total = int(data.get("total") or 0)
        if total == 0:
            msg = (
                '<div class="result-card pendente">'
                "<h4>Tabelas de preço</h4>"
                "<p>Nenhuma tabela de preço cadastrada no ambiente atual.</p>"
                '<p class="meta">Total: <strong>0</strong></p>'
                "</div>"
            )
            return _wrap_result(msg)
        rows = [
            [_campo(i, "id"), _campo(i, "nome"), _fmt_bool(_campo(i, "excluido", default=False))]
            for i in (data.get("itens") or [])
        ]
        head = f'<p class="meta">Total encontrado: <strong>{total}</strong> · Status: <strong>200</strong></p>'
        return _wrap_result(head + _table(["ID", "Nome", "Excluído"], rows))
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


def _destaque_nome_tipo_pedido(nome: str) -> bool:
    nome_l = (nome or "").lower()
    return (
        nome_l.startswith("19814a3")
        or nome_l.startswith("198314a3")
        or nome_l.startswith("0832f68")
        or nome_l.startswith("8df21d6c")
    )


def _params_tipos_do_form(
    alterado_apos: str = "",
    excluido: str = "",
    excluidos: str = "",
    somente_excluidos: str = "",
    incluir_excluidos: str = "",
) -> dict[str, str]:
    params: dict[str, str] = {}
    for chave, valor in (
        ("alterado_apos", alterado_apos),
        ("excluido", excluido),
        ("excluidos", excluidos),
        ("somente_excluidos", somente_excluidos),
        ("incluir_excluidos", incluir_excluidos),
    ):
        texto = (valor or "").strip()
        if texto:
            params[chave] = texto
    return params


def _html_lista_tipos_pedido(data: dict, *, titulo_filtro: str = "") -> str:
    if not data.get("ok", True) or data.get("status_code") == 404:
        paths = data.get("paths_testados") or []
        msg = data.get("mensagem") or (
            "Não foi possível localizar o endpoint oficial de Tipo de Pedido no sandbox. "
            f"Paths testados: {', '.join(paths)}"
        )
        return _card(
            "Tipo de Pedido",
            [("Situação", msg)],
            status_label="Pendente",
            css="pendente",
        )

    rows = []
    classes: list[str] = []
    tem_filtro_coluna = any(
        isinstance(i, dict) and i.get("_filtros_encontrados")
        for i in (data.get("itens") or [])
    )
    for item in data.get("itens") or []:
        nome = _campo(item, "nome", "name", "descricao", default="")
        nome_str = "" if nome == "—" else str(nome)
        row = [
            _campo(item, "id"),
            nome_str or "—",
            _fmt_bool(_campo(item, "excluido", default=False)),
            _campo(
                item,
                "ultima_alteracao",
                "updated_at",
                "alterado_em",
                "data_alteracao",
                "modificado_em",
            ),
        ]
        if tem_filtro_coluna:
            encontrados = item.get("_filtros_encontrados") or []
            row.append(" | ".join(str(x) for x in encontrados) if encontrados else "—")
        rows.append(row)
        classes.append(
            "destaque-homolog" if _destaque_nome_tipo_pedido(nome_str) else ""
        )

    headers = ["ID", "Nome", "Excluído", "Última alteração"]
    if tem_filtro_coluna:
        headers.append("Filtro que encontrou")

    table = _table(
        headers,
        rows,
        empty_msg="Endpoint encontrado, porém sem tipos de pedido cadastrados.",
        row_classes=classes,
    )
    filtros = dict(data.get("filtros") or {})
    head_parts = [
        "Status: <strong>200</strong>",
        f'Total: <strong>{_esc(data.get("total", 0))}</strong>',
    ]
    if titulo_filtro:
        head_parts.append(f"Filtro usado: <strong>{_esc(titulo_filtro)}</strong>")
    elif filtros:
        partes = [f"{_esc(k)} = <strong>{_esc(v)}</strong>" for k, v in filtros.items()]
        # rótulo amigável para singular/plural
        texto = " | ".join(partes).replace("excluidos =", "excluídos =").replace(
            "excluido =", "excluído ="
        )
        head_parts.append("Filtro usado: " + texto)
    return f'<p class="meta">{" · ".join(head_parts)}</p>' + table


@router.post("/homologacao-ui/acoes/tipos-pedido", response_class=HTMLResponse)
def acao_tipos_pedido(
    request: Request,
    token: str = Form(""),
    alterado_apos: str = Form(""),
    excluido: str = Form(""),
    excluidos: str = Form(""),
    somente_excluidos: str = Form(""),
    incluir_excluidos: str = Form(""),
):
    _auth(request, token)
    bloqueio = _bloqueio_tipos_ciclo_ativo(request)
    if bloqueio is not None:
        return bloqueio
    params = _params_tipos_do_form(
        alterado_apos=alterado_apos,
        excluido=excluido,
        excluidos=excluidos,
        somente_excluidos=somente_excluidos,
        incluir_excluidos=incluir_excluidos,
    )
    try:
        data = homolog.listar_tipos_pedido_descoberta(
            params_mercos=params or None,
            pagina_inicial=1,
            max_paginas=5,
        )
        titulo = ""
        if params.get("alterado_apos") and (
            params.get("excluido") or params.get("excluidos")
        ):
            flag = params.get("excluido") or params.get("excluidos")
            titulo = (
                f"alterado_apos = {params['alterado_apos']} | "
                f"excluídos = {flag}"
            )
            if params.get("excluido") and not params.get("excluidos"):
                titulo = (
                    f"alterado_apos = {params['alterado_apos']} | "
                    f"excluído = {params['excluido']}"
                )
        return _wrap_result(_html_lista_tipos_pedido(data, titulo_filtro=titulo))
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/tipos-pedido-combinacoes", response_class=HTMLResponse)
def acao_tipos_pedido_combinacoes(request: Request, token: str = Form("")):
    _auth(request, token)
    bloqueio = _bloqueio_tipos_ciclo_ativo(request)
    if bloqueio is not None:
        return bloqueio
    try:
        data = homolog.explorar_filtros_tipos_pedido(max_paginas=3)
        html = _html_lista_tipos_pedido(data)
        tentativas = data.get("tentativas") or []
        resumo = "".join(
            f"<li><span>{_esc(t.get('filtro'))}</span>"
            f"<strong>{'OK · ' + str(t.get('total', 0)) if t.get('ok') else 'sem retorno'}</strong></li>"
            for t in tentativas
        )
        bloco = (
            '<div class="result-card">'
            "<h4>Combinações testadas</h4>"
            f"<ul>{resumo}</ul></div>"
        )
        return _wrap_result(bloco + html)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/usuarios", response_class=HTMLResponse)
def acao_usuarios(
    request: Request,
    token: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Busca simples — bloqueada durante o ciclo ativo de homologação."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_usuarios(request)
    _hidratar_catalogo_usuarios_form(sessao, catalogo_json)
    if catalogo_usuarios.ciclo_ativo(sessao):
        resp = _wrap_result(
            _card(
                "Busca completa bloqueada durante a homologação",
                [
                    (
                        "Mensagem",
                        "Use apenas «Sincronizar próxima etapa» durante o ciclo ativo.",
                    )
                ]
                + _linhas_ciclo_usuarios(sessao),
                status_label="Bloqueado",
                css="erro",
            ),
            extra_attrs={
                "status-sync": "bloqueado",
                **_attrs_ciclo_usuarios(sessao),
            },
        )
        return _garantir_sessao_usuarios_cookie(resp, sessao)
    try:
        data = homolog.listar_usuarios(pagina_inicial=1, max_paginas=3)
        table = _html_tabela_usuarios(data.get("itens") or [])
        head = f'<p class="meta">Total: <strong>{_esc(data.get("total", 0))}</strong> · Status: <strong>200</strong></p>'
        resp = _wrap_result(head + table, extra_attrs=_attrs_ciclo_usuarios(sessao))
        return _garantir_sessao_usuarios_cookie(resp, sessao)
    except Exception as exc:
        resp = _wrap_result(_erro_html(exc))
        return _garantir_sessao_usuarios_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/usuarios-reiniciar", response_class=HTMLResponse)
def acao_usuarios_reiniciar(
    request: Request,
    token: str = Form(""),
):
    """Apaga cursor e catálogo de usuários, inicia ciclo na etapa 0 — sem chamar a Mercos."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_usuarios(request)
    catalogo_usuarios.iniciar_ciclo(sessao)
    homolog._limpar_resumes_da_sessao(sessao)
    estado = catalogo_usuarios.obter(sessao)
    mensagem = (
        '<div class="result-card ok">'
        "<h4>Ciclo de sincronização reiniciado</h4>"
        "<p>Cursor e catálogo anteriores apagados. Novo ciclo ativo na etapa 0. "
        "Use «Sincronizar próxima etapa» para a busca completa.</p>"
        "</div>"
    )
    resumo = _card(
        "Estado do ciclo",
        _linhas_ciclo_usuarios(sessao, estado),
        status_label="Ciclo ativo",
        css="ok",
    )
    resp = _wrap_result(
        mensagem + resumo + _html_patch_catalogo_usuarios(sessao),
        extra_attrs={
            "novo-cursor": "",
            "cursor-limpo": "1",
            "catalogo-limpo": "1",
            "status-sync": "reiniciado",
            "catalogo-total": "0",
            **_attrs_ciclo_usuarios(sessao),
        },
    )
    resp = _set_cursor_usuarios_cookie(resp, None)
    return _garantir_sessao_usuarios_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/usuarios-sincronizar", response_class=HTMLResponse)
def acao_usuarios_sincronizar(
    request: Request,
    token: str = Form(""),
    cursor: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Única ação que chama a Mercos no ciclo: etapa 0 completa; 1 e 2 incrementais."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_usuarios(request)
    _hidratar_catalogo_usuarios_form(sessao, catalogo_json)
    ciclo = catalogo_usuarios.obter_ciclo(sessao)
    if not ciclo.get("ativo"):
        catalogo_usuarios.iniciar_ciclo(sessao)
        ciclo = catalogo_usuarios.obter_ciclo(sessao)

    etapa = int(ciclo.get("etapa_interna") or 0)
    cursor_form = _cursor_usuarios(request, cursor)

    if etapa == 0:
        cursor_para_sync = None
        tipo_esperado = "completa"
    else:
        if not cursor_form:
            resp = _wrap_result(
                _card(
                    "Cursor ausente",
                    [
                        (
                            "Mensagem",
                            "Etapa incremental exige cursor salvo. Reinicie o ciclo se necessário.",
                        )
                    ]
                    + _linhas_ciclo_usuarios(sessao),
                    status_label="Erro",
                    css="erro",
                ),
                extra_attrs={"status-sync": "erro", **_attrs_ciclo_usuarios(sessao)},
            )
            return _garantir_sessao_usuarios_cookie(resp, sessao)
        cursor_para_sync = cursor_form
        tipo_esperado = "incremental"

    try:
        data = homolog.sincronizar_usuarios(
            cursor_para_sync, max_paginas=20, sessao_id=sessao
        )
        tipo_real = data.get("tipo") or tipo_esperado
        if etapa >= 1 and (
            tipo_real == "completa" or not data.get("alterado_apos_enviado")
        ):
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [
                        (
                            "Mensagem",
                            "A etapa atual exige busca incremental com alterado_apos.",
                        )
                    ]
                    + _linhas_ciclo_usuarios(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_usuarios(sessao)},
            )
            return _garantir_sessao_usuarios_cookie(resp, sessao)

        status_sync = data.get("status") or "concluida"
        motivo = data.get("motivo_parada") or ""
        status_label = "Timeout" if status_sync == "timeout" else "Concluída"
        meta = {
            "tipo": tipo_real,
            "cursor_base": data.get("cursor_base"),
            "alterado_apos_enviado": data.get("alterado_apos_enviado"),
            "novo_cursor": data.get("novo_cursor"),
            "total_lote": data.get("total", 0),
            "paginas_lidas": data.get("paginas_lidas") or 0,
            "motivo_parada": motivo,
            "status_sync": status_label,
            "requisicoes_extras": data.get("requisicoes_extras"),
            "requisicoes_previstas": data.get("requisicoes_previstas"),
            "requisicoes_executadas": data.get("requisicoes_executadas"),
        }
        if tipo_real == "completa":
            catalogo_usuarios.substituir_completo(
                sessao, data.get("itens") or [], meta=meta
            )
        else:
            catalogo_usuarios.upsert_incremental(
                sessao, data.get("itens") or [], meta=meta
            )
        try:
            catalogo_usuarios.registrar_sync_ciclo(sessao, tipo=tipo_real)
        except ValueError as exc:
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [("Mensagem", str(exc))] + _linhas_ciclo_usuarios(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_usuarios(sessao)},
            )
            return _garantir_sessao_usuarios_cookie(resp, sessao)

        estado = catalogo_usuarios.obter(sessao)
        total = data.get("total", 0)
        paginas = data.get("paginas_lidas") or 0
        css = "pendente" if status_sync == "timeout" else "ok"
        resumo = _card(
            "Sincronização de usuários",
            [
                ("Status da sincronização", status_label),
                ("Motivo da parada", motivo or "—"),
            ]
            + _linhas_ciclo_usuarios(sessao, estado),
            status_label=status_label,
            css=css,
        )
        table = _html_tabela_usuarios(data.get("itens") or [])
        resp = _wrap_result(
            resumo + table + _html_patch_catalogo_usuarios(sessao),
            extra_attrs={
                "novo-cursor": data.get("novo_cursor") or "",
                "cursor-anterior": data.get("cursor_anterior") or "",
                "cursor-base": data.get("cursor_base") or "",
                "alterado-apos-enviado": data.get("alterado_apos_enviado") or "",
                "tipo-busca": tipo_real,
                "total": str(total),
                "paginas-lidas": str(paginas),
                "requisicoes-extras": str(data.get("requisicoes_extras") if data.get("requisicoes_extras") is not None else ""),
                "requisicoes-previstas": str(data.get("requisicoes_previstas") if data.get("requisicoes_previstas") is not None else ""),
                "requisicoes-executadas": str(data.get("requisicoes_executadas") or 0),
                "motivo-parada": motivo,
                "catalogo-total": str(len(estado.get("usuarios") or {})),
                "catalogo-modo": "replace" if tipo_real == "completa" else "upsert",
                "status-sync": status_sync,
                **_attrs_ciclo_usuarios(sessao),
            },
        )
        resp = _set_cursor_usuarios_cookie(resp, data.get("novo_cursor"))
        return _garantir_sessao_usuarios_cookie(resp, sessao)
    except MercosApiError as exc:
        if exc.status_code == 429:
            segundos = exc.retry_after if exc.retry_after is not None else 10
            try:
                segundos = max(0, int(float(segundos)))
            except (TypeError, ValueError):
                segundos = 10
            pagina_atual = exc.pagina if exc.pagina is not None else "—"
            resp = _wrap_result(
                _card(
                    "Aguardando limite da Mercos",
                    [
                        ("Mensagem", "Aguardando limite da Mercos"),
                        ("Segundos restantes", segundos),
                        ("Página atual", pagina_atual),
                    ],
                    status_label="Aguardando",
                    css="pendente",
                ),
                extra_attrs={
                    "status-sync": "aguardando-429",
                    "aguardando-mercos": "1",
                    "segundos-espera": str(segundos),
                    "pagina-atual": str(pagina_atual),
                    "http-status": "429",
                    **_attrs_ciclo_usuarios(sessao),
                },
            )
            resp.status_code = 429
            resp.headers["Retry-After"] = str(segundos)
            resp.headers["X-Mercos-Pagina"] = str(pagina_atual)
            return _garantir_sessao_usuarios_cookie(resp, sessao)
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={
                "status-sync": "erro",
                "http-status": str(exc.status_code or ""),
                **_attrs_ciclo_usuarios(sessao),
            },
        )
        if exc.status_code in (409, 504):
            resp.status_code = exc.status_code
        return _garantir_sessao_usuarios_cookie(resp, sessao)
    except Exception as exc:
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={"status-sync": "erro", **_attrs_ciclo_usuarios(sessao)},
        )
        return _garantir_sessao_usuarios_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/usuarios-localizar", response_class=HTMLResponse)
def acao_usuarios_localizar(
    request: Request,
    token: str = Form(""),
    nome: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Localiza por nome completo ou prefixo no catálogo local. Não chama Mercos nem altera cursor."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_usuarios(request)
    _hidratar_catalogo_usuarios_form(sessao, catalogo_json)
    ciclo_antes = catalogo_usuarios.obter_ciclo(sessao)
    busca = (nome or "").strip()
    if not busca:
        return _garantir_sessao_usuarios_cookie(
            _wrap_result(
                _card(
                    "Localizar usuário",
                    [("Mensagem", "Informe o nome completo ou o prefixo do usuário.")],
                    status_label="Atenção",
                    css="erro",
                )
            ),
            sessao,
        )

    encontrado, no_ultimo_lote, estado = catalogo_usuarios.buscar_por_nome(
        sessao, busca
    )
    if not encontrado:
        return _garantir_sessao_usuarios_cookie(
            _wrap_result(
                _card(
                    "Usuário não encontrado",
                    [
                        ("Nome buscado", busca),
                        ("Usuários no catálogo local", catalogo_usuarios.total(sessao)),
                    ]
                    + _linhas_ciclo_usuarios(sessao, estado),
                    status_label="Não encontrado",
                    css="erro",
                ),
                extra_attrs={"cursor-fixo": "1", **_attrs_ciclo_usuarios(sessao)},
            ),
            sessao,
        )

    ultima = encontrado.get("ultima_alteracao")
    if ultima is None or ultima == "":
        ultima = "—"
    linhas: list[tuple[str, Any]] = [
        ("ID", encontrado.get("id")),
        ("Nome completo", encontrado.get("nome")),
        ("E-mail", encontrado.get("email") or "—"),
        ("Administrador", _fmt_bool(encontrado.get("administrador"))),
        ("Ativo", _ativo_usuario(encontrado)),
        ("Última alteração", ultima),
        ("Origem", "Catálogo local sincronizado"),
    ]
    linhas.extend(_linhas_ciclo_usuarios(sessao, estado))
    nota = ""
    if not no_ultimo_lote:
        nota = (
            '<p class="hint">Usuário localizado no catálogo do ERP; '
            "não veio no último lote incremental.</p>"
        )
    card = _card(
        "Usuário localizado",
        linhas,
        status_label="Encontrado",
        css="ok",
    )
    ciclo_depois = catalogo_usuarios.obter_ciclo(sessao)
    if ciclo_antes.get("etapa_interna") != ciclo_depois.get("etapa_interna"):
        catalogo_usuarios._salvar_ciclo(sessao, ciclo_antes)
    resp = _wrap_result(
        nota + card + _html_patch_catalogo_usuarios(sessao),
        extra_attrs={
            "status-sync": "localizado",
            "cursor-fixo": "1",
            **_attrs_ciclo_usuarios(sessao),
        },
    )
    return _garantir_sessao_usuarios_cookie(resp, sessao)


def _bloqueio_tipos_ciclo_ativo(request: Request) -> HTMLResponse | None:
    """Bloqueia as buscas manuais antigas de Tipo de Pedido durante o ciclo ativo."""
    sessao = (request.cookies.get(_COOKIE_TIPOS_SESSAO) or "").strip()
    if not sessao or not catalogo_tipos_pedido.ciclo_ativo(sessao):
        return None
    resp = _wrap_result(
        _card(
            "Busca manual bloqueada durante a homologação",
            [
                (
                    "Mensagem",
                    "O ciclo de sincronização de tipos de pedido está ativo. "
                    "Use apenas «Sincronizar próxima etapa» ou «Localizar tipo de pedido».",
                )
            ]
            + _linhas_ciclo_tipos(sessao),
            status_label="Bloqueado",
            css="erro",
        ),
        extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_tipos(sessao)},
    )
    return _garantir_sessao_tipos_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/tipos-pedido-reiniciar", response_class=HTMLResponse)
def acao_tipos_pedido_reiniciar(
    request: Request,
    token: str = Form(""),
):
    """Apaga cursor/catálogo de tipos de pedido, ciclo volta a 0/3 — sem chamar a Mercos."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_tipos(request)
    catalogo_tipos_pedido.iniciar_ciclo(sessao)
    homolog._limpar_resumes_da_sessao(sessao)
    estado = catalogo_tipos_pedido.obter(sessao)
    mensagem = (
        '<div class="result-card ok">'
        "<h4>Ciclo de sincronização reiniciado</h4>"
        "<p>Cursor e catálogo anteriores apagados. Novo ciclo ativo na etapa 0/3. "
        "Use «Sincronizar próxima etapa» para a busca completa.</p>"
        "</div>"
    )
    resumo = _card(
        "Estado do ciclo",
        _linhas_ciclo_tipos(sessao, estado),
        status_label="Ciclo ativo",
        css="ok",
    )
    resp = _wrap_result(
        mensagem + resumo + _html_patch_catalogo_tipos(sessao),
        extra_attrs={
            "novo-cursor": "",
            "cursor-limpo": "1",
            "catalogo-limpo": "1",
            "status-sync": "reiniciado",
            "catalogo-total": "0",
            **_attrs_ciclo_tipos(sessao),
        },
    )
    resp = _set_cursor_tipos_cookie(resp, None)
    return _garantir_sessao_tipos_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/tipos-pedido-sincronizar", response_class=HTMLResponse)
def acao_tipos_pedido_sincronizar(
    request: Request,
    token: str = Form(""),
    cursor: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Única ação que chama a Mercos no ciclo: etapa 0 completa; 1 e 2 incrementais."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_tipos(request)
    _hidratar_catalogo_tipos_form(sessao, catalogo_json)
    ciclo = catalogo_tipos_pedido.obter_ciclo(sessao)
    if not ciclo.get("ativo"):
        catalogo_tipos_pedido.iniciar_ciclo(sessao)
        ciclo = catalogo_tipos_pedido.obter_ciclo(sessao)

    etapa = int(ciclo.get("etapa_interna") or 0)
    cursor_form = _cursor_tipos(request, cursor)

    if etapa == 0:
        cursor_para_sync = None
        tipo_esperado = "completa"
    else:
        if not cursor_form:
            resp = _wrap_result(
                _card(
                    "Cursor ausente",
                    [
                        (
                            "Mensagem",
                            "Etapa incremental exige cursor salvo. Reinicie o ciclo se necessário.",
                        )
                    ]
                    + _linhas_ciclo_tipos(sessao),
                    status_label="Erro",
                    css="erro",
                ),
                extra_attrs={"status-sync": "erro", **_attrs_ciclo_tipos(sessao)},
            )
            return _garantir_sessao_tipos_cookie(resp, sessao)
        cursor_para_sync = cursor_form
        tipo_esperado = "incremental"

    try:
        data = homolog.sincronizar_tipos_pedido(
            cursor_para_sync, max_paginas=20, sessao_id=sessao
        )
        tipo_real = data.get("tipo") or tipo_esperado
        if etapa >= 1 and (
            tipo_real == "completa" or not data.get("alterado_apos_enviado")
        ):
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [
                        (
                            "Mensagem",
                            "A etapa atual exige busca incremental com alterado_apos.",
                        )
                    ]
                    + _linhas_ciclo_tipos(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_tipos(sessao)},
            )
            return _garantir_sessao_tipos_cookie(resp, sessao)

        status_sync = data.get("status") or "concluida"
        motivo = data.get("motivo_parada") or ""
        status_label = "Timeout" if status_sync == "timeout" else "Concluída"
        meta = {
            "tipo": tipo_real,
            "cursor_base": data.get("cursor_base"),
            "alterado_apos_enviado": data.get("alterado_apos_enviado"),
            "novo_cursor": data.get("novo_cursor"),
            "total_lote": data.get("total", 0),
            "paginas_lidas": data.get("paginas_lidas") or 0,
            "motivo_parada": motivo,
            "status_sync": status_label,
            "requisicoes_extras": data.get("requisicoes_extras"),
            "requisicoes_previstas": data.get("requisicoes_previstas"),
            "requisicoes_executadas": data.get("requisicoes_executadas"),
        }
        if tipo_real == "completa":
            catalogo_tipos_pedido.substituir_completo(
                sessao, data.get("itens") or [], meta=meta
            )
        else:
            catalogo_tipos_pedido.upsert_incremental(
                sessao, data.get("itens") or [], meta=meta
            )
        try:
            catalogo_tipos_pedido.registrar_sync_ciclo(sessao, tipo=tipo_real)
        except ValueError as exc:
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [("Mensagem", str(exc))] + _linhas_ciclo_tipos(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_tipos(sessao)},
            )
            return _garantir_sessao_tipos_cookie(resp, sessao)

        estado = catalogo_tipos_pedido.obter(sessao)
        total = data.get("total", 0)
        paginas = data.get("paginas_lidas") or 0
        css = "pendente" if status_sync == "timeout" else "ok"
        resumo = _card(
            "Sincronização de tipos de pedido",
            [
                ("Status da sincronização", status_label),
                ("Motivo da parada", motivo or "—"),
            ]
            + _linhas_ciclo_tipos(sessao, estado),
            status_label=status_label,
            css=css,
        )
        table = _html_tabela_tipos(data.get("itens") or [])
        resp = _wrap_result(
            resumo + table + _html_patch_catalogo_tipos(sessao),
            extra_attrs={
                "novo-cursor": data.get("novo_cursor") or "",
                "cursor-anterior": data.get("cursor_anterior") or "",
                "cursor-base": data.get("cursor_base") or "",
                "alterado-apos-enviado": data.get("alterado_apos_enviado") or "",
                "tipo-busca": tipo_real,
                "total": str(total),
                "paginas-lidas": str(paginas),
                "requisicoes-extras": str(data.get("requisicoes_extras") if data.get("requisicoes_extras") is not None else ""),
                "requisicoes-previstas": str(data.get("requisicoes_previstas") if data.get("requisicoes_previstas") is not None else ""),
                "requisicoes-executadas": str(data.get("requisicoes_executadas") or 0),
                "motivo-parada": motivo,
                "catalogo-total": str(len(estado.get("tipos") or {})),
                "catalogo-modo": "replace" if tipo_real == "completa" else "upsert",
                "status-sync": status_sync,
                **_attrs_ciclo_tipos(sessao),
            },
        )
        resp = _set_cursor_tipos_cookie(resp, data.get("novo_cursor"))
        return _garantir_sessao_tipos_cookie(resp, sessao)
    except MercosApiError as exc:
        if exc.status_code == 429:
            segundos = exc.retry_after if exc.retry_after is not None else 10
            try:
                segundos = max(0, int(float(segundos)))
            except (TypeError, ValueError):
                segundos = 10
            pagina_atual = exc.pagina if exc.pagina is not None else "—"
            resp = _wrap_result(
                _card(
                    "Aguardando limite da Mercos",
                    [
                        ("Mensagem", "Aguardando limite da Mercos"),
                        ("Segundos restantes", segundos),
                        ("Página atual", pagina_atual),
                    ],
                    status_label="Aguardando",
                    css="pendente",
                ),
                extra_attrs={
                    "status-sync": "aguardando-429",
                    "aguardando-mercos": "1",
                    "segundos-espera": str(segundos),
                    "pagina-atual": str(pagina_atual),
                    "http-status": "429",
                    **_attrs_ciclo_tipos(sessao),
                },
            )
            resp.status_code = 429
            resp.headers["Retry-After"] = str(segundos)
            resp.headers["X-Mercos-Pagina"] = str(pagina_atual)
            return _garantir_sessao_tipos_cookie(resp, sessao)
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={
                "status-sync": "erro",
                "http-status": str(exc.status_code or ""),
                **_attrs_ciclo_tipos(sessao),
            },
        )
        if exc.status_code in (409, 504):
            resp.status_code = exc.status_code
        return _garantir_sessao_tipos_cookie(resp, sessao)
    except Exception as exc:
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={"status-sync": "erro", **_attrs_ciclo_tipos(sessao)},
        )
        return _garantir_sessao_tipos_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/tipos-pedido-localizar", response_class=HTMLResponse)
def acao_tipos_pedido_localizar(
    request: Request,
    token: str = Form(""),
    nome: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Localiza por nome completo ou prefixo no catálogo local. Não chama Mercos nem altera cursor."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_tipos(request)
    _hidratar_catalogo_tipos_form(sessao, catalogo_json)
    ciclo_antes = catalogo_tipos_pedido.obter_ciclo(sessao)
    busca = (nome or "").strip()
    if not busca:
        return _garantir_sessao_tipos_cookie(
            _wrap_result(
                _card(
                    "Localizar tipo de pedido",
                    [("Mensagem", "Informe o nome completo ou o prefixo do tipo de pedido.")],
                    status_label="Atenção",
                    css="erro",
                )
            ),
            sessao,
        )

    encontrado, no_ultimo_lote, estado = catalogo_tipos_pedido.buscar_por_nome(
        sessao, busca
    )
    if not encontrado:
        return _garantir_sessao_tipos_cookie(
            _wrap_result(
                _card(
                    "Tipo de pedido não encontrado",
                    [
                        ("Nome buscado", busca),
                        (
                            "Tipos de pedido no catálogo local",
                            catalogo_tipos_pedido.total(sessao),
                        ),
                    ]
                    + _linhas_ciclo_tipos(sessao, estado),
                    status_label="Não encontrado",
                    css="erro",
                ),
                extra_attrs={"cursor-fixo": "1", **_attrs_ciclo_tipos(sessao)},
            ),
            sessao,
        )

    ultima = encontrado.get("ultima_alteracao")
    if ultima is None or ultima == "":
        ultima = "—"
    linhas: list[tuple[str, Any]] = [
        ("ID", encontrado.get("id")),
        ("Nome completo", encontrado.get("nome")),
        ("Excluído", _fmt_bool(encontrado.get("excluido", False))),
        ("Última alteração", ultima),
        ("Origem", "Catálogo local sincronizado"),
    ]
    linhas.extend(_linhas_ciclo_tipos(sessao, estado))
    nota = ""
    if not no_ultimo_lote:
        nota = (
            '<p class="hint">Tipo de pedido localizado no catálogo do ERP; '
            "não veio no último lote incremental.</p>"
        )
    card = _card(
        "Tipo de pedido localizado",
        linhas,
        status_label="Encontrado",
        css="ok",
    )
    ciclo_depois = catalogo_tipos_pedido.obter_ciclo(sessao)
    if ciclo_antes.get("etapa_interna") != ciclo_depois.get("etapa_interna"):
        catalogo_tipos_pedido._salvar_ciclo(sessao, ciclo_antes)
    resp = _wrap_result(
        nota + card + _html_patch_catalogo_tipos(sessao),
        extra_attrs={
            "status-sync": "localizado",
            "cursor-fixo": "1",
            **_attrs_ciclo_tipos(sessao),
        },
    )
    return _garantir_sessao_tipos_cookie(resp, sessao)


def _bloqueio_condicoes_ciclo_ativo(request: Request) -> HTMLResponse | None:
    """Bloqueia a busca simples antiga de Condições durante o ciclo ativo."""
    sessao = (request.cookies.get(_COOKIE_CONDICOES_SESSAO) or "").strip()
    if not sessao or not catalogo_condicoes.ciclo_ativo(sessao):
        return None
    resp = _wrap_result(
        _card(
            "Busca manual bloqueada durante a homologação",
            [
                (
                    "Mensagem",
                    "O ciclo de sincronização de condições de pagamento está ativo. "
                    "Use apenas «Sincronizar próxima etapa» ou «Localizar condição pelo nome».",
                )
            ]
            + _linhas_ciclo_condicoes(sessao),
            status_label="Bloqueado",
            css="erro",
        ),
        extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_condicoes(sessao)},
    )
    return _garantir_sessao_condicoes_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/condicoes-reiniciar", response_class=HTMLResponse)
def acao_condicoes_reiniciar(
    request: Request,
    token: str = Form(""),
):
    """Apaga cursor/catálogo de condições, ciclo volta a 0/3 — sem chamar a Mercos."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_condicoes(request)
    catalogo_condicoes.iniciar_ciclo(sessao)
    homolog._limpar_resumes_da_sessao(sessao)
    estado = catalogo_condicoes.obter(sessao)
    mensagem = (
        '<div class="result-card ok">'
        "<h4>Ciclo de sincronização reiniciado</h4>"
        "<p>Cursor e catálogo anteriores apagados. Novo ciclo ativo na etapa 0/3. "
        "Use «Sincronizar próxima etapa» para a busca completa.</p>"
        "</div>"
    )
    resumo = _card(
        "Estado do ciclo",
        _linhas_ciclo_condicoes(sessao, estado),
        status_label="Ciclo ativo",
        css="ok",
    )
    resp = _wrap_result(
        mensagem + resumo + _html_patch_catalogo_condicoes(sessao),
        extra_attrs={
            "novo-cursor": "",
            "cursor-limpo": "1",
            "catalogo-limpo": "1",
            "status-sync": "reiniciado",
            "catalogo-total": "0",
            **_attrs_ciclo_condicoes(sessao),
        },
    )
    resp = _set_cursor_condicoes_cookie(resp, None)
    return _garantir_sessao_condicoes_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/condicoes-sincronizar", response_class=HTMLResponse)
def acao_condicoes_sincronizar(
    request: Request,
    token: str = Form(""),
    cursor: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Única ação que chama a Mercos no ciclo: etapa 0 completa; 1 e 2 incrementais."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_condicoes(request)
    _hidratar_catalogo_condicoes_form(sessao, catalogo_json)
    ciclo = catalogo_condicoes.obter_ciclo(sessao)
    if not ciclo.get("ativo"):
        catalogo_condicoes.iniciar_ciclo(sessao)
        ciclo = catalogo_condicoes.obter_ciclo(sessao)

    etapa = int(ciclo.get("etapa_interna") or 0)
    cursor_form = _cursor_condicoes(request, cursor)

    if etapa == 0:
        cursor_para_sync = None
        tipo_esperado = "completa"
    else:
        if not cursor_form:
            resp = _wrap_result(
                _card(
                    "Cursor ausente",
                    [
                        (
                            "Mensagem",
                            "Etapa incremental exige cursor salvo. Reinicie o ciclo se necessário.",
                        )
                    ]
                    + _linhas_ciclo_condicoes(sessao),
                    status_label="Erro",
                    css="erro",
                ),
                extra_attrs={"status-sync": "erro", **_attrs_ciclo_condicoes(sessao)},
            )
            return _garantir_sessao_condicoes_cookie(resp, sessao)
        cursor_para_sync = cursor_form
        tipo_esperado = "incremental"

    try:
        data = homolog.sincronizar_condicoes_pagamento(
            cursor_para_sync, max_paginas=20, sessao_id=sessao
        )
        tipo_real = data.get("tipo") or tipo_esperado
        if etapa >= 1 and (
            tipo_real == "completa" or not data.get("alterado_apos_enviado")
        ):
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [
                        (
                            "Mensagem",
                            "A etapa atual exige busca incremental com alterado_apos.",
                        )
                    ]
                    + _linhas_ciclo_condicoes(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_condicoes(sessao)},
            )
            return _garantir_sessao_condicoes_cookie(resp, sessao)

        status_sync = data.get("status") or "concluida"
        motivo = data.get("motivo_parada") or ""
        status_label = "Timeout" if status_sync == "timeout" else "Concluída"
        meta = {
            "tipo": tipo_real,
            "cursor_base": data.get("cursor_base"),
            "alterado_apos_enviado": data.get("alterado_apos_enviado"),
            "novo_cursor": data.get("novo_cursor"),
            "total_lote": data.get("total", 0),
            "paginas_lidas": data.get("paginas_lidas") or 0,
            "motivo_parada": motivo,
            "status_sync": status_label,
            "requisicoes_extras": data.get("requisicoes_extras"),
            "requisicoes_previstas": data.get("requisicoes_previstas"),
            "requisicoes_executadas": data.get("requisicoes_executadas"),
        }
        if tipo_real == "completa":
            catalogo_condicoes.substituir_completo(
                sessao, data.get("itens") or [], meta=meta
            )
        else:
            catalogo_condicoes.upsert_incremental(
                sessao, data.get("itens") or [], meta=meta
            )
        try:
            catalogo_condicoes.registrar_sync_ciclo(sessao, tipo=tipo_real)
        except ValueError as exc:
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [("Mensagem", str(exc))] + _linhas_ciclo_condicoes(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_condicoes(sessao)},
            )
            return _garantir_sessao_condicoes_cookie(resp, sessao)

        estado = catalogo_condicoes.obter(sessao)
        total = data.get("total", 0)
        paginas = data.get("paginas_lidas") or 0
        css = "pendente" if status_sync == "timeout" else "ok"
        resumo = _card(
            "Sincronização de condições de pagamento",
            [
                ("Status da sincronização", status_label),
                ("Motivo da parada", motivo or "—"),
            ]
            + _linhas_ciclo_condicoes(sessao, estado),
            status_label=status_label,
            css=css,
        )
        table = _html_tabela_condicoes(data.get("itens") or [])
        resp = _wrap_result(
            resumo + table + _html_patch_catalogo_condicoes(sessao),
            extra_attrs={
                "novo-cursor": data.get("novo_cursor") or "",
                "cursor-anterior": data.get("cursor_anterior") or "",
                "cursor-base": data.get("cursor_base") or "",
                "alterado-apos-enviado": data.get("alterado_apos_enviado") or "",
                "tipo-busca": tipo_real,
                "total": str(total),
                "paginas-lidas": str(paginas),
                "requisicoes-extras": str(data.get("requisicoes_extras") if data.get("requisicoes_extras") is not None else ""),
                "requisicoes-previstas": str(data.get("requisicoes_previstas") if data.get("requisicoes_previstas") is not None else ""),
                "requisicoes-executadas": str(data.get("requisicoes_executadas") or 0),
                "motivo-parada": motivo,
                "catalogo-total": str(len(estado.get("condicoes") or {})),
                "catalogo-modo": "replace" if tipo_real == "completa" else "upsert",
                "status-sync": status_sync,
                **_attrs_ciclo_condicoes(sessao),
            },
        )
        resp = _set_cursor_condicoes_cookie(resp, data.get("novo_cursor"))
        return _garantir_sessao_condicoes_cookie(resp, sessao)
    except MercosApiError as exc:
        if exc.status_code == 429:
            segundos = exc.retry_after if exc.retry_after is not None else 10
            try:
                segundos = max(0, int(float(segundos)))
            except (TypeError, ValueError):
                segundos = 10
            pagina_atual = exc.pagina if exc.pagina is not None else "—"
            resp = _wrap_result(
                _card(
                    "Aguardando limite da Mercos",
                    [
                        ("Mensagem", "Aguardando limite da Mercos"),
                        ("Segundos restantes", segundos),
                        ("Página atual", pagina_atual),
                    ],
                    status_label="Aguardando",
                    css="pendente",
                ),
                extra_attrs={
                    "status-sync": "aguardando-429",
                    "aguardando-mercos": "1",
                    "segundos-espera": str(segundos),
                    "pagina-atual": str(pagina_atual),
                    "http-status": "429",
                    **_attrs_ciclo_condicoes(sessao),
                },
            )
            resp.status_code = 429
            resp.headers["Retry-After"] = str(segundos)
            resp.headers["X-Mercos-Pagina"] = str(pagina_atual)
            return _garantir_sessao_condicoes_cookie(resp, sessao)
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={
                "status-sync": "erro",
                "http-status": str(exc.status_code or ""),
                **_attrs_ciclo_condicoes(sessao),
            },
        )
        if exc.status_code in (409, 504):
            resp.status_code = exc.status_code
        return _garantir_sessao_condicoes_cookie(resp, sessao)
    except Exception as exc:
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={"status-sync": "erro", **_attrs_ciclo_condicoes(sessao)},
        )
        return _garantir_sessao_condicoes_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/condicoes-localizar", response_class=HTMLResponse)
def acao_condicoes_localizar(
    request: Request,
    token: str = Form(""),
    nome: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Localiza por nome completo ou prefixo no catálogo local. Não chama Mercos nem altera cursor."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_condicoes(request)
    _hidratar_catalogo_condicoes_form(sessao, catalogo_json)
    ciclo_antes = catalogo_condicoes.obter_ciclo(sessao)
    busca = (nome or "").strip()
    if not busca:
        return _garantir_sessao_condicoes_cookie(
            _wrap_result(
                _card(
                    "Localizar condição de pagamento",
                    [("Mensagem", "Informe o nome completo ou o prefixo da condição.")],
                    status_label="Atenção",
                    css="erro",
                )
            ),
            sessao,
        )

    encontrado, no_ultimo_lote, estado = catalogo_condicoes.buscar_por_nome(
        sessao, busca
    )
    if not encontrado:
        return _garantir_sessao_condicoes_cookie(
            _wrap_result(
                _card(
                    "Condição de pagamento não encontrada",
                    [
                        ("Nome buscado", busca),
                        (
                            "Condições no catálogo local",
                            catalogo_condicoes.total(sessao),
                        ),
                    ]
                    + _linhas_ciclo_condicoes(sessao, estado),
                    status_label="Não encontrado",
                    css="erro",
                ),
                extra_attrs={"cursor-fixo": "1", **_attrs_ciclo_condicoes(sessao)},
            ),
            sessao,
        )

    ultima = encontrado.get("ultima_alteracao")
    if ultima is None or ultima == "":
        ultima = "—"
    linhas: list[tuple[str, Any]] = [
        ("ID", encontrado.get("id")),
        ("Nome completo", encontrado.get("nome")),
        ("Valor mínimo", _fmt_valor_minimo(encontrado.get("valor_minimo"))),
        ("Disponível B2B", _fmt_bool(encontrado.get("disponivel_b2b", "—"))),
        ("Excluído", _fmt_bool(encontrado.get("excluido", False))),
        ("Última alteração", ultima),
        ("Origem", "Catálogo local sincronizado"),
    ]
    linhas.extend(_linhas_ciclo_condicoes(sessao, estado))
    nota = ""
    if not no_ultimo_lote:
        nota = (
            '<p class="hint">Condição localizada no catálogo do ERP; '
            "não veio no último lote incremental.</p>"
        )
    card = _card(
        "Condição de pagamento localizada",
        linhas,
        status_label="Encontrado",
        css="ok",
    )
    ciclo_depois = catalogo_condicoes.obter_ciclo(sessao)
    if ciclo_antes.get("etapa_interna") != ciclo_depois.get("etapa_interna"):
        catalogo_condicoes._salvar_ciclo(sessao, ciclo_antes)
    resp = _wrap_result(
        nota + card + _html_patch_catalogo_condicoes(sessao),
        extra_attrs={
            "status-sync": "localizado",
            "cursor-fixo": "1",
            **_attrs_ciclo_condicoes(sessao),
        },
    )
    return _garantir_sessao_condicoes_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/pedidos-reiniciar", response_class=HTMLResponse)
def acao_pedidos_reiniciar(
    request: Request,
    token: str = Form(""),
):
    """Apaga cursor e catálogo de pedidos, inicia ciclo na etapa 0 — sem chamar a Mercos."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_pedidos(request)
    catalogo_pedidos.iniciar_ciclo(sessao)
    homolog._limpar_resumes_da_sessao(sessao)
    estado = catalogo_pedidos.obter(sessao)
    mensagem = (
        '<div class="result-card ok">'
        "<h4>Ciclo de sincronização reiniciado</h4>"
        "<p>Cursor e catálogo anteriores apagados. Novo ciclo ativo na etapa 0. "
        "Use «Sincronizar próxima etapa» para a busca completa.</p>"
        "</div>"
    )
    resumo = _card(
        "Estado do ciclo",
        _linhas_ciclo_pedidos(sessao, estado),
        status_label="Ciclo ativo",
        css="ok",
    )
    resp = _wrap_result(
        mensagem + resumo + _html_patch_catalogo_pedidos(sessao),
        extra_attrs={
            "novo-cursor": "",
            "cursor-limpo": "1",
            "catalogo-limpo": "1",
            "status-sync": "reiniciado",
            "catalogo-total": "0",
            **_attrs_ciclo_pedidos(sessao),
        },
    )
    resp = _set_cursor_pedidos_cookie(resp, None)
    return _garantir_sessao_pedidos_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/pedidos-sincronizar", response_class=HTMLResponse)
def acao_pedidos_sincronizar(
    request: Request,
    token: str = Form(""),
    cursor: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Única ação que chama a Mercos no ciclo de pedidos: etapa 0 completa; 1 incremental."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_pedidos(request)
    _hidratar_catalogo_pedidos_form(sessao, catalogo_json)
    ciclo = catalogo_pedidos.obter_ciclo(sessao)
    if not ciclo.get("ativo"):
        catalogo_pedidos.iniciar_ciclo(sessao)
        ciclo = catalogo_pedidos.obter_ciclo(sessao)

    etapa = int(ciclo.get("etapa_interna") or 0)
    cursor_form = _cursor_pedidos(request, cursor)

    if etapa == 0:
        cursor_para_sync = None
        tipo_esperado = "completa"
    else:
        if not cursor_form:
            resp = _wrap_result(
                _card(
                    "Cursor ausente",
                    [
                        (
                            "Mensagem",
                            "Etapa incremental exige cursor salvo. Reinicie o ciclo se necessário.",
                        )
                    ]
                    + _linhas_ciclo_pedidos(sessao),
                    status_label="Erro",
                    css="erro",
                ),
                extra_attrs={"status-sync": "erro", **_attrs_ciclo_pedidos(sessao)},
            )
            return _garantir_sessao_pedidos_cookie(resp, sessao)
        cursor_para_sync = cursor_form
        tipo_esperado = "incremental"

    try:
        data = homolog.sincronizar_pedidos(
            cursor_para_sync, max_paginas=20, sessao_id=sessao
        )
        tipo_real = data.get("tipo") or tipo_esperado
        if etapa >= 1 and (
            tipo_real == "completa" or not data.get("alterado_apos_enviado")
        ):
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [
                        (
                            "Mensagem",
                            "A etapa atual exige busca incremental com alterado_apos.",
                        )
                    ]
                    + _linhas_ciclo_pedidos(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_pedidos(sessao)},
            )
            return _garantir_sessao_pedidos_cookie(resp, sessao)

        status_sync = data.get("status") or "concluida"
        motivo = data.get("motivo_parada") or ""
        status_label = "Timeout" if status_sync == "timeout" else "Concluída"
        meta = {
            "tipo": tipo_real,
            "cursor_base": data.get("cursor_base"),
            "alterado_apos_enviado": data.get("alterado_apos_enviado"),
            "novo_cursor": data.get("novo_cursor"),
            "total_lote": data.get("total", 0),
            "paginas_lidas": data.get("paginas_lidas") or 0,
            "motivo_parada": motivo,
            "status_sync": status_label,
            "requisicoes_extras": data.get("requisicoes_extras"),
            "requisicoes_previstas": data.get("requisicoes_previstas"),
            "requisicoes_executadas": data.get("requisicoes_executadas"),
            "intervalo_minimo_aplicado": data.get("intervalo_minimo_aplicado"),
            "menor_intervalo_real": data.get("menor_intervalo_real"),
            "throttling_respeitado": data.get("throttling_respeitado"),
        }
        if tipo_real == "completa":
            catalogo_pedidos.substituir_completo(
                sessao, data.get("itens") or [], meta=meta
            )
        else:
            catalogo_pedidos.upsert_incremental(
                sessao, data.get("itens") or [], meta=meta
            )
        try:
            catalogo_pedidos.registrar_sync_ciclo(sessao, tipo=tipo_real)
        except ValueError as exc:
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [("Mensagem", str(exc))] + _linhas_ciclo_pedidos(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_pedidos(sessao)},
            )
            return _garantir_sessao_pedidos_cookie(resp, sessao)

        estado = catalogo_pedidos.obter(sessao)
        total = data.get("total", 0)
        paginas = data.get("paginas_lidas") or 0
        css = "pendente" if status_sync == "timeout" else "ok"
        resumo = _card(
            "Sincronização de pedidos",
            [
                ("Status da sincronização", status_label),
                ("Motivo da parada", motivo or "—"),
            ]
            + _linhas_ciclo_pedidos(sessao, estado),
            status_label=status_label,
            css=css,
        )
        table = _html_tabela_pedidos(data.get("itens") or [])
        resp = _wrap_result(
            resumo + table + _html_patch_catalogo_pedidos(sessao),
            extra_attrs={
                "novo-cursor": data.get("novo_cursor") or "",
                "cursor-anterior": data.get("cursor_anterior") or "",
                "cursor-base": data.get("cursor_base") or "",
                "alterado-apos-enviado": data.get("alterado_apos_enviado") or "",
                "tipo-busca": tipo_real,
                "total": str(total),
                "paginas-lidas": str(paginas),
                "requisicoes-extras": str(data.get("requisicoes_extras") if data.get("requisicoes_extras") is not None else ""),
                "requisicoes-previstas": str(data.get("requisicoes_previstas") if data.get("requisicoes_previstas") is not None else ""),
                "requisicoes-executadas": str(data.get("requisicoes_executadas") or 0),
                "motivo-parada": motivo,
                "catalogo-total": str(len(estado.get("pedidos") or {})),
                "catalogo-modo": "replace" if tipo_real == "completa" else "upsert",
                "status-sync": status_sync,
                **_attrs_ciclo_pedidos(sessao),
            },
        )
        resp = _set_cursor_pedidos_cookie(resp, data.get("novo_cursor"))
        return _garantir_sessao_pedidos_cookie(resp, sessao)
    except MercosApiError as exc:
        if exc.status_code == 429:
            segundos = exc.retry_after if exc.retry_after is not None else 10
            try:
                segundos = max(0, int(float(segundos)))
            except (TypeError, ValueError):
                segundos = 10
            pagina_atual = exc.pagina if exc.pagina is not None else "—"
            resp = _wrap_result(
                _card(
                    "Aguardando limite da Mercos",
                    [
                        ("Mensagem", "Aguardando limite da Mercos"),
                        ("Segundos restantes", segundos),
                        ("Página atual", pagina_atual),
                    ],
                    status_label="Aguardando",
                    css="pendente",
                ),
                extra_attrs={
                    "status-sync": "aguardando-429",
                    "aguardando-mercos": "1",
                    "segundos-espera": str(segundos),
                    "pagina-atual": str(pagina_atual),
                    "http-status": "429",
                    **_attrs_ciclo_pedidos(sessao),
                },
            )
            resp.status_code = 429
            resp.headers["Retry-After"] = str(segundos)
            resp.headers["X-Mercos-Pagina"] = str(pagina_atual)
            return _garantir_sessao_pedidos_cookie(resp, sessao)
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={
                "status-sync": "erro",
                "http-status": str(exc.status_code or ""),
                **_attrs_ciclo_pedidos(sessao),
            },
        )
        if exc.status_code in (409, 504):
            resp.status_code = exc.status_code
        return _garantir_sessao_pedidos_cookie(resp, sessao)
    except Exception as exc:
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={"status-sync": "erro", **_attrs_ciclo_pedidos(sessao)},
        )
        return _garantir_sessao_pedidos_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/pedidos-localizar", response_class=HTMLResponse)
def acao_pedidos_localizar(
    request: Request,
    token: str = Form(""),
    razao_social: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Localiza pedido pela razão social do cliente no catálogo local.

    Não chama a Mercos e não altera cursor nem etapa. Se o pedido só tiver
    cliente_id, relaciona com o catálogo local de clientes já sincronizado.
    """
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_pedidos(request)
    _hidratar_catalogo_pedidos_form(sessao, catalogo_json)
    ciclo_antes = catalogo_pedidos.obter_ciclo(sessao)
    busca = (razao_social or "").strip()
    if not busca:
        return _garantir_sessao_pedidos_cookie(
            _wrap_result(
                _card(
                    "Localizar pedido",
                    [("Mensagem", "Informe a razão social completa ou o prefixo do cliente.")],
                    status_label="Atenção",
                    css="erro",
                )
            ),
            sessao,
        )

    razoes = _razoes_clientes_por_id(request)
    encontrado, estado = catalogo_pedidos.buscar_por_razao_social(
        sessao, busca, razoes_por_cliente_id=razoes
    )
    if not encontrado:
        return _garantir_sessao_pedidos_cookie(
            _wrap_result(
                _card(
                    "Pedido não encontrado",
                    [
                        ("Razão social buscada", busca),
                        ("Pedidos no catálogo local", catalogo_pedidos.total(sessao)),
                    ]
                    + _linhas_ciclo_pedidos(sessao, estado),
                    status_label="Não encontrado",
                    css="erro",
                ),
                extra_attrs={"cursor-fixo": "1", **_attrs_ciclo_pedidos(sessao)},
            ),
            sessao,
        )

    ultima = encontrado.get("ultima_alteracao")
    if ultima is None or ultima == "":
        ultima = "—"
    linhas: list[tuple[str, Any]] = [
        ("ID do pedido", encontrado.get("id")),
        ("ID do cliente", encontrado.get("cliente_id")),
        ("Razão social do cliente", encontrado.get("cliente_razao_social") or "—"),
        ("Total do pedido", _fmt_total_pedido(encontrado.get("total"))),
        ("Status", encontrado.get("status") or "—"),
        ("Data de emissão", encontrado.get("data_emissao") or "—"),
        ("Última alteração", ultima),
        ("Origem", "Catálogo local sincronizado"),
    ]
    linhas.extend(_linhas_ciclo_pedidos(sessao, estado))
    card = _card(
        "Pedido localizado",
        linhas,
        status_label="Encontrado",
        css="ok",
    )
    ciclo_depois = catalogo_pedidos.obter_ciclo(sessao)
    if ciclo_antes.get("etapa_interna") != ciclo_depois.get("etapa_interna"):
        catalogo_pedidos._salvar_ciclo(sessao, ciclo_antes)
    resp = _wrap_result(
        card + _html_patch_catalogo_pedidos(sessao),
        extra_attrs={
            "status-sync": "localizado",
            "cursor-fixo": "1",
            "pedido-total": _fmt_total_pedido(encontrado.get("total")),
            **_attrs_ciclo_pedidos(sessao),
        },
    )
    return _garantir_sessao_pedidos_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/pagamentos-reiniciar", response_class=HTMLResponse)
def acao_pagamentos_reiniciar(
    request: Request,
    token: str = Form(""),
):
    """Apaga cursor/catálogo de pagamentos, ciclo volta a 0/2 — sem chamar a Mercos."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_pagamentos(request)
    catalogo_pagamentos.iniciar_ciclo(sessao)
    homolog._limpar_resumes_da_sessao(sessao)
    estado = catalogo_pagamentos.obter(sessao)
    mensagem = (
        '<div class="result-card ok">'
        "<h4>Ciclo de sincronização reiniciado</h4>"
        "<p>Cursor e catálogo anteriores apagados. Novo ciclo ativo na etapa 0/2. "
        "Use «Sincronizar próxima etapa» para a busca completa.</p>"
        "</div>"
    )
    resumo = _card(
        "Estado do ciclo",
        _linhas_ciclo_pagamentos(sessao, estado),
        status_label="Ciclo ativo",
        css="ok",
    )
    resp = _wrap_result(
        mensagem + resumo + _html_patch_catalogo_pagamentos(sessao),
        extra_attrs={
            "novo-cursor": "",
            "cursor-limpo": "1",
            "catalogo-limpo": "1",
            "status-sync": "reiniciado",
            "catalogo-total": "0",
            **_attrs_ciclo_pagamentos(sessao),
        },
    )
    resp = _set_cursor_pagamentos_cookie(resp, None)
    return _garantir_sessao_pagamentos_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/pagamentos-sincronizar", response_class=HTMLResponse)
def acao_pagamentos_sincronizar(
    request: Request,
    token: str = Form(""),
    cursor: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Única ação que chama a Mercos no ciclo: etapa 0 completa; etapa 1 incremental."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_pagamentos(request)
    _hidratar_catalogo_pagamentos_form(sessao, catalogo_json)
    ciclo = catalogo_pagamentos.obter_ciclo(sessao)
    if not ciclo.get("ativo"):
        catalogo_pagamentos.iniciar_ciclo(sessao)
        ciclo = catalogo_pagamentos.obter_ciclo(sessao)

    etapa = int(ciclo.get("etapa_interna") or 0)
    cursor_form = _cursor_pagamentos(request, cursor)

    if etapa == 0:
        cursor_para_sync = None
        tipo_esperado = "completa"
    else:
        if not cursor_form:
            resp = _wrap_result(
                _card(
                    "Cursor ausente",
                    [
                        (
                            "Mensagem",
                            "Etapa incremental exige cursor salvo. Reinicie o ciclo se necessário.",
                        )
                    ]
                    + _linhas_ciclo_pagamentos(sessao),
                    status_label="Erro",
                    css="erro",
                ),
                extra_attrs={"status-sync": "erro", **_attrs_ciclo_pagamentos(sessao)},
            )
            return _garantir_sessao_pagamentos_cookie(resp, sessao)
        cursor_para_sync = cursor_form
        tipo_esperado = "incremental"

    try:
        data = homolog.sincronizar_pagamentos(
            cursor_para_sync, max_paginas=20, sessao_id=sessao
        )
        tipo_real = data.get("tipo") or tipo_esperado
        if etapa >= 1 and (
            tipo_real == "completa" or not data.get("alterado_apos_enviado")
        ):
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [
                        (
                            "Mensagem",
                            "A etapa atual exige busca incremental com alterado_apos.",
                        )
                    ]
                    + _linhas_ciclo_pagamentos(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_pagamentos(sessao)},
            )
            return _garantir_sessao_pagamentos_cookie(resp, sessao)

        status_sync = data.get("status") or "concluida"
        motivo = data.get("motivo_parada") or ""
        status_label = "Timeout" if status_sync == "timeout" else "Concluída"
        meta = {
            "tipo": tipo_real,
            "cursor_base": data.get("cursor_base"),
            "alterado_apos_enviado": data.get("alterado_apos_enviado"),
            "novo_cursor": data.get("novo_cursor"),
            "total_lote": data.get("total", 0),
            "paginas_lidas": data.get("paginas_lidas") or 0,
            "motivo_parada": motivo,
            "status_sync": status_label,
            "requisicoes_extras": data.get("requisicoes_extras"),
            "requisicoes_previstas": data.get("requisicoes_previstas"),
            "requisicoes_executadas": data.get("requisicoes_executadas"),
        }
        if tipo_real == "completa":
            catalogo_pagamentos.substituir_completo(
                sessao, data.get("itens") or [], meta=meta
            )
        else:
            catalogo_pagamentos.upsert_incremental(
                sessao, data.get("itens") or [], meta=meta
            )
        try:
            catalogo_pagamentos.registrar_sync_ciclo(sessao, tipo=tipo_real)
        except ValueError as exc:
            resp = _wrap_result(
                _card(
                    "Busca completa bloqueada durante a homologação",
                    [("Mensagem", str(exc))] + _linhas_ciclo_pagamentos(sessao),
                    status_label="Bloqueado",
                    css="erro",
                ),
                extra_attrs={"status-sync": "bloqueado", **_attrs_ciclo_pagamentos(sessao)},
            )
            return _garantir_sessao_pagamentos_cookie(resp, sessao)

        estado = catalogo_pagamentos.obter(sessao)
        total = data.get("total", 0)
        paginas = data.get("paginas_lidas") or 0
        css = "pendente" if status_sync == "timeout" else "ok"
        resumo = _card(
            "Sincronização de pagamentos",
            [
                ("Status da sincronização", status_label),
                ("Motivo da parada", motivo or "—"),
            ]
            + _linhas_ciclo_pagamentos(sessao, estado),
            status_label=status_label,
            css=css,
        )
        table = _html_tabela_pagamentos(data.get("itens") or [])
        resp = _wrap_result(
            resumo + table + _html_patch_catalogo_pagamentos(sessao),
            extra_attrs={
                "novo-cursor": data.get("novo_cursor") or "",
                "cursor-anterior": data.get("cursor_anterior") or "",
                "cursor-base": data.get("cursor_base") or "",
                "alterado-apos-enviado": data.get("alterado_apos_enviado") or "",
                "tipo-busca": tipo_real,
                "total": str(total),
                "paginas-lidas": str(paginas),
                "requisicoes-extras": str(
                    data.get("requisicoes_extras")
                    if data.get("requisicoes_extras") is not None
                    else ""
                ),
                "requisicoes-previstas": str(
                    data.get("requisicoes_previstas")
                    if data.get("requisicoes_previstas") is not None
                    else ""
                ),
                "requisicoes-executadas": str(data.get("requisicoes_executadas") or 0),
                "motivo-parada": motivo,
                "catalogo-total": str(len(estado.get("pagamentos") or {})),
                "catalogo-modo": "replace" if tipo_real == "completa" else "upsert",
                "status-sync": status_sync,
                **_attrs_ciclo_pagamentos(sessao),
            },
        )
        resp = _set_cursor_pagamentos_cookie(resp, data.get("novo_cursor"))
        return _garantir_sessao_pagamentos_cookie(resp, sessao)
    except MercosApiError as exc:
        if exc.status_code == 429:
            segundos = exc.retry_after if exc.retry_after is not None else 10
            try:
                segundos = max(0, int(float(segundos)))
            except (TypeError, ValueError):
                segundos = 10
            pagina_atual = exc.pagina if exc.pagina is not None else "—"
            resp = _wrap_result(
                _card(
                    "Aguardando limite da Mercos",
                    [
                        ("Mensagem", "Aguardando limite da Mercos"),
                        ("Segundos restantes", segundos),
                        ("Página atual", pagina_atual),
                    ],
                    status_label="Aguardando",
                    css="pendente",
                ),
                extra_attrs={
                    "status-sync": "aguardando-429",
                    "aguardando-mercos": "1",
                    "segundos-espera": str(segundos),
                    "pagina-atual": str(pagina_atual),
                    "http-status": "429",
                    **_attrs_ciclo_pagamentos(sessao),
                },
            )
            resp.status_code = 429
            resp.headers["Retry-After"] = str(segundos)
            resp.headers["X-Mercos-Pagina"] = str(pagina_atual)
            return _garantir_sessao_pagamentos_cookie(resp, sessao)
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={
                "status-sync": "erro",
                "http-status": str(exc.status_code or ""),
                **_attrs_ciclo_pagamentos(sessao),
            },
        )
        if exc.status_code in (409, 504):
            resp.status_code = exc.status_code
        return _garantir_sessao_pagamentos_cookie(resp, sessao)
    except Exception as exc:
        resp = _wrap_result(
            _erro_html(exc),
            extra_attrs={"status-sync": "erro", **_attrs_ciclo_pagamentos(sessao)},
        )
        return _garantir_sessao_pagamentos_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/pagamentos-localizar", response_class=HTMLResponse)
def acao_pagamentos_localizar(
    request: Request,
    token: str = Form(""),
    pagamento_id: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Localiza pagamento pelo ID no catálogo local. Não chama Mercos nem altera cursor."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_pagamentos(request)
    _hidratar_catalogo_pagamentos_form(sessao, catalogo_json)
    ciclo_antes = catalogo_pagamentos.obter_ciclo(sessao)
    busca = (pagamento_id or "").strip()
    if not busca:
        return _garantir_sessao_pagamentos_cookie(
            _wrap_result(
                _card(
                    "Localizar pagamento",
                    [("Mensagem", "Informe o ID do pagamento.")],
                    status_label="Atenção",
                    css="erro",
                )
            ),
            sessao,
        )

    encontrado, no_ultimo_lote, estado = catalogo_pagamentos.buscar_por_id(sessao, busca)
    if not encontrado:
        return _garantir_sessao_pagamentos_cookie(
            _wrap_result(
                _card(
                    "Pagamento não encontrado",
                    [
                        ("ID buscado", busca),
                        (
                            "Pagamentos no catálogo local",
                            catalogo_pagamentos.total(sessao),
                        ),
                    ]
                    + _linhas_ciclo_pagamentos(sessao, estado),
                    status_label="Não encontrado",
                    css="erro",
                ),
                extra_attrs={"cursor-fixo": "1", **_attrs_ciclo_pagamentos(sessao)},
            ),
            sessao,
        )

    ultima = encontrado.get("ultima_alteracao")
    if ultima is None or ultima == "":
        ultima = "—"
    data_pag = encontrado.get("data_criacao")
    if data_pag in (None, ""):
        data_pag = "—"
    linhas: list[tuple[str, Any]] = [
        ("ID", encontrado.get("id")),
        ("Valor do pagamento", _fmt_valor_pagamento(encontrado.get("valor"))),
        ("Pedido, título ou cliente relacionado", _relacionado_pagamento(encontrado)),
        ("Data", data_pag),
        ("Excluído", _fmt_bool(encontrado.get("excluido", False))),
        ("Última alteração", ultima),
        ("Origem", "Catálogo local sincronizado"),
    ]
    linhas.extend(_linhas_ciclo_pagamentos(sessao, estado))
    nota = ""
    if not no_ultimo_lote:
        nota = (
            '<p class="hint">Pagamento localizado no catálogo do ERP; '
            "não veio no último lote incremental.</p>"
        )
    card = _card(
        "Pagamento localizado",
        linhas,
        status_label="Encontrado",
        css="ok",
    )
    ciclo_depois = catalogo_pagamentos.obter_ciclo(sessao)
    if ciclo_antes.get("etapa_interna") != ciclo_depois.get("etapa_interna"):
        catalogo_pagamentos._salvar_ciclo(sessao, ciclo_antes)
    resp = _wrap_result(
        nota + card + _html_patch_catalogo_pagamentos(sessao),
        extra_attrs={
            "status-sync": "localizado",
            "cursor-intacto": "1",
            "pagamento-valor": _fmt_valor_pagamento(encontrado.get("valor")),
            **_attrs_ciclo_pagamentos(sessao),
        },
    )
    return _garantir_sessao_pagamentos_cookie(resp, sessao)


@router.post(
    "/homologacao-ui/acoes/pagamentos-localizar-vencimento",
    response_class=HTMLResponse,
)
def acao_pagamentos_localizar_vencimento(
    request: Request,
    token: str = Form(""),
    data_vencimento: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Localiza transação aninhada por vencimento somente no catálogo local."""
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_pagamentos(request)
    _hidratar_catalogo_pagamentos_form(sessao, catalogo_json)
    ciclo_antes = catalogo_pagamentos.obter_ciclo(sessao)
    busca = (data_vencimento or "").strip()
    if not busca:
        return _garantir_sessao_pagamentos_cookie(
            _wrap_result(
                _card(
                    "Localizar transação pela data de vencimento",
                    [("Mensagem", "Informe a data no formato DD/MM/AAAA ou AAAA-MM-DD.")],
                    status_label="Atenção",
                    css="erro",
                ),
                extra_attrs={
                    "cursor-intacto": "1",
                    **_attrs_ciclo_pagamentos(sessao),
                },
            ),
            sessao,
        )

    pagamento, transacao, no_ultimo_lote, estado = (
        catalogo_pagamentos.buscar_transacao_por_vencimento(sessao, busca)
    )
    if not pagamento or not transacao:
        return _garantir_sessao_pagamentos_cookie(
            _wrap_result(
                _card(
                    "Transação não encontrada",
                    [
                        ("Data de vencimento buscada", busca),
                        ("Pagamentos no catálogo local", catalogo_pagamentos.total(sessao)),
                    ]
                    + _linhas_ciclo_pagamentos(sessao, estado),
                    status_label="Não encontrada",
                    css="erro",
                ),
                extra_attrs={
                    "cursor-intacto": "1",
                    **_attrs_ciclo_pagamentos(sessao),
                },
            ),
            sessao,
        )

    linhas: list[tuple[str, Any]] = [
        ("ID do pagamento", pagamento.get("id")),
        ("ID da transação", transacao.get("transacao_id") or "—"),
        ("Data de vencimento", transacao.get("data_vencimento") or "—"),
        # Não traduzir, capitalizar ou normalizar o status retornado.
        ("Status da transação", transacao.get("status") or "—"),
        ("Valor", _fmt_valor_pagamento(transacao.get("valor"))),
        ("Pedido relacionado", pagamento.get("pedido_id") or "—"),
        ("Cliente relacionado", pagamento.get("cliente_id") or "—"),
        ("Origem", "Catálogo local sincronizado"),
    ]
    linhas.extend(_linhas_ciclo_pagamentos(sessao, estado))
    nota = ""
    if not no_ultimo_lote:
        nota = (
            '<p class="hint">Transação localizada no catálogo do ERP; '
            "não veio no último lote incremental.</p>"
        )
    card = _card(
        "Transação localizada",
        linhas,
        status_label="Encontrada",
        css="ok",
    )
    ciclo_depois = catalogo_pagamentos.obter_ciclo(sessao)
    if ciclo_antes.get("etapa_interna") != ciclo_depois.get("etapa_interna"):
        catalogo_pagamentos._salvar_ciclo(sessao, ciclo_antes)
    resp = _wrap_result(
        nota + card + _html_patch_catalogo_pagamentos(sessao),
        extra_attrs={
            "status-sync": "transacao-localizada",
            "cursor-intacto": "1",
            "status-transacao": str(transacao.get("status") or ""),
            **_attrs_ciclo_pagamentos(sessao),
        },
    )
    return _garantir_sessao_pagamentos_cookie(resp, sessao)


def _sem_acentos_minusculo(texto: str) -> str:
    import unicodedata

    norm = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in norm if unicodedata.category(c) != "Mn").lower()


@router.post("/homologacao-ui/acoes/condicoes-opcoes", response_class=HTMLResponse)
def acao_condicoes_opcoes(request: Request, token: str = Form("")):
    """Opções (nome + ID) para o seletor de condição de pagamento do Pedido POST.

    Reutiliza o catálogo GET /v1/condicoes_pagamento já homologado. Lista só
    condições ativas; a condição cujo nome contém "vista" (sem acentos) já vem
    marcada como selecionada. Se não houver condição à vista ativa, devolve o
    marcador data-vista-ausente para a UI avisar — o pedido pode ser enviado
    com a condição "a vista" pelo nome (mesmo contrato do restante do projeto).
    """
    _auth(request, token)
    try:
        data = homolog.listar_condicoes_pagamento(pagina_inicial=1, max_paginas=3)
        opcoes: list[str] = []
        vista_encontrada = False
        for item in data.get("itens") or []:
            if not isinstance(item, dict) or item.get("excluido"):
                continue
            cid = item.get("id")
            nome = str(item.get("nome") or "").strip()
            if cid in (None, "") or not nome:
                continue
            selecionada = ""
            if not vista_encontrada and "vista" in _sem_acentos_minusculo(nome):
                selecionada = " selected"
                vista_encontrada = True
            opcoes.append(
                f'<option value="{_esc(cid)}" data-nome="{_esc(nome)}"{selecionada}>'
                f"{_esc(nome)} (ID {_esc(cid)})</option>"
            )
        if not opcoes:
            return HTMLResponse(
                '<option value="" data-vista-ausente="1">'
                "Nenhuma condição ativa — será usada À vista pelo nome</option>"
            )
        if vista_encontrada:
            placeholder = '<option value="">Selecione a condição…</option>'
        else:
            placeholder = (
                '<option value="" data-vista-ausente="1" selected>'
                "À vista não encontrada — será usada pelo nome</option>"
            )
        return HTMLResponse(placeholder + "".join(opcoes))
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


def _parse_itens_pedido(
    itens_json: str,
    produto_id: str,
    quantidade: str,
    preco: str,
) -> list[dict[str, Any]]:
    """Itens do formulário: lista JSON interna (linhas da UI) ou campos únicos legados."""
    brutos: list[dict] = []
    texto = (itens_json or "").strip()
    if texto:
        try:
            payload = json.loads(texto)
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, list):
            brutos = [i for i in payload if isinstance(i, dict)]
    elif (produto_id or "").strip():
        brutos = [{"produto_id": produto_id, "quantidade": quantidade, "preco": preco}]

    itens: list[dict[str, Any]] = []
    for bruto in brutos:
        pid = str(bruto.get("produto_id") or "").strip()
        if not pid:
            continue
        qtd = float(str(bruto.get("quantidade") or "1").replace(",", "."))
        preco_f = float(str(bruto.get("preco") or "0").replace(",", "."))
        itens.append(
            {
                "produto_id": int(pid) if pid.isdigit() else pid,
                "quantidade": qtd,
                "preco_tabela": round(preco_f, 2),
            }
        )
    return itens


@router.post("/homologacao-ui/acoes/pedidos-criar", response_class=HTMLResponse)
def acao_pedidos_criar(
    request: Request,
    token: str = Form(""),
    cliente_id: str = Form(""),
    itens_json: str = Form(""),
    produto_id: str = Form(""),
    quantidade: str = Form("1"),
    preco: str = Form("10.00"),
    condicao_pagamento_id: str = Form(""),
    condicao_pagamento_nome: str = Form(""),
):
    """POST /v2/pedidos com um único pedido e lista de itens.

    Contrato oficial (Apiary): cliente_id e condicao_pagamento_id ficam no
    pedido; cada item usa produto_id, quantidade e preco_tabela — o cliente
    não vai dentro dos itens.
    """
    _auth(request, token)
    if not (cliente_id or "").strip():
        return _wrap_result(
            _card(
                "Campos obrigatórios",
                [("Ação", "Informe o código do cliente.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        itens = _parse_itens_pedido(itens_json, produto_id, quantidade, preco)
    except (TypeError, ValueError):
        itens = []
    if not itens:
        return _wrap_result(
            _card(
                "Itens obrigatórios",
                [
                    (
                        "Ação",
                        "Informe pelo menos um item com código do produto, quantidade e preço.",
                    )
                ],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        body: dict[str, Any] = {
            "cliente_id": int(cliente_id) if str(cliente_id).isdigit() else cliente_id,
            "data_emissao": date.today().isoformat(),
            "observacoes": f"Pedido homologação visual Xnamai {_agora_br()}",
            "itens": itens,
        }
        if (condicao_pagamento_id or "").strip():
            cid_pag = condicao_pagamento_id.strip()
            body["condicao_pagamento_id"] = int(cid_pag) if cid_pag.isdigit() else cid_pag
        else:
            # Sandbox sem condição ativa "À vista" no catálogo: o /v2/pedidos
            # aceita a condição pelo nome (mesmo contrato já usado no projeto).
            body["condicao_pagamento"] = "a vista"

        out = homolog.criar_pedido(body)
        pid = out.get("id") or (out.get("dados") or {}).get("id")
        numero = (out.get("dados") or {}).get("numero") or "—"
        total_calculado = round(
            sum(i["quantidade"] * i["preco_tabela"] for i in itens), 2
        )
        condicao_label = (condicao_pagamento_nome or "").strip()
        if (condicao_pagamento_id or "").strip():
            sufixo = f"(ID {condicao_pagamento_id.strip()})"
            condicao_label = f"{condicao_label} {sufixo}".strip() if condicao_label else sufixo
        elif not condicao_label:
            condicao_label = "À vista (pelo nome)"
        linhas: list[tuple[str, Any]] = [
            ("Status HTTP", out.get("status_code") or 201),
            ("ID do pedido", pid),
            ("Número do pedido", numero),
            ("Cliente", cliente_id),
            ("Condição de pagamento", condicao_label or "—"),
            ("Quantidade de itens", len(itens)),
        ]
        for idx, item in enumerate(itens, start=1):
            linhas.append(
                (
                    f"Item {idx}",
                    f"Produto {item['produto_id']} · Quantidade {item['quantidade']:g} · "
                    f"Preço {item['preco_tabela']:.2f}",
                )
            )
        linhas.append(("Total calculado", f"{total_calculado:.2f}"))
        card = _card(
            "Pedido criado",
            linhas,
            status_label=f"Status {out.get('status_code') or 201}",
            css="ok",
        )
        return _wrap_result(card, entity="pedido", entity_id=str(pid or ""))
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/pedidos-alterar", response_class=HTMLResponse)
def acao_pedidos_alterar(
    request: Request,
    token: str = Form(""),
    pedido_id: str = Form(""),
    cliente_id: str = Form(""),
    produto_id: str = Form(""),
    preco: str = Form("10.00"),
    condicao_pagamento_id: str = Form(""),
):
    _auth(request, token)
    pid = (pedido_id or "").strip()
    if not pid:
        return _wrap_result(
            _card(
                "Pedido não informado",
                [("Ação", "Informe o ID do pedido ou crie um pedido antes.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        preco_f = float(str(preco or "10").replace(",", "."))
        body: dict[str, Any] = {
            "itens": [
                {
                    "produto_id": (
                        int(produto_id) if str(produto_id).isdigit() else produto_id
                    ),
                    "quantidade": 2,
                    "preco_bruto": round(preco_f, 2),
                }
            ],
        }
        if (cliente_id or "").strip():
            body["cliente_id"] = (
                int(cliente_id) if str(cliente_id).isdigit() else cliente_id
            )
        if (condicao_pagamento_id or "").strip():
            cp = condicao_pagamento_id.strip()
            body["condicao_pagamento_id"] = int(cp) if cp.isdigit() else cp
        body["data_emissao"] = date.today().isoformat()

        out = homolog.alterar_pedido(pid, body)
        card = _card(
            "Pedido alterado",
            [
                ("Status", out.get("status_code") or 200),
                ("ID do pedido", pid),
                ("Quantidade atualizada", 2),
                ("Produto", produto_id or "—"),
            ],
            status_label=f"Status {out.get('status_code') or 200}",
            css="ok",
        )
        return _wrap_result(card, entity="pedido", entity_id=pid)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/pedidos-cancelar", response_class=HTMLResponse)
def acao_pedidos_cancelar(
    request: Request,
    token: str = Form(""),
    pedido_id: str = Form(""),
):
    """POST /v1/pedidos/cancelar/{id} — um único cancelamento por clique.

    Contrato oficial: id só na URL, corpo vazio, sem motivo/observação, sem
    DELETE e sem o PUT comum de pedidos. O pedido permanece no sistema com
    status Cancelado. Não altera ciclo GET, POST, PUT nem títulos.
    """
    _auth(request, token)
    pid = (pedido_id or "").strip()
    if not pid:
        return _wrap_result(
            _card(
                "Pedido não informado",
                [("Ação", "Informe o ID do pedido a cancelar.")],
                status_label="Pendente",
                css="pendente",
            )
        )

    # Status anterior: só consulta o catálogo local já sincronizado (sem
    # chamada extra à Mercos e sem alterar cursor/etapa do ciclo GET).
    status_anterior = "—"
    sessao = (request.cookies.get(_COOKIE_PEDIDOS_SESSAO) or "").strip()
    if sessao:
        ped_local = (catalogo_pedidos.obter(sessao).get("pedidos") or {}).get(pid)
        if isinstance(ped_local, dict) and ped_local.get("status") not in (None, ""):
            status_anterior = ped_local.get("status")

    try:
        out = homolog.cancelar_pedido(pid)
        status = out.get("status_code") or 200
        numero = (out.get("dados") or {}).get("numero") or "—"
        card = _card(
            "Pedido cancelado",
            [
                ("Status HTTP", status),
                ("ID do pedido", pid),
                ("Número do pedido", numero),
                ("Status anterior", status_anterior),
                ("Status atual", "Cancelado"),
                ("Origem", "Mercos Sandbox"),
            ],
            status_label=f"Status {status}",
            css="ok",
        )
        return _wrap_result(card, entity="pedido", entity_id=pid)
    except MercosApiError as exc:
        mensagem = exc.message or "Não foi possível cancelar o pedido."
        texto = mensagem.lower()
        if "inexistente" in texto or exc.status_code == 404:
            titulo = "Pedido não encontrado"
        elif "cancelado" in texto:
            titulo = "Pedido já cancelado"
        else:
            titulo = "Não foi possível cancelar o pedido"
        return _wrap_result(
            _card(
                titulo,
                [
                    ("Status HTTP", exc.status_code or "—"),
                    ("ID do pedido", pid),
                    ("Mensagem", mensagem),
                ],
                status_label=f"Erro {exc.status_code or ''}".strip(),
                css="erro",
            )
        )
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


def _fmt_valor_2casas(valor: Any) -> str:
    try:
        return f"{float(str(valor).replace(',', '.')):.2f}"
    except (TypeError, ValueError):
        return str(valor or "—")


@router.post("/homologacao-ui/acoes/pedidos-faturar-localizar", response_class=HTMLResponse)
def acao_pedidos_faturar_localizar(
    request: Request,
    token: str = Form(""),
    numero: str = Form(""),
    cliente: str = Form(""),
    total: str = Form(""),
    catalogo_json: str = Form(""),
):
    """Localiza o pedido a faturar pelo número, só no catálogo local de Pedido GET.

    Não chama a Mercos, não altera cursor nem etapa. Confere também o cliente
    e o total informados e devolve o ID interno para preencher o formulário.
    """
    _auth(request, token)
    sessao = _obter_ou_criar_sessao_pedidos(request)
    _hidratar_catalogo_pedidos_form(sessao, catalogo_json)
    ciclo_antes = catalogo_pedidos.obter_ciclo(sessao)
    numero_busca = (numero or "").strip()
    if not numero_busca:
        return _garantir_sessao_pedidos_cookie(
            _wrap_result(
                _card(
                    "Localizar pedido",
                    [("Mensagem", "Informe o número do pedido a faturar.")],
                    status_label="Atenção",
                    css="erro",
                )
            ),
            sessao,
        )

    estado = catalogo_pedidos.obter(sessao)
    encontrado = None
    for ped in (estado.get("pedidos") or {}).values():
        if isinstance(ped, dict) and str(ped.get("numero") or "") == numero_busca:
            encontrado = dict(ped)
            break

    if not encontrado:
        resp = _wrap_result(
            _card(
                "Pedido não encontrado no catálogo local",
                [
                    ("Número buscado", numero_busca),
                    ("Pedidos no catálogo local", catalogo_pedidos.total(sessao)),
                    ("Mensagem", "Sincronize os pedidos antes de faturar."),
                ],
                status_label="Não encontrado",
                css="erro",
            ),
            extra_attrs={"cursor-fixo": "1", "status-sync": "localizado"},
        )
        return _garantir_sessao_pedidos_cookie(resp, sessao)

    razoes = _razoes_clientes_por_id(request)
    razao = str(
        encontrado.get("cliente_razao_social")
        or razoes.get(str(encontrado.get("cliente_id")))
        or ""
    )
    cliente_esperado = (cliente or "").strip()
    cliente_confere = (
        "Sim"
        if cliente_esperado and razao and razao.lower() == cliente_esperado.lower()
        else ("—" if not cliente_esperado or not razao else "Não")
    )
    total_local = _fmt_valor_2casas(encontrado.get("total"))
    total_esperado = (total or "").strip()
    total_confere = (
        "Sim"
        if total_esperado and total_local == _fmt_valor_2casas(total_esperado)
        else ("—" if not total_esperado else "Não")
    )
    pid = str(encontrado.get("id"))
    card = _card(
        "Pedido localizado para faturamento",
        [
            ("ID do pedido (Mercos)", pid),
            ("Número do pedido", numero_busca),
            ("Cliente", razao or "—"),
            ("Cliente confere", cliente_confere),
            ("Total do pedido", total_local),
            ("Total confere", total_confere),
            ("Origem", "Catálogo local sincronizado"),
        ],
        status_label="Encontrado",
        css="ok",
    )
    ciclo_depois = catalogo_pedidos.obter_ciclo(sessao)
    if ciclo_antes.get("etapa_interna") != ciclo_depois.get("etapa_interna"):
        catalogo_pedidos._salvar_ciclo(sessao, ciclo_antes)
    resp = _wrap_result(
        card,
        extra_attrs={
            "cursor-fixo": "1",
            "status-sync": "localizado",
            "pedido-faturar-id": pid,
        },
    )
    return _garantir_sessao_pedidos_cookie(resp, sessao)


@router.post("/homologacao-ui/acoes/pedidos-faturar", response_class=HTMLResponse)
def acao_pedidos_faturar(
    request: Request,
    token: str = Form(""),
    pedido_id: str = Form(""),
    numero: str = Form(""),
    cliente: str = Form(""),
    total: str = Form(""),
    valor_faturado: str = Form(""),
):
    """POST /v1/faturamento — um único POST por clique, contrato oficial.

    Corpo objeto com pedido_id (ID Mercos), valor_faturado e data_faturamento.
    Sem DELETE, sem PUT comum de pedidos, sem criar novo pedido.
    """
    _auth(request, token)
    pid = (pedido_id or "").strip()
    if not pid:
        return _wrap_result(
            _card(
                "Pedido não localizado",
                [
                    (
                        "Ação",
                        "Use «Localizar pedido» para preencher o ID Mercos antes de faturar.",
                    )
                ],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        valor = float(str(valor_faturado or "").replace(",", "."))
    except (TypeError, ValueError):
        valor = 0.0
    if valor <= 0:
        return _wrap_result(
            _card(
                "Valor faturado inválido",
                [("Ação", "Informe um valor faturado maior que zero.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        out = homolog.faturar_pedido(pid, valor)
        status = out.get("status_code") or 201
        faturamento_id = out.get("id")
        linhas = [
            ("Status HTTP", status),
            ("ID do pedido", pid),
            ("Número do pedido", (numero or "").strip() or "—"),
            ("Cliente", (cliente or "").strip() or "—"),
            ("Total do pedido", _fmt_valor_2casas(total) if (total or "").strip() else "—"),
            ("Valor faturado", f"{valor:.2f}"),
            ("Status atual", "Faturado"),
            ("Origem", "Mercos Sandbox"),
        ]
        if faturamento_id not in (None, ""):
            # Necessário na etapa PUT: a URL de alteração usa o ID do faturamento
            linhas.insert(2, ("ID do faturamento", faturamento_id))
        card = _card(
            "Pedido faturado",
            linhas,
            status_label=f"Status {status}",
            css="ok",
        )
        extra = (
            {"faturamento-id": str(faturamento_id)}
            if faturamento_id not in (None, "")
            else None
        )
        return _wrap_result(card, entity="pedido", entity_id=pid, extra_attrs=extra)
    except MercosApiError as exc:
        mensagem = exc.message or "Não foi possível faturar o pedido."
        texto = mensagem.lower()
        if "cancelado" in texto:
            titulo = "Pedido cancelado não pode ser faturado"
        elif "faturado" in texto and ("já" in texto or "ja " in texto):
            titulo = "Pedido já faturado"
        elif "inexistente" in texto or exc.status_code == 404:
            titulo = "Pedido não encontrado"
        else:
            titulo = "Não foi possível faturar o pedido"
        return _wrap_result(
            _card(
                titulo,
                [
                    ("Status HTTP", exc.status_code or "—"),
                    ("ID do pedido", pid),
                    ("Mensagem", mensagem),
                ],
                status_label=f"Erro {exc.status_code or ''}".strip(),
                css="erro",
            )
        )
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/faturamento-alterar", response_class=HTMLResponse)
def acao_faturamento_alterar(
    request: Request,
    token: str = Form(""),
    faturamento_id: str = Form(""),
    pedido_id: str = Form(""),
    numero: str = Form(""),
    cliente: str = Form(""),
    total: str = Form(""),
    valor_anterior: str = Form(""),
    novo_valor: str = Form(""),
):
    """PUT /v1/faturamento/{id} — um único PUT por clique.

    Contrato oficial: a URL recebe o ID do FATURAMENTO (não o do pedido);
    o corpo reenvia pedido_id, valor_faturado e data_faturamento. Não executa
    POST de faturamento, DELETE nem o PUT comum de pedidos.
    """
    _auth(request, token)
    fid = (faturamento_id or "").strip()
    pid = (pedido_id or "").strip()
    if not fid or not pid:
        return _wrap_result(
            _card(
                "Faturamento não identificado",
                [
                    (
                        "Ação",
                        "Informe o ID do faturamento (mostrado no cartão do POST de "
                        "faturamento) e o ID Mercos do pedido.",
                    )
                ],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        valor = float(str(novo_valor or "").replace(",", "."))
    except (TypeError, ValueError):
        valor = 0.0
    if valor <= 0:
        return _wrap_result(
            _card(
                "Valor faturado inválido",
                [("Ação", "Informe um novo valor faturado maior que zero.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        out = homolog.alterar_faturamento(fid, pid, valor)
        status = out.get("status_code") or 201
        card = _card(
            "Faturamento alterado",
            [
                ("Status HTTP", status),
                ("ID do pedido", pid),
                ("Número do pedido", (numero or "").strip() or "—"),
                ("Cliente", (cliente or "").strip() or "—"),
                ("Total do pedido", _fmt_valor_2casas(total) if (total or "").strip() else "—"),
                (
                    "Valor faturado anterior",
                    _fmt_valor_2casas(valor_anterior)
                    if (valor_anterior or "").strip()
                    else "—",
                ),
                ("Novo valor faturado", f"{valor:.2f}"),
                ("Status atual", "Faturamento alterado"),
                ("Origem", "Mercos Sandbox"),
            ],
            status_label=f"Status {status}",
            css="ok",
        )
        return _wrap_result(card, entity="pedido", entity_id=pid)
    except MercosApiError as exc:
        mensagem = exc.message or "Não foi possível alterar o faturamento."
        texto = mensagem.lower()
        if "inexistente" in texto or exc.status_code == 404:
            titulo = "Faturamento não encontrado"
        elif "cancelado" in texto:
            titulo = "Pedido cancelado não pode ter faturamento alterado"
        else:
            titulo = "Não foi possível alterar o faturamento"
        return _wrap_result(
            _card(
                titulo,
                [
                    ("Status HTTP", exc.status_code or "—"),
                    ("ID do faturamento", fid),
                    ("Mensagem", mensagem),
                ],
                status_label=f"Erro {exc.status_code or ''}".strip(),
                css="erro",
            )
        )
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


def _numero_documento(valor: str = "") -> str:
    """Número do documento Mercos: obrigatório, máx. 18 caracteres."""
    doc = (valor or "").strip()
    if not doc:
        doc = f"HOMOLOG-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    return doc[:18]


@router.post("/homologacao-ui/acoes/titulos-criar", response_class=HTMLResponse)
def acao_titulos_criar(
    request: Request,
    token: str = Form(""),
    cliente_id: str = Form(""),
    valor: str = Form("100.00"),
    numero_documento: str = Form("HOMOLOG-001"),
):
    _auth(request, token)
    if not (cliente_id or "").strip():
        return _wrap_result(
            _card(
                "Cliente obrigatório",
                [("Ação", "Informe o código do cliente para incluir o título.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        valor_f = float(str(valor or "100").replace(",", "."))
        emissao = date.today().isoformat()
        venc = (date.today() + timedelta(days=30)).isoformat()
        doc = _numero_documento(numero_documento)
        body = {
            "cliente_id": int(cliente_id) if str(cliente_id).isdigit() else cliente_id,
            "valor": round(valor_f, 2),
            "data_emissao": emissao,
            "data_vencimento": venc,
            "numero_documento": doc,
        }
        out = homolog.criar_titulo(body)
        tid = out.get("id") or (out.get("dados") or {}).get("id")
        card = _card(
            "Título criado",
            [
                ("Status", out.get("status_code") or 201),
                ("ID do título", tid),
                ("Número do documento", doc),
                ("Valor", round(valor_f, 2)),
            ],
            status_label=f"Status {out.get('status_code') or 201}",
            css="ok",
        )
        return _wrap_result(card, entity="titulo", entity_id=str(tid or ""))
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/titulos-alterar", response_class=HTMLResponse)
def acao_titulos_alterar(
    request: Request,
    token: str = Form(""),
    titulo_id: str = Form(""),
    valor: str = Form("150.00"),
    numero_documento: str = Form("HOMOLOG-001"),
):
    _auth(request, token)
    tid = (titulo_id or "").strip()
    if not tid:
        return _wrap_result(
            _card(
                "Título não informado",
                [("Ação", "Informe o código do título ou inclua um título antes.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        valor_f = float(str(valor or "150").replace(",", "."))
        venc = (date.today() + timedelta(days=45)).isoformat()
        doc = _numero_documento(numero_documento)
        body = {
            "valor": round(valor_f, 2),
            "data_vencimento": venc,
            "numero_documento": doc,
        }
        out = homolog.alterar_titulo(tid, body)
        card = _card(
            "Título alterado",
            [
                ("Status", out.get("status_code") or 200),
                ("ID do título", tid),
                ("Número do documento", doc),
                ("Valor", round(valor_f, 2)),
            ],
            status_label=f"Status {out.get('status_code') or 200}",
            css="ok",
        )
        return _wrap_result(card, entity="titulo", entity_id=tid)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))
