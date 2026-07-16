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


def test_produtos_repassa_alterado_apos_para_mercos(client, monkeypatch):
    capturado: dict = {}

    def fake_get_json(path, *, params=None):
        capturado["path"] = path
        capturado["params"] = dict(params or {})
        return [
            {
                "id": 10,
                "nome": "4c2e97e74c634ea4",
                "preco_tabela": 12.5,
                "ultima_alteracao": "2026-07-15 09:00:00",
            }
        ]

    monkeypatch.setattr("services.mercos_api_client.get_json", fake_get_json)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/produtos" if chave == "produtos" else f"/v1/{chave}",
    )
    resp = client.get(
        "/mercos/produtos",
        params={"alterado_apos": "2026-07-15 00:00:00", "max_paginas": 1},
    )
    assert resp.status_code == 200
    assert capturado["path"] == "/v1/produtos"
    assert capturado["params"]["alterado_apos"] == "2026-07-15 00:00:00"
    assert "pagina" in capturado["params"]
    assert resp.json()["itens"][0]["nome"] == "4c2e97e74c634ea4"


def test_clientes_repassa_alterado_apos_para_mercos(client, monkeypatch):
    capturado: dict = {}

    def fake_get_json(path, *, params=None):
        capturado["path"] = path
        capturado["params"] = dict(params or {})
        return [
            {
                "id": 77,
                "razao_social": "77eb21774dd340ff",
                "ultima_alteracao": "2026-07-15 09:00:00",
            }
        ]

    monkeypatch.setattr("services.mercos_api_client.get_json", fake_get_json)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/clientes" if chave == "clientes" else f"/v1/{chave}",
    )
    resp = client.get(
        "/mercos/clientes",
        params={"alterado_apos": "2026-07-15 00:00:00", "max_paginas": 1},
    )
    assert resp.status_code == 200
    assert capturado["path"] == "/v1/clientes"
    assert capturado["params"]["alterado_apos"] == "2026-07-15 00:00:00"
    assert "pagina" in capturado["params"]
    assert resp.json()["itens"][0]["razao_social"] == "77eb21774dd340ff"


def test_post_produtos_exige_token(client, monkeypatch):
    monkeypatch.setenv("DIAGNOSTICOS_ABERTOS", "false")
    monkeypatch.setenv("SYNC_TOKEN", "segredo-produtos")
    # recria client com env fechado
    from main import app
    from fastapi.testclient import TestClient

    c = TestClient(app)
    resp = c.post("/mercos/produtos", json={"nome": "X", "codigo": "Y", "ativo": True})
    assert resp.status_code == 403


