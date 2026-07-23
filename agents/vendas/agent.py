"""Agente de Vendas da xNamai — coordenação de conversa (OpenAI + tools)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

from openai import APIStatusError, AsyncOpenAI, OpenAI

from .context_builder import (
    build_template_fallback,
    format_facts_for_prompt,
    gather_customer_facts,
    reply_from_preloaded_products,
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
from .prompt_source import (
    PromptSourceError,
    assert_no_secrets_in_variables,
    build_prompt_param,
    build_safe_prompt_variables,
    extract_function_calls,
    extract_request_id,
    extract_response_text,
    fallback_local_enabled,
    log_prompt_observability,
    now_ms_timer,
    openai_model,
    openai_prompt_id,
    openai_prompt_version,
    resolve_prompt_source,
    sanitize_text_for_prompt,
    tools_for_responses_api,
)
from .sales_knowledge import HUMAN_SUPPORT_MESSAGE
from .tools import PRODUCT_TOOLS, TOOL_SCHEMAS, execute_tool

MAX_REPLY_CHARS = int(os.getenv("MAX_REPLY_CHARS", "900"))
MAX_TOOL_ROUNDS = int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "3") or "3")


def _agent_total_timeout() -> float:
    try:
        return max(10.0, float(os.getenv("AGENT_TOTAL_TIMEOUT_SEGUNDOS", "55") or "55"))
    except (TypeError, ValueError):
        return 55.0


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
    return openai_model()


def _log_evento(evento: str, **extra: Any) -> None:
    try:
        from services.webhook_guard import log_seguro

        log_seguro(evento, **extra)
    except Exception:
        pass


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

Responda como Agente de Vendas da xNamai. Não invente dados.
Se houver CATÁLOGO PRÉ-CARREGADO acima, use esses produtos e NÃO chame search_products.
""".strip()


def _fallback_result(message: IncomingMessage, facts: dict[str, Any], *, reason: str) -> AgentResult:
    fallback = (
        reply_from_preloaded_products(facts)
        or build_template_fallback(message, facts)
        or default_safe_handoff()
    )
    return AgentResult(
        reply_text=fallback,
        intent=str(facts.get("primary_intent") or "geral"),
        handoff_required=reason.startswith("openai") or reason == "blocked",
        safety_reason=reason,
        sales_stage=str(facts.get("sales_stage") or None),
    )


def _safe_unavailable_result(facts: dict[str, Any], *, reason: str) -> AgentResult:
    texto = reply_from_preloaded_products(facts)
    if not texto:
        texto = (
            "Não consegui consultar o catálogo agora. "
            "Pode tentar novamente em instantes ou pedir atendimento humano?"
        )
    return AgentResult(
        reply_text=_truncate(texto),
        intent=str(facts.get("primary_intent") or "geral"),
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


def _schemas_for_turn(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """Se o Product Service já trouxe produtos, remove tools de busca Mercos."""
    if facts.get("produtos_precarregados"):
        return [
            schema
            for schema in TOOL_SCHEMAS
            if schema.get("function", {}).get("name") not in PRODUCT_TOOLS
        ]
    return list(TOOL_SCHEMAS)


async def _final_completion_without_tools(
    client: AsyncOpenAI,
    messages: list[dict[str, Any]],
) -> str | None:
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=_openai_model(),
                messages=messages,
                temperature=0.3,
                tool_choice="none",
            ),
            timeout=min(25.0, _agent_total_timeout()),
        )
        choice = response.choices[0] if response.choices else None
        assistant = choice.message if choice else None
        content = getattr(assistant, "content", None) if assistant else None
        return (content or "").strip() or None
    except Exception as exc:
        _log_evento("tool_erro", tool="final_completion", erro=type(exc).__name__)
        return None


