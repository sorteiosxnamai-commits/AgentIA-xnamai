"""mercoss_id nullable: cliente WhatsApp sem id Mercos."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import routes.api as api_mod
from services import supabase_service as sb


def test_migracao_017_existe_e_drop_not_null():
    path = Path(__file__).resolve().parents[1] / "supabase" / "017_clientes_mercos_id_nullable.sql"
    assert path.is_file()
    sql = path.read_text(encoding="utf-8")
    assert "ALTER COLUMN mercos_id DROP NOT NULL" in sql.replace("\n", " ").replace("  ", " ")
    assert "DEFAULT 0" not in sql.upper()
    assert "mercos_id = 0" not in sql.lower()


def test_criar_cliente_sem_mercos_id_no_payload(monkeypatch):
    inserted = {}
    sb._SCHEMA_FLAGS["clientes_celular"] = False

    class FakeTable:
        def select(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def insert(self, payload):
            inserted.update(payload)
            return self

        def execute(self):
            # simula linha criada com mercos_id null
            return MagicMock(
                data=[{
                    "id": "cli-wa-1",
                    "telefone": inserted.get("telefone"),
                    "nome": inserted.get("nome"),
                    "mercos_id": None,
                }]
            )

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable()))
    monkeypatch.setattr(sb, "_detectar_colunas_clientes", lambda: {"telefone", "nome", "mercos_id", "id"})
    row = sb.criar_cliente("5543999111222", nome="Arthur")
    assert "mercos_id" not in inserted
    assert "mercos_cliente_id" not in inserted
    assert inserted.keys() <= {"telefone", "nome", "celular"}
    assert row["mercos_id"] is None
    assert row["id"] == "cli-wa-1"


def test_criar_cliente_nao_inventa_mercos_id_zero(monkeypatch):
    inserted = {}

    class FakeTable:
        def select(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def insert(self, payload):
            # se o código tentar forçar 0, o teste falha
            assert payload.get("mercos_id") not in (0, "0", "")
            assert "mercos_id" not in payload
            inserted.update(payload)
            return self

        def execute(self):
            return MagicMock(data=[{"id": "cli-2", **inserted, "mercos_id": None}])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable()))
    monkeypatch.setattr(sb, "_detectar_colunas_clientes", lambda: {"telefone", "nome", "mercos_id"})
    sb._SCHEMA_FLAGS["clientes_celular"] = False
    sb.criar_cliente("5543999111333", nome="Ana")
    assert "mercos_id" not in inserted


def test_atualizar_mercos_id_depois_do_sync(monkeypatch):
    updates = {}

    class FakeTable:
        def update(self, payload):
            updates.update(payload)
            return self

        def eq(self, *_a, **_k):
            return self

        def execute(self):
            return MagicMock(data=[{"id": "cli-3", **updates}])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable()))
    sb.atualizar_cliente(cliente_id="cli-3", mercos_id=12345)
    assert updates["mercos_id"] == 12345


def test_classificar_erro_mercos_id_not_null():
    from postgrest.exceptions import APIError

    code, tipo, resumo = sb.classificar_erro_supabase(
        APIError({
            "message": 'null value in column "mercos_id" of relation "clientes" violates not-null constraint',
            "code": "23502",
        })
    )
    assert code == "23502"
    assert tipo == "NOT_NULL"
    assert "017" in resumo or "nullable" in resumo.lower()


def test_chat_persistir_ok_sem_mercos_id(monkeypatch):
    from tests.test_fix_cliente_ok_etapas import _data, _patch_fluxo

    created = {}

    def fake_criar(tel, nome=""):
        created["payload_ok"] = True
        return {
            "id": "cli-real-wa",
            "telefone": tel,
            "nome": nome or "Arthur",
            "mercos_id": None,
            "contexto_venda": {},
        }

    _patch_fluxo(monkeypatch, cliente=None, criar=fake_criar)
    out = api_mod.processar_mensagem(
        _data("quero comprar o headset gamer", mid="mercos-null-1"),
        dry_run=True,
        persistir=True,
    )
    assert created.get("payload_ok")
    assert out["persistencia_ok"] is True
    assert out["persistencia_etapas"]["cliente_ok"] is True
    assert out["persistencia_etapas"]["historico_ok"] is True
    assert out["persistencia_etapas"]["contexto_ok"] is True
    dbg = out.get("cliente_debug") or {}
    assert dbg.get("origem_cliente") != "ephemeral"
    assert dbg.get("tem_cliente_id") is True


def test_code_version_mercos_nullable():
    assert api_mod.CODE_VERSION == "2026-07-13-fix-catalogo-geral"
