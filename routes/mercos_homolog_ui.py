"""UI visual isolada para evidências de homologação Mercos (prints).

Não altera rotas JSON /mercos/produtos|clientes|pedidos|titulos.
Não cria recursos na abertura da página — só nos POSTs de ação.
"""

from __future__ import annotations

import html
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from services import mercos_homolog_service as homolog
from services.mercos_api_client import MercosApiError
from services.mercos_service import mercos_ambiente_sandbox, mercos_configurado

router = APIRouter(prefix="/mercos", tags=["mercos-homologacao-ui"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_COOKIE = "mercos_homolog_ui"
_COOKIE_MAX_AGE = 60 * 60 * 8


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


def _wrap_result(inner: str, *, entity: str = "", entity_id: str = "") -> HTMLResponse:
    attrs = []
    if entity:
        attrs.append(f'data-entity="{html.escape(entity)}"')
    if entity_id:
        attrs.append(f'data-id="{html.escape(str(entity_id))}"')
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


@router.post("/homologacao-ui/acoes/produtos", response_class=HTMLResponse)
def acao_produtos(request: Request, token: str = Form("")):
    _auth(request, token)
    try:
        data = homolog.listar_produtos(pagina_inicial=1, max_paginas=3)
        rows = []
        for item in data.get("itens") or []:
            rows.append(
                [
                    _campo(item, "id"),
                    _campo(item, "nome", "nome_produto"),
                    _campo(item, "codigo", "codigo_sku", "sku"),
                    _campo(item, "preco", "preco_tabela", "preco_bruto"),
                    _campo(item, "estoque", "saldo_estoque", "quantidade_estoque"),
                    _fmt_bool(_campo(item, "ativo", "excluido", default=None)),
                ]
            )
        # ativo: se veio excluido=True, inverter rótulo na coluna Ativo
        fixed = []
        for item, row in zip(data.get("itens") or [], rows):
            if "excluido" in item and "ativo" not in item:
                row[5] = "Não" if item.get("excluido") else "Sim"
            fixed.append(row)
        table = _table(
            ["ID", "Nome", "Código", "Preço", "Estoque", "Ativo"],
            fixed or rows,
        )
        head = (
            f'<p class="meta">Total: <strong>{_esc(data.get("total", 0))}</strong> · '
            f'Status: <strong>200</strong></p>'
        )
        return _wrap_result(head + table)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


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
def acao_clientes_buscar(request: Request, token: str = Form("")):
    _auth(request, token)
    try:
        data = homolog.listar_clientes(pagina_inicial=1, max_paginas=3)
        rows = [
            [
                _campo(i, "id"),
                _campo(i, "razao_social", "nome"),
                _campo(i, "nome_fantasia", "fantasia"),
                _campo(i, "email"),
            ]
            for i in (data.get("itens") or [])
        ]
        table = _table(["ID", "Razão Social", "Nome Fantasia", "Email"], rows)
        head = f'<p class="meta">Total: <strong>{_esc(data.get("total", 0))}</strong> · Status: <strong>200</strong></p>'
        return _wrap_result(head + table)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/clientes-criar", response_class=HTMLResponse)
def acao_clientes_criar(request: Request, token: str = Form("")):
    _auth(request, token)
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        body = {
            "razao_social": f"Homolog Xnamai {stamp}",
            "nome_fantasia": f"Homolog {stamp}",
            "email": f"homolog.{stamp}@xnamai.test",
            "tipo": "J",
        }
        out = homolog.criar_cliente(body)
        cid = out.get("id") or (out.get("dados") or {}).get("id")
        card = _card(
            "Cliente criado",
            [
                ("Status", out.get("status_code") or 201),
                ("ID criado", cid),
                ("Razão social", body["razao_social"]),
                ("Email", body["email"]),
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
):
    _auth(request, token)
    cid = (cliente_id or "").strip()
    if not cid:
        return _wrap_result(
            _card(
                "Cliente não informado",
                [("Ação", "Informe o ID do cliente ou crie um cliente antes.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        body = {
            "nome_fantasia": f"Homolog Alterado {stamp}",
            "observacao": f"Alteração homologação visual Xnamai em {_agora_br()}",
        }
        out = homolog.alterar_cliente(cid, body)
        card = _card(
            "Cliente alterado",
            [
                ("Status", out.get("status_code") or 200),
                ("ID alterado", cid),
                ("Nome fantasia", body["nome_fantasia"]),
                ("Observação", body["observacao"]),
            ],
            status_label=f"Status {out.get('status_code') or 200}",
            css="ok",
        )
        return _wrap_result(card, entity="cliente", entity_id=cid)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/condicoes", response_class=HTMLResponse)
def acao_condicoes(request: Request, token: str = Form("")):
    _auth(request, token)
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


@router.post("/homologacao-ui/acoes/tipos-pedido", response_class=HTMLResponse)
def acao_tipos_pedido(
    request: Request,
    token: str = Form(""),
    alterado_apos: str = Form(""),
    excluidos: str = Form(""),
    somente_excluidos: str = Form(""),
    incluir_excluidos: str = Form(""),
):
    _auth(request, token)
    filtro_alterado = (alterado_apos or "").strip()
    filtro_excluidos = (excluidos or "").strip()
    filtro_somente = (somente_excluidos or "").strip()
    filtro_incluir = (incluir_excluidos or "").strip()
    try:
        data = homolog.listar_tipos_pedido_descoberta(
            pagina_inicial=1,
            max_paginas=5,
            alterado_apos=filtro_alterado or None,
            excluidos=filtro_excluidos or None,
            somente_excluidos=filtro_somente or None,
            incluir_excluidos=filtro_incluir or None,
        )
        if not data.get("ok", True) or data.get("status_code") == 404:
            paths = data.get("paths_testados") or []
            msg = data.get("mensagem") or (
                "Não foi possível localizar o endpoint oficial de Tipo de Pedido no sandbox. "
                f"Paths testados: {', '.join(paths)}"
            )
            return _wrap_result(
                _card(
                    "Tipo de Pedido",
                    [("Situação", msg)],
                    status_label="Pendente",
                    css="pendente",
                )
            )

        rows = []
        classes: list[str] = []
        for item in data.get("itens") or []:
            nome = _campo(item, "nome", "name", "descricao", default="")
            nome_str = "" if nome == "—" else str(nome)
            rows.append(
                [
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
            )
            nome_l = nome_str.lower()
            destaque = (
                nome_l.startswith("19814a3")
                or nome_l.startswith("198314a3")
                or nome_l.startswith("0832f68")
                or nome_l.startswith("8df21d6c")
            )
            classes.append("destaque-homolog" if destaque else "")

        table = _table(
            ["ID", "Nome", "Excluído", "Última alteração"],
            rows,
            empty_msg="Endpoint encontrado, porém sem tipos de pedido cadastrados.",
            row_classes=classes,
        )
        filtros = dict(data.get("filtros") or {})
        if filtro_alterado and "alterado_apos" not in filtros:
            filtros["alterado_apos"] = filtro_alterado
        if filtro_excluidos and "excluidos" not in filtros:
            filtros["excluidos"] = filtro_excluidos
        head_parts = [
            "Status: <strong>200</strong>",
            f'Total: <strong>{_esc(data.get("total", 0))}</strong>',
        ]
        if filtros.get("alterado_apos") or filtros.get("excluidos"):
            partes_filtro = []
            if filtros.get("alterado_apos"):
                partes_filtro.append(
                    f'alterado_apos = <strong>{_esc(filtros["alterado_apos"])}</strong>'
                )
            if filtros.get("excluidos"):
                partes_filtro.append(
                    f'excluídos = <strong>{_esc(filtros["excluidos"])}</strong>'
                )
            head_parts.append("Filtro usado: " + " | ".join(partes_filtro))
        head = f'<p class="meta">{" · ".join(head_parts)}</p>'
        return _wrap_result(head + table)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/usuarios", response_class=HTMLResponse)
def acao_usuarios(request: Request, token: str = Form("")):
    _auth(request, token)
    try:
        data = homolog.listar_usuarios(pagina_inicial=1, max_paginas=3)
        rows = [
            [
                _campo(i, "id"),
                _campo(i, "nome", "name"),
                _campo(i, "email"),
                _fmt_bool(_campo(i, "administrador", "admin", "is_admin", default="—")),
            ]
            for i in (data.get("itens") or [])
        ]
        table = _table(["ID", "Nome", "Email", "Administrador"], rows)
        head = f'<p class="meta">Total: <strong>{_esc(data.get("total", 0))}</strong> · Status: <strong>200</strong></p>'
        return _wrap_result(head + table)
    except Exception as exc:
        return _wrap_result(_erro_html(exc))


@router.post("/homologacao-ui/acoes/pedidos-criar", response_class=HTMLResponse)
def acao_pedidos_criar(
    request: Request,
    token: str = Form(""),
    cliente_id: str = Form(""),
    produto_id: str = Form(""),
    quantidade: str = Form("1"),
    preco: str = Form("10.00"),
    condicao_pagamento_id: str = Form(""),
):
    _auth(request, token)
    if not (cliente_id or "").strip() or not (produto_id or "").strip():
        return _wrap_result(
            _card(
                "Campos obrigatórios",
                [("Ação", "Informe o código do cliente e do produto.")],
                status_label="Pendente",
                css="pendente",
            )
        )
    try:
        qtd = float(quantidade or "1")
        preco_f = float(str(preco or "10").replace(",", "."))
        body: dict[str, Any] = {
            "cliente_id": int(cliente_id) if str(cliente_id).isdigit() else cliente_id,
            "data_emissao": date.today().isoformat(),
            "observacoes": f"Pedido homologação visual Xnamai {_agora_br()}",
            "itens": [
                {
                    "produto_id": int(produto_id) if str(produto_id).isdigit() else produto_id,
                    "quantidade": qtd,
                    "preco_tabela": round(preco_f, 2),
                }
            ],
        }
        if (condicao_pagamento_id or "").strip():
            cid_pag = condicao_pagamento_id.strip()
            body["condicao_pagamento_id"] = int(cid_pag) if cid_pag.isdigit() else cid_pag
        else:
            body["condicao_pagamento"] = "a vista"

        out = homolog.criar_pedido(body)
        pid = out.get("id") or (out.get("dados") or {}).get("id")
        numero = (out.get("dados") or {}).get("numero") or "—"
        card = _card(
            "Pedido criado",
            [
                ("Status", out.get("status_code") or 201),
                ("ID do pedido", pid),
                ("Número do pedido", numero),
                ("Cliente", cliente_id),
                ("Produto", produto_id),
                ("Quantidade", qtd),
                ("Preço", round(preco_f, 2)),
            ],
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
