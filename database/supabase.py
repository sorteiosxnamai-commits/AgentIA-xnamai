"""Cliente Supabase — carrega .env local sem sobrescrever o ambiente (Render)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Em produção (Render), as variáveis já vêm do ambiente.
# override=False garante que .env local NÃO sobrescreve Render/CI.
_on_render = bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"))
if not _on_render:
    load_dotenv(override=False)

import httpx
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions

SUPABASE_URL = os.getenv("SUPABASE_URL")
# Preferir service role no backend (bypassa RLS). Nunca expor no frontend.
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or ""
).strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL e SUPABASE_KEY (ou SUPABASE_SERVICE_ROLE_KEY) são obrigatórios. "
        "Configure no .env (local) ou nas env vars do Render. "
        "No backend do agente use a service_role / secret key — anon sofre RLS."
    )

_http_client = httpx.Client(
    http2=False,
    timeout=httpx.Timeout(30.0, connect=10.0),
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
)

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
    options=SyncClientOptions(
        httpx_client=_http_client,
        postgrest_client_timeout=30,
    ),
)


def supabase_key_kind() -> str:
    """Classificação segura da chave (sem expor o valor)."""
    if SUPABASE_KEY.startswith("eyJ"):
        # JWT legado — não decodificamos o payload aqui
        return "jwt"
    if SUPABASE_KEY.startswith("sb_secret_"):
        return "sb_secret"
    if SUPABASE_KEY.startswith("sb_publishable_") or SUPABASE_KEY.startswith("sb_anon_"):
        return "sb_anon"
    return "other"
