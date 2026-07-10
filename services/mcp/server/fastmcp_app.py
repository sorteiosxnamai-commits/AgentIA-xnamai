"""
Servidor FastMCP opcional — exporta o registry in-process.

Uso (local):
  MCP_SERVER_ENABLED=true python -m services.mcp.server.fastmcp_app

No Render webhook worker permanece desligado (MCP_SERVER_ENABLED=false).
"""

from __future__ import annotations

import json
import os
import sys


def build_mcp_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit(
            "Pacote 'mcp' não instalado. pip install mcp"
        ) from exc

    from services.mcp import registry
    from services.mcp.context import build_session_context
    from services.mcp.executor import invoke

    app = FastMCP("xnamai-vendas")

    for spec in registry.list_tools():
        # Closure correta por tool
        def _make(name: str, description: str):
            async def _tool(arguments: str = "{}") -> str:
                try:
                    args = json.loads(arguments) if arguments else {}
                except json.JSONDecodeError:
                    args = {}
                ctx = build_session_context(
                    cliente_id=str(args.pop("cliente_id", "") or ""),
                    telefone=str(args.pop("telefone", "") or ""),
                    nome_cliente=str(args.pop("nome_cliente", "") or ""),
                    historico_texto=str(args.pop("historico_texto", "") or ""),
                    mensagem=str(args.pop("mensagem", "") or ""),
                    sessao=args.pop("sessao", {}) if isinstance(args.get("sessao"), dict) else {},
                    caller="admin",
                )
                result = invoke(name, args, ctx)
                return json.dumps(result.to_dict(), ensure_ascii=False)

            _tool.__name__ = name.replace(".", "_")
            _tool.__doc__ = description
            return _tool

        tool_fn = _make(spec.name, spec.description)
        app.tool(name=spec.name, description=spec.description)(tool_fn)

    return app


def main() -> None:
    if os.getenv("MCP_SERVER_ENABLED", "false").strip().lower() not in (
        "1",
        "true",
        "sim",
        "yes",
    ):
        print("MCP_SERVER_ENABLED=false — servidor não iniciado", file=sys.stderr)
        sys.exit(0)
    app = build_mcp_server()
    app.run()


if __name__ == "__main__":
    main()
