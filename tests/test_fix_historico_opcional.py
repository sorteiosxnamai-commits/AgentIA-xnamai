"""Histórico opcional quando clientes.historico não existe."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import routes.api as api_mod
from services import supabase_service as sb
from services.checkout_service import avaliar_checkout


def test_migracao_018_historico_opcional():
    path = Path(__file__).resolve().parents[1] / "supabase" / "018_clientes_historico.sql"
    assert path.is_file()
    sql = path.read_text(encoding="utf-8")
    assert "historico" in sql
    assert "jsonb" in sql.lower()


def test_salvar_mensagem_skip_sem_coluna(monkeypatch):
    sb._SCHEMA_FLAGS["conversas_thread"] = True
    sb._SCHEMA_FLAGS["clientes_historico"] = False
    monkeypatch.setattr(sb, "clientes_tem_historico", lambda: False)
    out = sb.salvar_mensagem("cli-1", "cliente", "oi")
    assert out["skipped"] is True
    assert out["motivo"] == "sem_coluna_historico"


def test_salvar_mensagem_grava_quando_coluna_existe(monkeypatch):
    sb._SCHEMA_FLAGS["conversas_thread"] = True
    sb._SCHEMA_FLAGS["clientes_historico"] = True
    sb._SCHEMA_FLAGS["contexto_venda"] = True
    updates = {}

    class FakeTable:
        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def update(self, payload):
            updates.update(payload)
            return self

        def execute(self):
            if "historico" in updates:
                return MagicMock(data=[{"id": "cli-1"}])
            return MagicMock(data=[{"historico": []}])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable()))
    monkeypatch.setattr(sb, "clientes_tem_historico", lambda: True)
    out = sb.salvar_mensagem("cli-1", "cliente", "quero headset")
    assert out.get("modo") == "historico_json"
    assert "historico" in updates
    assert isinstance(updates["historico"], list)
    assert updates["historico"][-1]["content"] == "quero headset"


def test_chat_sem_coluna_historico_persistencia_ok(monkeypatch):
    from tests.test_fix_cliente_ok_etapas import _data, _patch_fluxo

    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-h1", "telefone": "5543999999993", "nome": "Arthur", "contexto_venda": {}},
    )
    monkeypatch.setattr(api_mod, "clientes_tem_historico", lambda: False)
    monkeypatch.setattr(
        api_mod,
        "diagnostico_coluna_historico",
        lambda: {"historico_coluna_existe": False, "historico_tipo": "ausente"},
    )
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: {"skipped": True})
    out = api_mod.processar_mensagem(_data(mid="h-skip"), dry_run=True, persistir=True)
    assert out["persistencia_ok"] is True
    assert out["persistencia_etapas"]["cliente_ok"] is True
    assert out["persistencia_etapas"]["contexto_ok"] is True
    assert out["persistencia_etapas"]["historico_ok"] is True
    dbg = out.get("historico_debug") or {}
    assert dbg.get("historico_coluna_existe") is False
    assert dbg.get("historico_salvo_em") == "nenhum"
    assert dbg.get("historico_essencial") is False


def test_chat_com_historico_salva_banco(monkeypatch):
    from tests.test_fix_cliente_ok_etapas import _data, _patch_fluxo

    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-h2", "telefone": "5543999999993", "nome": "Arthur", "contexto_venda": {}},
    )
    monkeypatch.setattr(api_mod, "clientes_tem_historico", lambda: True)
    monkeypatch.setattr(
        api_mod,
        "diagnostico_coluna_historico",
        lambda: {"historico_coluna_existe": True, "historico_tipo": "jsonb"},
    )
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: {"ok": True, "modo": "historico_json"})
    out = api_mod.processar_mensagem(_data(mid="h-banco"), dry_run=True, persistir=True)
    assert out["persistencia_ok"] is True
    assert out["persistencia_etapas"]["historico_ok"] is True
    assert (out.get("cliente_debug") or {}).get("historico_salvo_em") == "banco"
    assert (out.get("historico_debug") or {}).get("historico_salvo_em") == "banco"


def test_message_log_e_thread_opcionais(monkeypatch):
    from tests.test_fix_cliente_ok_etapas import _data, _patch_fluxo

    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-h3", "telefone": "5543999999993", "nome": "Arthur"},
    )
    monkeypatch.setattr(api_mod, "clientes_tem_historico", lambda: True)
    monkeypatch.setattr(
        api_mod,
        "diagnostico_coluna_historico",
        lambda: {"historico_coluna_existe": True, "historico_tipo": "jsonb"},
    )
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(api_mod, "atualizar_thread_conversa", lambda *_a, **_k: False)
    out = api_mod.processar_mensagem(_data(mid="h-opt"), dry_run=True, persistir=True)
    assert out["persistencia_ok"] is True
    assert out["persistencia_etapas"]["thread_ok"] is False
    assert out["persistencia_etapas"]["message_log_ok"] is True  # dry_run


def test_checkout_sequencia_contexto():
    r1 = avaliar_checkout(
        mensagem="quero comprar o headset gamer",
        sessao={},
        produtos=[{"name": "Headset Gamer", "price": 249.9, "stock_quantity": 5, "stock_confirmed": True}],
        intent="COMPRA",
    )
    s = r1["sessao"]
    r2 = avaliar_checkout(
        mensagem="prefiro entrega",
        sessao=s,
        produtos=[{"name": "Headset Gamer", "price": 249.9, "stock_quantity": 5, "stock_confirmed": True}],
        intent="ENTREGA",
    )
    assert r2["sessao"]["forma_entrega"] == "entrega"
    r3 = avaliar_checkout(
        mensagem="sou de Londrina",
        sessao=r2["sessao"],
        produtos=[{"name": "Headset Gamer", "price": 249.9, "stock_quantity": 5, "stock_confirmed": True}],
        intent="ENTREGA",
    )
    assert "londrina" in (r3["sessao"].get("cidade") or "").lower()


def test_code_version_historico():
    assert api_mod.CODE_VERSION == "2026-07-13-feat-ultramsg-beta"
