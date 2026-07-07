
from fastapi import FastAPI, Response
from routes.api import receber_webhook

app = FastAPI()

from routes.api import router
app.include_router(router)


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