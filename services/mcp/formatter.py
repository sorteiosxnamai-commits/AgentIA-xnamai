"""Formata resultados MCP para o prompt da IA."""

from __future__ import annotations

import json

from services.mcp.types import ToolResult


def para_prompt(resultados: dict[str, ToolResult], *, max_chars: int = 3500) -> str:
    if not resultados:
        return ""

    blocos = []
    for nome, res in resultados.items():
        payload = res.to_dict() if hasattr(res, "to_dict") else res
        # Não vazar meta.internal
        if isinstance(payload, dict) and isinstance(payload.get("meta"), dict):
            meta = dict(payload["meta"])
            meta.pop("internal", None)
            payload = {**payload, "meta": meta}
        texto = json.dumps({nome: payload}, ensure_ascii=False, indent=2)
        blocos.append(texto)

    junto = "\n".join(blocos)
    if len(junto) > max_chars:
        junto = junto[: max_chars - 20] + "\n…(truncado)"
    return (
        "=== RESULTADOS MCP (fonte de verdade; não invente além disso) ===\n"
        + junto
    )