async def _generate_with_tools_local(
    message: IncomingMessage,
    customer_context: dict[str, Any],
    facts: dict[str, Any],
    *,
    fallback_from_openai: bool = False,
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
    context_products = list(facts.get("produtos_precarregados") or [])
    tools = _schemas_for_turn(facts)
    started = time.monotonic()
    deadline = started + _agent_total_timeout()
    catalog_tool_failed = False
    t0 = now_ms_timer()

    try:
        for round_idx in range(max(1, MAX_TOOL_ROUNDS)):
            if time.monotonic() >= deadline:
                _log_evento("tool_erro", tool="agent_loop", erro="timeout_total")
                return _safe_unavailable_result(facts, reason="agent_timeout")

            remaining = max(5.0, deadline - time.monotonic())
            create_kwargs: dict[str, Any] = {
                "model": _openai_model(),
                "messages": messages,
                "temperature": 0.3,
            }
            if tools:
                create_kwargs["tools"] = tools
                create_kwargs["tool_choice"] = "auto"
            else:
                create_kwargs["tool_choice"] = "none"

            response = await asyncio.wait_for(
                client.chat.completions.create(**create_kwargs),
                timeout=remaining,
            )
            choice = response.choices[0] if response.choices else None
            assistant = choice.message if choice else None
            tool_calls = getattr(assistant, "tool_calls", None) if assistant else None
            if not tool_calls:
                reply = _truncate(
                    (getattr(assistant, "content", None) if assistant else None)
                    or reply_from_preloaded_products(facts)
                    or build_template_fallback(message, facts)
                    or default_safe_handoff()
                )
                log_prompt_observability(
                    prompt_source="local",
                    model=_openai_model(),
                    request_id=getattr(response, "id", None),
                    elapsed_ms=(now_ms_timer() - t0) * 1000,
                    fallback_used=fallback_from_openai,
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

            force_final = False
            for call in tool_calls:
                if time.monotonic() >= deadline:
                    force_final = True
                    catalog_tool_failed = True
                    break
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

                # Evita segunda busca Mercos quando Product Service já trouxe itens
                ctx_for_tool = context_products if call.function.name in PRODUCT_TOOLS else None
                result = execute_tool(
                    call.function.name,
                    args,
                    context_products=ctx_for_tool,
                )
                data = result.get("data") if isinstance(result, dict) else None
                if isinstance(data, dict) and data.get("handoff"):
                    return AgentResult(
                        reply_text=str(data.get("message") or HUMAN_SUPPORT_MESSAGE),
                        intent="atendimento_humano",
                        handoff_required=True,
                        safety_reason=str(data.get("motivo") or "tool_handoff"),
                        sales_stage="atendimento_humano",
                    )
                if isinstance(data, dict):
                    prods = data.get("products") or []
                    if prods and isinstance(prods[0], dict) and prods[0].get("name"):
                        facts["ultimo_produto"] = prods[0]["name"]
                        facts["produto_mencionado"] = prods[0]["name"]
                    prod = data.get("product")
                    if isinstance(prod, dict) and prod.get("name"):
                        facts["ultimo_produto"] = prod["name"]
                        facts["produto_mencionado"] = prod["name"]

                if (
                    isinstance(result, dict)
                    and not result.get("ok")
                    and call.function.name in PRODUCT_TOOLS
                ):
                    catalog_tool_failed = True
                    # Com produtos no contexto, encerra o loop de tools e responde
                    if context_products:
                        force_final = True

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.function.name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

            if force_final or catalog_tool_failed:
                tools = []  # próxima iteração = resposta final sem tools
                if round_idx >= max(1, MAX_TOOL_ROUNDS) - 1 or force_final:
                    final = await _final_completion_without_tools(client, messages)
                    reply = _truncate(
                        final
                        or reply_from_preloaded_products(facts)
                        or (
                            "Não consegui consultar o catálogo agora. "
                            "Pode tentar novamente em instantes?"
                        )
                    )
                    log_prompt_observability(
                        prompt_source="local",
                        model=_openai_model(),
                        elapsed_ms=(now_ms_timer() - t0) * 1000,
                        fallback_used=fallback_from_openai,
                    )
                    return AgentResult(
                        reply_text=reply,
                        intent=str(facts.get("primary_intent") or "geral"),
                        safety_reason="catalog_tool_failed" if catalog_tool_failed else "force_final",
                        sales_stage=str(facts.get("sales_stage") or None),
                    )

        # Limite de ciclos
        final = await _final_completion_without_tools(client, messages)
        log_prompt_observability(
            prompt_source="local",
            model=_openai_model(),
            elapsed_ms=(now_ms_timer() - t0) * 1000,
            fallback_used=fallback_from_openai,
        )
        return AgentResult(
            reply_text=_truncate(
                final
                or reply_from_preloaded_products(facts)
                or "Não consegui concluir a consulta agora. Pode tentar novamente?"
            ),
            intent="geral",
            safety_reason="tool_loop_limit",
            sales_stage=str(facts.get("sales_stage") or None),
        )
    except asyncio.TimeoutError:
        _log_evento("tool_erro", tool="agent_loop", erro="TimeoutError")
        return _safe_unavailable_result(facts, reason="agent_timeout")
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


async def _generate_with_tools_openai(
    message: IncomingMessage,
    customer_context: dict[str, Any],
    facts: dict[str, Any],
) -> AgentResult:
    """Gera resposta via Responses API + Prompt salvo (OPENAI_PROMPT_ID)."""
    api_key = _openai_key()
    if not api_key:
        raise PromptSourceError("OPENAI_API_KEY ausente.", code="missing_api_key")

    prompt_base = build_prompt_param()
    variables = build_safe_prompt_variables(
        mensagem=message.text,
        nome_cliente=message.sender_name or customer_context.get("display_name"),
        customer_context=customer_context,
        facts=facts,
    )
    assert_no_secrets_in_variables(variables)

    client = AsyncOpenAI(api_key=api_key)
    telefone = message.sender_phone or customer_context.get("telefone")
    context_products = list(facts.get("produtos_precarregados") or [])
    tools_chat = _schemas_for_turn(facts)
    tools = tools_for_responses_api(tools_chat)
    started = time.monotonic()
    deadline = started + _agent_total_timeout()
    catalog_tool_failed = False
    t0 = now_ms_timer()
    previous_response_id: str | None = None
    pending_tool_outputs: list[dict[str, Any]] = []
    last_request_id: str | None = None
    model = _openai_model()

    try:
        for round_idx in range(max(1, MAX_TOOL_ROUNDS)):
            if time.monotonic() >= deadline:
                _log_evento("tool_erro", tool="agent_loop_openai", erro="timeout_total")
                return _safe_unavailable_result(facts, reason="agent_timeout")

            remaining = max(5.0, deadline - time.monotonic())
            kwargs: dict[str, Any] = {"model": model}
            if previous_response_id:
                kwargs["previous_response_id"] = previous_response_id
                kwargs["input"] = pending_tool_outputs
            else:
                prompt_obj = dict(prompt_base)
                prompt_obj["variables"] = variables
                kwargs["prompt"] = prompt_obj
                # Input mínimo: a mensagem já vai em variables; reforça o turno.
                kwargs["input"] = sanitize_text_for_prompt(message.text, max_chars=2000) or "—"

            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            else:
                kwargs["tool_choice"] = "none"

            response = await asyncio.wait_for(
                client.responses.create(**kwargs),
                timeout=remaining,
            )
            last_request_id = extract_request_id(response)
            previous_response_id = getattr(response, "id", None) or previous_response_id
            pending_tool_outputs = []

            function_calls = extract_function_calls(response)
            if not function_calls:
                reply = _truncate(
                    extract_response_text(response)
                    or reply_from_preloaded_products(facts)
                    or build_template_fallback(message, facts)
                    or default_safe_handoff()
                )
                log_prompt_observability(
                    prompt_source="openai",
                    prompt_id=openai_prompt_id(),
                    version=openai_prompt_version(),
                    model=model,
                    request_id=last_request_id,
                    elapsed_ms=(now_ms_timer() - t0) * 1000,
                    fallback_used=False,
                )
                return AgentResult(
                    reply_text=reply,
                    intent=str(facts.get("primary_intent") or "geral"),
                    sales_stage=str(facts.get("sales_stage") or None),
                )

            force_final = False
            for call in function_calls:
                if time.monotonic() >= deadline:
                    force_final = True
                    catalog_tool_failed = True
                    break
                name = str(call.get("name") or "")
                try:
                    args = json.loads(call.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                if name in (
                    "search_customer",
                    "get_customer",
                    "register_lead",
                    "update_lead",
                    "search_orders",
                ):
                    args["telefone"] = telefone

                ctx_for_tool = context_products if name in PRODUCT_TOOLS else None
                result = execute_tool(name, args, context_products=ctx_for_tool)
                data = result.get("data") if isinstance(result, dict) else None
                if isinstance(data, dict) and data.get("handoff"):
                    return AgentResult(
                        reply_text=str(data.get("message") or HUMAN_SUPPORT_MESSAGE),
                        intent="atendimento_humano",
                        handoff_required=True,
                        safety_reason=str(data.get("motivo") or "tool_handoff"),
                        sales_stage="atendimento_humano",
                    )
                if isinstance(data, dict):
                    prods = data.get("products") or []
                    if prods and isinstance(prods[0], dict) and prods[0].get("name"):
                        facts["ultimo_produto"] = prods[0]["name"]
                        facts["produto_mencionado"] = prods[0]["name"]
                    prod = data.get("product")
                    if isinstance(prod, dict) and prod.get("name"):
                        facts["ultimo_produto"] = prod["name"]
                        facts["produto_mencionado"] = prod["name"]

                if (
                    isinstance(result, dict)
                    and not result.get("ok")
                    and name in PRODUCT_TOOLS
                ):
                    catalog_tool_failed = True
                    if context_products:
                        force_final = True

                pending_tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.get("call_id"),
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

            if force_final or catalog_tool_failed:
                tools = []
                if round_idx >= max(1, MAX_TOOL_ROUNDS) - 1 or force_final:
                    # Uma última chamada Responses sem tools, com outputs pendentes.
                    if previous_response_id and pending_tool_outputs:
                        try:
                            final_resp = await asyncio.wait_for(
                                client.responses.create(
                                    model=model,
                                    previous_response_id=previous_response_id,
                                    input=pending_tool_outputs,
                                    tool_choice="none",
                                ),
                                timeout=max(5.0, deadline - time.monotonic()),
                            )
                            last_request_id = extract_request_id(final_resp) or last_request_id
                            final_text = extract_response_text(final_resp)
                        except Exception:
                            final_text = None
                    else:
                        final_text = None
                    reply = _truncate(
                        final_text
                        or reply_from_preloaded_products(facts)
                        or (
                            "Não consegui consultar o catálogo agora. "
                            "Pode tentar novamente em instantes?"
                        )
                    )
                    log_prompt_observability(
                        prompt_source="openai",
                        prompt_id=openai_prompt_id(),
                        version=openai_prompt_version(),
                        model=model,
                        request_id=last_request_id,
                        elapsed_ms=(now_ms_timer() - t0) * 1000,
                        fallback_used=False,
                    )
                    return AgentResult(
                        reply_text=reply,
                        intent=str(facts.get("primary_intent") or "geral"),
                        safety_reason="catalog_tool_failed" if catalog_tool_failed else "force_final",
                        sales_stage=str(facts.get("sales_stage") or None),
                    )

        log_prompt_observability(
            prompt_source="openai",
            prompt_id=openai_prompt_id(),
            version=openai_prompt_version(),
            model=model,
            request_id=last_request_id,
            elapsed_ms=(now_ms_timer() - t0) * 1000,
            fallback_used=False,
        )
        return AgentResult(
            reply_text=_truncate(
                reply_from_preloaded_products(facts)
                or "Não consegui concluir a consulta agora. Pode tentar novamente?"
            ),
            intent="geral",
            safety_reason="tool_loop_limit",
            sales_stage=str(facts.get("sales_stage") or None),
        )
    except asyncio.TimeoutError as exc:
        raise PromptSourceError("Timeout na Responses API.", code="timeout") from exc
    except APIStatusError as exc:
        raise PromptSourceError(
            f"OpenAI HTTP {exc.status_code}",
            code=f"openai_http_{exc.status_code}",
        ) from exc


async def _generate_with_tools(
    message: IncomingMessage,
    customer_context: dict[str, Any],
    facts: dict[str, Any],
) -> AgentResult:
    """Escolhe fonte do prompt (openai Responses vs local instructions)."""
    source = resolve_prompt_source()
    if source != "openai":
        return await _generate_with_tools_local(message, customer_context, facts)

    try:
        return await _generate_with_tools_openai(message, customer_context, facts)
    except PromptSourceError as exc:
        log_prompt_observability(
            prompt_source="openai",
            prompt_id=openai_prompt_id(),
            version=openai_prompt_version(),
            model=_openai_model(),
            fallback_used=False,
            erro=exc.code,
        )
        if fallback_local_enabled():
            log_prompt_observability(
                prompt_source="local",
                prompt_id=openai_prompt_id(),
                version=openai_prompt_version(),
                model=_openai_model(),
                fallback_used=True,
                erro=exc.code,
            )
            # Uma única resposta: só o caminho local após falha externa.
            return await _generate_with_tools_local(
                message,
                customer_context,
                facts,
                fallback_from_openai=True,
            )
        return _fallback_result(message, facts, reason=f"prompt_external_{exc.code}")
    except Exception as exc:
        log_prompt_observability(
            prompt_source="openai",
            prompt_id=openai_prompt_id(),
            version=openai_prompt_version(),
            model=_openai_model(),
            fallback_used=False,
            erro=type(exc).__name__,
        )
        if fallback_local_enabled():
            return await _generate_with_tools_local(
                message,
                customer_context,
                facts,
                fallback_from_openai=True,
            )
        return _fallback_result(message, facts, reason="prompt_external_unexpected")


def _generate_sync_simple(
    message: IncomingMessage,
    customer_context: dict[str, Any],
    facts: dict[str, Any],
) -> AgentResult:
    api_key = _openai_key()
    if not api_key:
        return _fallback_result(message, facts, reason="openai_api_key_missing")
    client = OpenAI(api_key=api_key)
    source = resolve_prompt_source()
    t0 = now_ms_timer()
    try:
        if source == "openai":
            try:
                prompt_obj = build_prompt_param()
                variables = build_safe_prompt_variables(
                    mensagem=message.text,
                    nome_cliente=message.sender_name or customer_context.get("display_name"),
                    customer_context=customer_context,
                    facts=facts,
                )
                assert_no_secrets_in_variables(variables)
                prompt_obj["variables"] = variables
                response = client.responses.create(
                    model=_openai_model(),
                    prompt=prompt_obj,
                    input=sanitize_text_for_prompt(message.text, max_chars=2000) or "—",
                )
                reply = _truncate(
                    extract_response_text(response)
                    or reply_from_preloaded_products(facts)
                    or build_template_fallback(message, facts)
                    or default_safe_handoff()
                )
                log_prompt_observability(
                    prompt_source="openai",
                    prompt_id=openai_prompt_id(),
                    version=openai_prompt_version(),
                    model=_openai_model(),
                    request_id=extract_request_id(response),
                    elapsed_ms=(now_ms_timer() - t0) * 1000,
                    fallback_used=False,
                )
                return AgentResult(
                    reply_text=reply,
                    intent=str(facts.get("primary_intent") or "geral"),
                    sales_stage=str(facts.get("sales_stage") or None),
                )
            except Exception as exc:
                if not fallback_local_enabled():
                    raise
                log_prompt_observability(
                    prompt_source="local",
                    prompt_id=openai_prompt_id(),
                    version=openai_prompt_version(),
                    model=_openai_model(),
                    elapsed_ms=(now_ms_timer() - t0) * 1000,
                    fallback_used=True,
                    erro=type(exc).__name__,
                )
                # cai no bloco local abaixo (uma resposta)

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
        or reply_from_preloaded_products(facts)
        or build_template_fallback(message, facts)
        or default_safe_handoff()
    )
    log_prompt_observability(
        prompt_source="local",
        model=_openai_model(),
        request_id=getattr(response, "id", None),
        elapsed_ms=(now_ms_timer() - t0) * 1000,
        fallback_used=source == "openai",
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
        tpl = (
            reply_from_preloaded_products(facts)
            or build_template_fallback(message, facts)
        )
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
        try:
            result = await asyncio.wait_for(
                _generate_with_tools(message, ctx, facts),
                timeout=_agent_total_timeout() + 5.0,
            )
        except asyncio.TimeoutError:
            result = _safe_unavailable_result(facts, reason="agent_timeout_outer")

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
    _log_evento(
        "resposta_final_gerada",
        intent=result.intent,
        etapa=result.sales_stage or facts.get("sales_stage") or "-",
        message_id=str(ctx.get("message_id") or "-")[:40],
        telefone=message.sender_phone or "-",
        handoff=bool(result.handoff_required),
        chars=len(result.reply_text or ""),
    )
    _log_evento(
        "agente_vendas_turno",
        intent=result.intent,
        etapa=result.sales_stage or facts.get("sales_stage") or "-",
        message_id=str(ctx.get("message_id") or "-")[:40],
        telefone=message.sender_phone or "-",
        handoff=bool(result.handoff_required),
    )
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
    produtos_contexto: list | None = None,
    fonte_produtos: str = "",
) -> str:
    """Interface pública do Agente de Vendas da xNamai."""
    try:
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
            "produtos_contexto": list(produtos_contexto or []),
            "fonte_produtos": (fonte_produtos or "").strip() or None,
        }
        result = await gerar_resposta(incoming, customer_context)
        texto = (result.reply_text or "").strip()
        if not texto:
            texto = (
                "Não consegui concluir o atendimento agora. "
                "Pode tentar novamente ou pedir atendimento humano?"
            )
        return texto
    except Exception as exc:
        _log_evento(
            "tool_erro",
            tool="processar_mensagem",
            erro=type(exc).__name__,
            message_id=(message_id or "-")[:40],
        )
        if produtos_contexto:
            try:
                facts = {"produtos_precarregados": list(produtos_contexto)}
                return reply_from_preloaded_products(facts) or (
                    "Não consegui consultar o catálogo agora. Tente novamente em instantes."
                )
            except Exception:
                pass
        return (
            "Não consegui concluir o atendimento agora. "
            "Pode tentar novamente ou pedir atendimento humano?"
        )
    finally:
        _log_evento(
            "processamento_finalizado",
            message_id=(message_id or "-")[:40],
            telefone=(telefone or "-")[:20],
        )


def processar_mensagem_sync(
    mensagem: str,
    telefone: str,
    nome: str | None = None,
    **kwargs: Any,
) -> str:
    """Wrapper síncrono para o pipeline WhatsApp atual."""
    timeout = _agent_total_timeout() + 10.0
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    try:
        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    processar_mensagem(mensagem, telefone, nome, **kwargs),
                )
                return future.result(timeout=timeout)

        return asyncio.run(processar_mensagem(mensagem, telefone, nome, **kwargs))
    except Exception as exc:
        _log_evento("tool_erro", tool="processar_mensagem_sync", erro=type(exc).__name__)
        produtos = kwargs.get("produtos_contexto") or []
        if produtos:
            try:
                return reply_from_preloaded_products({"produtos_precarregados": list(produtos)}) or (
                    "Não consegui consultar o catálogo agora. Tente novamente em instantes."
                )
            except Exception:
                pass
        return (
            "Não consegui concluir o atendimento agora. "
            "Pode tentar novamente ou pedir atendimento humano?"
        )
    finally:
        _log_evento("processamento_finalizado", origem="sync")
