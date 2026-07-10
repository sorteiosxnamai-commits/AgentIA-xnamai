"""Stubs MCP: frete, crédito, estorno, solicitação (sem backend ERP)."""

from __future__ import annotations

import os

from services.mcp.errors import stub_result
from services.mcp.registry import register
from services.mcp.types import SessionContext, ToolResult, ToolSpec


def _frete(args: dict, ctx: SessionContext) -> ToolResult:
    estimado = os.getenv("FRETE_ESTIMADO", "").strip()
    data = {
        "politica": "Frete/ST confirmados pela equipe após o pedido, com transparência.",
    }
    if estimado:
        try:
            data["frete_estimado"] = float(estimado)
        except ValueError:
            data["frete_estimado_raw"] = estimado
    return stub_result(
        "Cotação automática de frete ainda não integrada ao ERP.",
        policy_ref="xnamai_script",
        data=data,
    )


def _credito(args: dict, ctx: SessionContext) -> ToolResult:
    motivo = args.get("motivo") or ctx.mensagem or ""
    ctx.extras.setdefault("solicitacoes", []).append({"tipo": "credito", "motivo": motivo})
    return stub_result(
        "Crédito é tratado na separação/conferência pela equipe (sem API ERP nesta fase).",
        policy_ref="xnamai_script",
        data={"registrado_intencao": True, "motivo": motivo},
    )


def _estorno(args: dict, ctx: SessionContext) -> ToolResult:
    motivo = args.get("motivo") or ctx.mensagem or ""
    ctx.extras.setdefault("solicitacoes", []).append({"tipo": "estorno", "motivo": motivo})
    return stub_result(
        "Estorno é feito pela equipe no mesmo dia em caso de falta na separação.",
        policy_ref="xnamai_script",
        data={"registrado_intencao": True, "motivo": motivo},
    )


def _solicitacao(args: dict, ctx: SessionContext) -> ToolResult:
    texto = args.get("texto") or ctx.mensagem or ""
    tipo = args.get("tipo") or "geral"
    ctx.extras.setdefault("solicitacoes", []).append({"tipo": tipo, "texto": texto})
    return stub_result(
        "Solicitação anotada no contexto; equipe humana conclui fora do chat se necessário.",
        policy_ref="atendimento",
        data={"registrado_intencao": True, "tipo": tipo},
    )


def register_tools() -> None:
    register(
        ToolSpec(
            name="frete.cotar",
            description="Cotação de frete (stub — política Xnamai)",
            handler=_frete,
            tags=["frete", "stub"],
        )
    )
    register(
        ToolSpec(
            name="credito.registrar",
            description="Registra intenção de crédito (stub)",
            handler=_credito,
            write_guard=True,
            allowed_callers={"rules", "admin"},
            tags=["credito", "stub"],
        )
    )
    register(
        ToolSpec(
            name="estorno.registrar",
            description="Registra intenção de estorno (stub)",
            handler=_estorno,
            write_guard=True,
            allowed_callers={"rules", "admin"},
            tags=["estorno", "stub"],
        )
    )
    register(
        ToolSpec(
            name="solicitacao.registrar",
            description="Registra solicitação genérica no contexto (stub)",
            handler=_solicitacao,
            write_guard=True,
            allowed_callers={"rules", "admin"},
            tags=["solicitacao", "stub"],
        )
    )
