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
    # Não encontrado no sandbox (404); configure MERCOS_PATH_TIPOS_PEDIDO se a Mercos informar o path
    "tipos_pedido": "/v1/tipos_pedido",
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


def listar_produtos(**kw) -> dict:
    return listar_paginado(_path("produtos"), **kw)


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


def listar_tipos_pedido(**kw) -> dict:
    """Compatível com GET /mercos/tipos-pedido (path único via env/default)."""
    return listar_paginado(_path("tipos_pedido"), **kw)


def listar_tipos_pedido_descoberta(**kw) -> dict:
    """Lista Tipo de Pedido tentando paths alternativos até achar HTTP 200.

    Não altera o comportamento de listar_tipos_pedido (rota JSON antiga).
    """
    global _CACHE_PATH_TIPOS_PEDIDO

    candidatos = caminhos_candidatos_tipos_pedido()
    testados: list[str] = []
    path_ok: str | None = _CACHE_PATH_TIPOS_PEDIDO

    if path_ok and path_ok in candidatos:
        try:
            data = listar_paginado(path_ok, **kw)
            data["path_resolvido"] = path_ok
            data["paths_testados"] = [path_ok]
            data["descoberta"] = True
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
        "mensagem": (
            "Não foi possível localizar o endpoint oficial de Tipo de Pedido no sandbox. "
            f"Paths testados: {', '.join(testados)}"
        ),
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
    "caminhos_candidatos_tipos_pedido",
    "listar_usuarios",
    "criar_cliente",
    "alterar_cliente",
    "criar_pedido",
    "alterar_pedido",
    "criar_titulo",
    "alterar_titulo",
]
