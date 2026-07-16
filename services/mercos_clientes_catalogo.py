"""Catálogo local acumulado de clientes para homologação Mercos (memória por sessão).

Não chama a API Mercos. Usado pela UI de sincronização/localização de clientes.
"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from typing import Any

_LOCK = threading.Lock()
_CATALOGOS: dict[str, dict[str, Any]] = {}


def _ciclo_vazio() -> dict[str, Any]:
    return {
        "ativo": False,
        "etapa_interna": 0,
        "chamadas_completas": 0,
        "chamadas_incrementais": 0,
    }


def _estado_vazio() -> dict[str, Any]:
    return {
        "clientes": {},
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


def _email_de(item: dict) -> Any:
    email = item.get("email")
    if email not in (None, ""):
        return email
    emails = item.get("emails")
    if isinstance(emails, list) and emails:
        primeiro = emails[0]
        if isinstance(primeiro, dict):
            return primeiro.get("email") or primeiro.get("endereco")
        return primeiro
    return None


def _normalizar_cliente(item: dict) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    pid = item.get("id")
    if pid is None or pid == "":
        return None
    out: dict[str, Any] = {
        "id": pid,
        "razao_social": item.get("razao_social") or item.get("nome"),
        "nome_fantasia": item.get("nome_fantasia") or item.get("fantasia"),
        "cnpj": item.get("cnpj"),
        "email": _email_de(item),
        "ultima_alteracao": item.get("ultima_alteracao"),
    }
    if "ativo" in item:
        out["ativo"] = item.get("ativo")
    if "excluido" in item:
        out["excluido"] = item.get("excluido")
    if "bloqueado" in item:
        out["bloqueado"] = item.get("bloqueado")
    for chave in ("tipo", "observacao"):
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
        if etapa < 3:
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
    clientes: dict[str, dict] = {}
    ids_lote: list[str] = []
    for item in itens or []:
        norm = _normalizar_cliente(item) if isinstance(item, dict) else None
        if not norm:
            continue
        chave = str(norm["id"])
        clientes[chave] = norm
        ids_lote.append(chave)
    estado = _estado_vazio()
    estado["clientes"] = clientes
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
            norm = _normalizar_cliente(item) if isinstance(item, dict) else None
            if not norm:
                continue
            chave = str(norm["id"])
            estado["clientes"][chave] = norm
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

    src = payload.get("clientes")
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

    if not atual.get("clientes") and itens:
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


def buscar_por_razao_social(
    sessao_id: str,
    razao_social: str,
) -> tuple[dict[str, Any] | None, bool, dict[str, Any]]:
    estado = obter(sessao_id)
    busca = (razao_social or "").strip()
    if not busca:
        return None, False, estado
    encontrado = None
    for cli in (estado.get("clientes") or {}).values():
        if not isinstance(cli, dict):
            continue
        if str(cli.get("razao_social") or "") == busca:
            encontrado = cli
            break
    if not encontrado:
        return None, False, estado
    no_lote = str(encontrado.get("id")) in set(estado.get("ids_ultimo_lote") or [])
    return deepcopy(encontrado), no_lote, estado


def snapshot_sessao(sessao_id: str) -> dict[str, Any]:
    estado = obter(sessao_id)
    return {
        "clientes": estado.get("clientes") or {},
        "ids_ultimo_lote": estado.get("ids_ultimo_lote") or [],
        "ultima_sync": estado.get("ultima_sync") or {},
        "ciclo": _normalizar_ciclo(estado.get("ciclo")),
        "total": len(estado.get("clientes") or {}),
    }


def total(sessao_id: str) -> int:
    return len(obter(sessao_id).get("clientes") or {})


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
    "buscar_por_razao_social",
    "snapshot_sessao",
    "total",
    "_reset_todos_para_testes",
]
