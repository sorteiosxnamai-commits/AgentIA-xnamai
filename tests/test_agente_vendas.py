"""Testes do Agente de Vendas da xNamai (agents.vendas)."""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock

import pytest


def test_import_agents_vendas():
    from agents.vendas import processar_mensagem, processar_mensagem_sync

    assert callable(processar_mensagem)
    assert callable(processar_mensagem_sync)


def test_persona_xnamai_nao_newstore():
    from agents.vendas.instructions import build_system_instructions
    from agents.vendas.sales_knowledge import APRESENTACAO, NOME_AGENTE
    from agents.vendas.guardrails import default_safe_handoff

    instr = build_system_instructions()
    assert "xNamai" in NOME_AGENTE
    assert "Agente de Vendas" in NOME_AGENTE
    assert "Você é o Agente de Vendas da xNamai" in instr
    assert "xNamai" in APRESENTACAO
    assert "NewStoreAgent" not in APRESENTACAO
    assert "sorteio" not in APRESENTACAO.lower()
    assert "New Store" not in default_safe_handoff()
    assert "xNamai" in default_safe_handoff()


def test_sem_tray_brevo_identidade():
    import agents.vendas.instructions as instructions
    import agents.vendas.sales_knowledge as sk

    for mod in (instructions, sk):
        src = inspect.getsource(mod)
        assert "Tray" not in src or "Nunca" in src
        # identidade não deve apresentar Brevo/Tray como marca
    assert "Brevo" not in sk.APRESENTACAO
    assert "Tray" not in sk.APRESENTACAO
    assert "NewStore" not in sk.NOME_AGENTE


def test_quero_comprar_nao_bloqueado():
    from agents.vendas.guardrails import detect_blocked_request

    assert detect_blocked_request("quero comprar") is None
    assert detect_blocked_request("tem em estoque?") is None
    assert detect_blocked_request("qual o preço?") is None
    assert detect_blocked_request("quero dois") is None


def test_saudacao_fallback_xnamai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from agents.vendas import processar_mensagem_sync

    texto = processar_mensagem_sync("Olá", telefone="11999999999", nome="Ana")
    assert "xNamai" in texto


def test_humano_handoff_xnamai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from agents.vendas import processar_mensagem_sync

    texto = processar_mensagem_sync(
        "quero falar com atendente humano",
        telefone="11999999999",
        nome="Ana",
    )
    assert "xNamai" in texto or "atendente" in texto.lower()


