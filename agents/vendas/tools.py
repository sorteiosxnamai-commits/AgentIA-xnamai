"""Ferramentas comerciais — Mercos + Supabase (sem HTTP direto)."""

from __future__ import annotations

from typing import Any

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Pesquisar produtos reais no catálogo Mercos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product",
            "description": "Obter detalhes de um produto pelo nome/código (Mercos).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": "Confirmar estoque de um produto (Mercos).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_price",
            "description": "Consultar preço de um produto (Mercos).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_promotions",
            "description": "Consultar promoções no catálogo local (não inventa).",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_customer",
            "description": "Consultar cliente pelo telefone desta conversa (Supabase).",
            "parameters": {
                "type": "object",
                "properties": {"telefone": {"type": "string"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer",
            "description": "Alias de search_customer — dados do cliente da conversa.",
            "parameters": {
                "type": "object",
                "properties": {"telefone": {"type": "string"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_orders",
            "description": "Buscar pedidos do cliente (quando disponível no backend).",
            "parameters": {
                "type": "object",
                "properties": {"telefone": {"type": "string"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Detalhe de um pedido (quando disponível).",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "register_lead",
            "description": "Registrar interesse comercial (lead) no Supabase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "telefone": {"type": "string"},
                    "interesse": {"type": "string"},
                    "produto": {"type": "string"},
                    "orcamento": {"type": "string"},
                },
                "required": ["interesse"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_lead",
            "description": "Atualizar lead existente (mesmo fluxo de register_lead sem duplicar).",
            "parameters": {
                "type": "object",
                "properties": {
                    "telefone": {"type": "string"},
                    "interesse": {"type": "string"},
                    "produto": {"type": "string"},
                },
                "required": ["interesse"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_support",
            "description": "Encaminhar para atendimento humano da xNamai.",
            "parameters": {
                "type": "object",
                "properties": {"motivo": {"type": "string"}},
                "additionalProperties": False,
            },
        },
    },
]


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _err(mensagem: str) -> dict[str, Any]:
    safe = (mensagem or "erro_interno")[:180]
    for segredo in ("sk-", "eyJ", "sb_secret_", "Bearer ", "CompanyToken", "ApplicationToken"):
        if segredo in safe:
            safe = "erro_interno"
            break
    return {"ok": False, "data": None, "error": safe}


def _log_tool(nome: str, ok: bool, **extra: Any) -> None:
    try:
        from services.webhook_guard import log_seguro

        log_seguro("agente_tool", tool=nome, ok=ok, **extra)
    except Exception:
        pass


def _reduce_produto(produto: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for chave_src, chave_dst in (
        ("nome", "name"),
        ("codigo", "reference"),
        ("preco", "price"),
        ("estoque", "stock"),
        ("categoria", "category"),
        ("descricao", "description"),
        ("imagem_url", "image_url"),
        ("id", "id"),
    ):
        valor = produto.get(chave_src)
        if valor not in (None, ""):
            out[chave_dst] = valor
    return out


def _search_products(query: str, limit: int = 5) -> dict[str, Any]:
    from services.mercos_service import (
        buscar_produtos_por_termo,
        mercos_configurado,
        montar_catalogo_texto,
    )

    if not mercos_configurado():
        return _err("Mercos não configurada")
    try:
        encontrados = buscar_produtos_por_termo(query or "")
    except Exception as exc:
        return _err(f"falha_consulta_produtos:{type(exc).__name__}")
    limit = max(1, min(int(limit or 5), 5))
    reduzidos = [_reduce_produto(p) for p in (encontrados or [])[:limit]]
    return _ok(
        {
            "products": reduzidos,
            "catalog_text": montar_catalogo_texto(encontrados[:limit]) if encontrados else "",
        }
    )


def _get_product(query: str) -> dict[str, Any]:
    from services.mercos_service import (
        buscar_produto_bruto_por_mensagem,
        mercos_configurado,
        normalizar_produto,
    )

    if not mercos_configurado():
        return _err("Mercos não configurada")
    try:
        bruto = buscar_produto_bruto_por_mensagem(query or "")
    except Exception as exc:
        return _err(f"falha_get_product:{type(exc).__name__}")
    if not bruto:
        return _ok({"found": False, "product": None})
    return _ok({"found": True, "product": _reduce_produto(normalizar_produto(bruto))})


def _check_inventory(query: str) -> dict[str, Any]:
    from services.mercos_service import (
        buscar_produto_bruto_por_mensagem,
        estoque_confirmado,
        mercos_configurado,
        normalizar_produto,
    )

    if not mercos_configurado():
        return _err("Mercos não configurada")
    try:
        bruto = buscar_produto_bruto_por_mensagem(query or "")
    except Exception as exc:
        return _err(f"falha_consulta_estoque:{type(exc).__name__}")
    if not bruto:
        return _ok({"found": False, "products": []})
    normalizado = normalizar_produto(bruto)
    return _ok(
        {
            "found": True,
            "product": _reduce_produto(normalizado),
            "stock_confirmed": estoque_confirmado(bruto),
            "stock_raw": normalizado.get("estoque"),
        }
    )


def _get_product_price(query: str) -> dict[str, Any]:
    out = _get_product(query)
    if not out.get("ok"):
        return out
    data = out.get("data") or {}
    if not data.get("found"):
        return _ok({"found": False, "price": None})
    prod = data.get("product") or {}
    return _ok(
        {
            "found": True,
            "name": prod.get("name"),
            "reference": prod.get("reference"),
            "price": prod.get("price"),
            "product": prod,
        }
    )


def _search_customer(telefone: str | None) -> dict[str, Any]:
    from services.supabase_service import buscar_cliente

    if not (telefone or "").strip():
        return _err("telefone_ausente")
    try:
        cliente = buscar_cliente(telefone)
    except Exception as exc:
        return _err(f"falha_consulta_cliente:{type(exc).__name__}")
    if not cliente:
        return _ok({"found": False})
    return _ok(
        {
            "found": True,
            "id": cliente.get("id"),
            "name": cliente.get("nome") or cliente.get("name"),
            "telefone": cliente.get("telefone") or cliente.get("celular"),
            "mercos_cliente_id": cliente.get("mercos_cliente_id"),
        }
    )


def _lookup_promotions(slug: str | None = None) -> dict[str, Any]:
    if not slug:
        return _ok(
            {
                "promotions": [],
                "note": "Informe o slug para localizar no catálogo local. Não invento promoção.",
            }
        )
    return _ok(
        {
            "promotions": [],
            "slug": slug,
            "note": "Sem promoção confirmada no catálogo local; não invento desconto.",
        }
    )


def _orders_unsupported(kind: str) -> dict[str, Any]:
    return _err(
        f"{kind}_indisponivel: não há tabela de pedidos no backend atual; "
        "encaminhe para atendimento humano se o cliente precisar."
    )


def _register_or_update_lead(
    telefone: str | None,
    interesse: str,
    *,
    produto: str | None = None,
    orcamento: str | None = None,
    update_only: bool = False,
) -> dict[str, Any]:
    from services.supabase_service import buscar_cliente, buscar_lead, criar_lead

    if not (interesse or "").strip():
        return _err("interesse_ausente")
    # Não criar lead só por saudação
    baixo = interesse.strip().lower()
    if baixo in {"saudacao", "saudação", "oi", "ola", "olá", "geral"}:
        return _ok({"skipped": True, "reason": "interesse_insuficiente"})

    interesse_final = interesse.strip()[:180]
    if produto:
        interesse_final = f"{interesse_final} | produto={produto.strip()[:80]}"
    if orcamento:
        interesse_final = f"{interesse_final} | orcamento={orcamento.strip()[:40]}"

    try:
        cliente = buscar_cliente(telefone) if telefone else None
        if not cliente or not cliente.get("id"):
            return _ok(
                {
                    "saved": False,
                    "reason": "cliente_inexistente",
                    "note": "Não crio cadastro automaticamente; interesse guardado só na memória.",
                }
            )
        existente = buscar_lead(cliente["id"], interesse_final)
        if existente:
            return _ok(
                {
                    "saved": False,
                    "updated": False,
                    "duplicado": True,
                    "lead_id": existente.get("id"),
                    "interesse": interesse_final,
                }
            )
        if update_only and not existente:
            # update_lead sem registro prévio: cria uma vez
            pass
        criar_lead(cliente["id"], interesse_final)
        return _ok(
            {
                "saved": True,
                "duplicado": False,
                "interesse": interesse_final,
                "cliente_id": cliente["id"],
            }
        )
    except Exception as exc:
        return _err(f"falha_lead:{type(exc).__name__}")


def _request_human_support(motivo: str | None = None) -> dict[str, Any]:
    from .sales_knowledge import HUMAN_SUPPORT_MESSAGE

    return _ok(
        {
            "handoff": True,
            "message": HUMAN_SUPPORT_MESSAGE,
            "motivo": (motivo or "").strip() or "solicitacao_cliente",
        }
    )


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    args = arguments or {}
    try:
        if name == "search_products":
            out = _search_products(str(args.get("query") or ""), int(args.get("limit") or 5))
        elif name == "get_product":
            out = _get_product(str(args.get("query") or ""))
        elif name == "check_inventory":
            out = _check_inventory(str(args.get("query") or ""))
        elif name == "get_product_price":
            out = _get_product_price(str(args.get("query") or ""))
        elif name == "lookup_promotions":
            out = _lookup_promotions(args.get("slug"))
        elif name in ("search_customer", "get_customer"):
            out = _search_customer(args.get("telefone"))
        elif name == "search_orders":
            out = _orders_unsupported("search_orders")
        elif name == "get_order":
            out = _orders_unsupported("get_order")
        elif name == "register_lead":
            out = _register_or_update_lead(
                args.get("telefone"),
                str(args.get("interesse") or ""),
                produto=args.get("produto"),
                orcamento=args.get("orcamento"),
            )
        elif name == "update_lead":
            out = _register_or_update_lead(
                args.get("telefone"),
                str(args.get("interesse") or ""),
                produto=args.get("produto"),
                update_only=True,
            )
        elif name == "request_human_support":
            out = _request_human_support(args.get("motivo"))
        else:
            out = _err(f"unknown_tool:{name}")
        _log_tool(name, bool(out.get("ok")), erro=out.get("error") or "-")
        return out
    except Exception as exc:
        out = _err(f"tool_failed:{type(exc).__name__}")
        _log_tool(name, False, erro=out["error"])
        return out
