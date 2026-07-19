"""Catálogo local acumulado de pagamentos para homologação Mercos.

Memória por sessão; não chama a API Mercos. Usado pela UI de sincronização e
localização de Pagamento GET (Mercos Pay). Entidade distinta de Condições de
Pagamento, Formas de Pagamento, Faturamento e Títulos. Ciclo de 2 etapas.
"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from typing import Any

_LOCK = threading.Lock()
_CATALOGOS: dict[str, dict[str, Any]] = {}

ETAPA_MAXIMA = 2


def _ciclo_vazio() -> dict[str, Any]:
    return {
        "ativo": False,
        "etapa_interna": 0,
        "chamadas_completas": 0,
        "chamadas_incrementais": 0,
    }


def _estado_vazio() -> dict[str, Any]:
    return {
        "pagamentos": {},
        "ids_ultimo_lote": [],
        "ultima_sync": {
            "tipo": None,
            "cursor_base": None,
            "alterado_apos_enviado": None,
            "novo_cursor": None,
            "total_lote": 0,
            "paginas_lidas": 0,
            "motivo_parada": None,
            "status_sync": None,
            "requisicoes_extras": None,
            "requisicoes_previstas": None,
            "requisicoes_executadas": None,
        },
        "ciclo": _ciclo_vazio(),
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
    base["etapa_interna"] = max(0, min(ETAPA_MAXIMA, etapa))
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


def _normalizar_pagamento(item: dict) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    pid = item.get("id")
    if pid is None or pid == "":
        return None
    out: dict[str, Any] = {
        "id": pid,
        "valor": item.get("valor"),
        "pedido_id": item.get("pedido_id"),
        "cliente_id": item.get("cliente_id"),
        "titulo_id": item.get("titulo_id"),
        "data_criacao": item.get("data_criacao") or item.get("data"),
        "data_expiracao": item.get("data_expiracao"),
        "forma_pagamento": item.get("forma_pagamento"),
        "numero_parcelas": item.get("numero_parcelas"),
        "excluido": item.get("excluido"),
        "ultima_alteracao": item.get("ultima_alteracao"),
    }
    # Nunca persistir token de link de pagamento (não exibir na UI).
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
        if etapa < ETAPA_MAXIMA:
            ciclo["etapa_interna"] = etapa + 1
    ciclo["ativo"] = True
    return _salvar_ciclo(sessao_id, ciclo)


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
        "paginas_lidas",
        "motivo_parada",
        "status_sync",
        "requisicoes_extras",
        "requisicoes_previstas",
        "requisicoes_executadas",
    ):
        if chave in meta:
            sync[chave] = meta[chave]


def substituir_completo(
    sessao_id: str,
    itens: list | None,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sid = (sessao_id or "").strip()
    if not sid:
        return _estado_vazio()
    pagamentos: dict[str, dict] = {}
    ids_lote: list[str] = []
    for item in itens or []:
        norm = _normalizar_pagamento(item) if isinstance(item, dict) else None
        if not norm:
            continue
        chave = str(norm["id"])
        pagamentos[chave] = norm
        ids_lote.append(chave)
    estado = _estado_vazio()
    estado["pagamentos"] = pagamentos
    estado["ids_ultimo_lote"] = ids_lote
    meta_final = dict(meta or {})
    meta_final.setdefault("tipo", "completa")
    meta_final.setdefault("total_lote", len(ids_lote))
    _aplicar_meta(estado, meta_final)
    with _LOCK:
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
    sid = (sessao_id or "").strip()
    if not sid:
        return _estado_vazio()
    with _LOCK:
        estado = deepcopy(_CATALOGOS.get(sid) or _estado_vazio())
        ids_lote: list[str] = []
        for item in itens or []:
            norm = _normalizar_pagamento(item) if isinstance(item, dict) else None
            if not norm:
                continue
            chave = str(norm["id"])
            estado["pagamentos"][chave] = norm
            ids_lote.append(chave)
        estado["ids_ultimo_lote"] = ids_lote
        meta_final = dict(meta or {})
        meta_final.setdefault("tipo", "incremental")
        meta_final.setdefault("total_lote", len(ids_lote))
        _aplicar_meta(estado, meta_final)
        _CATALOGOS[sid] = estado
        return deepcopy(estado)


def hidratar_se_vazio(sessao_id: str, payload: Any) -> dict[str, Any]:
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

    src = payload.get("pagamentos")
    itens: list[dict] = []
    if isinstance(src, dict):
        itens = [v for v in src.values() if isinstance(v, dict)]
    elif isinstance(src, list):
        itens = [v for v in src if isinstance(v, dict)]

    meta = (
        payload.get("ultima_sync")
        if isinstance(payload.get("ultima_sync"), dict)
        else None
    )

    if not atual.get("pagamentos") and itens:
        substituir_completo(sid, itens, meta=meta)
        if ciclo_cli.get("ativo"):
            _salvar_ciclo(sid, ciclo_cli)
        return obter(sid)

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


def buscar_por_id(
    sessao_id: str,
    pagamento_id: str | int,
) -> tuple[dict[str, Any] | None, bool, dict[str, Any]]:
    """Busca no catálogo local pelo ID. Não chama a Mercos."""
    estado = obter(sessao_id)
    chave = str(pagamento_id or "").strip()
    if not chave:
        return None, False, estado
    encontrado = (estado.get("pagamentos") or {}).get(chave)
    if not encontrado:
        # Comparação tolerante a int/str
        for pid, item in (estado.get("pagamentos") or {}).items():
            if str(pid) == chave or str(item.get("id")) == chave:
                encontrado = item
                break
    if not encontrado:
        return None, False, estado
    no_lote = str(encontrado.get("id")) in set(estado.get("ids_ultimo_lote") or [])
    return deepcopy(encontrado), no_lote, estado


def snapshot_sessao(sessao_id: str) -> dict[str, Any]:
    estado = obter(sessao_id)
    return {
        "pagamentos": estado.get("pagamentos") or {},
        "ids_ultimo_lote": estado.get("ids_ultimo_lote") or [],
        "ultima_sync": estado.get("ultima_sync") or {},
        "ciclo": _normalizar_ciclo(estado.get("ciclo")),
        "total": len(estado.get("pagamentos") or {}),
    }


def total(sessao_id: str) -> int:
    return len(obter(sessao_id).get("pagamentos") or {})


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
    "buscar_por_id",
    "snapshot_sessao",
    "total",
    "_reset_todos_para_testes",
]
