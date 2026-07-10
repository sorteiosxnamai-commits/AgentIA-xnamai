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
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    # Não imprime valores — só indica ausência
    raise RuntimeError(
        "SUPABASE_URL e SUPABASE_KEY são obrigatórios. "
        "Configure no .env (local) ou nas env vars do Render."
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