def test_buscar_produto_fallback(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from agents.vendas import processar_mensagem_sync

    texto = processar_mensagem_sync(
        "Estou procurando um celular",
        telefone="11999999999",
        nome="Ana",
    )
    assert texto
    assert "sorteio" not in texto.lower()


def test_orcamento_detectado():
    from agents.vendas.guardrails import extract_budget
    from agents.vendas.context_builder import gather_customer_facts
    from agents.vendas.models import IncomingMessage

    assert extract_budget("Até R$ 2.000")
    facts = gather_customer_facts(
        IncomingMessage(text="Quero um notebook até R$ 3.000"),
        {},
    )
    assert facts["primary_intent"] in ("buscar_produto", "geral")
    assert facts.get("orcamento")


def test_contexto_quero_dois_e_esse():
    from agents.vendas.guardrails import extract_quantity
    from agents.vendas.context_builder import gather_customer_facts
    from agents.vendas.models import IncomingMessage

    assert extract_quantity("quero dois") == 2
    facts = gather_customer_facts(
        IncomingMessage(text="esse"),
        {"memoria_sessao": {"produto_mencionado": "Notebook X"}},
    )
    assert facts.get("resposta_curta") == "esse"
    assert facts.get("produto_mencionado") == "Notebook X"


def test_comparar_produtos_intent():
    from agents.vendas.context_builder import detect_customer_intents

    intents = detect_customer_intents("Qual desses é melhor?")
    assert "comparar_produtos" in intents


def test_tools_search_products_usa_mercos_service(monkeypatch):
    from agents.vendas import tools

    fake = MagicMock(
        return_value=[{"nome": "Relógio X", "codigo": "RX1", "preco": 100, "estoque": 2}]
    )
    monkeypatch.setattr("services.mercos_service.mercos_configurado", lambda: True)
    monkeypatch.setattr("services.mercos_service.buscar_produtos_por_termo", fake)
    monkeypatch.setattr(
        "services.mercos_service.montar_catalogo_texto",
        lambda produtos: "catalogo",
    )

    out = tools.execute_tool("search_products", {"query": "relogio", "limit": 3})
    assert out["ok"] is True
    assert out["data"]["products"][0]["name"] == "Relógio X"
    fake.assert_called_once()


def test_check_inventory_e_preco_usam_mercos(monkeypatch):
    from agents.vendas import tools

    bruto = {"nome": "Y", "codigo": "2", "estoque": 3, "preco": 99}
    monkeypatch.setattr("services.mercos_service.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "services.mercos_service.buscar_produto_bruto_por_mensagem",
        lambda q: bruto,
    )
    monkeypatch.setattr(
        "services.mercos_service.normalizar_produto",
        lambda p: {"nome": "Y", "codigo": "2", "estoque": 3, "preco": 99},
    )
    monkeypatch.setattr("services.mercos_service.estoque_confirmado", lambda p: True)

    inv = tools.execute_tool("check_inventory", {"query": "y"})
    assert inv["ok"] is True
    assert inv["data"]["found"] is True

    price = tools.execute_tool("get_product_price", {"query": "y"})
    assert price["ok"] is True
    assert price["data"]["price"] == 99


def test_tools_sem_http_direto():
    import agents.vendas.tools as tools

    src = inspect.getsource(tools)
    assert "requests." not in src
    assert "httpx" not in src
    assert "mercos.com" not in src


def test_lead_nao_em_saudacao(monkeypatch):
    from agents.vendas import tools

    chamado = {"n": 0}

    def fake_criar(*a, **k):
        chamado["n"] += 1

    monkeypatch.setattr("services.supabase_service.buscar_cliente", lambda t: {"id": "c1"})
    monkeypatch.setattr("services.supabase_service.buscar_lead", lambda *a, **k: None)
    monkeypatch.setattr("services.supabase_service.criar_lead", fake_criar)

    out = tools.execute_tool("register_lead", {"telefone": "1199", "interesse": "saudacao"})
    assert out["ok"] is True
    assert out["data"].get("skipped") is True
    assert chamado["n"] == 0


def test_lead_com_interesse_nao_duplica(monkeypatch):
    from agents.vendas import tools

    monkeypatch.setattr("services.supabase_service.buscar_cliente", lambda t: {"id": "c1"})
    monkeypatch.setattr(
        "services.supabase_service.buscar_lead",
        lambda *a, **k: {"id": "L1"},
    )
    monkeypatch.setattr(
        "services.supabase_service.criar_lead",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("não deve criar")),
    )
    out = tools.execute_tool(
        "register_lead",
        {"telefone": "1199", "interesse": "buscar_produto", "produto": "celular"},
    )
    assert out["ok"] is True
    assert out["data"].get("duplicado") is True


def test_perguntar_ia_delega_ao_vendas(monkeypatch):
    from services import openai_service

    monkeypatch.setenv("AGENT_VERSION", "novo")
    chamado = {}

    def fake_sync(mensagem, telefone, nome=None, **kwargs):
        chamado["mensagem"] = mensagem
        chamado["telefone"] = telefone
        chamado["nome"] = nome
        return "resposta vendas xNamai"

    monkeypatch.setattr("agents.vendas.processar_mensagem_sync", fake_sync)
    monkeypatch.setattr(
        "services.intent_service.sanitizar_frases_comerciais",
        lambda texto, stock_confirmed=False: texto,
    )

    out = openai_service.perguntar_ia(
        mensagem="oi",
        catalogo="",
        historico_texto="cliente: oi",
        nome_cliente="Ana",
        memoria_sessao={"telefone": "11988887777"},
    )
    assert out == "resposta vendas xNamai"
    assert chamado["telefone"] == "11988887777"


def test_apenas_uma_resposta_async(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from agents.vendas.agent import processar_mensagem

    async def _run():
        a = await processar_mensagem("Olá", "1199999", "Ana")
        b = await processar_mensagem("Olá", "1199999", "Ana")
        return a, b

    a, b = asyncio.run(_run())
    assert isinstance(a, str) and a
    assert isinstance(b, str) and b
