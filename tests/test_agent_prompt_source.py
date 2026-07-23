"""Fonte de prompt do Agente de Vendas (local vs OpenAI Responses Prompt)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


def test_source_local_default(monkeypatch):
    monkeypatch.delenv("AGENT_PROMPT_SOURCE", raising=False)
    from agents.vendas.prompt_source import resolve_prompt_source

    assert resolve_prompt_source() == "local"


def test_source_invalido_usa_local(monkeypatch):
    monkeypatch.setenv("AGENT_PROMPT_SOURCE", "assistants")
    from agents.vendas.prompt_source import resolve_prompt_source

    assert resolve_prompt_source() == "local"


def test_source_openai_exige_prompt_id(monkeypatch):
    monkeypatch.setenv("AGENT_PROMPT_SOURCE", "openai")
    monkeypatch.delenv("OPENAI_PROMPT_ID", raising=False)
    from agents.vendas.prompt_source import PromptSourceError, build_prompt_param

    with pytest.raises(PromptSourceError) as exc:
        build_prompt_param()
    assert exc.value.code == "missing_prompt_id"


def test_asst_id_rejeitado(monkeypatch):
    monkeypatch.setenv("OPENAI_PROMPT_ID", "asst_abc123")
    from agents.vendas.prompt_source import PromptSourceError, build_prompt_param

    with pytest.raises(PromptSourceError) as exc:
        build_prompt_param()
    assert exc.value.code == "assistants_id_forbidden"


def test_build_prompt_com_versao(monkeypatch):
    monkeypatch.setenv("OPENAI_PROMPT_ID", "pmpt_teste123456")
    monkeypatch.setenv("OPENAI_PROMPT_VERSION", "3")
    from agents.vendas.prompt_source import build_prompt_param

    p = build_prompt_param()
    assert p == {"id": "pmpt_teste123456", "version": "3"}


def test_build_prompt_sem_versao(monkeypatch):
    monkeypatch.setenv("OPENAI_PROMPT_ID", "pmpt_teste123456")
    monkeypatch.delenv("OPENAI_PROMPT_VERSION", raising=False)
    from agents.vendas.prompt_source import build_prompt_param

    p = build_prompt_param()
    assert p == {"id": "pmpt_teste123456"}
    assert "version" not in p


def test_variaveis_seguras_sem_segredos():
    from agents.vendas.prompt_source import build_safe_prompt_variables

    vars_ = build_safe_prompt_variables(
        mensagem="Quero um notebook sk-proj-SECRETTOKEN123456789012345678",
        nome_cliente="Ana",
        customer_context={
            "historico_texto": "CompanyToken=abc ApplicationToken=xyz",
            "ultima_resposta_ia": "Olá",
            "memoria_sessao": {"interesse_atual": "notebook", "api_key": "nao-deve-ir"},
        },
        facts={
            "primary_intent": "buscar_produto",
            "sales_stage": "busca_produto",
            "display_name": "Ana",
            "produtos_precarregados": [{"name": "NB1", "price": 10}],
        },
    )
    assert set(vars_.keys()) == {
        "mensagem",
        "nome_cliente",
        "historico",
        "contexto_comercial",
    }
    assert vars_["nome_cliente"] == "Ana"
    blob = " ".join(vars_.values()).lower()
    assert "sk-proj-secrettoken" not in blob
    assert "[redacted]" in vars_["mensagem"].lower() or "sk-" not in vars_["mensagem"]
    assert "companytoken=abc" not in blob
    assert "api_key" not in vars_["historico"].lower()


def test_openai_source_chama_responses_com_prompt_id(monkeypatch):
    monkeypatch.setenv("AGENT_PROMPT_SOURCE", "openai")
    monkeypatch.setenv("OPENAI_PROMPT_ID", "pmpt_abc123xyz")
    monkeypatch.setenv("OPENAI_PROMPT_VERSION", "2")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-mini")
    monkeypatch.setenv("OPENAI_PROMPT_FALLBACK_LOCAL", "false")

    capturado = {}

    class FakeResp:
        id = "resp_111"
        output_text = "Resposta via prompt externo"
        output = []

    async def fake_create(**kwargs):
        capturado.update(kwargs)
        return FakeResp()

    class FakeAsyncOpenAI:
        def __init__(self, **kw):
            self.responses = SimpleNamespace(create=fake_create)

    monkeypatch.setattr("agents.vendas.agent.AsyncOpenAI", FakeAsyncOpenAI)

    from agents.vendas.agent import _generate_with_tools
    from agents.vendas.models import IncomingMessage

    msg = IncomingMessage(text="Olá, quero produto", sender_phone="5511999", sender_name="Ana")
    facts = {"primary_intent": "geral", "sales_stage": "descoberta"}
    out = asyncio.run(_generate_with_tools(msg, {"display_name": "Ana"}, facts))

    assert out.reply_text == "Resposta via prompt externo"
    assert "prompt" in capturado
    assert capturado["prompt"]["id"] == "pmpt_abc123xyz"
    assert capturado["prompt"]["version"] == "2"
    assert capturado["model"] == "gpt-5-mini"
    vars_ = capturado["prompt"]["variables"]
    assert vars_["mensagem"]
    assert vars_["nome_cliente"] == "Ana"
    assert "historico" in vars_
    assert "contexto_comercial" in vars_
    assert "messages" not in capturado


def test_local_source_usa_instructions(monkeypatch):
    monkeypatch.setenv("AGENT_PROMPT_SOURCE", "local")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-mini")

    capturado = {}

    class FakeMsg:
        content = "Resposta local"
        tool_calls = None

    class FakeChoice:
        message = FakeMsg()

    class FakeResp:
        id = "chatcmpl_1"
        choices = [FakeChoice()]

    async def fake_create(**kwargs):
        capturado.update(kwargs)
        return FakeResp()

    class FakeCompletions:
        create = staticmethod(fake_create)

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, **kw):
            self.chat = FakeChat()

    monkeypatch.setattr("agents.vendas.agent.AsyncOpenAI", FakeAsyncOpenAI)

    from agents.vendas.agent import _generate_with_tools
    from agents.vendas.instructions import build_system_instructions
    from agents.vendas.models import IncomingMessage

    msg = IncomingMessage(text="Oi", sender_phone="5511", sender_name="Bob")
    out = asyncio.run(
        _generate_with_tools(msg, {}, {"primary_intent": "geral", "sales_stage": "descoberta"})
    )
    assert out.reply_text == "Resposta local"
    assert "messages" in capturado
    assert capturado["messages"][0]["role"] == "system"
    assert capturado["messages"][0]["content"] == build_system_instructions()
    assert "prompt" not in capturado


def test_falha_externa_fallback_local_uma_vez(monkeypatch):
    monkeypatch.setenv("AGENT_PROMPT_SOURCE", "openai")
    monkeypatch.setenv("OPENAI_PROMPT_ID", "pmpt_fail")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_PROMPT_FALLBACK_LOCAL", "true")

    contadores = {"responses": 0, "chat": 0}

    async def boom(**kwargs):
        contadores["responses"] += 1
        raise RuntimeError("prompt not published")

    class FakeMsg:
        content = "Fallback local OK"
        tool_calls = None

    class FakeChoice:
        message = FakeMsg()

    class FakeChatResp:
        id = "chatcmpl_fb"
        choices = [FakeChoice()]

    async def fake_chat(**kwargs):
        contadores["chat"] += 1
        return FakeChatResp()

    class FakeCompletions:
        create = staticmethod(fake_chat)

    class FakeChat:
        completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, **kw):
            self.responses = SimpleNamespace(create=boom)
            self.chat = FakeChat()

    monkeypatch.setattr("agents.vendas.agent.AsyncOpenAI", FakeAsyncOpenAI)

    from agents.vendas.agent import _generate_with_tools
    from agents.vendas.models import IncomingMessage

    msg = IncomingMessage(text="teste", sender_phone="5511")
    out = asyncio.run(_generate_with_tools(msg, {}, {"primary_intent": "geral"}))
    assert out.reply_text == "Fallback local OK"
    assert contadores["responses"] == 1
    assert contadores["chat"] == 1


def test_falha_sem_fallback_nao_duplica(monkeypatch):
    monkeypatch.setenv("AGENT_PROMPT_SOURCE", "openai")
    monkeypatch.setenv("OPENAI_PROMPT_ID", "")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_PROMPT_FALLBACK_LOCAL", "false")

    contadores = {"chat": 0}

    async def fake_chat(**kwargs):
        contadores["chat"] += 1
        raise AssertionError("não deveria chamar chat")

    class FakeCompletions:
        create = staticmethod(fake_chat)

    class FakeChat:
        completions = FakeCompletions()

    async def never_create(**kwargs):
        raise AssertionError("responses não deveria ser chamado sem prompt id")

    class FakeAsyncOpenAI:
        def __init__(self, **kw):
            self.chat = FakeChat()
            self.responses = SimpleNamespace(create=never_create)

    monkeypatch.setattr("agents.vendas.agent.AsyncOpenAI", FakeAsyncOpenAI)

    from agents.vendas.agent import _generate_with_tools
    from agents.vendas.models import IncomingMessage

    msg = IncomingMessage(text="teste", sender_phone="5511")
    out = asyncio.run(_generate_with_tools(msg, {}, {"primary_intent": "geral"}))
    assert contadores["chat"] == 0
    assert out.reply_text
    assert out.handoff_required or out.safety_reason


def test_openai_tools_executam_no_backend(monkeypatch):
    monkeypatch.setenv("AGENT_PROMPT_SOURCE", "openai")
    monkeypatch.setenv("OPENAI_PROMPT_ID", "pmpt_tools")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("OPENAI_PROMPT_FALLBACK_LOCAL", "false")

    chamadas = {"n": 0, "tool": 0}

    class Call1:
        id = "resp_1"
        output_text = ""
        output = [
            SimpleNamespace(
                type="function_call",
                call_id="call_1",
                name="search_products",
                arguments='{"query":"mouse"}',
            )
        ]

    class Call2:
        id = "resp_2"
        output_text = "Temos o mouse X."
        output = []

    async def fake_create(**kwargs):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            assert "prompt" in kwargs
            assert kwargs.get("tools")
            return Call1()
        assert kwargs.get("previous_response_id") == "resp_1"
        assert kwargs["input"][0]["type"] == "function_call_output"
        return Call2()

    def fake_execute(name, args, context_products=None):
        chamadas["tool"] += 1
        assert name == "search_products"
        return {"ok": True, "data": {"products": [{"name": "Mouse X", "price": 50}]}}

    class FakeAsyncOpenAI:
        def __init__(self, **kw):
            self.responses = SimpleNamespace(create=fake_create)

    monkeypatch.setattr("agents.vendas.agent.AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setattr("agents.vendas.agent.execute_tool", fake_execute)

    from agents.vendas.agent import _generate_with_tools
    from agents.vendas.models import IncomingMessage

    msg = IncomingMessage(text="quero mouse", sender_phone="5511")
    out = asyncio.run(
        _generate_with_tools(msg, {}, {"primary_intent": "buscar_produto"})
    )
    assert out.reply_text == "Temos o mouse X."
    assert chamadas["tool"] == 1
    assert chamadas["n"] == 2


def test_tools_conversion_responses():
    from agents.vendas.prompt_source import tools_for_responses_api
    from agents.vendas.tools import TOOL_SCHEMAS

    converted = tools_for_responses_api(TOOL_SCHEMAS[:1])
    assert converted[0]["type"] == "function"
    assert converted[0]["name"] == "search_products"
    assert "function" not in converted[0]
    assert "parameters" in converted[0]


def test_mercos_modulos_nao_alterados_por_prompt_source():
    from pathlib import Path

    for rel in (
        "services/mercos_api_client.py",
        "services/mercos_service.py",
        "services/mercos_throttle.py",
    ):
        src = Path(rel).read_text(encoding="utf-8")
        assert "AGENT_PROMPT_SOURCE" not in src
        assert "OPENAI_PROMPT_ID" not in src


def test_supabase_brevo_audio_intactos_prompt_source():
    from pathlib import Path

    for rel in (
        "services/supabase_service.py",
        "services/audio_service.py",
    ):
        src = Path(rel).read_text(encoding="utf-8")
        assert "OPENAI_PROMPT_ID" not in src
        assert "AGENT_PROMPT_SOURCE" not in src
    assert Path("agents/vendas/instructions.py").exists()


def test_instructions_local_ainda_existe():
    from agents.vendas.instructions import build_system_instructions

    text = build_system_instructions()
    assert "xNamai" in text
    assert "Agente" in text or "atendente" in text.lower()
