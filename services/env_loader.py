"""Carrega .env local sem sobrescrever variáveis já definidas (ex.: Render)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

_LOADED = False


def carregar_env() -> None:
    """Idempotente. Em Render não força .env; nunca usa override=True."""
    global _LOADED
    if _LOADED:
        return
    on_render = bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"))
    if not on_render:
        load_dotenv(override=False)
    _LOADED = True
