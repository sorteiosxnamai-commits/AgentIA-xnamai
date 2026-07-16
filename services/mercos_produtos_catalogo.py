"""Catálogo local acumulado de produtos para homologação Mercos (memória por sessão).

Não chama a API Mercos. Usado pela UI de sincronização/localização.
"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from typing import Any

_LOCK = threading.Lock()
# sessao_id -> estado do catálogo
_CATALOGOS: dict[str, dict[str, Any]] = {}


def _estado_vazio() -> dict[str, Any]:
    return {
        "produtos": {},  # id_str -> produto normalizado
        "ids_ultimo_lote": [],
        "ultima_sync": {
            "tipo": None,
            "cursor_base": None,
            "alterado_apos_enviado": None,
            "novo_cursor": None,
            "total_lote": 0,
        },
    }


def _normalizar_produto(item: dict) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    pid = item.get("id")
    if pid is None or pid == "":
        return None
    out: dict[str, Any] = {
        "id": pid,
        "nome": item.get("nome"),
        "preco_tabela": item.get("preco_tabela"),
        "ultima_alteracao": item.get("ultima_alteracao"),
    }
    if "ativo" in item:
        out["ativo"] = item.get("ativo")
    if "excluido" in item:
        out["excluido"] = item.get("excluido")
    for chave in ("codigo", "codigo_sku", "sku", "estoque", "saldo_estoque"):
        if chave in item and item[chave] not in (None, ""):
            out[chave] = item[chave]
    return out


def obter(sessao_id: str) -> dict[str, Any]:
    sid = (sessao_id or "").strip()
    if not sid:
        return _estado_vazio()
    with _LOCK:
        atual = _CATALOGOS.get(sid)
        if atual is None:
            return _estado_vazio()
        return deepcopy(atual)


def limpar(sessao_id: str) -> None:
    sid = (sessao_id or "").strip()
    if not sid:
        return
    with _LOCK:
        _CATALOGOS.pop(sid, None)


def _aplicar_meta(estado: dict[str, Any], meta: dict[str, Any] | None) -> None:
    if not meta:
        return
    sync = estado.setdefault("ultima_sync", {})
    for chave in (
        "tipo",
        "cursor_base",
        "alterado_apos_enviado",
        "novo_cursor",
        "total_lote",
    ):
        if chave in meta:
            sync[chave] = meta[chave]


def substituir_completo(
    sessao_id: str,
    itens: list | None,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sincronização completa: substitui o catálogo pelos itens retornados."""
    sid = (sessao_id or "").strip()
    if not sid:
        return _estado_vazio()
    produtos: dict[str, dict] = {}
    ids_lote: list[str] = []
    for item in itens or []:
        norm = _normalizar_produto(item) if isinstance(item, dict) else None
        if not norm:
            continue
        chave = str(norm["id"])
        produtos[chave] = norm
        ids_lote.append(chave)
    estado = _estado_vazio()
    estado["produtos"] = produtos
    estado["ids_ultimo_lote"] = ids_lote
    meta_final = dict(meta or {})
    meta_final.setdefault("tipo", "completa")
    meta_final.setdefault("total_lote", len(ids_lote))
    _aplicar_meta(estado, meta_final)
    with _LOCK:
        _CATALOGOS[sid] = estado
        return deepcopy(estado)


def upsert_incremental(
    sessao_id: str,
    itens: list | None,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Sincronização incremental: atualiza/insere por ID; preserva os demais."""
    sid = (sessao_id or "").strip()
    if not sid:
        return _estado_vazio()
    with _LOCK:
        estado = deepcopy(_CATALOGOS.get(sid) or _estado_vazio())
        ids_lote: list[str] = []
        for item in itens or []:
            norm = _normalizar_produto(item) if isinstance(item, dict) else None
            if not norm:
                continue
            chave = str(norm["id"])
            estado["produtos"][chave] = norm
            ids_lote.append(chave)
        estado["ids_ultimo_lote"] = ids_lote
        meta_final = dict(meta or {})
        meta_final.setdefault("tipo", "incremental")
        meta_final.setdefault("total_lote", len(ids_lote))
        _aplicar_meta(estado, meta_final)
        _CATALOGOS[sid] = estado
        return deepcopy(estado)


def hidratar_se_vazio(
    sessao_id: str,
    payload: Any,
) -> dict[str, Any]:
    """Recupera catálogo do cliente (localStorage) se o servidor estiver vazio."""
    sid = (sessao_id or "").strip()
    atual = obter(sid)
    if atual.get("produtos"):
        return atual
    if payload is None or payload == "":
        return atual
    if isinstance(payload, str):
        texto = payload.strip()
        if not texto:
            return atual
        try:
            payload = json.loads(texto)
        except json.JSONDecodeError:
            return atual
    if not isinstance(payload, dict):
        return atual
    produtos_src = payload.get("produtos")
    itens: list[dict] = []
    if isinstance(produtos_src, dict):
        itens = [v for v in produtos_src.values() if isinstance(v, dict)]
    elif isinstance(produtos_src, list):
        itens = [v for v in produtos_src if isinstance(v, dict)]
    else:
        return atual
    if not itens:
        return atual
    meta = payload.get("ultima_sync") if isinstance(payload.get("ultima_sync"), dict) else None
    # Hidrata como snapshot (não é sync Mercos): substitui só se vazio
    return substituir_completo(sid, itens, meta=meta)


def buscar_por_nome(
    sessao_id: str,
    nome: str,
) -> tuple[dict[str, Any] | None, bool, dict[str, Any]]:
    """Retorna (produto, estava_no_ultimo_lote, estado)."""
    estado = obter(sessao_id)
    nome_busca = (nome or "").strip()
    if not nome_busca:
        return None, False, estado
    encontrado = None
    for prod in (estado.get("produtos") or {}).values():
        if not isinstance(prod, dict):
            continue
        if str(prod.get("nome") or "") == nome_busca:
            encontrado = prod
            break
    if not encontrado:
        return None, False, estado
    no_lote = str(encontrado.get("id")) in set(estado.get("ids_ultimo_lote") or [])
    return deepcopy(encontrado), no_lote, estado


def lista_produtos(sessao_id: str) -> list[dict]:
    estado = obter(sessao_id)
    return list((estado.get("produtos") or {}).values())


def snapshot_cliente(sessao_id: str) -> dict[str, Any]:
    """Formato serializável para localStorage (mercos_produtos_catalogo)."""
    estado = obter(sessao_id)
    return {
        "produtos": estado.get("produtos") or {},
        "ids_ultimo_lote": estado.get("ids_ultimo_lote") or [],
        "ultima_sync": estado.get("ultima_sync") or {},
        "total": len(estado.get("produtos") or {}),
    }


def total(sessao_id: str) -> int:
    return len(obter(sessao_id).get("produtos") or {})


# Helper de testes
def _reset_todos_para_testes() -> None:
    with _LOCK:
        _CATALOGOS.clear()


__all__ = [
    "obter",
    "limpar",
    "substituir_completo",
    "upsert_incremental",
    "hidratar_se_vazio",
    "buscar_por_nome",
    "lista_produtos",
    "snapshot_cliente",
    "total",
    "_reset_todos_para_testes",
]
