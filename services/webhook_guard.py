"""Idempotência de webhook e lock por telefone (concorrência)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from services.config_tabelas import mascarar_telefone, normalizar_telefone
from services.webhook_service import (
    _IDS_PROCESSADOS,
    _limpar_ids_antigos,
    extrair_id_mensagem,
)

# msg_id -> "processing" | "done"
_IDS_ESTADO: dict[str, str] = {}
# IDs cujo WhatsApp já foi enviado com sucesso — nunca liberar para retry
_IDS_ENVIADOS: set[str] = set()
_IDS_LOCK = threading.Lock()

# telefone -> lock
_PHONE_LOCKS: dict[str, threading.Lock] = defaultdict(threading.Lock)
_PHONE_META_LOCK = threading.Lock()


def reclamar_mensagem(data: dict) -> tuple[bool, str]:
    """
    Tenta 'claim' do ID da mensagem antes de processar.
    Retorna (ok, motivo). ok=False => duplicado ou já em processamento.
    Memória + banco (message_id em conversas/historico) como fonte final.
    """
    evento = data.get("data") or {}
    msg_id = extrair_id_mensagem(data, evento)
    if not msg_id:
        return True, "sem_id"

    with _IDS_LOCK:
        _limpar_ids_antigos()
        if msg_id in _IDS_ENVIADOS:
            return False, f"ja_enviado id={msg_id}"
        estado = _IDS_ESTADO.get(msg_id)
        if estado == "done" or msg_id in _IDS_PROCESSADOS:
            return False, f"duplicado id={msg_id}"
        if estado == "processing":
            return False, f"em_processamento id={msg_id}"

    # Fonte final: já gravado no Supabase?
    try:
        from services.supabase_service import mensagem_ja_existe

        if mensagem_ja_existe(msg_id):
            with _IDS_LOCK:
                _IDS_ESTADO[msg_id] = "done"
                _IDS_ENVIADOS.add(msg_id)
                _IDS_PROCESSADOS[msg_id] = time.time()
            return False, f"duplicado_banco id={msg_id}"
    except Exception as exc:
        log_seguro("checagem_banco_falhou", message_id=msg_id, erro=type(exc).__name__)

    with _IDS_LOCK:
        if msg_id in _IDS_ENVIADOS:
            return False, f"ja_enviado id={msg_id}"
        estado = _IDS_ESTADO.get(msg_id)
        if estado == "done" or msg_id in _IDS_PROCESSADOS:
            return False, f"duplicado id={msg_id}"
        if estado == "processing":
            return False, f"em_processamento id={msg_id}"
        _IDS_ESTADO[msg_id] = "processing"
        _IDS_PROCESSADOS[msg_id] = time.time()
    return True, f"claim id={msg_id}"


def marcar_envio_concluido(data: dict | None = None, message_id: str | None = None) -> None:
    """Marca message_id como já enviado — nunca libera em finalizar_mensagem."""
    msg_id = (message_id or "").strip()
    if not msg_id and isinstance(data, dict):
        evento = data.get("data") or {}
        msg_id = extrair_id_mensagem(data, evento)
    if not msg_id:
        return
    with _IDS_LOCK:
        _IDS_ENVIADOS.add(msg_id)
        _IDS_ESTADO[msg_id] = "done"
        _IDS_PROCESSADOS[msg_id] = time.time()
    log_seguro("message_id_enviado", message_id=msg_id)


def finalizar_mensagem(data: dict, sucesso: bool = True) -> None:
    evento = data.get("data") or {}
    msg_id = extrair_id_mensagem(data, evento)
    if not msg_id:
        return
    with _IDS_LOCK:
        if msg_id in _IDS_ENVIADOS:
            # Já enviou WhatsApp: nunca liberar para retry (evita resposta duplicada)
            _IDS_ESTADO[msg_id] = "done"
            _IDS_PROCESSADOS[msg_id] = time.time()
            return
        if sucesso:
            _IDS_ESTADO[msg_id] = "done"
            _IDS_PROCESSADOS[msg_id] = time.time()
        else:
            # Libera para retry apenas se ainda não houve envio
            _IDS_ESTADO.pop(msg_id, None)
            _IDS_PROCESSADOS.pop(msg_id, None)


def lock_telefone(telefone: str) -> threading.Lock:
    tel = normalizar_telefone(telefone)
    with _PHONE_META_LOCK:
        return _PHONE_LOCKS[tel]


def log_seguro(evento: str, **campos) -> None:
    partes = [f"EVT={evento}"]
    for k, v in campos.items():
        if k in ("token", "key", "api_key", "authorization"):
            continue
        if k == "telefone":
            partes.append(f"tel={mascarar_telefone(str(v))}")
        else:
            val = str(v)
            if len(val) > 160:
                val = val[:160] + "…"
            partes.append(f"{k}={val}")
    print(" | ".join(partes))
