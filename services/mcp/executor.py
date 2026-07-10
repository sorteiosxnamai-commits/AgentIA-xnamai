"""Executor MCP: validação, permissões, timeout, retry, logs."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from services.mcp import registry
from services.mcp.errors import MCPError, result_from_exception
from services.mcp.flags import mcp_tool_timeout
from services.mcp.types import SessionContext, ToolResult

_executor_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mcp")


def _validate_params(spec, args: dict) -> None:
    args = args or {}
    for key in spec.required:
        if key not in args or args[key] in (None, ""):
            raise MCPError("invalid_params", f"Parâmetro obrigatório ausente: {key}")
    # Tipos básicos do schema
    props = (spec.parameters or {}).get("properties") or {}
    for key, schema in props.items():
        if key not in args or args[key] is None:
            continue
        expected = schema.get("type")
        val = args[key]
        if expected == "string" and not isinstance(val, str):
            raise MCPError("invalid_params", f"{key} deve ser string")
        if expected == "number" and not isinstance(val, (int, float)):
            raise MCPError("invalid_params", f"{key} deve ser número")
        if expected == "integer" and not isinstance(val, int):
            raise MCPError("invalid_params", f"{key} deve ser inteiro")
        if expected == "object" and not isinstance(val, dict):
            raise MCPError("invalid_params", f"{key} deve ser objeto")
        if expected == "array" and not isinstance(val, list):
            raise MCPError("invalid_params", f"{key} deve ser lista")


def _check_permission(spec, ctx: SessionContext) -> None:
    caller = (ctx.caller if ctx else "rules") or "rules"
    allowed = spec.allowed_callers or {"rules", "llm", "admin"}
    if caller not in allowed:
        raise MCPError(
            "forbidden",
            f"Caller '{caller}' não pode usar {spec.name}",
            public="Operação não permitida neste contexto.",
        )
    if spec.write_guard and caller == "llm":
        raise MCPError(
            "forbidden_write",
            f"Write tool bloqueada para LLM: {spec.name}",
            public="Operação de escrita não disponível via assistente.",
        )


def invoke(
    name: str,
    args: dict | None = None,
    ctx: SessionContext | None = None,
    *,
    timeout: float | None = None,
    retries: int = 1,
) -> ToolResult:
    ctx = ctx or SessionContext()
    args = dict(args or {})
    spec = registry.get(name)
    if not spec:
        return ToolResult(
            ok=False,
            error={"code": "unknown_tool", "message": f"Ferramenta desconhecida: {name}"},
            meta={"tool": name},
        )

    t0 = time.perf_counter()
    try:
        _check_permission(spec, ctx)
        _validate_params(spec, args)
    except Exception as exc:
        result = result_from_exception(exc, name)
        result.meta["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        print(f"MCP {name} ok={result.ok} stub={result.stub} ms={result.meta['latency_ms']}")
        return result

    timeout_s = timeout if timeout is not None else mcp_tool_timeout()
    last_exc: Exception | None = None
    attempts = max(1, retries + 1)

    for attempt in range(attempts):
        try:
            future = _executor_pool.submit(spec.handler, args, ctx)
            result = future.result(timeout=timeout_s)
            if not isinstance(result, ToolResult):
                result = ToolResult(ok=True, data=result)
            result.meta = {
                **(result.meta or {}),
                "tool": name,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "attempt": attempt + 1,
            }
            print(
                f"MCP {name} ok={result.ok} stub={result.stub} "
                f"ms={result.meta['latency_ms']}"
            )
            return result
        except FuturesTimeout:
            last_exc = MCPError("timeout", f"Timeout em {name}", public="A consulta demorou demais.")
            break
        except Exception as exc:
            last_exc = exc
            # Retry só erros de rede genéricos
            transient = type(exc).__name__ in (
                "ConnectError",
                "ReadError",
                "TimeoutException",
                "APIConnectionError",
                "APIError",
            )
            if not transient or attempt >= attempts - 1:
                break
            time.sleep(0.2 * (attempt + 1))

    result = result_from_exception(last_exc or MCPError("tool_error"), name)
    result.meta["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    print(f"MCP {name} ok=False ms={result.meta['latency_ms']}")
    return result


def invoke_many(
    calls: list[dict[str, Any]],
    ctx: SessionContext | None = None,
) -> dict[str, ToolResult]:
    """calls: [{name, args}, ...] — executa sequencialmente (contexto compartilhado)."""
    out: dict[str, ToolResult] = {}
    for call in calls:
        name = call.get("name") or call.get("tool")
        if not name:
            continue
        args = call.get("args") or call.get("arguments") or {}
        out[name] = invoke(name, args, ctx)
    return out
