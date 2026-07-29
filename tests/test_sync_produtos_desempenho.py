"""Sync produtos: índice local único + dry-run em memória."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services import mercos_service as ms
from services import supabase_service as sb
from services import sync_mercos_service as sync_mod


class _FakeQuery:
    def __init__(self, store: "FakeStore", op: str = "select"):
        self.store = store
        self.op = op
        self._offset = 0
        self._limit_to = None
        self._eq = None
        self.payload = None
        self._on_conflict = None

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def eq(self, campo, valor):
        self._eq = (campo, valor)
        self.store.select_eq_calls += 1
        return self

    def range(self, start, end):
        self._offset = start
        self._limit_to = end
        self.store.range_calls.append((start, end))
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = dict(payload)
        return self

    def upsert(self, payload, on_conflict=None):
        self.op = "upsert"
        self.payload = payload
        self._on_conflict = on_conflict
        self.store.upsert_calls.append(payload if isinstance(payload, list) else [payload])
        return self

    def insert(self, payload):
        self.op = "insert"
        self.payload = payload
        self.store.insert_calls.append(payload)
        return self

    def execute(self):
        if self.op == "select":
            rows = list(self.store.rows)
            if self._eq:
                campo, valor = self._eq
                rows = [r for r in rows if str(r.get(campo)) == str(valor)]
            if self._limit_to is not None:
                rows = rows[self._offset : self._limit_to + 1]
            return MagicMock(data=rows)
        if self.op == "upsert":
            lote = self.payload if isinstance(self.payload, list) else [self.payload]
            for p in lote:
                mid = p.get("mercos_id")
                found = False
                for r in self.store.rows:
                    if str(r.get("mercos_id")) == str(mid):
                        r.update(p)
                        found = True
                        break
                if not found:
                    row = dict(p)
                    row.setdefault("id", self.store.next_id())
                    self.store.rows.append(row)
            return MagicMock(data=lote)
        if self.op == "update":
            return MagicMock(data=[])
        return MagicMock(data=[])


class FakeStore:
    def __init__(self, rows=None):
        self.rows = [dict(r) for r in (rows or [])]
        self.range_calls: list[tuple[int, int]] = []
        self.select_eq_calls = 0
        self.upsert_calls: list = []
        self.insert_calls: list = []
        self._seq = 0

    def next_id(self):
        self._seq += 1
        return f"id-{self._seq}"

    def table(self, name: str):
        assert name == "produtos"
        return _FakeQuery(self)


def test_carregar_indice_paginado(monkeypatch):
    rows = [{"id": f"p{i}", "mercos_id": i, "codigo": f"C{i}", "nome": f"N{i}"} for i in range(2500)]
    store = FakeStore(rows)
    monkeypatch.setattr(sb, "supabase", store)

    indice = sb.carregar_indice_produtos_locais(page_size=1000)
    assert indice["total_carregados"] == 2500
    assert indice["paginas"] == 3
    assert len(store.range_calls) == 3
    assert len(indice["por_mercos_id"]) == 2500
    assert store.select_eq_calls == 0


def test_dry_run_usa_indice_sem_eq_por_produto(monkeypatch):
    store = FakeStore(
        [
            {"id": "a", "mercos_id": 1, "codigo": "A1", "nome": "A"},
            {"id": "b", "mercos_id": 2, "codigo": "B1", "nome": "B"},
        ]
    )
    monkeypatch.setattr(sb, "supabase", store)
    monkeypatch.setattr(sync_mod, "mercos_configurado", lambda: True)
    monkeypatch.setattr(
        sync_mod,
        "buscar_produtos_mercos_detalhado",
        lambda **_k: {
            "produtos": [
                {"id": 1, "nome": "A", "codigo": "A1", "excluido": False},
                {"id": 99, "nome": "Novo", "codigo": "N1", "excluido": False},
            ],
            "chamadas_mercos": 1,
            "total_informado_mercos": 2,
            "unicos_recebidos": 2,
            "excluidos": 0,
            "inativos": 0,
            "ativos_processados": 2,
        },
    )
    monkeypatch.setattr(sync_mod, "normalizar_produto", lambda p: {
        "nome": p.get("nome"),
        "codigo": p.get("codigo"),
        "preco": 1,
        "estoque": 0,
        "descricao": "",
    })
    monkeypatch.setattr(sync_mod, "extrair_imagem_mercos", lambda p: None)

    resumo = sync_mod.sincronizar_produtos_mercos(dry_run=True)
    assert resumo["dry_run"] is True
    assert resumo["ja_vinculados"] == 1
    assert resumo["novos"] == 1
    assert store.select_eq_calls == 0
    assert store.upsert_calls == []
    assert store.insert_calls == []


def test_dry_run_milhares_sem_escrita(monkeypatch):
    n_local = 1500
    n_mercos = 3000
    store = FakeStore(
        [
            {"id": f"l{i}", "mercos_id": i, "codigo": f"C{i}", "nome": f"L{i}"}
            for i in range(n_local)
        ]
    )
    monkeypatch.setattr(sb, "supabase", store)
    monkeypatch.setattr(sync_mod, "mercos_configurado", lambda: True)
    monkeypatch.setattr(
        sync_mod,
        "buscar_produtos_mercos_detalhado",
        lambda **_k: {
            "produtos": [
                {
                    "id": i,
                    "nome": f"M{i}",
                    "codigo": f"C{i}",
                    "excluido": False,
                }
                for i in range(n_mercos)
            ],
            "chamadas_mercos": 6,
            "total_informado_mercos": n_mercos,
            "unicos_recebidos": n_mercos,
            "excluidos": 0,
            "inativos": 0,
            "ativos_processados": n_mercos,
        },
    )
    monkeypatch.setattr(sync_mod, "normalizar_produto", lambda p: {
        "nome": p.get("nome"),
        "codigo": p.get("codigo"),
        "preco": 1,
        "estoque": 0,
        "descricao": "",
    })
    monkeypatch.setattr(sync_mod, "extrair_imagem_mercos", lambda p: None)
    monkeypatch.setenv("SYNC_PRODUTOS_PROGRESSO", "1000")

    resumo = sync_mod.sincronizar_produtos_mercos(dry_run=True)
    assert resumo["ativos_processados"] == n_mercos
    assert resumo["ja_vinculados"] == n_local
    assert resumo["novos"] == n_mercos - n_local
    assert store.select_eq_calls == 0
    assert store.upsert_calls == []
    assert store.insert_calls == []


def test_modo_resumido_sem_log_excluido(monkeypatch, capsys):
    ms.invalidar_cache_produtos_mercos()
    monkeypatch.setenv("MERCOS_OCULTAR_EXEMPLOS", "false")
    monkeypatch.delenv("SYNC_PRODUTOS_LOG_DETALHADO", raising=False)

    def fake_exec(*_a, **_k):
        r = MagicMock()
        r.status_code = 200
        r.headers = {
            "MEUSPEDIDOS_LIMITOU_REGISTROS": "0",
            "MEUSPEDIDOS_REQUISICOES_EXTRAS": "0",
            "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "2",
        }
        r.json.return_value = [
            {"id": 1, "nome": "Ok", "codigo": "A", "excluido": False, "ativo": True},
            {"id": 2, "nome": "X", "codigo": "B", "excluido": True, "ativo": True},
        ]
        return r

    monkeypatch.setattr(ms, "_executar_requisicao_mercos", fake_exec)
    out = ms.buscar_produtos_mercos_detalhado(usar_cache=False)
    assert out["excluidos"] == 1
    assert len(out["produtos"]) == 1
    logged = capsys.readouterr().out
    assert "EVT=sync_produto_ignorado" not in logged
    assert "excluidos=1" in logged


def test_total_informado_preserva_maior(monkeypatch):
    ms.invalidar_cache_produtos_mercos()
    monkeypatch.setenv("MERCOS_OCULTAR_EXEMPLOS", "false")
    chamadas = []

    def fake_exec(method, path, params=None, **_k):
        n = len(chamadas)
        chamadas.append(1)
        r = MagicMock()
        r.status_code = 200
        if n == 0:
            r.headers = {
                "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                "MEUSPEDIDOS_REQUISICOES_EXTRAS": "1",
                "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "11558",
            }
            r.json.return_value = [
                {
                    "id": 1,
                    "nome": "A",
                    "excluido": False,
                    "ultima_alteracao": "2024-01-01 00:00:00",
                }
            ]
        else:
            # último lote com total residual/errado
            r.headers = {
                "MEUSPEDIDOS_LIMITOU_REGISTROS": "0",
                "MEUSPEDIDOS_REQUISICOES_EXTRAS": "0",
                "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "59",
            }
            r.json.return_value = [
                {
                    "id": 2,
                    "nome": "B",
                    "excluido": False,
                    "ultima_alteracao": "2024-01-02 00:00:00",
                }
            ]
        return r

    monkeypatch.setattr(ms, "_executar_requisicao_mercos", fake_exec)
    out = ms.buscar_produtos_mercos_detalhado(usar_cache=False)
    assert out["total_informado_mercos"] == 11558
    assert out["unicos_recebidos"] == 2


def test_timeout_mensagem_clara(monkeypatch):
    class Boom(Exception):
        pass

    class ReadTimeout(Boom):
        pass

    monkeypatch.setattr(
        ms,
        "_requisicao_produtos",
        lambda *_a, **_k: (_ for _ in ()).throw(ReadTimeout("timed out")),
    )
    ms.invalidar_cache_produtos_mercos()
    with pytest.raises(ValueError, match="timeout"):
        ms.buscar_produtos_mercos_detalhado(usar_cache=False)


def test_upsert_em_lote_on_conflict_mercos_id(monkeypatch):
    store = FakeStore([])
    monkeypatch.setattr(sb, "supabase", store)
    n = sb.upsert_produtos_mercos_em_lote(
        [
            {"mercos_id": 1, "nome": "A", "codigo": "A", "preco_tabela": 1},
            {"mercos_id": 2, "nome": "B", "codigo": "B", "preco_tabela": 2},
        ],
        batch_size=100,
    )
    assert n == 2
    assert store.upsert_calls
    assert store.upsert_calls[0][0]["mercos_id"] == 1
