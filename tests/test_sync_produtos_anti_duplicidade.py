"""Testes da sync Mercos → produtos (schema real: mercos_id UNIQUE)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from services import supabase_service as sb
from services import sync_mercos_service as sync_mod


class _FakeQuery:
    def __init__(self, store: "FakeProdutosStore", op: str, payload: dict | None = None):
        self.store = store
        self.op = op
        self.payload = payload or {}
        self._filters: list[tuple[str, str, Any]] = []
        self._on_conflict: str | None = None

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def eq(self, campo: str, valor: Any):
        self._filters.append(("eq", campo, valor))
        return self

    def update(self, payload: dict):
        self.op = "update"
        self.payload = dict(payload)
        return self

    def insert(self, payload: dict):
        self.op = "insert"
        self.payload = dict(payload)
        return self

    def upsert(self, payload: dict, on_conflict: str | None = None):
        self.op = "upsert"
        self.payload = dict(payload)
        self._on_conflict = on_conflict
        return self

    def execute(self):
        if self.op == "select":
            rows = list(self.store.rows)
            for _, campo, valor in self._filters:
                rows = [
                    r
                    for r in rows
                    if str(r.get(campo) if r.get(campo) is not None else "")
                    == str(valor if valor is not None else "")
                ]
            return MagicMock(data=rows)

        if self.op == "insert":
            row = dict(self.payload)
            row.setdefault("id", self.store.next_id())
            self.store.rows.append(row)
            self.store.writes.append(("insert", row))
            return MagicMock(data=[row])

        if self.op == "update":
            ids = [v for kind, c, v in self._filters if kind == "eq" and c == "id"]
            updated = []
            for r in self.store.rows:
                if ids and r.get("id") == ids[0]:
                    r.update(self.payload)
                    updated.append(dict(r))
                    self.store.writes.append(("update", dict(r)))
            return MagicMock(data=updated)

        if self.op == "upsert":
            mid = self.payload.get("mercos_id")
            conflict = (self._on_conflict or "").replace(" ", "")
            assert conflict == "mercos_id"
            if mid is not None:
                for r in self.store.rows:
                    if str(r.get("mercos_id")) == str(mid):
                        r.update(self.payload)
                        self.store.writes.append(("upsert_update", dict(r)))
                        return MagicMock(data=[dict(r)])
            row = dict(self.payload)
            row.setdefault("id", self.store.next_id())
            self.store.rows.append(row)
            self.store.writes.append(("upsert_insert", row))
            return MagicMock(data=[row])

        return MagicMock(data=[])


class FakeProdutosStore:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = [dict(r) for r in (rows or [])]
        self.writes: list[tuple[str, dict]] = []
        self._seq = 1000

    def next_id(self) -> str:
        self._seq += 1
        return f"p-{self._seq}"

    def table(self, name: str):
        assert name == "produtos"
        return _FakeQuery(self, "select")


def _patch_store(monkeypatch, store: FakeProdutosStore):
    monkeypatch.setattr(sb, "supabase", store)
    monkeypatch.setattr("services.webhook_guard.log_seguro", lambda *a, **k: None)


def test_diagnostico_021_sem_alterar_schema():
    path = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "021_produtos_diagnostico_pre_sync.sql"
    )
    assert path.is_file()
    sql = path.read_text(encoding="utf-8")
    sql_l = sql.lower()
    assert "mercos_id" in sql_l
    assert "add column" not in sql_l
    assert "create unique" not in sql_l
    assert "create index" not in sql_l
    assert "alter table" not in sql_l
    assert not (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "021_produtos_mercos_produto_id.sql"
    ).exists()


def test_produto_novo(monkeypatch):
    store = FakeProdutosStore([])
    _patch_store(monkeypatch, store)
    out = sb.sincronizar_produto_mercos_seguro(
        {"mercos_id": 9001, "codigo": "SKU-A", "nome": "Produto A", "preco_tabela": 10}
    )
    assert out["acao"] == "criado"
    assert len(store.rows) == 1
    assert store.rows[0]["mercos_id"] == 9001
    assert store.writes[0][0] == "upsert_insert"
    assert store.writes[0][1].get("mercos_id") == 9001


def test_ja_existente_por_mercos_id(monkeypatch):
    store = FakeProdutosStore(
        [
            {
                "id": "p-1",
                "mercos_id": 9001,
                "codigo": "SKU-A",
                "nome": "Antigo",
                "preco_tabela": 5,
            }
        ]
    )
    _patch_store(monkeypatch, store)
    out = sb.sincronizar_produto_mercos_seguro(
        {
            "mercos_id": 9001,
            "codigo": "SKU-A",
            "nome": "Atualizado",
            "preco_tabela": 12,
        }
    )
    assert out["acao"] == "atualizado"
    assert out["match"] == "mercos_id"
    assert len(store.rows) == 1
    assert store.rows[0]["nome"] == "Atualizado"
    assert any(op == "upsert_update" for op, _ in store.writes)


def test_antigo_encontrado_por_sku(monkeypatch):
    """Sandbox tinha outro mercos_id; associação por codigo atualiza para o ID de produção."""
    store = FakeProdutosStore(
        [
            {
                "id": "p-legado",
                "mercos_id": 111,
                "codigo": "SKU-LEG",
                "nome": "Legado",
                "preco_tabela": 1,
            }
        ]
    )
    _patch_store(monkeypatch, store)
    out = sb.sincronizar_produto_mercos_seguro(
        {
            "mercos_id": 777,
            "codigo": "SKU-LEG",
            "nome": "Legado sync",
            "preco_tabela": 9,
        }
    )
    assert out["acao"] == "atualizado"
    assert out["match"] == "codigo"
    assert store.rows[0]["mercos_id"] == 777
    assert len(store.rows) == 1
    assert any(op == "update" for op, _ in store.writes)


def test_dois_locais_mesmo_sku_ambiguo(monkeypatch):
    store = FakeProdutosStore(
        [
            {"id": "a", "codigo": "DUP", "mercos_id": 1, "nome": "A"},
            {"id": "b", "codigo": "DUP", "mercos_id": 2, "nome": "B"},
        ]
    )
    _patch_store(monkeypatch, store)
    out = sb.sincronizar_produto_mercos_seguro(
        {"mercos_id": 999, "codigo": "DUP", "nome": "Mercos"}
    )
    assert out["acao"] == "ambiguo"
    assert out["motivo"] == "codigo_duplicado"
    assert len(store.rows) == 2
    assert store.writes == []


def test_sync_duas_vezes_nao_duplica(monkeypatch):
    store = FakeProdutosStore([])
    _patch_store(monkeypatch, store)
    payload = {"mercos_id": 42, "codigo": "SKU-42", "nome": "Item", "preco_tabela": 3}
    assert sb.sincronizar_produto_mercos_seguro(payload)["acao"] == "criado"
    assert sb.sincronizar_produto_mercos_seguro(payload)["acao"] == "atualizado"
    assert len(store.rows) == 1


def test_sem_id_mercos_ignorado(monkeypatch):
    store = FakeProdutosStore([])
    _patch_store(monkeypatch, store)
    out = sb.sincronizar_produto_mercos_seguro(
        {"codigo": "X", "nome": "Sem ID", "mercos_id": None}
    )
    assert out["acao"] == "ignorado"
    assert out["motivo"] == "sem_mercos_id"
    assert store.rows == []
    assert store.writes == []


def test_dry_run_nao_grava(monkeypatch):
    store = FakeProdutosStore(
        [{"id": "p1", "codigo": "SKU-D", "mercos_id": 50, "nome": "D"}]
    )
    _patch_store(monkeypatch, store)
    out = sb.sincronizar_produto_mercos_seguro(
        {"mercos_id": 88, "codigo": "SKU-D", "nome": "D"},
        dry_run=True,
    )
    assert out["acao"] == "dry_run_atualizaria"
    assert out["match"] == "codigo"
    assert store.writes == []
    assert store.rows[0]["mercos_id"] == 50

    out2 = sb.sincronizar_produto_mercos_seguro(
        {"mercos_id": 99, "codigo": "NOVO-DRY", "nome": "Novo"},
        dry_run=True,
    )
    assert out2["acao"] == "dry_run_criaria"
    assert len(store.rows) == 1
    assert store.writes == []


def test_nunca_associa_so_pelo_nome(monkeypatch):
    store = FakeProdutosStore(
        [
            {
                "id": "p-nome",
                "codigo": "OUTRO-COD",
                "mercos_id": 10,
                "nome": "Mesmo Nome",
            }
        ]
    )
    _patch_store(monkeypatch, store)
    out = sb.sincronizar_produto_mercos_seguro(
        {"mercos_id": 333, "codigo": "COD-DIFERENTE", "nome": "Mesmo Nome"}
    )
    assert out["acao"] == "criado"
    assert len(store.rows) == 2


def test_sync_service_dry_run_resumo(monkeypatch):
    store = FakeProdutosStore([])
    _patch_store(monkeypatch, store)

    monkeypatch.setattr(sync_mod, "mercos_configurado", lambda: True)
    monkeypatch.setattr(
        sync_mod,
        "buscar_produtos_mercos_detalhado",
        lambda **_k: {
            "produtos": [
                {"id": 1, "codigo": "A1", "nome": "Alpha", "preco_tabela": 1},
                {"id": None, "codigo": "B1", "nome": "SemId"},
            ],
            "chamadas_mercos": 1,
            "total_informado_mercos": 2,
            "unicos_recebidos": 2,
            "excluidos": 0,
            "inativos": 0,
            "ativos_processados": 2,
        },
    )
    monkeypatch.setattr(
        sync_mod,
        "carregar_indice_produtos_locais",
        lambda **_k: {
            "por_mercos_id": {},
            "por_codigo": {},
            "total_carregados": 0,
            "paginas": 0,
        },
    )
    monkeypatch.setattr(
        sync_mod,
        "normalizar_produto",
        lambda p: {
            "nome": p.get("nome"),
            "codigo": p.get("codigo"),
            "preco": p.get("preco_tabela"),
            "estoque": 0,
            "descricao": "",
        },
    )
    monkeypatch.setattr(sync_mod, "extrair_imagem_mercos", lambda p: None)
    monkeypatch.setattr(sync_mod, "invalidar_cache_produtos", lambda: None)

    resumo = sync_mod.sincronizar_produtos_mercos(dry_run=True)
    assert resumo["dry_run"] is True
    assert resumo["recebidos"] == 2
    assert resumo["novos"] == 1
    assert resumo["ignorados"] == 1
    assert "vinculados_por_ean" not in resumo
    assert store.writes == []
    assert store.rows == []


def test_compat_sincronizar_produto_mercos_string(monkeypatch):
    store = FakeProdutosStore([])
    _patch_store(monkeypatch, store)
    assert (
        sb.sincronizar_produto_mercos(
            {"mercos_id": 10, "codigo": "C10", "nome": "N", "preco_tabela": 1}
        )
        == "criado"
    )
