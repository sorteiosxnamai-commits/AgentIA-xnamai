"""Serviço de homologação Mercos — entidades da ata beta.

Não altera o agente IA nem CHECKOUT_CREATE_ORDER.
"""

from __future__ import annotations

from typing import Any

from services.mercos_api_client import (
    MercosApiError,
    get_json,
    listar_paginado,
    post_json,
    put_json,
)
from services.mercos_service import mercos_ambiente_sandbox, mercos_configurado

# Paths confirmados no sandbox Xnamai (probe 2026-07-13)
PATHS = {
    "categorias": "/v1/categorias",
    "clientes": "/v1/clientes",
    "condicoes_pagamento": "/v1/condicoes_pagamento",
    "produtos": "/v1/produtos",
    "segmentos": "/v1/segmentos",
    "tabelas_preco": "/v1/tabelas_preco",
    # Não encontrado path listagem global no sandbox; use nested ou MERCOS_PATH_TABELAS_PRECO_PRODUTO
    "tabelas_preco_produto": "/v1/tabelas_preco",
    # Doc Mercos: listagem GET /v1/pedidos/tipo
    "tipos_pedido": "/v1/pedidos/tipo",
    "usuarios": "/v1/usuarios",
    "titulos": "/v1/titulos",
    "pedidos": "/v1/pedidos",
    "pedidos_v2": "/v2/pedidos",
}


def _path(chave: str) -> str:
    import os

    env_key = f"MERCOS_PATH_{chave.upper()}"
    override = os.getenv(env_key, "").strip()
    if override:
        return override if override.startswith("/") else f"/{override}"
    return PATHS[chave]


def inventario_homologacao() -> dict[str, Any]:
    """Status das entidades exigidas na ata."""
    return {
        "sandbox": mercos_ambiente_sandbox(),
        "mercos_configurado": mercos_configurado(),
        "company_token_env": "MERCOS_COMPANY_TOKEN",
        "application_token_env": "MERCOS_APPLICATION_TOKEN",
        "entidades": [
            {"entidade": "Categorias de Produtos", "metodo": "GET", "path": _path("categorias"), "status": "pronto"},
            {"entidade": "Clientes", "metodo": "GET", "path": _path("clientes"), "status": "pronto"},
            {"entidade": "Clientes", "metodo": "POST", "path": _path("clientes"), "status": "pronto"},
            {"entidade": "Clientes", "metodo": "PUT", "path": _path("clientes") + "/{id}", "status": "pronto"},
            {"entidade": "Condições de Pagamento", "metodo": "GET", "path": _path("condicoes_pagamento"), "status": "pronto"},
            {"entidade": "Produtos", "metodo": "GET", "path": _path("produtos"), "status": "pronto"},
            {"entidade": "Segmentos de Clientes", "metodo": "GET", "path": _path("segmentos"), "status": "pronto"},
            {"entidade": "Tabelas de Preço", "metodo": "GET", "path": _path("tabelas_preco"), "status": "pronto"},
            {
                "entidade": "Tabelas de Preço por Produto",
                "metodo": "GET",
                "path": "/v1/tabelas_preco/{id}/produtos (preferencial) ou MERCOS_PATH_TABELAS_PRECO_PRODUTO",
                "status": "rota_local_pronta_path_mercos_a_confirmar",
                "nota": (
                    "Sandbox não expôs listagem global. Use GET /mercos/tabelas-preco/{id}/produtos "
                    "ou defina MERCOS_PATH_TABELAS_PRECO_PRODUTO com o path oficial da Mercos."
                ),
            },
            {
                "entidade": "Tipo de Pedido",
                "metodo": "GET",
                "path": _path("tipos_pedido"),
                "status": "rota_local_pronta_path_mercos_a_confirmar",
                "nota": "Sandbox retornou 404 em /v1/tipos_pedido. Confirmar path com suporte Mercos e setar MERCOS_PATH_TIPOS_PEDIDO.",
            },
            {"entidade": "Usuários", "metodo": "GET", "path": _path("usuarios"), "status": "pronto"},
            {"entidade": "Pedidos", "metodo": "POST", "path": _path("pedidos_v2"), "status": "pronto"},
            {"entidade": "Pedidos", "metodo": "PUT", "path": _path("pedidos") + "/{id}", "status": "pronto"},
            {"entidade": "Títulos", "metodo": "POST", "path": _path("titulos"), "status": "pronto"},
            {"entidade": "Títulos", "metodo": "PUT", "path": _path("titulos") + "/{id}", "status": "pronto"},
            {"entidade": "DELETE", "metodo": "DELETE", "path": "-", "status": "nao_requerido_ata"},
        ],
    }


