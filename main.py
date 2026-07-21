
from fastapi import FastAPI, Response
import os

from routes.api import receber_webhook

app = FastAPI()

from routes.api import router
from routes.mercos_homolog import router as mercos_homolog_router
from routes.mercos_homolog_ui import router as mercos_homolog_ui_router

app.include_router(router)
app.include_router(mercos_homolog_router)
app.include_router(mercos_homolog_ui_router)


@app.middleware("http")
async def _mercos_modo_exclusivo_e_origem(request, call_next):
    """Modo exclusivo de homologação de Promoções + origem de auditoria.

    Enquanto o ciclo de Promoções está ativo, bloqueia com 409 amigável as demais
    ações Mercos da UI (exceto Promoções, buscas locais e reinícios). Também
    registra a rota interna como origem para a auditoria do throttling global.
    """
    path = request.url.path
    if request.method == "POST" and path.startswith("/mercos/homologacao-ui/acoes/"):
        from routes.mercos_homolog_ui import (
            _acao_permitida_no_modo_exclusivo,
            modo_exclusivo_bloqueio,
        )

        if not _acao_permitida_no_modo_exclusivo(path):
            bloqueio = modo_exclusivo_bloqueio(request)
            if bloqueio is not None:
                return bloqueio

    from services import mercos_throttle

    token = mercos_throttle.definir_origem(path)
    try:
        return await call_next(request)
    finally:
        mercos_throttle.limpar_origem(token)


@app.on_event("startup")
def validar_tabelas_no_startup():
    """Valida CLIENTES_TABLE / CONVERSAS_TABLE sem fallback silencioso."""
    flag = os.getenv("VALIDAR_TABELAS_STARTUP", "true").strip().lower()
    if flag in ("0", "false", "nao", "não", "no"):
        print("VALIDAR_TABELAS_STARTUP desligado — pulando checagem")
        return
    try:
        from services.config_tabelas import validar_tabelas_supabase

        # obrigatorio=False no boot: tabela inexistente ainda loga erro claro;
        # rede temporária não derruba o Render. Use /status para ver status.
        resultado = validar_tabelas_supabase(obrigatorio=False)
        if not resultado.get("ok") and resultado.get("erros"):
            print(
                "ATENÇÃO: tabelas configuradas inválidas. "
                "Ajuste CLIENTES_TABLE/CONVERSAS_TABLE. Sem fallback silencioso."
            )
    except Exception as exc:
        print("Falha na validação de tabelas no startup:", type(exc).__name__, str(exc)[:200])


@app.get("/")
def home():
    return {
        "status": "online",
        "service": "agente-vendas"
    }


@app.head("/")
def home_head():
    return Response(status_code=200)


@app.post("/")
async def root_webhook(data: dict):
    return await receber_webhook(data)
