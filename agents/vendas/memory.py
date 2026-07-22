"""Memória do agente de vendas: cache em processo + clientes.historico."""

from __future__ import annotations

import threading
from typing import Any

from agents.vendas.memory_repository import (
    carregar_memoria_persistida,
    persistir_memoria,
)

_LOCK = threading.RLock()
_MEMORIA: dict[str, dict[str, Any]] = {}


def limpar_cache_para_testes() -> None:
    with _LOCK:
        _MEMORIA.clear()


def _chave(telefone: str | None) -> str:
    return (telefone or "").strip()


def carregar_memoria(telefone: str | None) -> dict[str, Any]:
    chave = _chave(telefone)
    if not chave:
        return {}
    with _LOCK:
        if chave in _MEMORIA:
            return dict(_MEMORIA[chave])
    persistida = carregar_memoria_persistida(chave)
    if persistida:
        with _LOCK:
            _MEMORIA[chave] = dict(persistida)
        return dict(persistida)
    return {}


def atualizar_memoria(
    telefone: str | None,
    *,
    nome: str | None = None,
    interesse: str | None = None,
    produto: str | None = None,
    orcamento: str | None = None,
    quantidade: int | None = None,
    ultima_pergunta: str | None = None,
    intent: str | None = None,
    etapa: str | None = None,
    ultimo_produto: str | None = None,
    persistir: bool = True,
    mensagem_cliente: str | None = None,
    mensagem_agente: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    chave = _chave(telefone)
    if not chave:
        return {}
    with _LOCK:
        atual = dict(_MEMORIA.get(chave) or {})
        if nome:
            atual["nome"] = nome.strip()[:120]
        if interesse:
            atual["interesse_atual"] = interesse.strip()[:200]
        if produto:
            atual["produto_mencionado"] = produto.strip()[:200]
        if orcamento:
            atual["orcamento"] = str(orcamento).strip()[:80]
        if quantidade is not None:
            atual["quantidade"] = int(quantidade)
        if ultima_pergunta:
            atual["ultima_pergunta"] = ultima_pergunta.strip()[:400]
        if intent:
            atual["ultima_intencao"] = intent.strip()[:80]
        if etapa:
            atual["etapa"] = etapa.strip()[:80]
            atual["sales_stage"] = etapa.strip()[:80]
        if ultimo_produto:
            atual["ultimo_produto"] = ultimo_produto.strip()[:200]
        _MEMORIA[chave] = atual
        snapshot = dict(atual)

    if persistir:
        try:
            persistir_memoria(
                chave,
                snapshot,
                mensagem_cliente=mensagem_cliente,
                mensagem_agente=mensagem_agente,
                message_id=message_id,
            )
        except Exception:
            pass
    return snapshot
