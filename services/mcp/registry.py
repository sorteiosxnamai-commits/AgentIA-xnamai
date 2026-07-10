"""Registry centralizado de tools MCP."""

from __future__ import annotations

from services.mcp.types import ToolSpec

_REGISTRY: dict[str, ToolSpec] = {}
_LOADED = False


def register(spec: ToolSpec) -> ToolSpec:
    if not spec.name:
        raise ValueError("ToolSpec.name obrigatório")
    _REGISTRY[spec.name] = spec
    return spec


def get(name: str) -> ToolSpec | None:
    ensure_loaded()
    return _REGISTRY.get(name)


def list_tools() -> list[ToolSpec]:
    ensure_loaded()
    return list(_REGISTRY.values())


def list_names() -> list[str]:
    ensure_loaded()
    return sorted(_REGISTRY.keys())


def clear_registry() -> None:
    global _LOADED
    _REGISTRY.clear()
    _LOADED = False


def ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    # Import side-effect: cada módulo registra suas tools
    from services.mcp import tools as _tools  # noqa: F401

    _tools.load_all()
    _LOADED = True
