"""Agente de Vendas da xNamai — coordenação de conversa (OpenAI + tools)."""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from openai import APIStatusError, AsyncOpenAI, OpenAI

from .context_builder import (
    build_template_fallback,
    format_facts_for_prompt,
    gather_customer_facts,
)
from .guardrails import (
    default_safe_handoff,
    detect_blocked_request,
    detect_human_support_request,
    detect_purchase_intent,
    detect_product_inquiry,
    detect_price_inquiry,
    detect_stock_inquiry,
    detect_negotiation,
    detect_compare,
)
from .instructions import build_system_instructions
from .memory import atualizar_memoria, carregar_memoria
from .models import AgentResult, IncomingMessage
from .sales_knowledge import HUMAN_SUPPORT_MESSAGE
from .tools import TOOL_SCHEMAS, execute_tool

MAX_REPLY_CHARS = int(os.getenv("MAX_REPLY_CHARS", "900"))
MAX_TOOL_ROUNDS = 3


def _truncate(text: str, max_chars: int = MAX_REPLY_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _sanitize_log_message(text: str) -> str:
    redacted = re.sub(r"sk-(?:proj-)?[^\s'\"]+", "sk-***", text or "")
    return redacted[:300]


def _openai_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or "").strip()


def _openai_model() -> str:
    return (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()


def build_agent_input(
    message: IncomingMessage,
    customer_context: dict[str, Any],
    facts: dict[str, Any],
) -> str:
    display_name = (
        facts.get("display_name")
        or customer_context.get("display_name")
        or message.sender_name
        or "não informado"
    )
    modality_note = ""
    if message.input_modality == "audio":
        modality_note = "\n- Origem: áudio transcrito para texto"

    return f"""
Mensagem recebida via WhatsApp (xNamai):
- Nome para tratamento: {display_name}
- Telefone presente: {'sim' if message.sender_phone else 'não'}{modality_note}
- Texto do cliente: {message.text}
- Intenção detectada: {facts.get('primary_intent')}
- Estágio da venda: {facts.get('sales_stage')}

{format_facts_for_prompt(facts)}

Responda como Agente de Vendas da xNamai. Não invente dados. Use ferramentas para Mercos/Supabase.
""".strip()


def _fallback_result(message: IncomingMessage, facts: dict[str, Any], *, reason: str) -> AgentResult:
    fallback = build_template_fallback(message, facts) or default_safe_handoff()
    return AgentResult(
        reply_text=fallback,
        intent=str(facts.get("primary_intent") or "geral"),
        handoff_required=reason.startswith("openai") or reason == "blocked",
        safety_reason=reason,
        sales_stage=str(facts.get("sales_stage") or None),
    )


def _detect_preferred_name(text: str) -> str | None:
    m = re.search(
        r"(?:pode\s+me\s+chamar\s+de|me\s+chama(?:r)?\s+de|meu\s+nome\s+(?:é|e)\s+)\s*([A-Za-zÀ-ÿ]{2,40})",
        text or "",
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    return m.group(1).strip().title()


def _maybe_register_lead(telefone: str | None, facts: dict[str, Any], text: str) -> None:
    """Lead apenas com interesse comercial real (não saudação)."""
    intent = str(facts.get("primary_intent") or "")
    sinais = {
        "buscar_produto",
        "consultar_preco",
        "consultar_estoque",
        "comparar_produtos",
        "negociacao",
        "intencao_compra",
        "atendimento_humano",
        "consultar_promocao",
    }
    if intent not in sinais and not (
        detect_product_inquiry(text)
        or detect_price_inquiry(text)
        or detect_stock_inquiry(text)
        or detect_purchase_intent(text)
        or detect_negotiation(text)
        or detect_compare(text)
        or facts.get("orcamento")
    ):
        return
    interesse = intent or "interesse_comercial"
    execute_tool(
        "register_lead",
        {
            "telefone": telefone,
            "interesse": interesse,
            "produto": facts.get("produto_mencionado") or facts.get("ultimo_produto"),
            "orcamento": facts.get("orcamento"),
        },
    )


async def _generate_with_tools(
    message: IncomingMessage,
    customer_context: dict[str, Any],
    facts: dict[str, Any],
) -> AgentResult:
    api_key = _openai_key()
    if not api_key:
        return _fallback_result(message, facts, reason="openai_api_key_missing")

    client = AsyncOpenAI(api_key=api_key)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_instructions()},
        {"role": "user", "content": build_agent_input(message, customer_context, facts)},
    ]
    telefone = message.sender_phone or customer_context.get("telefone")

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            response = await client.chat.completions.create(
                model=_openai_model(),
                messages=messages,
                temperature=0.3,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
            choice = response.choices[0] if response.choices else None
            assistant = choice.message if choice else None
            tool_calls = getattr(assistant, "tool_calls", None) if assistant else None
            if not tool_calls:
                reply = _truncate(
                    (getattr(assistant, "content", None) if assistant else None)
                    or build_template_fallback(message, facts)
                    or default_safe_handoff()
                )
                return AgentResult(
                    reply_text=reply,
                    intent=str(facts.get("primary_intent") or "geral"),
                    sales_stage=str(facts.get("sales_stage") or None),
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": getattr(assistant, "content", None),
                    "tool_calls": [
                        call.model_dump() if hasattr(call, "model_dump") else {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in tool_calls
                    ],
                }
            )
            for call in tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                if call.function.name in (
                    "search_customer",
                    "get_customer",
                    "register_lead",
                    "update_lead",
                    "search_orders",
                ):
                    args["telefone"] = telefone
                result = execute_tool(call.function.name, args)
                data = result.get("data") if isinstance(result, dict) else None
                if isinstance(data, dict) and data.get("handoff"):
                    return AgentResult(
                        reply_text=str(data.get("message") or HUMAN_SUPPORT_MESSAGE),
                        intent="atendimento_humano",
                        handoff_required=True,
                        safety_reason=str(data.get("motivo") or "tool_handoff"),
                        sales_stage="atendimento_humano",
                    )
                # Atualiza produto no contexto se tools retornaram produtos
                if isinstance(data, dict):
                    prods = data.get("products") or []
                    if prods and isinstance(prods[0], dict) and prods[0].get("name"):
                        facts["ultimo_produto"] = prods[0]["name"]
                        facts["produto_mencionado"] = prods[0]["name"]
                    prod = data.get("product")
                    if isinstance(prod, dict) and prod.get("name"):
                        facts["ultimo_produto"] = prod["name"]
                        facts["produto_mencionado"] = prod["name"]
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.function.name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        return AgentResult(
            reply_text="Não consegui concluir a consulta agora. Pode tentar novamente?",
            intent="geral",
            safety_reason="tool_loop_limit",
            sales_stage=str(facts.get("sales_stage") or None),
        )
    except APIStatusError as exc:
        print(
            "[agents.vendas] openai_failed",
            {"status_code": exc.status_code, "message": _sanitize_log_message(str(exc))},
        )
        return _fallback_result(message, facts, reason=f"openai_error_{exc.status_code}")
    except Exception as exc:
        print(
            "[agents.vendas] unexpected_failed",
            {"error_type": type(exc).__name__, "message": _sanitize_log_message(str(exc))},
        )
        return _fallback_result(message, facts, reason="unexpected_error")


def _generate_sync_simple(
    message: IncomingMessage,
    customer_context: dict[str, Any],
    facts: dict[str, Any],
) -> AgentResult:
    api_key = _openai_key()
    if not api_key:
        return _fallback_result(message, facts, reason="openai_api_key_missing")
    client = OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=_openai_model(),
            messages=[
                {"role": "system", "content": build_system_instructions()},
                {"role": "user", "content": build_agent_input(message, customer_context, facts)},
            ],
            temperature=0.3,
        )
    except Exception as exc:
        print(
            "[agents.vendas] sync_openai_failed",
            {"error_type": type(exc).__name__, "message": _sanitize_log_message(str(exc))},
        )
        return _fallback_result(message, facts, reason="openai_sync_failed")
    reply = _truncate(
        (response.choices[0].message.content if response.choices else None)
        or build_template_fallback(message, facts)
        or default_safe_handoff()
    )
    return AgentResult(
        reply_text=reply,
        intent=str(facts.get("primary_intent") or "geral"),
        sales_stage=str(facts.get("sales_stage") or None),
    )


