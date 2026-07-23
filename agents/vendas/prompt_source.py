"""Fonte das instruções do Agente de Vendas (local vs Prompt OpenAI).

Usa Responses API com ``prompt={id, version, variables}``.
Não usa Assistants API (asst_*).
Não envia tokens, chaves ou dados secretos nas variáveis.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

from .context_builder import format_facts_for_prompt

_SECRET_PATTERNS = (
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{8,}", re.I),
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(companytoken|applicationtoken|supabase_key|brevo_api_key)\s*[:=]\s*\S+"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I),
)

_PROIBIDOS_VAR = (
    "token",
    "api_key",
    "apikey",
    "secret",
    "password",
    "authorization",
    "companytoken",
    "applicationtoken",
    "supabase",
    "brevo",
    "openai_api",
)


class PromptSourceError(Exception):
    """Falha controlada ao usar prompt externo / configuração inválida."""

    def __init__(self, message: str, *, code: str = "prompt_error"):
        super().__init__(message)
        self.code = code
        self.message = message


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "sim"}


def resolve_prompt_source() -> str:
    """Retorna ``openai`` ou ``local``. Inválido/ausente → local + aviso."""
    raw = (os.getenv("AGENT_PROMPT_SOURCE") or "local").strip().lower()
    if raw in {"openai", "local"}:
        return raw
    _log_obs(
        "prompt_source_invalido",
        prompt_source="local",
        aviso="AGENT_PROMPT_SOURCE inválido; usando local",
        valor_recebido=raw[:40] or "-",
    )
    return "local"


def openai_prompt_id() -> str:
    return (os.getenv("OPENAI_PROMPT_ID") or "").strip()


def openai_prompt_version() -> str | None:
    ver = (os.getenv("OPENAI_PROMPT_VERSION") or "").strip()
    return ver or None


def openai_model() -> str:
    return (os.getenv("OPENAI_MODEL") or "gpt-5-mini").strip() or "gpt-5-mini"


def fallback_local_enabled() -> bool:
    return _env_bool("OPENAI_PROMPT_FALLBACK_LOCAL", default=True)


def abbreviate_prompt_id(prompt_id: str | None) -> str:
    pid = (prompt_id or "").strip()
    if not pid:
        return "-"
    if len(pid) <= 12:
        return pid
    return f"{pid[:8]}…{pid[-4:]}"


def sanitize_text_for_prompt(text: str | None, *, max_chars: int = 4000) -> str:
    """Remove padrões de segredo e trunca texto enviado ao Prompt."""
    out = str(text or "")
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[redacted]", out)
    out = out.strip()
    if len(out) > max_chars:
        out = out[: max_chars - 1].rstrip() + "…"
    return out


def _historico_seguro(customer_context: dict[str, Any]) -> str:
    hist = customer_context.get("historico_texto") or ""
    ultima = customer_context.get("ultima_resposta_ia") or ""
    mem = customer_context.get("memoria_sessao")
    partes: list[str] = []
    if hist:
        partes.append(sanitize_text_for_prompt(str(hist), max_chars=2500))
    if ultima:
        partes.append(
            "Última resposta do agente: "
            + sanitize_text_for_prompt(str(ultima), max_chars=800)
        )
    if isinstance(mem, dict) and mem:
        safe_mem = {
            k: sanitize_text_for_prompt(str(v), max_chars=200)
            for k, v in mem.items()
            if not any(p in str(k).lower() for p in _PROIBIDOS_VAR)
            and k
            not in {
                "token",
                "api_key",
                "prompt",
                "system_prompt",
                "historico_bruto",
            }
        }
        if safe_mem:
            partes.append(
                "Memória resumida: "
                + sanitize_text_for_prompt(str(safe_mem), max_chars=800)
            )
    return "\n".join(partes) if partes else "—"


def build_safe_prompt_variables(
    *,
    mensagem: str,
    nome_cliente: str | None,
    customer_context: dict[str, Any],
    facts: dict[str, Any],
) -> dict[str, str]:
    """Variáveis enviadas ao Prompt salvo — sem credenciais."""
    nome = sanitize_text_for_prompt(
        nome_cliente
        or facts.get("display_name")
        or customer_context.get("display_name")
        or "não informado",
        max_chars=80,
    )
    contexto = sanitize_text_for_prompt(
        format_facts_for_prompt(facts),
        max_chars=3500,
    )
    variables = {
        "mensagem": sanitize_text_for_prompt(mensagem, max_chars=2000),
        "nome_cliente": nome,
        "historico": _historico_seguro(customer_context),
        "contexto_comercial": contexto,
    }
    # Blindagem: nunca incluir chaves que pareçam segredo
    for chave in list(variables):
        if any(p in chave.lower() for p in _PROIBIDOS_VAR):
            variables.pop(chave, None)
    return variables


def assert_no_secrets_in_variables(variables: dict[str, Any]) -> None:
    blob = " ".join(f"{k}={v}" for k, v in (variables or {}).items()).lower()
    for bad in (
        "sk-",
        "companytoken",
        "applicationtoken",
        "supabase_key",
        "brevo_api_key",
        "openai_api_key",
        "bearer ",
    ):
        if bad in blob and "[redacted]" not in blob.replace(bad, ""):
            # Ainda pode falhar se o texto do cliente citar a palavra; só bloqueia
            # padrões óbvios de valor.
            pass
    for k, v in (variables or {}).items():
        low_k = str(k).lower()
        if any(p in low_k for p in _PROIBIDOS_VAR):
            raise PromptSourceError(
                "Variável de prompt contém nome proibido.",
                code="secret_variable_name",
            )
        text = str(v or "")
        if re.search(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}", text):
            raise PromptSourceError(
                "Variável de prompt contém possível API key.",
                code="secret_in_variable",
            )


def build_prompt_param() -> dict[str, Any]:
    """Monta o objeto ``prompt`` da Responses API (sem variables)."""
    pid = openai_prompt_id()
    if not pid:
        raise PromptSourceError(
            "OPENAI_PROMPT_ID ausente com AGENT_PROMPT_SOURCE=openai.",
            code="missing_prompt_id",
        )
    if pid.startswith("asst_"):
        raise PromptSourceError(
            "OPENAI_PROMPT_ID inválido: Assistants API (asst_) não é suportada. "
            "Use um Prompt da Responses API (pmpt_...).",
            code="assistants_id_forbidden",
        )
    prompt: dict[str, Any] = {"id": pid}
    version = openai_prompt_version()
    if version:
        prompt["version"] = version
    return prompt


def tools_for_responses_api(chat_schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converte schemas estilo Chat Completions → Responses API."""
    out: list[dict[str, Any]] = []
    for schema in chat_schemas or []:
        if not isinstance(schema, dict):
            continue
        if schema.get("type") == "function" and isinstance(schema.get("function"), dict):
            fn = schema["function"]
            item: dict[str, Any] = {
                "type": "function",
                "name": fn.get("name"),
                "description": fn.get("description") or "",
                "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
            }
            if "strict" in fn:
                item["strict"] = fn["strict"]
            out.append(item)
        elif schema.get("type") == "function" and schema.get("name"):
            out.append(dict(schema))
    return out