def listar_categorias(**kw) -> dict:
    return listar_paginado(_path("categorias"), **kw)


def listar_clientes(**kw) -> dict:
    return listar_paginado(_path("clientes"), **kw)


def listar_condicoes_pagamento(**kw) -> dict:
    return listar_paginado(_path("condicoes_pagamento"), **kw)


def listar_produtos(alterado_apos: str | None = None, **kw) -> dict:
    """GET /v1/produtos — repassa alterado_apos à Mercos (sem filtro local)."""
    params_extra = dict(kw.pop("params_extra", None) or {})
    if alterado_apos is not None and str(alterado_apos).strip():
        params_extra["alterado_apos"] = str(alterado_apos).strip()
    if params_extra:
        kw["params_extra"] = params_extra
    data = listar_paginado(_path("produtos"), **kw)
    if "alterado_apos" in params_extra:
        data["filtros"] = {"alterado_apos": params_extra["alterado_apos"]}
    return data


def listar_segmentos(**kw) -> dict:
    return listar_paginado(_path("segmentos"), **kw)


def listar_tabelas_preco(**kw) -> dict:
    return listar_paginado(_path("tabelas_preco"), **kw)


def listar_tabelas_preco_produto(**kw) -> dict:
    """Listagem global (path configurável). Preferir listar_produtos_da_tabela_preco."""
    return listar_paginado(_path("tabelas_preco_produto"), **kw)


def listar_produtos_da_tabela_preco(tabela_id: int | str, **kw) -> dict:
    """GET /v1/tabelas_preco/{id}/produtos — variação comum na API Mercos."""
    path = f"{_path('tabelas_preco').rstrip('/')}/{tabela_id}/produtos"
    return listar_paginado(path, **kw)


# Candidatos sandbox — ordem da ata de homologação (além do env)
# Doc Mercos: GET /api/v1/pedidos/tipo (listagem); GET /api/v1/pedidos/tipo/{id} (item)
CANDIDATOS_TIPOS_PEDIDO = (
    "/v1/pedidos/tipo",
    "/v1/tipos_pedido",
    "/v1/tipos_pedidos",
    "/v1/tipo_pedido",
    "/v1/tipos-de-pedido",
    "/v1/tipos_de_pedido",
    "/v2/tipos_pedido",
    "/v2/tipos_pedidos",
    "/v2/tipo_pedido",
)

_CACHE_PATH_TIPOS_PEDIDO: str | None = None


def caminhos_candidatos_tipos_pedido() -> list[str]:
    """Ordem: MERCOS_PATH_TIPOS_PEDIDO (se setado) + candidatos fixos, sem duplicar."""
    import os

    paths: list[str] = []
    override = os.getenv("MERCOS_PATH_TIPOS_PEDIDO", "").strip()
    if override:
        p = override if override.startswith("/") else f"/{override}"
        paths.append(p)
    for p in CANDIDATOS_TIPOS_PEDIDO:
        if p not in paths:
            paths.append(p)
    return paths


def _probe_status(path: str) -> int | None:
    """GET página 1; retorna status HTTP ou None se falha sem status."""
    from services.mercos_api_client import request_mercos

    try:
        resp = request_mercos("GET", path, params={"pagina": 1})
        return int(resp.status_code)
    except MercosApiError as exc:
        return int(exc.status_code) if exc.status_code else None


