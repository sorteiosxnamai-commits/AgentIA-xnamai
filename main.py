
from fastapi import FastAPI, Response
import os

from routes.api import receber_webhook

app = FastAPI()

from routes.api import router
from routes.mercos_homolog import router as mercos_homolog_router

app.include_router(router)
app.include_router(mercos_homolog_router)


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
