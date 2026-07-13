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

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
_SERVICE_ROLE = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
_FALLBACK_KEY = (os.getenv("SUPABASE_KEY") or "").strip()
# Preferir service role no backend (bypassa RLS). Nunca expor no frontend.
SUPABASE_KEY = _SERVICE_ROLE or _FALLBACK_KEY

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


def supabase_key_source() -> str:
    """Origem da chave usada pelo client (sem expor o valor).

    service_role  → SUPABASE_SERVICE_ROLE_KEY definida (preferencial)
    fallback_key  → só SUPABASE_KEY (pode ser secret, anon ou publishable)
    missing       → nenhuma chave
    """
    if _SERVICE_ROLE:
        return "service_role"
    if _FALLBACK_KEY:
        return "fallback_key"
    return "missing"


def supabase_key_kind() -> str:
    """Classificação segura do formato da chave (sem expor o valor)."""
    if not SUPABASE_KEY:
        return "missing"
    if SUPABASE_KEY.startswith("eyJ"):
        # JWT legado — role está no payload; não decodificamos aqui
        return "jwt"
    if SUPABASE_KEY.startswith("sb_secret_"):
        return "sb_secret"
    if SUPABASE_KEY.startswith("sb_publishable_") or SUPABASE_KEY.startswith("sb_anon_"):
        return "sb_anon"
    return "other"


def supabase_url_configurada() -> bool:
    return bool(SUPABASE_URL)


def supabase_client_ready() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY and supabase is not None)