async def gerar_resposta(
    message: IncomingMessage,
    customer_context: dict[str, Any] | None = None,
) -> AgentResult:
    """Gera UMA resposta para a mensagem (guardrails + tools Mercos/Supabase)."""
    ctx = dict(customer_context or {})
    if message.input_modality == "audio" and (
        getattr(message, "transcription_failed", False) or not (message.text or "").strip()
    ):
        from services.audio_service import mensagem_falha_audio

        return AgentResult(
            reply_text=mensagem_falha_audio(),
            intent="audio_transcription_failed",
        )

    blocked = detect_blocked_request(message.text)
    if blocked:
        return AgentResult(
            reply_text=default_safe_handoff(),
            intent="atendimento_humano",
            handoff_required=True,
            safety_reason=blocked,
            sales_stage="atendimento_humano",
        )

    if detect_human_support_request(message.text):
        return AgentResult(
            reply_text=HUMAN_SUPPORT_MESSAGE,
            intent="atendimento_humano",
            handoff_required=True,
            safety_reason="human_support_request",
            sales_stage="atendimento_humano",
        )

    preferred = _detect_preferred_name(message.text)
    if preferred:
        ctx["display_name"] = preferred

    mem = carregar_memoria(message.sender_phone)
    if mem:
        ctx.setdefault("memoria_sessao", mem)
        if mem.get("nome") and not ctx.get("display_name"):
            ctx["display_name"] = mem["nome"]
        if mem.get("interesse_atual"):
            ctx.setdefault("interesse_atual", mem["interesse_atual"])
        if mem.get("produto_mencionado"):
            ctx.setdefault("produto_mencionado", mem["produto_mencionado"])
        if mem.get("ultimo_produto"):
            ctx.setdefault("ultimo_produto", mem["ultimo_produto"])

    facts = gather_customer_facts(message, ctx)

    # Saudação: resposta institucional sem LLM (evita persona errada).
    if facts.get("primary_intent") == "saudacao":
        tpl = build_template_fallback(message, facts)
        if tpl:
            result = AgentResult(
                reply_text=tpl,
                intent="saudacao",
                sales_stage="descoberta",
            )
            atualizar_memoria(
                message.sender_phone,
                nome=ctx.get("display_name") or message.sender_name,
                interesse="saudacao",
                ultima_pergunta=message.text,
                intent="saudacao",
                etapa="descoberta",
                mensagem_cliente=message.text,
                mensagem_agente=result.reply_text,
                message_id=ctx.get("message_id"),
            )
            return result

    # Fallbacks sem OpenAI para intenções simples
    if not _openai_key():
        tpl = build_template_fallback(message, facts)
        if tpl:
            result = AgentResult(
                reply_text=tpl,
                intent=str(facts.get("primary_intent") or "geral"),
                sales_stage=str(facts.get("sales_stage") or None),
                handoff_required=facts.get("primary_intent") == "atendimento_humano",
            )
        else:
            result = _generate_sync_simple(message, ctx, facts)
    else:
        result = await _generate_with_tools(message, ctx, facts)

    _maybe_register_lead(message.sender_phone, facts, message.text)

    atualizar_memoria(
        message.sender_phone,
        nome=ctx.get("display_name") or message.sender_name,
        interesse=facts.get("primary_intent"),
        produto=facts.get("produto_mencionado"),
        orcamento=facts.get("orcamento"),
        quantidade=facts.get("quantidade"),
        ultima_pergunta=message.text,
        intent=result.intent,
        etapa=result.sales_stage or facts.get("sales_stage"),
        ultimo_produto=facts.get("ultimo_produto"),
        mensagem_cliente=message.text,
        mensagem_agente=result.reply_text,
        message_id=ctx.get("message_id"),
    )
    try:
        from services.webhook_guard import log_seguro

        log_seguro(
            "agente_vendas_turno",
            intent=result.intent,
            etapa=result.sales_stage or facts.get("sales_stage") or "-",
            message_id=str(ctx.get("message_id") or "-")[:40],
            telefone=message.sender_phone or "-",
            handoff=bool(result.handoff_required),
        )
    except Exception:
        pass
    return result


