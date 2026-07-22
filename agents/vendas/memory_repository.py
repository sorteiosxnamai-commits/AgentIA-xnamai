"""Persistência da memória comercial em ``clientes.historico`` (Supabase).

Chave preferencial: ``_xnamai_sales_memory``.
Compatível com ``_ns_agent_memory`` (migração lógica, sem apagar).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from services.config_tabelas import CLIENTES_TABLE, mascarar_telefone, normalizar_telefone

_HIST_MEMORY_ROLE = "_xnamai_sales_memory"
_HIST_MEMORY_ROLE_LEGACY = "_ns_agent_memory"
_MAX_MSGS = 80
_LOCK = threading.RLock()
_AVISO_CONVERSAS_EMITIDO = False


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(evento: str, **campos: Any) -> None:
    try:
        from services.webhook_guard import log_seguro

        log_seguro(evento, **campos)
    except Exception:
        print(f"EVT={evento} | " + " | ".join(f"{k}={v}" for k, v in campos.items()))


def avisar_conversas_ausente_uma_vez() -> None:
    global _AVISO_CONVERSAS_EMITIDO
    if _AVISO_CONVERSAS_EMITIDO:
        return
    try:
        from services.config_tabelas import CONVERSAS_TABLE
        from database.supabase import supabase

        supabase.table(CONVERSAS_TABLE).select("id").limit(1).execute()
    except Exception as exc:
        msg = str(exc).lower()
        if "pgrst205" in msg or "does not exist" in msg or "schema cache" in msg:
            _AVISO_CONVERSAS_EMITIDO = True
            _log(
                "aviso_tabela_conversas_ausente",
                tabela=CONVERSAS_TABLE,
                acao="usando_clientes_historico",
                erro=type(exc).__name__,
            )


def _extrair_mensagens(historico_raw: Any) -> list[dict]:
    from services.supabase_service import _mensagens_do_historico_json

    return _mensagens_do_historico_json(historico_raw)


def _extrair_memoria(historico_raw: Any) -> dict[str, Any]:
    """Prefere _xnamai_sales_memory; cai para _ns_agent_memory se necessário."""
    if isinstance(historico_raw, dict):
        mem = historico_raw.get(_HIST_MEMORY_ROLE)
        if isinstance(mem, dict):
            return dict(mem)
        legacy = historico_raw.get(_HIST_MEMORY_ROLE_LEGACY)
        return dict(legacy) if isinstance(legacy, dict) else {}
    if isinstance(historico_raw, list):
        found_legacy: dict[str, Any] = {}
        for item in reversed(historico_raw):
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role == _HIST_MEMORY_ROLE and isinstance(content, dict):
                return dict(content)
            if role == _HIST_MEMORY_ROLE_LEGACY and isinstance(content, dict) and not found_legacy:
                found_legacy = dict(content)
        return found_legacy
    return {}


def _montar_payload(mensagens: list[dict], memoria: dict[str, Any], ctx: dict[str, Any]) -> list:
    from services.supabase_service import _HIST_CTX_ROLE

    limpas = [m for m in mensagens if isinstance(m, dict)][-_MAX_MSGS:]
    out: list[dict] = [
        m
        for m in limpas
        if m.get("role") not in (_HIST_MEMORY_ROLE, _HIST_MEMORY_ROLE_LEGACY, _HIST_CTX_ROLE)
    ]
    if ctx:
        out.append({"role": _HIST_CTX_ROLE, "content": ctx})
    out.append({"role": _HIST_MEMORY_ROLE, "content": memoria})
    return out


def carregar_memoria_persistida(telefone: str | None) -> dict[str, Any]:
    avisar_conversas_ausente_uma_vez()
    tel = normalizar_telefone(telefone or "")
    if not tel:
        return {}
    try:
        from services.supabase_service import buscar_cliente, clientes_tem_historico

        if not clientes_tem_historico():
            return {}
        cliente = buscar_cliente(tel)
        if not cliente:
            return {}
        return _extrair_memoria(cliente.get("historico"))
    except Exception as exc:
        _log("memoria_carga_falhou", telefone=mascarar_telefone(tel), erro=type(exc).__name__)
        return {}


def message_id_no_historico(message_id: str) -> bool:
    mid = (message_id or "").strip()
    if not mid:
        return False
    try:
        from database.supabase import supabase
        from services.supabase_service import clientes_tem_historico

        if not clientes_tem_historico():
            return False
        r = (
            supabase.table(CLIENTES_TABLE)
            .select("historico")
            .order("criado_em", desc=True)
            .limit(40)
            .execute()
        )
        for row in r.data or []:
            for m in _extrair_mensagens(row.get("historico")):
                if str(m.get("message_id") or "") == mid:
                    return True
        return False
    except Exception as exc:
        _log("memoria_check_mid_falhou", erro=type(exc).__name__)
        return False


def persistir_memoria(
    telefone: str | None,
    memoria: dict[str, Any],
    *,
    mensagem_cliente: str | None = None,
    mensagem_agente: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    avisar_conversas_ausente_uma_vez()
    tel = normalizar_telefone(telefone or "")
    if not tel:
        return {"ok": False, "error": "telefone_ausente"}

    with _LOCK:
        try:
            from database.supabase import supabase
            from services.supabase_service import (
                buscar_cliente,
                clientes_tem_historico,
                extrair_contexto_do_historico_json,
            )

            if not clientes_tem_historico():
                return {"ok": False, "error": "sem_coluna_historico"}

            cliente = buscar_cliente(tel)
            if not cliente or not cliente.get("id"):
                _log("memoria_sem_cliente", telefone=mascarar_telefone(tel), acao="somente_cache")
                return {"ok": False, "error": "cliente_inexistente"}

            hist_raw = cliente.get("historico")
            msgs = _extrair_mensagens(hist_raw)
            ctx = extrair_contexto_do_historico_json(hist_raw) or {}
            mem = dict(_extrair_memoria(hist_raw))
            mem.update({k: v for k, v in (memoria or {}).items() if v is not None})
            mem["atualizado_em"] = _agora_iso()
            for proibido in ("token", "api_key", "prompt", "system_prompt"):
                mem.pop(proibido, None)

            if mensagem_cliente:
                entry = {
                    "role": "user",
                    "content": str(mensagem_cliente)[:2000],
                    "timestamp": _agora_iso(),
                }
                if message_id:
                    entry["message_id"] = str(message_id)[:120]
                if not any(
                    isinstance(m, dict)
                    and message_id
                    and m.get("message_id") == message_id
                    for m in msgs
                ):
                    msgs.append(entry)
            if mensagem_agente:
                msgs.append(
                    {
                        "role": "assistant",
                        "content": str(mensagem_agente)[:2000],
                        "timestamp": _agora_iso(),
                    }
                )

            payload = _montar_payload(msgs, mem, ctx if isinstance(ctx, dict) else {})
            supabase.table(CLIENTES_TABLE).update({"historico": payload}).eq(
                "id", cliente["id"]
            ).execute()
            _log(
                "memoria_persistida",
                telefone=mascarar_telefone(tel),
                msgs=len(msgs),
                etapa=mem.get("etapa") or "-",
                message_id=(message_id or "-")[:40],
            )
            return {"ok": True, "error": None}
        except Exception as exc:
            _log(
                "memoria_persist_falhou",
                telefone=mascarar_telefone(tel),
                erro=type(exc).__name__,
            )
            return {"ok": False, "error": type(exc).__name__}