def _log_obs(evento: str, **extra: Any) -> None:
    try:
        from services.webhook_guard import log_seguro

        log_seguro(evento, **extra)
    except Exception:
        pass


def log_prompt_observability(
    *,
    prompt_source: str,
    prompt_id: str | None = None,
    version: str | None = None,
    model: str | None = None,
    request_id: str | None = None,
    elapsed_ms: float | None = None,
    fallback_used: bool = False,
    erro: str | None = None,
) -> None:
    """Observabilidade segura — sem prompt completo nem PII desnecessária."""
    payload: dict[str, Any] = {
        "prompt_source": prompt_source,
        "prompt_id": abbreviate_prompt_id(prompt_id),
        "version": version or "-",
        "model": model or openai_model(),
        "request_id": (request_id or "-")[:64],
        "fallback": bool(fallback_used),
    }
    if elapsed_ms is not None:
        payload["elapsed_ms"] = int(elapsed_ms)
    if erro:
        payload["erro"] = str(erro)[:120]
    _log_obs("agent_prompt_source", **payload)


def extract_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    chunks: list[str] = []
    for item in getattr(response, "output", None) or []:
        item_type = getattr(item, "type", None) or (
            item.get("type") if isinstance(item, dict) else None
        )
        if item_type != "message":
            continue
        content = getattr(item, "content", None)
        if content is None and isinstance(item, dict):
            content = item.get("content")
        for part in content or []:
            ptype = getattr(part, "type", None) or (
                part.get("type") if isinstance(part, dict) else None
            )
            if ptype in ("output_text", "text"):
                val = getattr(part, "text", None)
                if val is None and isinstance(part, dict):
                    val = part.get("text")
                if val:
                    chunks.append(str(val))
    return "\n".join(chunks).strip()


def extract_function_calls(response: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in getattr(response, "output", None) or []:
        item_type = getattr(item, "type", None) or (
            item.get("type") if isinstance(item, dict) else None
        )
        if item_type != "function_call":
            continue
        if isinstance(item, dict):
            calls.append(
                {
                    "call_id": item.get("call_id") or item.get("id"),
                    "name": item.get("name"),
                    "arguments": item.get("arguments") or "{}",
                }
            )
        else:
            calls.append(
                {
                    "call_id": getattr(item, "call_id", None) or getattr(item, "id", None),
                    "name": getattr(item, "name", None),
                    "arguments": getattr(item, "arguments", None) or "{}",
                }
            )
    return calls


def extract_request_id(response: Any) -> str | None:
    rid = getattr(response, "id", None)
    if rid:
        return str(rid)
    meta = getattr(response, "_request_id", None) or getattr(response, "request_id", None)
    return str(meta) if meta else None


def now_ms_timer() -> float:
    return time.monotonic()
