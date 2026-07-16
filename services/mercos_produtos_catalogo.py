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
        "ciclo": _ciclo_vazio(),
    }


def _ciclo_vazio() -> dict[str, Any]:
    return {
        "ativo": False,
        "etapa_interna": 0,
        "chamadas_completas": 0,
        "chamadas_incrementais": 0,
    }


def _normalizar_ciclo(raw: Any) -> dict[str, Any]:
    base = _ciclo_vazio()
    if not isinstance(raw, dict):
        return base
    base["ativo"] = bool(raw.get("ativo"))
    try:
        etapa = int(raw.get("etapa_interna") or 0)
    except (TypeError, ValueError):
        etapa = 0
    base["etapa_interna"] = max(0, min(3, etapa))
    try:
        base["chamadas_completas"] = max(0, int(raw.get("chamadas_completas") or 0))
    except (TypeError, ValueError):
        base["chamadas_completas"] = 0
    try:
        base["chamadas_incrementais"] = max(
            0, int(raw.get("chamadas_incrementais") or 0)
        )
    except (TypeError, ValueError):
        base["chamadas_incrementais"] = 0
    return base


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


def obter_ciclo(sessao_id: str) -> dict[str, Any]:
    return _normalizar_ciclo(obter(sessao_id).get("ciclo"))


def ciclo_ativo(sessao_id: str) -> bool:
    return bool(obter_ciclo(sessao_id).get("ativo"))


def iniciar_ciclo(sessao_id: str) -> dict[str, Any]:
    """Reinicia ciclo: limpa catálogo/cursor no servidor e define etapa 0."""
    sid = (sessao_id or "").strip()
    if not sid:
        return _estado_vazio()
    estado = _estado_vazio()
    estado["ciclo"] = {
        "ativo": True,
        "etapa_interna": 0,
        "chamadas_completas": 0,
        "chamadas_incrementais": 0,
    }
    with _LOCK:
        _CATALOGOS[sid] = estado
        return deepcopy(estado)


def _salvar_ciclo(sessao_id: str, ciclo: dict[str, Any]) -> dict[str, Any]:
    sid = (sessao_id or "").strip()
    with _LOCK:
        estado = deepcopy(_CATALOGOS.get(sid) or _estado_vazio())
        estado["ciclo"] = _normalizar_ciclo(ciclo)
        _CATALOGOS[sid] = estado
        return deepcopy(estado)


def registrar_sync_ciclo(sessao_id: str, *, tipo: str) -> dict[str, Any]:
    """Avança etapa após sync bem-sucedida (uma etapa por chamada)."""
    ciclo = obter_ciclo(sessao_id)
    if not ciclo.get("ativo"):
        ciclo["ativo"] = True
        ciclo["etapa_interna"] = 0
        ciclo["chamadas_completas"] = 0
        ciclo["chamadas_incrementais"] = 0
    etapa = int(ciclo.get("etapa_interna") or 0)
    if tipo == "completa":
        if etapa != 0:
            raise ValueError(
                "Busca completa bloqueada: o ciclo já passou da etapa inicial."
            )
        ciclo["chamadas_completas"] = int(ciclo.get("chamadas_completas") or 0) + 1
        ciclo["etapa_interna"] = 1
    else:
        if etapa < 1:
            raise ValueError(
                "Busca incremental inválida antes da etapa completa do ciclo."
            )
        ciclo["chamadas_incrementais"] = int(ciclo.get("chamadas_incrementais") or 0) + 1
        if etapa < 3:
            ciclo["etapa_interna"] = etapa + 1
    ciclo["ativo"] = True
    return _salvar_ciclo(sessao_id, ciclo)


def _preservar_ciclo(estado_novo: dict[str, Any], sid: str) -> None:
    with _LOCK:
        prev = _CATALOGOS.get(sid)
        if prev and isinstance(prev.get("ciclo"), dict):
            estado_novo["ciclo"] = _normalizar_ciclo(prev.get("ciclo"))
        elif "ciclo" not in estado_novo:
            estado_novo["ciclo"] = _ciclo_vazio()


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
    _preservar_ciclo(estado, sid)
    with _LOCK:
        # _preservar_ciclo já leu o ciclo; reaplicar sob lock
        prev = _CATALOGOS.get(sid)
        if prev and isinstance(prev.get("ciclo"), dict):
            estado["ciclo"] = _normalizar_ciclo(prev.get("ciclo"))
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
    """Recupera catálogo/ciclo do cliente se o servidor estiver vazio (ex.: após F5)."""
    sid = (sessao_id or "").strip()
    atual = obter(sid)
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

    ciclo_cli = _normalizar_ciclo(payload.get("ciclo"))
    ciclo_srv = _normalizar_ciclo(atual.get("ciclo"))

    produtos_src = payload.get("produtos")
    itens: list[dict] = []
    if isinstance(produtos_src, dict):
        itens = [v for v in produtos_src.values() if isinstance(v, dict)]
    elif isinstance(produtos_src, list):
        itens = [v for v in produtos_src if isinstance(v, dict)]

    meta = (
        payload.get("ultima_sync")
        if isinstance(payload.get("ultima_sync"), dict)
        else None
    )

    # Sem produtos no servidor: restaura do cliente
    if not atual.get("produtos") and itens:
        substituir_completo(sid, itens, meta=meta)
        if ciclo_cli.get("ativo"):
            _salvar_ciclo(sid, ciclo_cli)
        return obter(sid)

    # Servidor sem ciclo ativo, cliente tem: restaura só o ciclo (não reinicia)
    if (not ciclo_srv.get("ativo")) and ciclo_cli.get("ativo"):
        _salvar_ciclo(sid, ciclo_cli)
        if meta:
            with _LOCK:
                estado = deepcopy(_CATALOGOS.get(sid) or _estado_vazio())
                _aplicar_meta(estado, meta)
                if payload.get("ids_ultimo_lote") and not estado.get("ids_ultimo_lote"):
                    estado["ids_ultimo_lote"] = list(payload.get("ids_ultimo_lote") or [])
                _CATALOGOS[sid] = estado
        return obter(sid)

    return obter(sid)


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
        "ciclo": _normalizar_ciclo(estado.get("ciclo")),
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
    "obter_ciclo",
    "ciclo_ativo",
    "iniciar_ciclo",
    "registrar_sync_ciclo",
    "substituir_completo",
    "upsert_incremental",
    "hidratar_se_vazio",
    "buscar_por_nome",
    "lista_produtos",
    "snapshot_cliente",
    "total",
    "_reset_todos_para_testes",
]
