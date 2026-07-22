"""Modelos do Agente de Vendas da xNamai."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IncomingMessage:
    text: str = ""
    sender_phone: str | None = None
    sender_name: str | None = None
    input_modality: str = "text"
    transcription_failed: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    reply_text: str
    intent: str = "geral"
    handoff_required: bool = False
    safety_reason: str | None = None
    sales_stage: str | None = None