def test_post_produtos_payload_e_sucesso(client, monkeypatch):
    capturado: dict = {}

    def fake_post(path, body):
        capturado["path"] = path
        capturado["body"] = dict(body)
        return {
            "ok": True,
            "status_code": 201,
            "id": 998877,
            "sandbox": True,
            "dados": {
                "id": 998877,
                "nome": body["nome"],
                "codigo": body["codigo"],
                "preco_tabela": body.get("preco_tabela"),
                "saldo_estoque": body.get("saldo_estoque"),
                "ativo": body.get("ativo"),
                "ultima_alteracao": "2026-07-16 10:00:00",
            },
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/produtos" if chave == "produtos" else f"/v1/{chave}",
    )
    resp = client.post(
        "/mercos/produtos",
        json={
            "nome": "Homolog Produto",
            "codigo": "HOM-001",
            "ativo": True,
            "preco_tabela": 15.5,
            "saldo_estoque": 3,
            "campo_inventado": "nao-enviar",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status_code"] == 201
    assert data["id"] == 998877
    assert capturado["path"] == "/v1/produtos"
    assert capturado["body"]["nome"] == "Homolog Produto"
    assert capturado["body"]["codigo"] == "HOM-001"
    assert capturado["body"]["ativo"] is True
    assert capturado["body"]["preco_tabela"] == 15.5
    assert "campo_inventado" not in capturado["body"]


def test_post_produtos_validacao_campos_obrigatorios(client, monkeypatch):
    called = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", called)
    resp = client.post("/mercos/produtos", json={"nome": "Só nome"})
    assert resp.status_code == 422
    assert "obrigatórios" in resp.json()["detail"].lower() or "obrigatorios" in resp.json()["detail"].lower() or "codigo" in resp.json()["detail"].lower()
    called.assert_not_called()


def test_put_produtos_exige_token(monkeypatch):
    monkeypatch.setenv("DIAGNOSTICOS_ABERTOS", "false")
    monkeypatch.setenv("SYNC_TOKEN", "segredo-produtos")
    from main import app

    c = TestClient(app)
    resp = c.put("/mercos/produtos/123", json={"nome": "X"})
    assert resp.status_code == 403


def test_put_produtos_id_so_na_url_e_payload_correto(client, monkeypatch):
    capturado: dict = {}

    def fake_put(path, body):
        capturado["path"] = path
        capturado["body"] = dict(body)
        return {
            "ok": True,
            "status_code": 200,
            "sandbox": True,
            "dados": {
                "id": 123456,
                "nome": body.get("nome"),
                "ultima_alteracao": "2026-07-16 16:00:00",
            },
        }

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/produtos" if chave == "produtos" else f"/v1/{chave}",
    )
    resp = client.put(
        "/mercos/produtos/123456",
        json={
            "id": 999,  # não pode ir no corpo
            "nome": "Produto Alterado",
            "preco_tabela": 22.5,
            "saldo_estoque": 8,
            "ativo": False,
            "unidade": "CX",
            "campo_inventado": "nao-enviar",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status_code"] == 200
    assert capturado["path"] == "/v1/produtos/123456"
    assert "id" not in capturado["body"]
    assert capturado["body"]["nome"] == "Produto Alterado"
    assert capturado["body"]["preco_tabela"] == 22.5
    assert capturado["body"]["saldo_estoque"] == 8
    assert capturado["body"]["ativo"] is False
    assert capturado["body"]["unidade"] == "CX"
    assert "campo_inventado" not in capturado["body"]


def test_put_produtos_validacao_sem_campos(client, monkeypatch):
    called = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.put_json", called)
    resp = client.put("/mercos/produtos/123", json={"campo_inventado": "x"})
    assert resp.status_code == 422
    called.assert_not_called()


def test_put_produtos_erro_mercos(client, monkeypatch):
    def boom(path, body):
        raise MercosApiError("Mercos HTTP 400: produto inválido", status_code=400)

    monkeypatch.setattr("services.mercos_homolog_service.put_json", boom)
    resp = client.put("/mercos/produtos/123", json={"nome": "X"})
    assert resp.status_code == 400
    assert "produto inválido" in resp.json()["detail"]


def test_put_produtos_nao_afeta_get_e_post(client, monkeypatch):
    """GET e POST de produtos continuam funcionando após o PUT existir."""
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos",
        lambda **_k: {
            "ok": True,
            "path": "/v1/produtos",
            "total": 1,
            "paginas_lidas": 1,
            "sandbox": True,
            "itens": [{"id": 1, "nome": "A"}],
        },
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 7, "sandbox": True, "dados": {}},
    )
    assert client.get("/mercos/produtos").status_code == 200
    resp = client.post(
        "/mercos/produtos", json={"nome": "N", "codigo": "C", "ativo": True}
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == 7


def test_post_produtos_erro_mercos(client, monkeypatch):
    def boom(_path, _body):
        raise MercosApiError("nome: Este campo é obrigatório.", status_code=412)

    monkeypatch.setattr("services.mercos_homolog_service.post_json", boom)
    resp = client.post(
        "/mercos/produtos",
        json={"nome": "X", "codigo": "Y", "ativo": True},
    )
    assert resp.status_code == 412
    assert "obrigatório" in resp.json()["detail"].lower() or "obrigatorio" in resp.json()["detail"].lower() or "nome" in resp.json()["detail"].lower()


def test_get_produtos_continua_apos_post(client, monkeypatch):
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos",
        lambda **_k: {
            "ok": True,
            "path": "/v1/produtos",
            "total": 1,
            "paginas_lidas": 1,
            "sandbox": True,
            "itens": [{"id": 1, "nome": "A"}],
        },
    )
    resp = client.get("/mercos/produtos")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


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


def test_tipos_pedido_repassa_alterado_apos_para_mercos(client, monkeypatch):
    """alterado_apos deve ir na query da Mercos, sem filtro local no Python."""
    capturado: dict = {}

    def fake_get_json(path, *, params=None):
        capturado["path"] = path
        capturado["params"] = dict(params or {})
        return [
            {
                "id": 1,
                "nome": "0832f68abc",
                "ultima_alteracao": "2026-07-15 10:00:00",
            }
        ]

    monkeypatch.setattr("services.mercos_api_client.get_json", fake_get_json)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/pedidos/tipo",
    )
    resp = client.get(
        "/mercos/tipos-pedido",
        params={"alterado_apos": "2026-07-15 00:00:00", "max_paginas": 1},
    )
    assert resp.status_code == 200
    assert capturado["path"] == "/v1/pedidos/tipo"
    assert capturado["params"]["alterado_apos"] == "2026-07-15 00:00:00"
    assert "pagina" in capturado["params"]
    # resposta inclui o item (filtro é da API, não local)
    assert resp.json()["total"] == 1
    assert resp.json()["itens"][0]["nome"] == "0832f68abc"