async def processar_mensagem(
    mensagem: str,
    telefone: str,
    nome: str | None = None,
    *,
    historico_texto: str = "",
    ultima_resposta_ia: str = "",
    catalogo: str = "",
    memoria_sessao: dict | None = None,
    input_modality: str = "text",
    message_id: str | None = None,
) -> str:
    """Interface pública do Agente de Vendas da xNamai."""
    incoming = IncomingMessage(
        text=(mensagem or "").strip(),
        sender_phone=(telefone or "").strip() or None,
        sender_name=(nome or "").strip() or None,
        input_modality=input_modality or "text",
    )
    customer_context: dict[str, Any] = {
        "display_name": (nome or "").strip() or None,
        "name": (nome or "").strip() or None,
        "telefone": (telefone or "").strip() or None,
        "historico_texto": historico_texto or "",
        "ultima_resposta_ia": ultima_resposta_ia or "",
        "catalogo": catalogo or "",
        "memoria_sessao": memoria_sessao or {},
        "message_id": (message_id or "").strip() or None,
    }
    result = await gerar_resposta(incoming, customer_context)
    return (result.reply_text or "").strip()


def processar_mensagem_sync(
    mensagem: str,
    telefone: str,
    nome: str | None = None,
    **kwargs: Any,
) -> str:
    """Wrapper síncrono para o pipeline WhatsApp atual."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                processar_mensagem(mensagem, telefone, nome, **kwargs),
            )
            return future.result(timeout=90)

    return asyncio.run(processar_mensagem(mensagem, telefone, nome, **kwargs))
