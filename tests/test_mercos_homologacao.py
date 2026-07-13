"""Testes das rotas de homologação Mercos (mocks — sem chamar sandbox)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import routes.mercos_homolog as rh
from services.mercos_api_client import MercosApiError, listar_paginado, request_mercos


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DIAGNOSTICOS_ABERTOS", "true")
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    from main import app

    return TestClient(app)


def test_homologacao_status(client, monkeypatch):
    monkeypatch.setattr(rh, "mercos_configurado", lambda: True)
    monkeypatch.setattr(rh, "mercos_ambiente_sandbox", lambda: True)
    resp = client.get("/mercos/homologacao")
    assert resp.status_code == 200
    data = resp.json()
    assert data["checkout_create_order_agente"] == "false"
    assert "entidades" in data
    assert data["company_token_env"] == "MERCOS_COMPANY_TOKEN"
    # Nenhum token na resposta
    blob = str(data).lower()
    assert "companytoken" not in blob or data["company_token_env"] == "MERCOS_COMPANY_TOKEN"
    assert "7a1540f6" not in blob


def test_get_produtos_lista(client, monkeypatch):
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos",
        lambda **_k: {
            "ok": True,
            "path": "/v1/produtos",
            "total": 2,
            "paginas_lidas": 1,
            "sandbox": True,
            "itens": [{"id": 1, "nome": "A"}, {"id": 2, "nome": "B"}],
        },
    )
    resp = client.get("/mercos/produtos")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_get_clientes_categorias_etc(client, monkeypatch):
    fake = lambda **_k: {"ok": True, "total": 1, "itens": [{"id": 1}], "paginas_lidas": 1, "sandbox": True, "path": "/x"}
    for nome in (
        "listar_categorias",
        "listar_clientes",
        "listar_condicoes_pagamento",
        "listar_segmentos",
        "listar_tabelas_preco",
        "listar_usuarios",
    ):
        monkeypatch.setattr(f"services.mercos_homolog_service.{nome}", fake)
    assert client.get("/mercos/categorias").status_code == 200
    assert client.get("/mercos/clientes").status_code == 200
    assert client.get("/mercos/condicoes-pagamento").status_code == 200
    assert client.get("/mercos/segmentos").status_code == 200
    assert client.get("/mercos/tabelas-preco").status_code == 200
    assert client.get("/mercos/usuarios").status_code == 200


def test_put_pedido_nao_envia_id_no_body(monkeypatch):
    """Mercos rejeita extra keys @ data['id'] — id deve ir só na URL."""
    capturado: dict = {}

    def _fake_put(path, body):
        capturado["path"] = path
        capturado["body"] = body
        return {"ok": True, "status_code": 200, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.put_json",
        _fake_put,
    )
    from services.mercos_homolog_service import alterar_pedido

    body = {
        "id": 999,  # se vier do cliente, deve ser removido
        "cliente_id": 9289641,
        "condicao_pagamento_id": 264893,
        "data_emissao": "2026-07-13",
        "itens": [
            {
                "produto_id": 20386169,
                "quantidade": 2,
                "preco_bruto": 249.90,
            }
        ],
    }
    out = alterar_pedido(2149596, body)
    assert out["ok"] is True
    assert capturado["path"] == "/v1/pedidos/2149596"
    assert "id" not in capturado["body"]
    assert capturado["body"]["cliente_id"] == 9289641
    assert capturado["body"]["itens"][0]["produto_id"] == 20386169
    assert capturado["body"]["itens"][0]["quantidade"] == 2
    assert capturado["body"]["itens"][0]["preco_bruto"] == 249.90


def test_post_put_clientes_pedidos_titulos(client, monkeypatch):
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_cliente",
        lambda body: {"ok": True, "id": 99, "dados": body},
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.alterar_cliente",
        lambda cid, body: {"ok": True, "dados": {"id": cid, **body}},
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_pedido",
        lambda body: {"ok": True, "id": 55, "dados": body},
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.alterar_pedido",
        lambda pid, body: {"ok": True, "dados": {"id": pid}},
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_titulo",
        lambda body: {"ok": True, "id": 7, "dados": body},
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.alterar_titulo",
        lambda tid, body: {"ok": True, "dados": {"id": tid}},
    )
    assert client.post("/mercos/clientes", json={"razao_social": "Teste"}).json()["id"] == 99
    assert client.put("/mercos/clientes/99", json={"nome_fantasia": "X"}).status_code == 200
    assert client.post("/mercos/pedidos", json={"cliente_id": 1}).json()["id"] == 55
    assert client.put("/mercos/pedidos/55", json={"observacoes": "ok"}).status_code == 200
    assert client.post("/mercos/titulos", json={"valor": 10}).json()["id"] == 7
    assert client.put("/mercos/titulos/7", json={"valor": 11}).status_code == 200


def test_erro_mercos_vira_http_exception(client, monkeypatch):
    def _boom(**_k):
        raise MercosApiError("Mercos HTTP 404: not found", status_code=404)

    monkeypatch.setattr("services.mercos_homolog_service.listar_tipos_pedido", _boom)
    resp = client.get("/mercos/tipos-pedido")
    assert resp.status_code == 404
    assert "404" in resp.json()["detail"]
    assert "token" not in resp.json()["detail"].lower() or "CompanyToken" not in resp.json()["detail"]


def test_bloqueio_sem_token(monkeypatch):
    monkeypatch.setenv("DIAGNOSTICOS_ABERTOS", "false")
    monkeypatch.setenv("SYNC_TOKEN", "segredo-teste")
    from main import app

    c = TestClient(app)
    resp = c.get("/mercos/produtos")
    assert resp.status_code == 403


def test_paginacao_para_quando_lote_curto(monkeypatch):
    chamadas = {"n": 0}

    def fake_get(path, params=None):
        chamadas["n"] += 1
        pagina = (params or {}).get("pagina", 1)
        if pagina == 1:
            return [{"id": i} for i in range(50)]
        if pagina == 2:
            return [{"id": 100}]  # < 50 → para
        return []

    monkeypatch.setattr("services.mercos_api_client.get_json", fake_get)
    out = listar_paginado("/v1/produtos", max_paginas=10, page_size_hint=50)
    assert out["paginas_lidas"] == 2
    assert out["total"] == 51
    assert chamadas["n"] == 2


def test_paginacao_respeita_max_paginas(monkeypatch):
    monkeypatch.setattr(
        "services.mercos_api_client.get_json",
        lambda path, params=None: [{"id": i} for i in range(50)],
    )
    out = listar_paginado("/v1/produtos", max_paginas=3, page_size_hint=50)
    assert out["paginas_lidas"] == 3
    assert out["total"] == 150


def test_429_esgota_retries(monkeypatch):
    resp = MagicMock()
    resp.status_code = 429
    resp.text = "too many"
    monkeypatch.setattr(
        "services.mercos_api_client.mercos_configurado",
        lambda: True,
    )
    monkeypatch.setenv("MERCOS_COMPANY_TOKEN", "x")
    monkeypatch.setattr(
        "services.mercos_api_client._application_tokens",
        lambda: ["app-token-fake"],
    )
    sleeps: list[int] = []

    monkeypatch.setattr("services.mercos_api_client.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(
        "services.mercos_api_client.requests.request",
        lambda *a, **k: resp,
    )
    with pytest.raises(MercosApiError) as ei:
        request_mercos("GET", "/v1/produtos")
    assert ei.value.status_code == 429
    assert len(sleeps) == 2  # 3 tentativas → 2 sleeps


def test_request_nao_loga_token(monkeypatch, capsys):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "[]"
    resp.json.return_value = []
    monkeypatch.setattr("services.mercos_api_client.mercos_configurado", lambda: True)
    monkeypatch.setenv("MERCOS_COMPANY_TOKEN", "SEGREDO_COMPANY")
    monkeypatch.setattr(
        "services.mercos_api_client._application_tokens",
        lambda: ["SEGREDO_APP"],
    )
    captured = {}

    def _req(*a, **k):
        captured["headers"] = k.get("headers")
        return resp

    monkeypatch.setattr("services.mercos_api_client.requests.request", _req)
    request_mercos("GET", "/v1/produtos")
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "SEGREDO_COMPANY" not in out
    assert "SEGREDO_APP" not in out
    # headers existem na chamada, mas não foram impressos
    assert captured["headers"]["CompanyToken"] == "SEGREDO_COMPANY"
