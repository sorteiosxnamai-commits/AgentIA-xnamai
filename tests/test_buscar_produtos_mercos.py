"""buscar_produtos_mercos: paginação por alterado_apos (sem pagina)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from services import mercos_service as ms


@pytest.fixture(autouse=True)
def _limpar_cache(monkeypatch):
    ms.invalidar_cache_produtos_mercos()
    monkeypatch.setenv("MERCOS_OCULTAR_EXEMPLOS", "false")
    monkeypatch.setenv("MERCOS_PRODUTOS_MAX_CHAMADAS", "100")
    monkeypatch.setenv("MERCOS_PRODUTOS_ALTERADO_APOS", "2000-01-01T00:00:00")
    yield
    ms.invalidar_cache_produtos_mercos()


def _resp(payload, *, headers=None, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    r.headers = headers or {}
    return r


def _headers(*, limitou=0, total=None, extras=0):
    h = {
        "MEUSPEDIDOS_LIMITOU_REGISTROS": str(limitou),
        "MEUSPEDIDOS_REQUISICOES_EXTRAS": str(extras),
    }
    if total is not None:
        h["MEUSPEDIDOS_QTDE_TOTAL_REGISTROS"] = str(total)
    return h


def test_lote_unico_menor_que_500(monkeypatch):
    chamadas = []

    def fake_exec(method, path, params=None, json_body=None, timeout=15):
        chamadas.append({"method": method, "path": path, "params": dict(params or {})})
        return _resp(
            [
                {
                    "id": 20386165,
                    "nome": "A",
                    "excluido": False,
                    "ultima_alteracao": "2024-01-01 10:00:00",
                },
                {
                    "id": 2,
                    "nome": "B",
                    "excluido": False,
                    "ultima_alteracao": "2024-01-02 10:00:00",
                },
            ],
            headers=_headers(limitou=0, total=2, extras=0),
        )

    monkeypatch.setattr(ms, "_executar_requisicao_mercos", fake_exec)
    out = ms.buscar_produtos_mercos()

    assert len(chamadas) == 1
    assert chamadas[0]["method"] == "GET"
    assert chamadas[0]["path"] == "/v1/produtos"
    assert chamadas[0]["params"]["excluido"] == "false"
    assert chamadas[0]["params"]["alterado_apos"] == "2000-01-01T00:00:00"
    assert "pagina" not in chamadas[0]["params"]
    assert len(out) == 2
    assert out[0]["id"] == 20386165


def test_varios_lotes(monkeypatch):
    chamadas = []

    def fake_exec(method, path, params=None, json_body=None, timeout=15):
        n = len(chamadas)
        chamadas.append(dict(params or {}))
        if n == 0:
            return _resp(
                [
                    {
                        "id": 1,
                        "nome": "A",
                        "excluido": False,
                        "ultima_alteracao": "2024-01-01 00:00:00",
                    },
                    {
                        "id": 2,
                        "nome": "B",
                        "excluido": False,
                        "ultima_alteracao": "2024-01-02 00:00:00",
                    },
                ],
                headers=_headers(limitou=1, total=4, extras=1),
            )
        return _resp(
            [
                {
                    "id": 3,
                    "nome": "C",
                    "excluido": False,
                    "ultima_alteracao": "2024-01-03 00:00:00",
                },
                {
                    "id": 4,
                    "nome": "D",
                    "excluido": False,
                    "ultima_alteracao": "2024-01-04 00:00:00",
                },
            ],
            headers=_headers(limitou=0, total=4, extras=0),
        )

    monkeypatch.setattr(ms, "_executar_requisicao_mercos", fake_exec)
    out = ms.buscar_produtos_mercos()
    assert len(chamadas) == 2
    assert chamadas[0]["alterado_apos"] == "2000-01-01T00:00:00"
    assert chamadas[1]["alterado_apos"] == "2024-01-02 00:00:00"
    assert [p["id"] for p in out] == [1, 2, 3, 4]


def test_ids_repetidos_entre_lotes(monkeypatch):
    def fake_exec(method, path, params=None, json_body=None, timeout=15):
        cursor = (params or {}).get("alterado_apos")
        if cursor == "2000-01-01T00:00:00":
            return _resp(
                [
                    {
                        "id": 10,
                        "nome": "A",
                        "excluido": False,
                        "ultima_alteracao": "2024-06-01 12:00:00",
                    },
                    {
                        "id": 11,
                        "nome": "B",
                        "excluido": False,
                        "ultima_alteracao": "2024-06-01 12:00:00",
                    },
                ],
                headers=_headers(limitou=1, total=3, extras=1),
            )
        return _resp(
            [
                {
                    "id": 11,
                    "nome": "B2",
                    "excluido": False,
                    "ultima_alteracao": "2024-06-01 12:00:00",
                },
                {
                    "id": 12,
                    "nome": "C",
                    "excluido": False,
                    "ultima_alteracao": "2024-06-02 12:00:00",
                },
            ],
            headers=_headers(limitou=0, total=3, extras=0),
        )

    monkeypatch.setattr(ms, "_executar_requisicao_mercos", fake_exec)
    out = ms.buscar_produtos_mercos()
    assert len(out) == 3
    assert {p["id"] for p in out} == {10, 11, 12}


def test_mesma_ultima_alteracao_entre_lotes(monkeypatch):
    """Repete o timestamp final; dedupe por id; avança quando há IDs novos."""
    chamadas = []

    def fake_exec(method, path, params=None, json_body=None, timeout=15):
        chamadas.append(dict(params or {}))
        if len(chamadas) == 1:
            return _resp(
                [
                    {
                        "id": 1,
                        "nome": "A",
                        "excluido": False,
                        "ultima_alteracao": "2025-01-01 00:00:00",
                    },
                ],
                headers=_headers(limitou=1, total=2, extras=1),
            )
        return _resp(
            [
                {
                    "id": 1,
                    "nome": "A",
                    "excluido": False,
                    "ultima_alteracao": "2025-01-01 00:00:00",
                },
                {
                    "id": 2,
                    "nome": "B",
                    "excluido": False,
                    "ultima_alteracao": "2025-01-01 00:00:00",
                },
            ],
            headers=_headers(limitou=0, total=2, extras=0),
        )

    monkeypatch.setattr(ms, "_executar_requisicao_mercos", fake_exec)
    out = ms.buscar_produtos_mercos()
    assert chamadas[1]["alterado_apos"] == "2025-01-01 00:00:00"
    assert len(out) == 2


def test_cursor_sem_progresso(monkeypatch):
    def fake_exec(method, path, params=None, json_body=None, timeout=15):
        return _resp(
            [
                {
                    "id": 1,
                    "nome": "A",
                    "excluido": False,
                    "ultima_alteracao": "2024-01-01 00:00:00",
                },
            ],
            headers=_headers(limitou=1, total=99, extras=5),
        )

    monkeypatch.setattr(ms, "_executar_requisicao_mercos", fake_exec)
    # 1ª chamada acumula id=1; 2ª com mesmo cursor/mesmo id → sem progresso
    with pytest.raises(ValueError, match="sem progresso"):
        ms.buscar_produtos_mercos()


def test_resposta_vazia(monkeypatch):
    monkeypatch.setattr(
        ms,
        "_executar_requisicao_mercos",
        lambda *a, **k: _resp([], headers=_headers(limitou=0, total=0, extras=0)),
    )
    assert ms.buscar_produtos_mercos() == []


def test_resposta_nao_lista(monkeypatch):
    monkeypatch.setattr(
        ms,
        "_executar_requisicao_mercos",
        lambda *a, **k: _resp({"produtos": [{"id": 1}]}),
    )
    with pytest.raises(ValueError, match="lista"):
        ms.buscar_produtos_mercos()


def test_erro_conexao(monkeypatch):
    def boom(*_a, **_k):
        raise requests.exceptions.ConnectionError("falha de rede")

    monkeypatch.setattr(ms, "_executar_requisicao_mercos", boom)
    with pytest.raises(requests.exceptions.ConnectionError):
        ms.buscar_produtos_mercos()


def test_limite_maximo_chamadas(monkeypatch):
    monkeypatch.setenv("MERCOS_PRODUTOS_MAX_CHAMADAS", "3")

    def fake_exec(method, path, params=None, json_body=None, timeout=15):
        n = len(getattr(fake_exec, "n", []))
        fake_exec.n = getattr(fake_exec, "n", [])
        fake_exec.n.append(1)
        return _resp(
            [
                {
                    "id": n + 1,
                    "nome": f"P{n}",
                    "excluido": False,
                    "ultima_alteracao": f"2024-01-0{n + 1} 00:00:00",
                }
            ],
            headers=_headers(limitou=1, total=100, extras=50),
        )

    monkeypatch.setattr(ms, "_executar_requisicao_mercos", fake_exec)
    with pytest.raises(ValueError, match="limite de segurança"):
        ms.buscar_produtos_mercos()


def test_nao_envia_pagina_em_lote_grande(monkeypatch):
    """Lote de 64 com LIMITOU=0 → uma chamada; nunca envia pagina."""
    chamadas = []
    lote = [
        {
            "id": i,
            "nome": f"P{i}",
            "excluido": False,
            "ultima_alteracao": "2024-01-01 00:00:00",
        }
        for i in range(64)
    ]

    def fake_exec(method, path, params=None, **_k):
        chamadas.append(dict(params or {}))
        return _resp(lote, headers=_headers(limitou=0, total=64, extras=0))

    monkeypatch.setattr(ms, "_executar_requisicao_mercos", fake_exec)
    out = ms.buscar_produtos_mercos()
    assert len(chamadas) == 1
    assert "pagina" not in chamadas[0]
    assert len(out) == 64


def test_produto_excluido_conta_sem_log_padrao(monkeypatch, capsys):
    lote = [
        {"id": 1, "nome": "Ok", "codigo": "A", "excluido": False, "ativo": True},
        {
            "id": 20400678,
            "nome": "d9b02dfac23a4192",
            "codigo": "HOM-PROD-001",
            "excluido": True,
            "ativo": True,
        },
    ]
    monkeypatch.setattr(
        ms,
        "_executar_requisicao_mercos",
        lambda *a, **k: _resp(lote, headers=_headers(limitou=0, total=2)),
    )
    monkeypatch.delenv("SYNC_PRODUTOS_LOG_DETALHADO", raising=False)
    out = ms.buscar_produtos_mercos_detalhado(usar_cache=False)
    assert len(out["produtos"]) == 1
    assert out["excluidos"] == 1
    logged = capsys.readouterr().out
    assert "EVT=sync_produto_ignorado" not in logged


def test_produto_excluido_loga_se_detalhado(monkeypatch, capsys):
    lote = [
        {"id": 1, "nome": "Ok", "codigo": "A", "excluido": False, "ativo": True},
        {
            "id": 20400678,
            "nome": "d9b02dfac23a4192",
            "codigo": "HOM-PROD-001",
            "excluido": True,
            "ativo": True,
        },
    ]
    monkeypatch.setattr(
        ms,
        "_executar_requisicao_mercos",
        lambda *a, **k: _resp(lote, headers=_headers(limitou=0, total=2)),
    )
    monkeypatch.setenv("SYNC_PRODUTOS_LOG_DETALHADO", "true")
    out = ms.buscar_produtos_mercos_detalhado(usar_cache=False)
    assert out["excluidos"] == 1
    logged = capsys.readouterr().out
    assert "EVT=sync_produto_ignorado" in logged
    assert "motivo=excluido" in logged
    assert "mercos_id=20400678" in logged


def test_dry_run_sync_sem_escrita(monkeypatch):
    from services import sync_mercos_service as sync_mod

    writes = {"n": 0}

    def fake_seguro(dados, *, dry_run=False, log_item=True, indice=None, defer_upsert=False):
        if not dry_run:
            writes["n"] += 1
            raise AssertionError("dry-run não deve gravar")
        return {"acao": "dry_run_criaria", "match": None}

    monkeypatch.setattr(sync_mod, "mercos_configurado", lambda: True)
    monkeypatch.setattr(
        sync_mod,
        "buscar_produtos_mercos_detalhado",
        lambda **_k: {
            "produtos": [
                {"id": i, "nome": f"P{i}", "codigo": f"C{i}", "excluido": False}
                for i in range(5)
            ],
            "chamadas_mercos": 1,
            "total_informado_mercos": 5,
            "unicos_recebidos": 5,
            "excluidos": 0,
            "inativos": 0,
            "ativos_processados": 5,
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
            "preco": 1,
            "estoque": 0,
            "descricao": "",
        },
    )
    monkeypatch.setattr(sync_mod, "extrair_imagem_mercos", lambda p: None)
    monkeypatch.setattr(sync_mod, "sincronizar_produto_mercos_seguro", fake_seguro)
    monkeypatch.setattr(
        sync_mod,
        "invalidar_cache_produtos",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run")),
    )

    resumo = sync_mod.sincronizar_produtos_mercos(dry_run=True)
    assert resumo["dry_run"] is True
    assert resumo["novos"] == 5
    assert writes["n"] == 0
