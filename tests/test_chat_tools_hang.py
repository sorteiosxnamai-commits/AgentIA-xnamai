"""Testes: evitar busca duplicada, ConnectionError sem travar, timeout e /chat."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import MagicMock


PRODUTOS_CTX = [
    {
        "id": "1",
        "name": "Celular Samsung Galaxy A36",
        "nome": "Celular Samsung Galaxy A36",
        "price": 1699.9,
        "preco": 1699.9,
        "stock_quantity": 6.0,
        "estoque": 6.0,
        "category": "Celulares",
        "source": "supabase",
    },
    {
        "id": "2",
        "name": "Celular Redmi Note 14",
        "nome": "Celular Redmi Note 14",
        "price": 1499.9,
        "preco": 1499.9,
        "stock_quantity": 8.0,
        "estoque": 8.0,
        "category": "Celulares",
        "source": "supabase",
    },
]


def test_contexto_com_produtos_nao_chama_mercos(monkeypatch):
    from agents.vendas import tools

    chamado = {"n": 0}

    def boom(*a, **k):
        chamado["n"] += 1
        raise AssertionError("não deve consultar Mercos com contexto")

    monkeypatch.setattr("services.mercos_service.mercos_configurado", lambda: True)
    monkeypatch.setattr("services.mercos_service.buscar_produtos_por_termo", boom)

    out = tools.execute_tool(
        "search_products",
        {"query": "celular", "limit": 3},
        context_products=PRODUTOS_CTX,
    )
    assert out["ok"] is True
    assert out["data"]["skipped_mercos"] is True
    assert out["data"]["products"][0]["name"].startswith("Celular")
    assert chamado["n"] == 0


def test_search_products_connection_error_retorna_erro_controlado(monkeypatch):
    from agents.vendas import tools

    monkeypatch.setattr("services.mercos_service.mercos_configurado", lambda: True)

    def falha(_q):
        raise ConnectionError("Mercos offline")

    monkeypatch.setattr("services.mercos_service.buscar_produtos_por_termo", falha)
    out = tools.execute_tool("search_products", {"query": "fone"})
    assert out["ok"] is False
    assert out["data"] is None
    assert out["error"] == "Não foi possível consultar o catálogo agora."


def test_search_products_timeout_retorna_erro_controlado(monkeypatch):
    from agents.vendas import tools

    monkeypatch.setenv("AGENT_TOOL_TIMEOUT_SEGUNDOS", "1")
    monkeypatch.setattr("services.mercos_service.mercos_configurado", lambda: True)

    def lento(_q):
        import time

        time.sleep(5)
        return []

    monkeypatch.setattr("services.mercos_service.buscar_produtos_por_termo", lento)
    out = tools.execute_tool("search_products", {"query": "tablet"})
    assert out["ok"] is False
    assert out["error"] == "Não foi possível consultar o catálogo agora."


def test_falha_mercos_usa_produtos_do_contexto(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from agents.vendas.agent import processar_mensagem_sync

    texto = processar_mensagem_sync(
        "quero celular até 2000",
        "11999999999",
        "Arthur",
        produtos_contexto=PRODUTOS_CTX,
        fonte_produtos="supabase",
        catalogo="Celular Samsung Galaxy A36 — R$ 1699.9",
    )
    assert texto
    assert "Samsung" in texto or "Redmi" in texto or "opções" in texto.lower()


def test_sem_informacao_resposta_segura(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from agents.vendas.agent import processar_mensagem_sync
    from agents.vendas import tools

    monkeypatch.setattr("services.mercos_service.mercos_configurado", lambda: True)

    def falha(_q):
        raise ConnectionError("down")

    monkeypatch.setattr("services.mercos_service.buscar_produtos_por_termo", falha)

    texto = processar_mensagem_sync(
        "tem notebook gamer?",
        "11999999999",
        "Ana",
        produtos_contexto=[],
        catalogo="",
    )
    assert isinstance(texto, str) and texto.strip()
    out = tools.execute_tool("search_products", {"query": "notebook"})
    assert out["ok"] is False


def test_schemas_omit_product_tools_quando_contexto():
    from agents.vendas.agent import _schemas_for_turn
    from agents.vendas.tools import PRODUCT_TOOLS

    schemas = _schemas_for_turn({"produtos_precarregados": PRODUTOS_CTX})
    nomes = {s["function"]["name"] for s in schemas}
    assert PRODUCT_TOOLS.isdisjoint(nomes)


def test_processar_mensagem_sempre_finaliza(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from agents.vendas.agent import processar_mensagem

    async def _run():
        return await processar_mensagem(
            "olá",
            "1199",
            "Ana",
            produtos_contexto=PRODUTOS_CTX,
        )

    out = asyncio.run(_run())
    assert isinstance(out, str) and out


def test_post_chat_sempre_finaliza(monkeypatch):
    from fastapi.testclient import TestClient
    import routes.api as api_mod
    from main import app

    def fake_processar(data, dry_run=True, persistir=True):
        return {"resposta": "ok chat", "persistencia_ok": False}

    monkeypatch.setattr(api_mod, "processar_mensagem", fake_processar)
    client = TestClient(app)
    resp = client.post(
        "/chat",
        json={
            "telefone": "5543999999999",
            "mensagem": "quero celular",
            "nome": "Arthur",
            "dry_run": True,
            "persistir": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("resposta")
    assert body.get("status") in ("ok", "erro")


def test_post_chat_timeout_controlado(monkeypatch):
    from fastapi.testclient import TestClient
    import routes.api as api_mod
    from main import app
    import time

    monkeypatch.setenv("CHAT_TIMEOUT_SEGUNDOS", "1")

    def lento(data, dry_run=True, persistir=True):
        time.sleep(3)
        return {"resposta": "tarde demais", "persistencia_ok": False}

    monkeypatch.setattr(api_mod, "processar_mensagem", lento)
    client = TestClient(app)
    resp = client.post(
        "/chat",
        json={
            "telefone": "5543999999999",
            "mensagem": "quero celular",
            "dry_run": True,
            "persistir": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "erro"
    assert body.get("code") == "timeout"
    assert body.get("resposta")


def test_perguntar_ia_passa_produtos_contexto(monkeypatch):
    from services import openai_service
    from services.vendas.contexto import ContextoVenda

    monkeypatch.setenv("AGENT_VERSION", "novo")
    capturado = {}

    def fake_sync(mensagem, telefone, nome=None, **kwargs):
        capturado.update(kwargs)
        capturado["mensagem"] = mensagem
        return "com produtos"

    monkeypatch.setattr("agents.vendas.processar_mensagem_sync", fake_sync)
    monkeypatch.setattr(
        "services.intent_service.sanitizar_frases_comerciais",
        lambda texto, stock_confirmed=False: texto,
    )

    ctx = ContextoVenda(catalogo="cat")
    ctx.produtos = PRODUTOS_CTX
    ctx.fonte = "supabase"

    out = openai_service.perguntar_ia(
        mensagem="celular",
        catalogo="cat",
        historico_texto="",
        nome_cliente="Arthur",
        contexto_venda=ctx,
        memoria_sessao={"telefone": "1199"},
    )
    assert out == "com produtos"
    assert capturado.get("produtos_contexto") == PRODUTOS_CTX
    assert capturado.get("fonte_produtos") == "supabase"


def test_arquivos_mercos_nao_alterados():
    root = Path(__file__).resolve().parents[1]
    for nome in (
        "services/mercos_service.py",
        "services/mercos_api_client.py",
        "services/mercos_throttle.py",
        "services/mercos_homolog_service.py",
        "routes/mercos_homolog.py",
        "routes/mercos_homolog_ui.py",
    ):
        path = root / nome
        assert path.exists(), nome
        src = path.read_text(encoding="utf-8", errors="replace")
        assert "AGENT_TOOL_TIMEOUT" not in src
        assert "produtos_precarregados" not in src


def test_tools_ainda_usam_mercos_service_sem_http(monkeypatch):
    from agents.vendas import tools

    fake = MagicMock(return_value=[{"nome": "X", "codigo": "1", "preco": 10, "estoque": 1}])
    monkeypatch.setattr("services.mercos_service.mercos_configurado", lambda: True)
    monkeypatch.setattr("services.mercos_service.buscar_produtos_por_termo", fake)
    monkeypatch.setattr(
        "services.mercos_service.montar_catalogo_texto",
        lambda produtos: "cat",
    )
    out = tools.execute_tool("search_products", {"query": "x"})
    assert out["ok"] is True
    fake.assert_called_once()
    src = inspect.getsource(tools)
    assert "requests." not in src
    assert "httpx" not in src
