"""Contexto compartilhado MCP (carrinho, preferências, sessão)."""

from __future__ import annotations

from services.mcp.types import SessionContext

# Carrinhos por cliente_id (processo)
_carrinhos: dict[str, list[dict]] = {}


def get_carrinho(cliente_id: str) -> list[dict]:
    return list(_carrinhos.get(str(cliente_id), []))


def set_carrinho(cliente_id: str, itens: list[dict]) -> list[dict]:
    _carrinhos[str(cliente_id)] = list(itens)
    return get_carrinho(cliente_id)


def limpar_carrinho(cliente_id: str) -> None:
    _carrinhos.pop(str(cliente_id), None)


def build_session_context(
    *,
    cliente_id: str = "",
    telefone: str = "",
    nome_cliente: str = "",
    historico_texto: str = "",
    mensagem: str = "",
    sessao: dict | None = None,
    caller: str = "rules",
) -> SessionContext:
    cid = str(cliente_id or "")
    ctx = SessionContext(
        cliente_id=cid,
        telefone=telefone or "",
        nome_cliente=nome_cliente or "",
        historico_texto=historico_texto or "",
        mensagem=mensagem or "",
        sessao=dict(sessao or {}),
        caller=caller,
        carrinho=get_carrinho(cid) if cid else [],
        preferencias={
            "nf": (sessao or {}).get("nf"),
            "envio": (sessao or {}).get("envio"),
            "pagamento": (sessao or {}).get("pagamento"),
        },
        dados_confirmados={
            k: (sessao or {}).get(k)
            for k in ("produto_ativo", "preco_cotado", "nf", "envio", "pagamento")
            if (sessao or {}).get(k) not in (None, "")
        },
        historico_resumo=(sessao or {}).get("resumo_curto") or "",
        ultima_intencao=(sessao or {}).get("intencao") or "",
    )
    return ctx


def sync_carrinho_to_store(ctx: SessionContext) -> None:
    if ctx.cliente_id:
        set_carrinho(ctx.cliente_id, ctx.carrinho)
