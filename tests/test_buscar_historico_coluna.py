"""Testes: buscar_historico sem criado_em / 42703 e /chat resiliente."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError


@pytest.fixture(autouse=True)
def _reset_schema_flags():
    from services import supabase_service as sb

    prev = dict(sb._SCHEMA_FLAGS)
    prev_meta = dict(sb._META_BUSCAR_HISTORICO)
    yield
    sb._SCHEMA_FLAGS.clear()
    sb._SCHEMA_FLAGS.update(prev)
    sb._META_BUSCAR_HISTORICO.clear()
    sb._META_BUSCAR_HISTORICO.update(prev_meta)


def _api_error_42703(coluna: str = "criado_em") -> APIError:
    return APIError(
        {
            "code": "42703",
            "message": f"column conversas.{coluna} does not exist",
            "details": None,
            "hint": None,
        }
    )


def test_detectar_coluna_ordem_created_at(monkeypatch):
    monkeypatch.delenv("CONVERSAS_CREATED_AT_COLUMN", raising=False)
    from services import supabase_service as sb

    sb._SCHEMA_FLAGS["conversas_ordem_coluna"] = None
    assert sb.detectar_coluna_ordem_conversas({"id", "created_at", "cliente_id"}) == "created_at"


def test_detectar_coluna_ordem_env(monkeypatch):
    monkeypatch.setenv("CONVERSAS_CREATED_AT_COLUMN", "last_message_at")
    from services import supabase_service as sb

    assert sb.detectar_coluna_ordem_conversas({"created_at"}) == "last_message_at"


def test_conversas_thread_com_cliente_id_nao_vira_mensagens(monkeypatch):
    """PulseDesk com cliente_id FK + contact_phone continua modo thread."""
    from services import supabase_service as sb

    sb._SCHEMA_FLAGS["conversas_thread"] = None
    sb._SCHEMA_FLAGS["conversas_ordem_coluna"] = None

    class FakeTable:
        def select(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def execute(self):
            return SimpleNamespace(
                data=[
                    {
                        "id": "1",
                        "contact_phone": "5543",
                        "last_message": "oi",
                        "last_message_at": "2026-01-01",
                        "cliente_id": "uuid-x",
                    }
                ]
            )

    class FakeSB:
        def table(self, name):
            return FakeTable()

    monkeypatch.setattr(sb, "supabase", FakeSB())
    assert sb.conversas_e_thread() is True
    assert sb._SCHEMA_FLAGS.get("conversas_ordem_coluna") == "last_message_at"


def test_buscar_historico_sem_criado_em_usa_created_at(monkeypatch):
    from services import supabase_service as sb

    sb._SCHEMA_FLAGS["conversas_thread"] = False
    sb._SCHEMA_FLAGS["conversas_ordem_coluna"] = None
    monkeypatch.delenv("CONVERSAS_CREATED_AT_COLUMN", raising=False)

    orders = []

    class FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def order(self, col):
            orders.append(col)
            if col == "criado_em":
                raise _api_error_42703("criado_em")
            return self

        def execute(self):
            return SimpleNamespace(data=self._rows)

    class FakeSB:
        def __init__(self):
            self._n = 0

        def table(self, name):
            self._n += 1
            row = {
                "id": 1,
                "created_at": "t",
                "cliente_id": "c",
                "tipo": "cliente",
                "mensagem": "oi",
            }
            return FakeQuery([row])

    monkeypatch.setattr(sb, "supabase", FakeSB())
    out = sb.buscar_historico("c")
    assert len(out) == 1
    assert "created_at" in orders
    assert sb.historico_leitura_indisponivel() is False


def test_buscar_historico_42703_fallback_sem_order(monkeypatch):
    from services import supabase_service as sb

    sb._SCHEMA_FLAGS["conversas_thread"] = False
    sb._SCHEMA_FLAGS["conversas_ordem_coluna"] = None
    monkeypatch.setenv("CONVERSAS_CREATED_AT_COLUMN", "criado_em")

    calls = {"order": 0, "exec": 0}

    class Q:
        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def order(self, col):
            calls["order"] += 1
            raise _api_error_42703(col)

        def execute(self):
            calls["exec"] += 1
            return SimpleNamespace(
                data=[{"id": 1, "cliente_id": "c", "tipo": "cliente", "mensagem": "ok"}]
            )

    class SB:
        def table(self, name):
            return Q()

    monkeypatch.setattr(sb, "supabase", SB())
    out = sb.buscar_historico("c")
    assert out and out[0]["mensagem"] == "ok"
    assert calls["order"] >= 1
    assert calls["exec"] >= 1
    assert sb.meta_buscar_historico().get("sem_order") is True
    assert sb.historico_leitura_indisponivel() is False


def test_buscar_historico_erro_total_retorna_vazio(monkeypatch):
    from services import supabase_service as sb

    sb._SCHEMA_FLAGS["conversas_thread"] = False
    sb._SCHEMA_FLAGS["conversas_ordem_coluna"] = ""
    monkeypatch.delenv("CONVERSAS_CREATED_AT_COLUMN", raising=False)

    class Boom:
        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def execute(self):
            raise _api_error_42703("qualquer")

    class SB:
        def table(self, name):
            return Boom()

    monkeypatch.setattr(sb, "supabase", SB())
    out = sb.buscar_historico("c")
    assert out == []
    assert sb.historico_leitura_indisponivel() is True


def test_erro_coluna_ausente_42703():
    from services.supabase_service import erro_coluna_ausente

    exc = _api_error_42703("criado_em")
    assert erro_coluna_ausente(exc, "criado_em") is True
    assert erro_coluna_ausente(exc, "created_at") is False


def test_chat_dry_run_continua_com_historico_vazio(monkeypatch):
    monkeypatch.setenv("DIAGNOSTICOS_ABERTOS", "true")
    monkeypatch.setenv("AGENT_VERSION", "novo")

    from fastapi.testclient import TestClient
    from main import app
    import routes.api as api_mod

    openai_calls = {"n": 0}

    def fake_processar(data, dry_run=True, persistir=True):
        openai_calls["n"] += 1
        return {
            "resposta": "Olá! Como posso ajudar?",
            "persistencia_ok": False,
            "historico_indisponivel": True,
        }

    monkeypatch.setattr(api_mod, "processar_mensagem", fake_processar)
    client = TestClient(app)
    resp = client.post(
        "/chat",
        json={
            "telefone": "5543999999999",
            "mensagem": "oi",
            "dry_run": True,
            "persistir": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok"
    assert openai_calls["n"] == 1
    assert "Olá" in (body.get("resposta") or "")
    assert body.get("historico_indisponivel") is True


def test_prompt_externo_ainda_chamado_apos_historico_falhar(monkeypatch):
    """Uma única chamada ao gerador — histórico vazio não duplica resposta."""
    monkeypatch.setenv("AGENT_VERSION", "novo")
    monkeypatch.setenv("AGENT_PROMPT_SOURCE", "local")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    from services import supabase_service as sb

    sb._SCHEMA_FLAGS["conversas_thread"] = False
    sb._SCHEMA_FLAGS["conversas_ordem_coluna"] = None

    class Boom:
        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def order(self, *a, **k):
            raise _api_error_42703("criado_em")

        def execute(self):
            raise _api_error_42703("criado_em")

    class SB:
        def table(self, name):
            return Boom()

    monkeypatch.setattr(sb, "supabase", SB())
    assert sb.buscar_historico("uuid") == []
    assert sb.historico_leitura_indisponivel() is True

    calls = {"n": 0}

    async def fake_gen(*a, **k):
        calls["n"] += 1
        from agents.vendas.models import AgentResult

        return AgentResult(reply_text="ok-unico", intent="geral")

    monkeypatch.setattr("agents.vendas.agent._generate_with_tools", fake_gen)
    import asyncio
    from agents.vendas.agent import processar_mensagem

    out = asyncio.run(processar_mensagem("quero notebook gamer", "5543999", "Ana"))
    assert out == "ok-unico"
    assert calls["n"] == 1
