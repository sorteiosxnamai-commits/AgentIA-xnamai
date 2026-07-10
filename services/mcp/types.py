"""Tipos do protocolo MCP in-process (compatível com contratos JSON do MCP)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: dict | None = None
    stub: bool = False
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "stub": self.stub,
            "meta": self.meta,
        }


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., ToolResult]
    parameters: dict = field(default_factory=dict)  # JSON-schema-like
    required: list[str] = field(default_factory=list)
    write_guard: bool = False
    allowed_callers: set[str] = field(default_factory=lambda: {"rules", "llm", "admin"})
    tags: list[str] = field(default_factory=list)


@dataclass
class SessionContext:
    """Contexto compartilhado entre tools MCP na mesma mensagem."""

    cliente_id: str = ""
    telefone: str = ""
    nome_cliente: str = ""
    historico_texto: str = ""
    mensagem: str = ""
    sessao: dict = field(default_factory=dict)
    caller: str = "rules"  # rules | llm | admin

    # Estado compartilhado mutável
    cliente: dict | None = None
    carrinho: list[dict] = field(default_factory=list)
    produtos_consultados: list[dict] = field(default_factory=list)
    preferencias: dict = field(default_factory=dict)
    dados_confirmados: dict = field(default_factory=dict)
    historico_resumo: str = ""
    ultima_intencao: str = ""
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "cliente_id": self.cliente_id,
            "telefone": self.telefone,
            "nome_cliente": self.nome_cliente,
            "sessao": self.sessao,
            "carrinho": self.carrinho,
            "produtos_consultados": self.produtos_consultados[:10],
            "preferencias": self.preferencias,
            "dados_confirmados": self.dados_confirmados,
            "historico_resumo": self.historico_resumo,
            "ultima_intencao": self.ultima_intencao,
        }