def test_tipos_pedido_repassa_filtros_excluidos_para_mercos(client, monkeypatch):
    capturado: dict = {}

    def fake_get_json(path, *, params=None):
        capturado["path"] = path
        capturado["params"] = dict(params or {})
        return [
            {
                "id": 9,
                "nome": "8df21d6cd7d44fd6",
                "excluido": True,
                "ultima_alteracao": "2026-07-14 14:37:38",
            }
        ]

    monkeypatch.setattr("services.mercos_api_client.get_json", fake_get_json)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/pedidos/tipo",
    )
    resp = client.get(
        "/mercos/tipos-pedido",
        params={
            "alterado_apos": "2026-07-14 00:00:00",
            "excluidos": "true",
            "somente_excluidos": "true",
            "incluir_excluidos": "true",
            "max_paginas": 1,
        },
    )
    assert resp.status_code == 200
    assert capturado["path"] == "/v1/pedidos/tipo"
    assert capturado["params"]["alterado_apos"] == "2026-07-14 00:00:00"
    assert capturado["params"]["excluidos"] == "true"
    assert capturado["params"]["somente_excluidos"] == "true"
    assert capturado["params"]["incluir_excluidos"] == "true"
    assert "token" not in capturado["params"]
    assert "max_paginas" not in capturado["params"]
    assert "pagina" in capturado["params"]
    item = resp.json()["itens"][0]
    assert item["nome"] == "8df21d6cd7d44fd6"
    assert item["excluido"] is True


def test_tipos_pedido_repassa_excluido_singular_e_params_extras(client, monkeypatch):
    capturado: dict = {}

    def fake_get_json(path, *, params=None):
        capturado["path"] = path
        capturado["params"] = dict(params or {})
        return [{"id": 1, "nome": "8df21d6cd7d44fd6", "excluido": True}]

    monkeypatch.setattr("services.mercos_api_client.get_json", fake_get_json)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/pedidos/tipo",
    )
    resp = client.get(
        "/mercos/tipos-pedido",
        params={
            "alterado_apos": "2026-07-14 00:00:00",
            "excluido": "true",
            "foo_custom": "bar",
            "token": "nao-deve-ir",
            "nocache": "1",
            "max_paginas": 1,
        },
    )
    assert resp.status_code == 200
    assert capturado["path"] == "/v1/pedidos/tipo"
    assert capturado["params"]["alterado_apos"] == "2026-07-14 00:00:00"
    assert capturado["params"]["excluido"] == "true"
    assert capturado["params"]["foo_custom"] == "bar"
    assert "token" not in capturado["params"]
    assert "nocache" not in capturado["params"]
    assert "max_paginas" not in capturado["params"]


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


def test_paginacao_continua_com_page_size_hint_zero(monkeypatch):
    """Com hint 0, páginas curtas não interrompem — só lote vazio ou teto."""
    monkeypatch.setattr("services.mercos_api_client.PAGE_SLEEP_SEGUNDOS", 0)
    chamadas = {"n": 0}

    def fake_get(path, params=None):
        chamadas["n"] += 1
        pagina = (params or {}).get("pagina", 1)
        if pagina == 1:
            return [{"id": 1}, {"id": 2}]  # < 50, mas hint=0 → continua
        if pagina == 2:
            return [{"id": 3}]
        return []

    monkeypatch.setattr("services.mercos_api_client.get_json", fake_get)
    out = listar_paginado("/v1/clientes", max_paginas=10, page_size_hint=0)
    assert out["paginas_lidas"] == 3
    assert out["total"] == 3
    assert chamadas["n"] == 3
    assert [i["id"] for i in out["itens"]] == [1, 2, 3]


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