def _valor_query_opcional(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return "true" if valor else "false"
    texto = str(valor).strip()
    return texto or None


_PARAMS_INTERNO_TIPOS = frozenset(
    {
        "pagina_inicial",
        "max_paginas",
        "page_size_hint",
        "params_extra",
        "params_mercos",
    }
)


def _kw_filtros_tipos_pedido(
    params_mercos: dict | None = None,
    **kw,
) -> tuple[dict, dict]:
    """Monta kwargs de listar_paginado + mapa dos filtros enviados à Mercos.

    Aceita dict livre em params_mercos e também kwargs nomeados (legado).
    Não faz filtro local — só repassa query params.
    """
    params_extra = dict(kw.pop("params_extra", None) or {})
    filtros: dict[str, str] = {}
    unidos: dict[str, Any] = {}
    if params_mercos:
        unidos.update(params_mercos)

    kwargs_paginacao: dict[str, Any] = {}
    for chave, valor in kw.items():
        if chave in ("pagina_inicial", "max_paginas", "page_size_hint"):
            kwargs_paginacao[chave] = valor
        elif chave in _PARAMS_INTERNO_TIPOS:
            continue
        else:
            unidos[chave] = valor

    for chave, valor in unidos.items():
        normalizado = _valor_query_opcional(valor)
        if normalizado is not None:
            params_extra[str(chave)] = normalizado
            filtros[str(chave)] = normalizado

    if params_extra:
        kwargs_paginacao["params_extra"] = params_extra
    return kwargs_paginacao, filtros

def listar_tipos_pedido(
    params_mercos: dict | None = None,
    **kw,
) -> dict:
    """GET tipos de pedido — path /v1/pedidos/tipo (ou MERCOS_PATH_TIPOS_PEDIDO).

    Repassa query params à Mercos (sem filtro local no Python).
    """
    kw, filtros = _kw_filtros_tipos_pedido(params_mercos=params_mercos, **kw)
    data = listar_paginado(_path("tipos_pedido"), **kw)
    if filtros:
        data["filtros"] = filtros
    return data


def listar_tipos_pedido_descoberta(
    params_mercos: dict | None = None,
    **kw,
) -> dict:
    """Lista Tipo de Pedido tentando paths alternativos até achar HTTP 200.

    Repassa filtros à Mercos via query (não filtra no Python).
    """
    global _CACHE_PATH_TIPOS_PEDIDO

    kw, filtros = _kw_filtros_tipos_pedido(params_mercos=params_mercos, **kw)
    candidatos = caminhos_candidatos_tipos_pedido()
    testados: list[str] = []
    path_ok: str | None = _CACHE_PATH_TIPOS_PEDIDO

    if path_ok and path_ok in candidatos:
        try:
            data = listar_paginado(path_ok, **kw)
            data["path_resolvido"] = path_ok
            data["paths_testados"] = [path_ok]
            data["descoberta"] = True
            if filtros:
                data["filtros"] = filtros
                if "alterado_apos" in filtros:
                    data["alterado_apos"] = filtros["alterado_apos"]
            return data
        except MercosApiError:
            _CACHE_PATH_TIPOS_PEDIDO = None
            path_ok = None

    for path in candidatos:
        testados.append(path)
        status = _probe_status(path)
        if status == 200:
            _CACHE_PATH_TIPOS_PEDIDO = path
            data = listar_paginado(path, **kw)
            data["path_resolvido"] = path
            data["paths_testados"] = list(testados)
            data["descoberta"] = True
            data["status_code"] = 200
            if filtros:
                data["filtros"] = filtros
                if "alterado_apos" in filtros:
                    data["alterado_apos"] = filtros["alterado_apos"]
            return data

    return {
        "ok": False,
        "path": None,
        "path_resolvido": None,
        "paths_testados": testados,
        "total": 0,
        "itens": [],
        "paginas_lidas": 0,
        "sandbox": mercos_ambiente_sandbox(),
        "descoberta": True,
        "status_code": 404,
        "filtros": filtros or None,
        "alterado_apos": (filtros or {}).get("alterado_apos"),
        "mensagem": (
            "Não foi possível localizar o endpoint oficial de Tipo de Pedido no sandbox. "
            f"Paths testados: {', '.join(testados)}"
        ),
    }


COMBINACOES_FILTROS_TIPOS_PEDIDO: tuple[dict[str, str], ...] = (
    {"alterado_apos": "2026-07-14 00:00:00", "excluido": "true"},
    {"alterado_apos": "2026-07-14 00:00:00", "excluido": "1"},
    {"alterado_apos": "2026-07-14 00:00:00", "excluidos": "true"},
    {"alterado_apos": "2026-07-14 00:00:00", "somente_excluidos": "true"},
    {"alterado_apos": "2026-07-14 00:00:00", "incluir_excluidos": "true"},
    {
        "alterado_apos": "2026-07-14 00:00:00",
        "excluido": "true",
        "incluir_excluidos": "true",
    },
)


def explorar_filtros_tipos_pedido(
    combinacoes: tuple[dict[str, str], ...] | list[dict[str, str]] | None = None,
    *,
    max_paginas: int = 3,
) -> dict[str, Any]:
    """Tenta várias combinações de filtro e agrega registros com rótulo do filtro."""
    combos = list(combinacoes or COMBINACOES_FILTROS_TIPOS_PEDIDO)
    por_chave: dict[str, dict[str, Any]] = {}
    tentativas: list[dict[str, Any]] = []

    for combo in combos:
        label = "&".join(f"{k}={v}" for k, v in combo.items())
        try:
            data = listar_tipos_pedido_descoberta(
                params_mercos=combo,
                pagina_inicial=1,
                max_paginas=max_paginas,
            )
        except MercosApiError as exc:
            tentativas.append(
                {
                    "filtro": label,
                    "ok": False,
                    "total": 0,
                    "erro": exc.message[:180],
                }
            )
            continue

        ok = bool(data.get("ok", True)) and data.get("status_code") != 404
        itens = list(data.get("itens") or []) if ok else []
        tentativas.append(
            {
                "filtro": label,
                "ok": ok,
                "total": len(itens),
            }
        )
        if not ok:
            continue
        for item in itens:
            if not isinstance(item, dict):
                continue
            chave = str(item.get("id") or item.get("nome") or item.get("name") or "")
            if not chave:
                continue
            if chave not in por_chave:
                por_chave[chave] = {
                    "item": item,
                    "filtros_encontrados": [label],
                }
            elif label not in por_chave[chave]["filtros_encontrados"]:
                por_chave[chave]["filtros_encontrados"].append(label)

    itens_agregados = []
    for entry in por_chave.values():
        item = dict(entry["item"])
        item["_filtros_encontrados"] = entry["filtros_encontrados"]
        itens_agregados.append(item)

    return {
        "ok": True,
        "descoberta": True,
        "status_code": 200,
        "total": len(itens_agregados),
        "itens": itens_agregados,
        "tentativas": tentativas,
        "sandbox": mercos_ambiente_sandbox(),
    }


def listar_usuarios(**kw) -> dict:
    return listar_paginado(_path("usuarios"), **kw)


def criar_cliente(body: dict) -> dict:
    return post_json(_path("clientes"), body)


def alterar_cliente(cliente_id: int | str, body: dict) -> dict:
    payload = dict(body or {})
    if "id" not in payload:
        payload["id"] = int(cliente_id) if str(cliente_id).isdigit() else cliente_id
    return put_json(f"{_path('clientes')}/{cliente_id}", payload)


def criar_pedido(body: dict) -> dict:
    # Preferência v2 (já usada no projeto)
    return post_json(_path("pedidos_v2"), body)


def alterar_pedido(pedido_id: int | str, body: dict) -> dict:
    """PUT /v1/pedidos/{id} — id só na URL; nunca no JSON (Mercos rejeita extra keys)."""
    payload = dict(body or {})
    payload.pop("id", None)
    return put_json(f"{_path('pedidos')}/{pedido_id}", payload)


def criar_titulo(body: dict) -> dict:
    return post_json(_path("titulos"), body)


def alterar_titulo(titulo_id: int | str, body: dict) -> dict:
    payload = dict(body or {})
    if "id" not in payload:
        payload["id"] = int(titulo_id) if str(titulo_id).isdigit() else titulo_id
    return put_json(f"{_path('titulos')}/{titulo_id}", payload)


def get_um(path: str, params: dict | None = None) -> Any:
    return get_json(path, params=params)


__all__ = [
    "MercosApiError",
    "inventario_homologacao",
    "listar_categorias",
    "listar_clientes",
    "listar_condicoes_pagamento",
    "listar_produtos",
    "listar_segmentos",
    "listar_tabelas_preco",
    "listar_tabelas_preco_produto",
    "listar_produtos_da_tabela_preco",
    "listar_tipos_pedido",
    "listar_tipos_pedido_descoberta",
    "explorar_filtros_tipos_pedido",
    "COMBINACOES_FILTROS_TIPOS_PEDIDO",
    "caminhos_candidatos_tipos_pedido",
    "listar_usuarios",
    "criar_cliente",
    "alterar_cliente",
    "criar_pedido",
    "alterar_pedido",
    "criar_titulo",
    "alterar_titulo",
]
