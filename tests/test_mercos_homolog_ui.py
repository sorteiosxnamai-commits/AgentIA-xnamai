"""Testes da UI visual de homologação Mercos."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DIAGNOSTICOS_ABERTOS", "false")
    monkeypatch.setenv("SYNC_TOKEN", "segredo-ui-homolog")
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    from main import app

    return TestClient(app)


def test_homologacao_ui_exige_token(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    resp = client.get("/mercos/homologacao-ui")
    assert resp.status_code == 403


def test_homologacao_ui_token_invalido_403(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    resp = client.get("/mercos/homologacao-ui?token=errado")
    assert resp.status_code == 403


def test_homologacao_ui_token_valido_200(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    criar_cliente = MagicMock()
    criar_pedido = MagicMock()
    criar_titulo = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_cliente", criar_cliente
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_pedido", criar_pedido
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_titulo", criar_titulo
    )

    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    body = resp.text
    assert "Xnamai ERP - Homologação Mercos Sandbox" in body
    assert "Origem dos dados:" in body
    assert "Mercos Sandbox" in body
    assert "Status visual:" in body
    assert "Aprovado" in body
    assert "Número do documento" in body
    assert "HOMOLOG-001" in body
    assert "configurad" not in body.lower()
    assert "configuração" not in body.lower()
    # Não vazar token / JSON cru na tela
    assert "segredo-ui-homolog" not in body
    assert "CompanyToken" not in body
    assert '"itens"' not in body

    criar_cliente.assert_not_called()
    criar_pedido.assert_not_called()
    criar_titulo.assert_not_called()


def test_acao_produtos_exige_auth(client):
    resp = client.post("/mercos/homologacao-ui/acoes/produtos")
    assert resp.status_code == 403


def test_incluir_titulo_envia_numero_documento(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    capturado: dict = {}

    def _fake_criar(body):
        capturado["body"] = dict(body)
        return {"ok": True, "status_code": 201, "id": 777, "dados": {"id": 777}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_titulo", _fake_criar
    )

    # Autentica via cookie da página
    page = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    assert page.status_code == 200

    resp = client.post(
        "/mercos/homologacao-ui/acoes/titulos-criar",
        data={
            "cliente_id": "9289641",
            "valor": "100.00",
            "numero_documento": "HOMOLOG-001",
        },
    )
    assert resp.status_code == 200
    body = capturado["body"]
    assert body["cliente_id"] == 9289641
    assert body["valor"] == 100.0
    assert body["numero_documento"] == "HOMOLOG-001"
    assert len(body["numero_documento"]) <= 18
    assert "data_emissao" in body
    assert "data_vencimento" in body
    html = resp.text
    assert "777" in html
    assert "HOMOLOG-001" in html
    assert "201" in html
    assert "{" not in html or '"cliente_id"' not in html


def test_incluir_titulo_gera_numero_documento_se_vazio(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    capturado: dict = {}

    def _fake_criar(body):
        capturado["body"] = dict(body)
        return {"ok": True, "status_code": 201, "id": 778, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_titulo", _fake_criar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/titulos-criar",
        data={"cliente_id": "1", "valor": "50", "numero_documento": ""},
    )
    assert resp.status_code == 200
    doc = capturado["body"]["numero_documento"]
    assert doc.startswith("HOMOLOG-")
    assert len(doc) <= 18


def test_alterar_titulo_envia_numero_documento(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    capturado: dict = {}

    def _fake_alterar(titulo_id, body):
        capturado["id"] = titulo_id
        capturado["body"] = dict(body)
        return {"ok": True, "status_code": 200, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.alterar_titulo", _fake_alterar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/titulos-alterar",
        data={
            "titulo_id": "555",
            "valor": "150.00",
            "numero_documento": "HOMOLOG-ALT01",
        },
    )
    assert resp.status_code == 200
    assert capturado["id"] == "555"
    assert capturado["body"]["numero_documento"] == "HOMOLOG-ALT01"
    assert len(capturado["body"]["numero_documento"]) <= 18
    assert "HOMOLOG-ALT01" in resp.text
    assert "200" in resp.text


def test_homologacao_ui_tem_15_secoes_obrigatorias(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    assert resp.status_code == 200
    body = resp.text
    obrigatorias = [
        "Produto — Buscar",
        "Produto — Cadastrar",
        "Categoria de produto — Buscar",
        "Cliente — Buscar",
        "Cliente — Incluir",
        "Cliente — Alterar",
        "Condições de pagamento — Buscar",
        "Segmentos de Clientes — Buscar",
        "Tabela de preço — Buscar",
        "Tabela de preço por produto — Buscar",
        "Tipo de Pedido — Buscar",
        "Usuários — Buscar",
        "Pedido — Incluir",
        "Pedido — Alterar",
        "Títulos — Incluir",
        "Títulos — Alterar",
    ]
    for titulo in obrigatorias:
        assert titulo in body, f"Seção ausente: {titulo}"
    assert "tabela de preço cadastrada no sandbox" in body
    assert "Buscar Tipo de Pedido" in body
    assert "Buscar excluídos/alterados" in body
    assert "Buscar excluído singular" in body
    assert "Tentar todos os filtros" in body
    assert 'data-action="/mercos/homologacao-ui/acoes/tipos-pedido"' in body
    assert body.count("Número do documento") >= 2
    assert "Sincronizar próxima etapa" in body
    assert "Reiniciar ciclo de sincronização" in body
    assert "Localizar produto pelo nome" in body
    assert "mercos_produtos_cursor" in body
    assert "mercos_produtos_catalogo" in body
    assert "btn-produtos-sincronizar" in body
    assert "btn-produtos-buscar" in body
    assert "Busca completa bloqueada durante a homologação" in body
    assert "Produto — Cadastrar" in body
    assert 'data-action="/mercos/homologacao-ui/acoes/produtos-criar"' in body
    assert "Localizar cliente pela razão social" in body
    assert "mercos_clientes_cursor" in body
    assert "mercos_clientes_catalogo" in body
    assert "btn-clientes-sincronizar" in body
    assert "btn-clientes-buscar" in body
    assert "btn-clientes-reiniciar" in body
    assert "btn-clientes-localizar" in body
    assert body.count("Sincronizar próxima etapa") >= 2
    assert body.count("Reiniciar ciclo de sincronização") >= 2


def test_acao_produtos_criar_sucesso_sem_interferir_ciclo(client, monkeypatch):
    from services import mercos_produtos_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    capturado: dict = {}

    def fake_criar(body):
        capturado["body"] = dict(body)
        return {
            "ok": True,
            "status_code": 201,
            "id": 555,
            "dados": {
                "id": 555,
                "nome": body["nome"],
                "codigo": body["codigo"],
                "preco_tabela": body.get("preco_tabela"),
                "saldo_estoque": body.get("saldo_estoque"),
                "ativo": body.get("ativo"),
                "ultima_alteracao": "2026-07-16 12:00:00",
            },
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_produto", fake_criar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    sessao = client.cookies.get("mercos_produtos_sessao")
    etapa_antes = cat.obter_ciclo(sessao)["etapa_interna"]
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-criar",
        data={
            "nome": "Produto Homolog",
            "codigo": "HOM-P-01",
            "preco_tabela": "19.90",
            "saldo_estoque": "5",
            "ativo": "true",
            "unidade": "UN",
        },
    )
    assert resp.status_code == 200
    html = resp.text
    assert "Produto cadastrado" in html
    assert "Status HTTP" in html
    assert "555" in html
    assert "19.9" in html
    assert "Preço tabela" in html
    assert '"dados"' not in html
    assert capturado["body"]["nome"] == "Produto Homolog"
    assert capturado["body"]["codigo"] == "HOM-P-01"
    assert capturado["body"]["ativo"] is True
    assert capturado["body"]["preco_tabela"] == 19.9
    assert cat.obter_ciclo(sessao)["etapa_interna"] == etapa_antes
    assert cat.obter_ciclo(sessao)["ativo"] is True


def test_acao_produtos_repassa_alterado_apos_e_destaca(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    capturado: dict = {}

    def fake_listar(**kwargs):
        capturado["kwargs"] = dict(kwargs)
        return {
            "ok": True,
            "total": 3,
            "itens": [
                {
                    "id": 1,
                    "nome": "4c2e97e74c634ea4",
                    "codigo": "A",
                    "preco_tabela": 10,
                    "estoque": 1,
                    "excluido": False,
                    "ultima_alteracao": "2026-07-15 10:00:00",
                },
                {
                    "id": 2,
                    "nome": "87109c4efa4b4f3f",
                    "codigo": "B",
                    "preco_tabela": 20,
                    "saldo_estoque": 2,
                    "ativo": True,
                },
                {
                    "id": 3,
                    "nome": "Produto Normal",
                    "codigo": "C",
                    "preco_tabela": 5,
                    "estoque": 0,
                    "ativo": True,
                },
            ],
            "filtros": {"alterado_apos": "2026-07-15 00:00:00"},
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos",
        data={"alterado_apos": "2026-07-15 00:00:00"},
    )
    assert resp.status_code == 200
    assert capturado["kwargs"].get("alterado_apos") == "2026-07-15 00:00:00"
    html = resp.text
    assert "Filtro usado: alterado_apos =" in html
    assert "2026-07-15 00:00:00" in html
    assert "Última alteração" in html
    assert "4c2e97e74c634ea4" in html
    assert html.count("destaque-homolog") >= 2
    assert '"itens"' not in html


def test_produtos_sync_primeira_sem_alterado_apos(client, monkeypatch):
    from services import mercos_produtos_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    capturado: dict = {}

    def fake_listar(**kwargs):
        capturado["kwargs"] = dict(kwargs)
        return {
            "ok": True,
            "path": "/v1/produtos",
            "total": 2,
            "itens": [
                {
                    "id": 1,
                    "nome": "4c2e97e74c634ea4",
                    "preco_tabela": 11.5,
                    "ultima_alteracao": "2026-07-14 10:00:00",
                    "ativo": True,
                },
                {
                    "id": 2,
                    "nome": "outro",
                    "preco_tabela": 9,
                    "ultima_alteracao": "2026-07-15 12:30:00",
                    "ativo": True,
                },
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/produtos-sincronizar")
    assert resp.status_code == 200
    assert capturado["kwargs"].get("alterado_apos") in (None, "")
    html = resp.text
    assert "Tipo da última busca" in html
    assert "Completa" in html
    assert "Etapa interna" in html
    assert "1/3" in html
    assert "Chamadas completas no ciclo" in html
    assert "Novo cursor" in html
    assert "2026-07-15 12:30:00" in html
    from urllib.parse import unquote

    cookie_raw = (resp.cookies.get("mercos_produtos_cursor") or "").strip('"')
    assert unquote(cookie_raw) == "2026-07-15 12:30:00"
    assert "data-novo-cursor=\"2026-07-15 12:30:00\"" in html
    assert '"itens"' not in html


def test_produtos_sync_segunda_com_cursor_anterior(client, monkeypatch):
    from services import mercos_produtos_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    capturado: dict = {}
    fase = {"n": 0}

    def fake_listar(**kwargs):
        fase["n"] += 1
        capturado["kwargs"] = dict(kwargs)
        if fase["n"] == 1:
            return {
                "ok": True,
                "total": 1,
                "itens": [
                    {
                        "id": 1,
                        "nome": "base",
                        "preco_tabela": 1,
                        "ultima_alteracao": "2026-07-15 12:30:00",
                        "ativo": True,
                    }
                ],
            }
        return {
            "ok": True,
            "total": 1,
            "itens": [
                {
                    "id": 9,
                    "nome": "5db65d7102b54a98",
                    "preco_tabela": 33,
                    "ultima_alteracao": "2026-07-16 08:00:00",
                    "ativo": True,
                }
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    r1 = client.post("/mercos/homologacao-ui/acoes/produtos-sincronizar")
    assert r1.status_code == 200
    assert "1/3" in r1.text
    cursor_anterior = "2026-07-15 12:30:00"
    esperado_enviado = "2026-07-15 12:29:59"
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-sincronizar",
        data={"cursor": cursor_anterior},
    )
    assert resp.status_code == 200
    assert capturado["kwargs"].get("alterado_apos") == esperado_enviado
    html = resp.text
    assert "Incremental" in html
    assert "2/3" in html
    assert "Cursor base" in html
    assert cursor_anterior in html
    assert esperado_enviado in html
    assert "2026-07-16 08:00:00" in html
    from urllib.parse import unquote

    cookie_raw = (resp.cookies.get("mercos_produtos_cursor") or "").strip('"')
    assert unquote(cookie_raw) == "2026-07-16 08:00:00"


def test_produtos_sync_sobreposicao_um_segundo_e_dedup(client, monkeypatch):
    from services import mercos_produtos_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    capturado: dict = {}
    fase = {"n": 0}

    def fake_listar(**kwargs):
        fase["n"] += 1
        capturado["kwargs"] = dict(kwargs)
        if fase["n"] == 1:
            return {
                "ok": True,
                "total": 1,
                "itens": [
                    {
                        "id": 1,
                        "nome": "seed",
                        "preco_tabela": 1,
                        "ultima_alteracao": "2026-07-15 20:53:55",
                        "ativo": True,
                    }
                ],
            }
        return {
            "ok": True,
            "total": 3,
            "itens": [
                {
                    "id": 10,
                    "nome": "4ac7237b574b4166",
                    "preco_tabela": 1,
                    "ultima_alteracao": "2026-07-15 20:53:55",
                    "ativo": True,
                },
                {
                    "id": 10,
                    "nome": "4ac7237b574b4166",
                    "preco_tabela": 1,
                    "ultima_alteracao": "2026-07-15 20:53:55",
                    "ativo": True,
                },
                {
                    "id": 11,
                    "nome": "outro",
                    "preco_tabela": 2,
                    "ultima_alteracao": "2026-07-15 20:54:01",
                    "ativo": True,
                },
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    client.post("/mercos/homologacao-ui/acoes/produtos-sincronizar")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-sincronizar",
        data={"cursor": "2026-07-15 20:53:55"},
    )
    assert resp.status_code == 200
    assert capturado["kwargs"].get("alterado_apos") == "2026-07-15 20:53:54"
    html = resp.text
    assert "Cursor base" in html
    assert "2026-07-15 20:53:55" in html
    assert "2026-07-15 20:53:54" in html
    assert html.split("mercos-catalogo-blob")[0].count("4ac7237b574b4166") == 1
    from urllib.parse import unquote

    cookie_raw = (resp.cookies.get("mercos_produtos_cursor") or "").strip('"')
    assert unquote(cookie_raw) == "2026-07-15 20:54:01"


def test_produtos_sync_preserva_cursor_sem_registros(client, monkeypatch):
    from services import mercos_produtos_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    fase = {"n": 0}

    def fake_listar(**kwargs):
        fase["n"] += 1
        if fase["n"] == 1:
            return {
                "ok": True,
                "total": 1,
                "itens": [
                    {
                        "id": 1,
                        "nome": "x",
                        "preco_tabela": 1,
                        "ultima_alteracao": "2026-07-15 12:30:00",
                    }
                ],
            }
        return {"ok": True, "total": 0, "itens": []}

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    client.post("/mercos/homologacao-ui/acoes/produtos-sincronizar")
    cursor_anterior = "2026-07-15 12:30:00"
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-sincronizar",
        data={"cursor": cursor_anterior},
    )
    assert resp.status_code == 200
    from urllib.parse import unquote

    cookie_raw = (resp.cookies.get("mercos_produtos_cursor") or "").strip('"')
    assert unquote(cookie_raw) == cursor_anterior
    assert f'data-novo-cursor="{cursor_anterior}"' in resp.text


def test_produtos_sync_impede_chamadas_duplicadas(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", called
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")

    from services.mercos_homolog_service import _SYNC_PRODUTOS_LOCK

    assert _SYNC_PRODUTOS_LOCK.acquire(blocking=False)
    try:
        resp = client.post("/mercos/homologacao-ui/acoes/produtos-sincronizar")
        assert resp.status_code == 409
        assert "já em andamento" in resp.text
        called.assert_not_called()
    finally:
        _SYNC_PRODUTOS_LOCK.release()


def test_produtos_localizar_usa_somente_preco_tabela(client, monkeypatch):
    from services import mercos_produtos_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )

    def fake_listar(**kwargs):
        return {
            "ok": True,
            "total": 1,
            "itens": [
                {
                    "id": 55,
                    "nome": "4c2e97e74c634ea4",
                    "preco": 999,
                    "preco_bruto": 888,
                    "preco_tabela": 42.5,
                    "ultima_alteracao": "2026-07-15 11:00:00",
                    "ativo": True,
                }
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    sync = client.post("/mercos/homologacao-ui/acoes/produtos-sincronizar")
    assert sync.status_code == 200
    api = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", api
    )
    cursor_cookie = client.cookies.get("mercos_produtos_cursor")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-localizar",
        data={"nome": "4c2e97e74c634ea4"},
    )
    assert resp.status_code == 200
    html = resp.text
    assert "Produto localizado" in html
    assert "Preço tabela" in html
    assert "42.5" in html
    assert "999" not in html
    assert "888" not in html
    assert "Catálogo local sincronizado" in html
    api.assert_not_called()
    assert client.cookies.get("mercos_produtos_cursor") == cursor_cookie


def test_catalogo_completa_salva_e_incremental_preserva(client, monkeypatch):
    from services import mercos_produtos_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    fases = {"n": 0}

    def fake_listar(**kwargs):
        fases["n"] += 1
        if fases["n"] == 1:
            return {
                "ok": True,
                "total": 2,
                "itens": [
                    {
                        "id": 1,
                        "nome": "4ac7237b574b4166",
                        "preco_tabela": 10,
                        "ultima_alteracao": "2026-07-15 10:00:00",
                        "ativo": True,
                    },
                    {
                        "id": 2,
                        "nome": "outro",
                        "preco_tabela": 20,
                        "ultima_alteracao": "2026-07-15 11:00:00",
                        "ativo": True,
                    },
                ],
            }
        return {
            "ok": True,
            "total": 1,
            "itens": [
                {
                    "id": 2,
                    "nome": "outro-atualizado",
                    "preco_tabela": 25,
                    "ultima_alteracao": "2026-07-15 12:00:00",
                    "ativo": True,
                }
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    r1 = client.post("/mercos/homologacao-ui/acoes/produtos-sincronizar")
    assert r1.status_code == 200
    assert "Produtos no catálogo acumulado" in r1.text
    assert "1/3" in r1.text
    sessao = client.cookies.get("mercos_produtos_sessao")
    assert sessao
    assert cat.total(sessao) == 2
    assert cat.obter_ciclo(sessao)["chamadas_completas"] == 1

    r2 = client.post(
        "/mercos/homologacao-ui/acoes/produtos-sincronizar",
        data={"cursor": "2026-07-15 11:00:00"},
    )
    assert r2.status_code == 200
    assert "2/3" in r2.text
    assert cat.total(sessao) == 2
    assert cat.obter_ciclo(sessao)["chamadas_completas"] == 1
    assert cat.obter_ciclo(sessao)["chamadas_incrementais"] == 1
    prod2 = cat.obter(sessao)["produtos"]["2"]
    assert prod2["nome"] == "outro-atualizado"
    assert prod2["preco_tabela"] == 25
    assert "4ac7237b574b4166" in cat.obter(sessao)["produtos"]["1"]["nome"]

    api = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", api
    )
    cursor_antes = client.cookies.get("mercos_produtos_cursor")
    etapa_antes = cat.obter_ciclo(sessao)["etapa_interna"]
    loc = client.post(
        "/mercos/homologacao-ui/acoes/produtos-localizar",
        data={"nome": "4ac7237b574b4166"},
    )
    assert loc.status_code == 200
    assert "Produto localizado" in loc.text
    assert "não veio no último lote incremental" in loc.text
    assert "Catálogo local sincronizado" in loc.text
    assert "Etapa interna" in loc.text
    api.assert_not_called()
    assert client.cookies.get("mercos_produtos_cursor") == cursor_antes
    assert cat.obter_ciclo(sessao)["etapa_interna"] == etapa_antes


def test_ciclo_bloqueia_busca_completa_e_exige_alterado_apos(client, monkeypatch):
    from services import mercos_produtos_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    chamadas = []

    def fake_listar(**kwargs):
        chamadas.append(dict(kwargs))
        n = len(chamadas)
        if n == 1:
            return {
                "ok": True,
                "total": 1,
                "itens": [
                    {
                        "id": 1,
                        "nome": "A",
                        "preco_tabela": 1,
                        "ultima_alteracao": "2026-07-15 10:00:00",
                    }
                ],
            }
        return {
            "ok": True,
            "total": 1,
            "itens": [
                {
                    "id": 2,
                    "nome": "B",
                    "preco_tabela": 2,
                    "ultima_alteracao": f"2026-07-15 11:0{n}:00",
                }
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")

    # Busca completa da UI bloqueada no ciclo ativo (antes mesmo da 1ª sync)
    bloqueado = client.post("/mercos/homologacao-ui/acoes/produtos")
    assert bloqueado.status_code == 200
    assert "Busca completa bloqueada durante a homologação" in bloqueado.text
    assert len(chamadas) == 0

    r1 = client.post("/mercos/homologacao-ui/acoes/produtos-sincronizar")
    assert r1.status_code == 200
    assert chamadas[0].get("alterado_apos") in (None, "")
    assert "1/3" in r1.text

    # Ainda bloqueada após etapa 1
    bloqueado2 = client.post("/mercos/homologacao-ui/acoes/produtos")
    assert "Busca completa bloqueada durante a homologação" in bloqueado2.text
    assert len(chamadas) == 1

    r2 = client.post(
        "/mercos/homologacao-ui/acoes/produtos-sincronizar",
        data={"cursor": "2026-07-15 10:00:00"},
    )
    assert r2.status_code == 200
    assert chamadas[1].get("alterado_apos") == "2026-07-15 09:59:59"
    assert "2/3" in r2.text

    r3 = client.post(
        "/mercos/homologacao-ui/acoes/produtos-sincronizar",
        data={"cursor": "2026-07-15 11:02:00"},
    )
    assert r3.status_code == 200
    assert chamadas[2].get("alterado_apos")
    assert "3/3" in r3.text
    sessao = client.cookies.get("mercos_produtos_sessao")
    ciclo = cat.obter_ciclo(sessao)
    assert ciclo["chamadas_completas"] == 1
    assert ciclo["chamadas_incrementais"] == 2
    assert ciclo["etapa_interna"] == 3


def test_recarregar_nao_reinicia_ciclo(client, monkeypatch):
    """Simula F5: memória limpa no servidor, cliente reidrata ciclo via localStorage."""
    from services import mercos_produtos_catalogo as cat
    import json

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )

    def fake_listar(**kwargs):
        return {
            "ok": True,
            "total": 1,
            "itens": [
                {
                    "id": 1,
                    "nome": "keep",
                    "preco_tabela": 1,
                    "ultima_alteracao": "2026-07-15 10:00:00",
                }
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    r1 = client.post("/mercos/homologacao-ui/acoes/produtos-sincronizar")
    assert "1/3" in r1.text
    sessao = client.cookies.get("mercos_produtos_sessao")
    snap = cat.snapshot_cliente(sessao)

    # Simula reinício do processo (memória zerada), cookie de sessão permanece
    cat._reset_todos_para_testes()
    assert cat.obter_ciclo(sessao)["ativo"] is False

    r2 = client.post(
        "/mercos/homologacao-ui/acoes/produtos-sincronizar",
        data={
            "cursor": "2026-07-15 10:00:00",
            "catalogo_json": json.dumps(snap),
        },
    )
    assert r2.status_code == 200
    assert "2/3" in r2.text
    assert cat.obter_ciclo(sessao)["chamadas_completas"] == 1
    assert cat.obter_ciclo(sessao)["chamadas_incrementais"] == 1


def test_produtos_reiniciar_ciclo_nao_chama_mercos(client, monkeypatch):
    from services import mercos_produtos_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", called
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    assert resp.status_code == 200
    assert "Ciclo de sincronização reiniciado" in resp.text
    assert "0/3" in resp.text
    assert "data-ciclo-ativo=\"1\"" in resp.text
    called.assert_not_called()
    sessao = client.cookies.get("mercos_produtos_sessao")
    assert cat.total(sessao) == 0
    assert cat.obter_ciclo(sessao)["etapa_interna"] == 0


def test_clientes_sync_primeira_sem_alterado_apos(client, monkeypatch):
    from services import mercos_clientes_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    capturado: dict = {}

    def fake_listar(**kwargs):
        capturado["kwargs"] = dict(kwargs)
        return {
            "ok": True,
            "path": "/v1/clientes",
            "total": 2,
            "itens": [
                {
                    "id": 1,
                    "razao_social": "Cliente Antigo",
                    "nome_fantasia": "Antigo",
                    "email": "a@test.com",
                    "ultima_alteracao": "2026-07-14 10:00:00",
                    "ativo": True,
                },
                {
                    "id": 2,
                    "razao_social": "77eb21774dd340ff",
                    "nome_fantasia": "Homolog",
                    "cnpj": "123",
                    "email": "h@test.com",
                    "ultima_alteracao": "2026-07-15 12:30:00",
                    "ativo": True,
                },
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_clientes", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert resp.status_code == 200
    assert capturado["kwargs"].get("alterado_apos") in (None, "")
    html = resp.text
    assert "Tipo da última busca" in html
    assert "Completa" in html
    assert "Etapa interna" in html
    assert "1/3" in html
    assert "Chamadas completas no ciclo" in html
    assert "Novo cursor" in html
    assert "2026-07-15 12:30:00" in html
    from urllib.parse import unquote

    cookie_raw = (resp.cookies.get("mercos_clientes_cursor") or "").strip('"')
    assert unquote(cookie_raw) == "2026-07-15 12:30:00"
    assert "data-novo-cursor=\"2026-07-15 12:30:00\"" in html
    assert '"itens"' not in html


def test_clientes_sync_etapas_2_e_3_com_alterado_apos(client, monkeypatch):
    from services import mercos_clientes_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    chamadas = []

    def fake_listar(**kwargs):
        chamadas.append(dict(kwargs))
        n = len(chamadas)
        if n == 1:
            return {
                "ok": True,
                "total": 1,
                "itens": [
                    {
                        "id": 1,
                        "razao_social": "A",
                        "ultima_alteracao": "2026-07-15 10:00:00",
                        "ativo": True,
                    }
                ],
            }
        return {
            "ok": True,
            "total": 1,
            "itens": [
                {
                    "id": 2,
                    "razao_social": "77eb21774dd340ff",
                    "ultima_alteracao": f"2026-07-15 11:0{n}:00",
                    "ativo": True,
                }
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_clientes", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")

    bloqueado = client.post("/mercos/homologacao-ui/acoes/clientes-buscar")
    assert bloqueado.status_code == 200
    assert "Busca completa bloqueada durante a homologação" in bloqueado.text
    assert len(chamadas) == 0

    r1 = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert r1.status_code == 200
    assert chamadas[0].get("alterado_apos") in (None, "")
    assert "1/3" in r1.text

    r2 = client.post(
        "/mercos/homologacao-ui/acoes/clientes-sincronizar",
        data={"cursor": "2026-07-15 10:00:00"},
    )
    assert r2.status_code == 200
    assert chamadas[1].get("alterado_apos") == "2026-07-15 09:59:59"
    assert "2/3" in r2.text
    assert "Incremental" in r2.text

    r3 = client.post(
        "/mercos/homologacao-ui/acoes/clientes-sincronizar",
        data={"cursor": "2026-07-15 11:02:00"},
    )
    assert r3.status_code == 200
    assert chamadas[2].get("alterado_apos")
    assert "3/3" in r3.text
    sessao = client.cookies.get("mercos_clientes_sessao")
    ciclo = cat.obter_ciclo(sessao)
    assert ciclo["chamadas_completas"] == 1
    assert ciclo["chamadas_incrementais"] == 2
    assert ciclo["etapa_interna"] == 3


def test_clientes_catalogo_completa_salva_e_incremental_preserva(client, monkeypatch):
    from services import mercos_clientes_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    fases = {"n": 0}

    def fake_listar(**kwargs):
        fases["n"] += 1
        if fases["n"] == 1:
            return {
                "ok": True,
                "total": 2,
                "itens": [
                    {
                        "id": 1,
                        "razao_social": "Cliente Base",
                        "ultima_alteracao": "2026-07-15 10:00:00",
                        "ativo": True,
                    },
                    {
                        "id": 2,
                        "razao_social": "Outro",
                        "ultima_alteracao": "2026-07-15 11:00:00",
                        "ativo": True,
                    },
                ],
            }
        return {
            "ok": True,
            "total": 1,
            "itens": [
                {
                    "id": 3,
                    "razao_social": "77eb21774dd340ff",
                    "ultima_alteracao": "2026-07-16 08:00:00",
                    "ativo": True,
                }
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_clientes", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    r1 = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert r1.status_code == 200
    sessao = client.cookies.get("mercos_clientes_sessao")
    assert cat.total(sessao) == 2
    assert "Total de clientes" in r1.text

    r2 = client.post(
        "/mercos/homologacao-ui/acoes/clientes-sincronizar",
        data={"cursor": "2026-07-15 11:00:00"},
    )
    assert r2.status_code == 200
    assert cat.total(sessao) == 3
    assert "77eb21774dd340ff" in r2.text
    estado = cat.obter(sessao)
    assert "1" in estado["clientes"]
    assert "2" in estado["clientes"]
    assert "3" in estado["clientes"]


def test_clientes_localizar_nao_chama_api_nem_altera_cursor(client, monkeypatch):
    from services import mercos_clientes_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )

    def fake_listar(**kwargs):
        return {
            "ok": True,
            "total": 2,
            "itens": [
                {
                    "id": 10,
                    "razao_social": "Cliente Velho",
                    "nome_fantasia": "Velho",
                    "cnpj": "00",
                    "email": "v@test.com",
                    "ultima_alteracao": "2026-07-14 10:00:00",
                    "ativo": True,
                },
                {
                    "id": 11,
                    "razao_social": "77eb21774dd340ff",
                    "nome_fantasia": "Homolog Cli",
                    "cnpj": "11.111.111/0001-11",
                    "email": "homolog@test.com",
                    "ultima_alteracao": "2026-07-15 11:00:00",
                    "ativo": True,
                },
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_clientes", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    sync = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert sync.status_code == 200
    sessao = client.cookies.get("mercos_clientes_sessao")
    assert cat.obter_ciclo(sessao)["chamadas_completas"] == 1

    api = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_clientes", api
    )
    cursor_antes = client.cookies.get("mercos_clientes_cursor")
    etapa_antes = cat.obter_ciclo(sessao)["etapa_interna"]
    loc = client.post(
        "/mercos/homologacao-ui/acoes/clientes-localizar",
        data={"razao_social": "77eb21774dd340ff"},
    )
    assert loc.status_code == 200
    html = loc.text
    assert "Cliente localizado" in html
    assert "77eb21774dd340ff" in html
    assert "Homolog Cli" in html
    assert "11.111.111/0001-11" in html
    assert "homolog@test.com" in html
    assert "Catálogo local sincronizado" in html
    assert "Origem" in html
    api.assert_not_called()
    assert client.cookies.get("mercos_clientes_cursor") == cursor_antes
    assert cat.obter_ciclo(sessao)["etapa_interna"] == etapa_antes
    assert cat.obter_ciclo(sessao)["chamadas_completas"] == 1


def test_clientes_recarregar_nao_reinicia_ciclo(client, monkeypatch):
    """Simula F5: memória limpa no servidor, cliente reidrata ciclo via localStorage."""
    from services import mercos_clientes_catalogo as cat
    import json

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )

    def fake_listar(**kwargs):
        return {
            "ok": True,
            "total": 1,
            "itens": [
                {
                    "id": 1,
                    "razao_social": "keep",
                    "ultima_alteracao": "2026-07-15 10:00:00",
                    "ativo": True,
                }
            ],
        }

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_clientes", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    r1 = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert r1.status_code == 200
    sessao = client.cookies.get("mercos_clientes_sessao")
    snap = cat.snapshot_sessao(sessao)
    assert snap["ciclo"]["ativo"] is True
    assert snap["ciclo"]["etapa_interna"] == 1

    # Simula F5 limpando memória do servidor
    cat._reset_todos_para_testes()
    assert cat.obter_ciclo(sessao)["ativo"] is False

    r2 = client.post(
        "/mercos/homologacao-ui/acoes/clientes-sincronizar",
        data={
            "cursor": "2026-07-15 10:00:00",
            "catalogo_json": json.dumps(snap),
        },
    )
    assert r2.status_code == 200
    assert "2/3" in r2.text
    assert cat.obter_ciclo(sessao)["chamadas_completas"] == 1
    assert cat.obter_ciclo(sessao)["chamadas_incrementais"] == 1


def test_clientes_reiniciar_ciclo_nao_chama_mercos(client, monkeypatch):
    from services import mercos_clientes_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_clientes", called
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    assert resp.status_code == 200
    assert "Ciclo de sincronização reiniciado" in resp.text
    assert "0/3" in resp.text
    assert "data-ciclo-ativo=\"1\"" in resp.text
    called.assert_not_called()
    sessao = client.cookies.get("mercos_clientes_sessao")
    assert cat.total(sessao) == 0
    assert cat.obter_ciclo(sessao)["etapa_interna"] == 0


def test_clientes_sync_completa_percorre_varias_paginas(client, monkeypatch):
    """Busca completa agrega todas as páginas; cliente da 2ª página entra no catálogo."""
    from services import mercos_clientes_catalogo as cat
    from urllib.parse import unquote

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_api_client.PAGE_SLEEP_SEGUNDOS", 0
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/clientes" if chave == "clientes" else f"/v1/{chave}",
    )
    # Contrato real Mercos: cursor alterado_apos + header REQUISICOES_EXTRAS.
    cursores_vistos: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        params = params or {}
        assert "pagina" not in params  # API real ignora "pagina"; não enviar
        cursor = params.get("alterado_apos")
        cursores_vistos.append(cursor)
        if cursor is None:
            return (
                [
                    {
                        "id": 1,
                        "razao_social": "Cliente Pagina 1A",
                        "ultima_alteracao": "2026-07-06 11:29:15",
                        "ativo": True,
                    },
                    {
                        "id": 2,
                        "razao_social": "Cliente Pagina 1B",
                        "ultima_alteracao": "2026-07-05 10:00:00",
                        "ativo": True,
                    },
                ],
                {
                    "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                    "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "5",
                    "MEUSPEDIDOS_REQUISICOES_EXTRAS": "2",
                },
            )
        if cursor == "2026-07-06 11:29:15":
            return (
                [
                    {
                        "id": 3,
                        "razao_social": "77eb21774dd340ff",
                        "nome_fantasia": "Homolog",
                        "cnpj": "11.111.111/0001-11",
                        "email": "h@test.com",
                        "ultima_alteracao": "2026-07-16 08:00:00",
                        "ativo": True,
                    },
                    {
                        "id": 3,
                        "razao_social": "77eb21774dd340ff",
                        "ultima_alteracao": "2026-07-16 08:00:00",
                        "ativo": True,
                    },
                ],
                {},
            )
        if cursor == "2026-07-16 08:00:00":
            return (
                [
                    {
                        "id": 4,
                        "razao_social": "Ultimo",
                        "ultima_alteracao": "2026-07-16 09:00:00",
                        "ativo": True,
                    }
                ],
                {},
            )
        return ([], {})

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert resp.status_code == 200
    html = resp.text
    assert "Completa" in html
    assert "Total de páginas consultadas" in html
    # extras=2 → exatamente 3 requisições (1 inicial + 2), sem chamada extra
    # para confirmar lote vazio.
    assert 'data-paginas-lidas="3"' in html
    assert cursores_vistos == [
        None,
        "2026-07-06 11:29:15",
        "2026-07-16 08:00:00",
    ]
    assert "Total retornado em todas as páginas" in html
    assert 'data-catalogo-total="4"' in html
    assert "77eb21774dd340ff" in html
    assert "Total de clientes" in html
    assert "Requisições extras informadas pela Mercos" in html
    assert "Requisições previstas" in html
    assert "Requisições executadas" in html
    assert 'data-requisicoes-extras="2"' in html
    assert 'data-requisicoes-previstas="3"' in html
    assert 'data-requisicoes-executadas="3"' in html
    assert "Motivo da parada" in html
    assert "Quantidade indicada pela Mercos concluída" in html
    assert "Novo cursor" in html
    cookie_raw = (resp.cookies.get("mercos_clientes_cursor") or "").strip('"')
    assert unquote(cookie_raw) == "2026-07-16 09:00:00"
    assert 'data-novo-cursor="2026-07-16 09:00:00"' in html
    sessao = client.cookies.get("mercos_clientes_sessao")
    assert cat.total(sessao) == 4  # ids 1,2,3,4 (dup id3 removido)
    estado = cat.obter(sessao)
    assert estado["clientes"]["3"]["razao_social"] == "77eb21774dd340ff"
    # Sem duplicata visual do id+alteracao na tabela (antes do blob)
    assert html.split("mercos-clientes-catalogo-blob")[0].count("77eb21774dd340ff") == 1


def test_clientes_sync_incremental_percorre_varias_paginas(client, monkeypatch):
    from services import mercos_clientes_catalogo as cat
    from urllib.parse import unquote

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_api_client.PAGE_SLEEP_SEGUNDOS", 0
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/clientes" if chave == "clientes" else f"/v1/{chave}",
    )
    cursores: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        params = params or {}
        assert "pagina" not in params
        cursor = params.get("alterado_apos")
        cursores.append(cursor)
        if cursor is None:
            # Completa: extras=0 → apenas 1 requisição
            return (
                [
                    {
                        "id": 1,
                        "razao_social": "Base",
                        "ultima_alteracao": "2026-07-15 10:00:00",
                        "ativo": True,
                    }
                ],
                {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "0"},
            )
        # Incremental: cursor salvo 10:00:00 - 1s de sobreposição.
        # Headers minúsculos para validar leitura case-insensitive.
        if cursor == "2026-07-15 09:59:59":
            return (
                [
                    {
                        "id": 2,
                        "razao_social": "Inc A",
                        "ultima_alteracao": "2026-07-15 12:00:00",
                        "ativo": True,
                    }
                ],
                {"meuspedidos_requisicoes_extras": "1"},
            )
        if cursor == "2026-07-15 12:00:00":
            return (
                [
                    {
                        "id": 3,
                        "razao_social": "77eb21774dd340ff",
                        "ultima_alteracao": "2026-07-16 15:30:00",
                        "ativo": True,
                    },
                    {
                        "id": 3,
                        "razao_social": "77eb21774dd340ff",
                        "ultima_alteracao": "2026-07-16 15:30:00",
                        "ativo": True,
                    },
                ],
                {},
            )
        return ([], {})

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    r1 = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert r1.status_code == 200
    r2 = client.post(
        "/mercos/homologacao-ui/acoes/clientes-sincronizar",
        data={"cursor": "2026-07-15 10:00:00"},
    )
    assert r2.status_code == 200
    # Completa: 1 requisição (extras=0). Incremental: extras=1 → 2 requisições,
    # sem chamada final para confirmar lote vazio.
    assert cursores == [
        None,
        "2026-07-15 09:59:59",
        "2026-07-15 12:00:00",
    ]
    html = r2.text
    assert "Incremental" in html
    assert "Total de páginas consultadas" in html
    assert "77eb21774dd340ff" in html
    cookie_raw = (r2.cookies.get("mercos_clientes_cursor") or "").strip('"')
    assert unquote(cookie_raw) == "2026-07-16 15:30:00"
    sessao = client.cookies.get("mercos_clientes_sessao")
    assert cat.total(sessao) == 3
    assert html.split("mercos-clientes-catalogo-blob")[0].count("77eb21774dd340ff") == 1


def test_clientes_throttle_respeita_retry_after(monkeypatch):
    from services.mercos_homolog_service import (
        _obter_lote_pagina_clientes,
        _reset_resume_clientes_para_testes,
    )
    from services.mercos_api_client import MercosApiError

    _reset_resume_clientes_para_testes()
    sleeps: list[float] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep",
        lambda s: sleeps.append(float(s)),
    )
    n = {"c": 0}

    def fake_get(path, *, params=None, **_kw):
        n["c"] += 1
        if n["c"] == 1:
            raise MercosApiError("429", status_code=429, retry_after=7.0)
        return (
            [{"id": 1, "razao_social": "OK", "ultima_alteracao": "2026-07-15 10:00:00"}],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    lote, espera, _headers = _obter_lote_pagina_clientes(
        path="/v1/clientes",
        params={"alterado_apos": "2026-07-15 09:00:00"},
        timeout=10,
        pagina=2,
    )
    assert len(lote) == 1
    assert sleeps == [7.0]
    assert espera == 7.0


def test_clientes_throttle_backoff_progressivo(monkeypatch):
    from services.mercos_homolog_service import (
        CLIENTES_BACKOFF_429,
        _obter_lote_pagina_clientes,
        _reset_resume_clientes_para_testes,
    )
    from services.mercos_api_client import MercosApiError

    _reset_resume_clientes_para_testes()
    sleeps: list[float] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep",
        lambda s: sleeps.append(float(s)),
    )
    n = {"c": 0}

    def fake_get(path, *, params=None, **_kw):
        n["c"] += 1
        if n["c"] < 3:
            raise MercosApiError("429", status_code=429, retry_after=None)
        return (
            [{"id": 9, "razao_social": "X", "ultima_alteracao": "2026-07-15 10:00:00"}],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    lote, espera, _headers = _obter_lote_pagina_clientes(
        path="/v1/clientes",
        params={},
        timeout=10,
        pagina=1,
    )
    assert len(lote) == 1
    assert sleeps == [CLIENTES_BACKOFF_429[0], CLIENTES_BACKOFF_429[1]]
    assert espera == sum(sleeps)


def test_clientes_throttle_esgota_libera_lock_e_resume(client, monkeypatch):
    from services import mercos_clientes_catalogo as cat
    from services.mercos_homolog_service import (
        _SYNC_CLIENTES_LOCK,
        _carregar_resume_clientes,
        _chave_resume_clientes,
        _reset_resume_clientes_para_testes,
    )
    from services.mercos_api_client import MercosApiError

    cat._reset_todos_para_testes()
    _reset_resume_clientes_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/clientes",
    )

    def always_429(path, *, params=None, **_kw):
        raise MercosApiError("429", status_code=429, retry_after=3.0)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", always_429
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert resp.status_code == 429
    assert "Aguardando limite da Mercos" in resp.text
    assert "Segundos restantes" in resp.text
    assert "Página atual" in resp.text
    assert resp.headers.get("Retry-After") == "3"
    assert resp.headers.get("X-Mercos-Pagina") == "1"
    # Lock liberado
    assert _SYNC_CLIENTES_LOCK.acquire(blocking=False) is True
    _SYNC_CLIENTES_LOCK.release()
    sessao = client.cookies.get("mercos_clientes_sessao")
    resume = _carregar_resume_clientes(_chave_resume_clientes(sessao, None))
    assert resume is not None
    assert resume.get("pagina") == 1


def test_clientes_intervalo_um_segundo_entre_paginas(monkeypatch):
    from services.mercos_homolog_service import (
        CLIENTES_INTERVALO_ENTRE_PAGINAS,
        listar_clientes_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )

    _reset_resume_clientes_para_testes()
    sleeps: list[float] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep",
        lambda s: sleeps.append(float(s)),
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/clientes",
    )

    def fake_get(path, *, params=None, **_kw):
        cursor = (params or {}).get("alterado_apos")
        if cursor is None:
            return (
                [{"id": 1, "razao_social": "C1", "ultima_alteracao": "2026-07-15 10:01:00"}],
                {},
            )
        if cursor == "2026-07-15 10:01:00":
            return (
                [{"id": 2, "razao_social": "C2", "ultima_alteracao": "2026-07-15 10:02:00"}],
                {},
            )
        return ([], {})

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_clientes_paginado_seguro(max_paginas=20, timeout_total=60)
    assert out["total"] == 2
    assert CLIENTES_INTERVALO_ENTRE_PAGINAS in sleeps
    assert CLIENTES_INTERVALO_ENTRE_PAGINAS == 2.0


def test_clientes_sync_para_em_pagina_repetida(client, monkeypatch):
    from services import mercos_clientes_catalogo as cat
    from services.mercos_homolog_service import MOTIVO_PARADA_REPETIDA

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr("services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/clientes" if chave == "clientes" else f"/v1/{chave}",
    )
    chamadas = []

    def fake_get(path, *, params=None, **_kw):
        chamadas.append((params or {}).get("alterado_apos"))
        lote = [
            {
                "id": 1,
                "razao_social": "Mesmo",
                "ultima_alteracao": "2026-07-15 10:00:00",
                "ativo": True,
            }
        ]
        # Sem headers de extras → fallback; API repete o mesmo lote → para
        return (lote, {})

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert resp.status_code == 200
    assert MOTIVO_PARADA_REPETIDA in resp.text
    assert "Concluída" in resp.text or "concluida" in resp.text.lower()
    assert "500" not in resp.text
    assert chamadas == [None, "2026-07-15 10:00:00"]
    sessao = client.cookies.get("mercos_clientes_sessao")
    assert cat.total(sessao) == 1


def test_clientes_sync_para_sem_ids_novos(client, monkeypatch):
    from services import mercos_clientes_catalogo as cat
    from services.mercos_homolog_service import MOTIVO_PARADA_REPETIDA

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr("services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/clientes",
    )

    def fake_get(path, *, params=None, **_kw):
        cursor = (params or {}).get("alterado_apos")
        if cursor is None:
            return (
                [
                    {"id": 1, "razao_social": "A", "ultima_alteracao": "2026-07-15 10:00:00"},
                    {"id": 2, "razao_social": "B", "ultima_alteracao": "2026-07-15 11:00:00"},
                ],
                {},
            )
        # Mesmos IDs, assinatura diferente (outra ordem / alteração) → nenhum ID novo
        return (
            [
                {"id": 2, "razao_social": "B2", "ultima_alteracao": "2026-07-15 12:00:00"},
                {"id": 1, "razao_social": "A2", "ultima_alteracao": "2026-07-15 12:01:00"},
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert resp.status_code == 200
    assert MOTIVO_PARADA_REPETIDA in resp.text
    sessao = client.cookies.get("mercos_clientes_sessao")
    assert cat.total(sessao) == 2


def test_clientes_sync_timeout_retorna_parciais(client, monkeypatch):
    from services import mercos_clientes_catalogo as cat
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import MOTIVO_PARADA_TIMEOUT

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr("services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/clientes",
    )
    n = {"c": 0}

    def fake_get(path, *, params=None, **_kw):
        n["c"] += 1
        if n["c"] == 1:
            return (
                [
                    {
                        "id": 1,
                        "razao_social": "Parcial",
                        "ultima_alteracao": "2026-07-15 10:00:00",
                    }
                ],
                {},
            )
        raise MercosApiError("Timeout na chamada à Mercos.", status_code=504)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert resp.status_code == 200
    assert MOTIVO_PARADA_TIMEOUT in resp.text
    assert "Timeout" in resp.text
    assert "Parcial" in resp.text
    sessao = client.cookies.get("mercos_clientes_sessao")
    assert cat.total(sessao) == 1


def test_clientes_sync_limite_20_paginas(monkeypatch):
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_LIMITE,
        listar_clientes_paginado_seguro,
    )

    monkeypatch.setattr("services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/clientes",
    )

    n = {"c": 0}

    def fake_get(path, *, params=None, **_kw):
        n["c"] += 1
        i = n["c"]
        return (
            [
                {
                    "id": i,
                    "razao_social": f"C{i}",
                    "ultima_alteracao": f"2026-07-15 10:{i:02d}:00",
                }
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_clientes_paginado_seguro(max_paginas=20, timeout_total=60)
    assert out["paginas_lidas"] == 20
    assert out["total"] == 20
    assert out["motivo_parada"] == MOTIVO_PARADA_LIMITE
    assert out["status"] == "concluida"


def test_clientes_paginacao_por_cursor_paginas_diferentes(monkeypatch):
    """Fallback sem headers: página 2 via alterado_apos do lote 1 traz IDs diferentes;
    para no lote vazio quando o header REQUISICOES_EXTRAS não existe."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_LOTE_VAZIO,
        listar_clientes_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr("services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/clientes",
    )
    params_vistos: list[dict] = []

    def fake_get(path, *, params=None, **_kw):
        params = dict(params or {})
        params_vistos.append(params)
        cursor = params.get("alterado_apos")
        if cursor is None:
            return (
                [
                    {"id": 9282664, "razao_social": "Antigo A", "ultima_alteracao": "2026-07-06 11:27:03"},
                    {"id": 9282665, "razao_social": "Antigo B", "ultima_alteracao": "2026-07-06 11:29:15"},
                ],
                {},
            )
        if cursor == "2026-07-06 11:29:15":
            return (
                [
                    {"id": 9282668, "razao_social": "Novo C", "ultima_alteracao": "2026-07-06 11:30:39"},
                    {"id": 9282669, "razao_social": "77eb21774dd340ff", "ultima_alteracao": "2026-07-06 11:31:57"},
                ],
                {},
            )
        return ([], {})

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_clientes_paginado_seguro(max_paginas=20, timeout_total=60)
    # Nenhuma requisição usa "pagina"; a 2ª usa o cursor do lote 1
    assert all("pagina" not in p for p in params_vistos)
    assert params_vistos[0].get("alterado_apos") is None
    assert params_vistos[1]["alterado_apos"] == "2026-07-06 11:29:15"
    ids = [c["id"] for c in out["itens"]]
    assert ids == [9282664, 9282665, 9282668, 9282669]
    assert out["total"] == 4
    assert out["paginas_lidas"] == 3
    assert out["motivo_parada"] == MOTIVO_PARADA_LOTE_VAZIO
    assert out["requisicoes_extras"] is None
    assert out["requisicoes_previstas"] is None


def _lotes_16_clientes_em_8_paginas() -> list[list[dict]]:
    """16 clientes, 2 por lote, ultima_alteracao crescente (como o sandbox)."""
    lotes = []
    for p in range(8):
        lotes.append(
            [
                {
                    "id": 100 + 2 * p + i,
                    "razao_social": f"Cliente {2 * p + i}",
                    "ultima_alteracao": f"2026-07-06 11:{p:02d}:{i:02d}",
                    "ativo": True,
                }
                for i in (1, 2)
            ]
        )
    return lotes


def test_clientes_extras_7_resulta_em_8_chamadas(monkeypatch):
    """extras=7 → 1 inicial + 7 adicionais = 8 chamadas; sem 9ª para lote vazio."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_EXTRAS,
        listar_clientes_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr("services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path", lambda chave: "/v1/clientes"
    )
    lotes = _lotes_16_clientes_em_8_paginas()
    cursores: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        cursores.append((params or {}).get("alterado_apos"))
        idx = len(cursores) - 1
        assert idx < 8, "não pode existir 9ª chamada"
        headers = (
            {
                "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "16",
                "MEUSPEDIDOS_REQUISICOES_EXTRAS": "7",
            }
            if idx == 0
            else {}
        )
        return (lotes[idx], headers)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_clientes_paginado_seguro(max_paginas=20, timeout_total=60)
    assert len(cursores) == 8
    assert out["paginas_lidas"] == 8
    assert out["requisicoes_extras"] == 7
    assert out["requisicoes_previstas"] == 8
    assert out["requisicoes_executadas"] == 8
    assert out["total"] == 16
    assert out["motivo_parada"] == MOTIVO_PARADA_EXTRAS
    # Cursor avança a cada lote: alterado_apos = maior ultima_alteracao anterior
    assert cursores[0] is None
    for i in range(1, 8):
        esperado = max(item["ultima_alteracao"] for item in lotes[i - 1])
        assert cursores[i] == esperado


def test_clientes_extras_respeita_retry_after_sem_reiniciar(monkeypatch):
    """429 no meio do plano: espera Retry-After e repete só a chamada atual."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_EXTRAS,
        listar_clientes_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )
    from services.mercos_api_client import MercosApiError

    _reset_resume_clientes_para_testes()
    sleeps: list[float] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep",
        lambda s: sleeps.append(float(s)),
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service._path", lambda chave: "/v1/clientes"
    )
    lotes = _lotes_16_clientes_em_8_paginas()[:3]
    estado = {"chamadas": 0, "falhou_429": False}
    cursores: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        estado["chamadas"] += 1
        cursor = (params or {}).get("alterado_apos")
        # 2ª requisição falha uma vez com 429 antes de responder
        if len(cursores) == 1 and not estado["falhou_429"]:
            estado["falhou_429"] = True
            raise MercosApiError("429", status_code=429, retry_after=4.0)
        cursores.append(cursor)
        idx = len(cursores) - 1
        headers = {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "2"} if idx == 0 else {}
        return (lotes[idx], headers)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_clientes_paginado_seguro(max_paginas=20, timeout_total=60)
    assert 4.0 in sleeps  # Retry-After respeitado
    assert estado["chamadas"] == 4  # 3 planejadas + 1 repetição da chamada atual
    assert cursores[0] is None  # sincronização não reiniciou
    assert out["paginas_lidas"] == 3
    assert out["total"] == 6
    assert out["motivo_parada"] == MOTIVO_PARADA_EXTRAS


def test_clientes_localizar_nao_faz_requisicao_http(client, monkeypatch):
    """Localizar usa só o catálogo local: nenhuma chamada HTTP à Mercos."""
    from services import mercos_clientes_catalogo as cat

    cat._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )

    def explode(*_a, **_k):
        raise AssertionError("Localizar cliente não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", explode)
    monkeypatch.setattr("services.mercos_api_client.request_mercos", explode)

    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    sessao_resp = client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    assert sessao_resp.status_code == 200
    sessao = client.cookies.get("mercos_clientes_sessao")
    cat.upsert_incremental(
        sessao,
        [
            {
                "id": 77,
                "razao_social": "77eb21774dd340ff",
                "ultima_alteracao": "2026-07-06 11:31:57",
                "ativo": True,
            }
        ],
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-localizar",
        data={"razao_social": "77eb21774dd340ff"},
    )
    assert resp.status_code == 200
    assert "Cliente localizado" in resp.text
    assert "77eb21774dd340ff" in resp.text
    # Não altera o cursor salvo
    assert resp.cookies.get("mercos_clientes_cursor") is None
    assert 'data-cursor-fixo="1"' in resp.text


def test_clientes_lock_libera_em_erro_e_expira(monkeypatch):
    from services.mercos_homolog_service import (
        _SYNC_CLIENTES_LOCK,
        sincronizar_clientes,
    )
    from services.mercos_api_client import MercosApiError

    # Garante limpo
    _SYNC_CLIENTES_LOCK.release()
    assert _SYNC_CLIENTES_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(MercosApiError) as exc:
            sincronizar_clientes()
        assert exc.value.status_code == 409
    finally:
        _SYNC_CLIENTES_LOCK.release()

    # Expira após TTL
    assert _SYNC_CLIENTES_LOCK.acquire(blocking=False)
    _SYNC_CLIENTES_LOCK._since = __import__("time").monotonic() - 121
    assert _SYNC_CLIENTES_LOCK.acquire(blocking=False) is True
    _SYNC_CLIENTES_LOCK.release()

    # Libera no finally mesmo com erro
    def boom(**_k):
        raise MercosApiError("falha", status_code=502)

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_clientes", boom
    )
    with pytest.raises(MercosApiError):
        sincronizar_clientes()
    assert _SYNC_CLIENTES_LOCK.acquire(blocking=False) is True
    _SYNC_CLIENTES_LOCK.release()


def _prep_usuarios(client, monkeypatch):
    from services import mercos_usuarios_catalogo as catu
    from services.mercos_homolog_service import _reset_resume_clientes_para_testes

    catu._reset_todos_para_testes()
    _reset_resume_clientes_para_testes()
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    return catu


def test_ui_secao_usuarios_ciclo_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    secao = html.split('id="sec-usuarios"')[1].split("</section>")[0]
    assert 'id="btn-usuarios-reiniciar"' in secao
    assert 'id="btn-usuarios-sincronizar"' in secao
    assert 'id="btn-usuarios-buscar"' in secao
    assert 'id="input-usuarios-nome"' in secao
    assert 'id="btn-usuarios-localizar"' in secao
    assert "Reiniciar ciclo de sincronização" in secao


def test_usuarios_reiniciar_nao_chama_mercos(client, monkeypatch):
    catu = _prep_usuarios(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    resp = client.post("/mercos/homologacao-ui/acoes/usuarios-reiniciar")
    assert resp.status_code == 200
    assert "Ciclo de sincronização reiniciado" in resp.text
    assert "0/3" in resp.text
    assert 'data-ciclo-ativo="1"' in resp.text
    called.assert_not_called()
    sessao = client.cookies.get("mercos_usuarios_sessao")
    assert catu.total(sessao) == 0
    assert catu.obter_ciclo(sessao)["etapa_interna"] == 0


def _fake_usuarios_sandbox(cursores_vistos):
    """Mock do contrato real: 1ª sem alterado_apos; incrementais com cursor EXATO."""

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/usuarios"
        params = params or {}
        assert "pagina" not in params
        cursor = params.get("alterado_apos")
        # A Mercos recusa cursor - 1s: nunca pode chegar um valor "subtraído"
        assert cursor not in ("2026-07-16 09:51:27", "2026-07-17 09:56:36")
        cursores_vistos.append(cursor)
        headers = {
            "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
            "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "4",
            "MEUSPEDIDOS_REQUISICOES_EXTRAS": "0",
        }
        if cursor is None:
            return (
                [
                    {
                        "id": 78809,
                        "nome": "Arthur",
                        "email": "a@x.com",
                        "administrador": True,
                        "excluido": False,
                        "ultima_alteracao": "2026-07-06 10:16:53",
                    },
                    {
                        "id": 78928,
                        "nome": "085215c21d364f7bc1a38deb76704d64",
                        "email": "b@x.com",
                        "administrador": False,
                        "excluido": False,
                        "ultima_alteracao": "2026-07-16 09:51:28",
                    },
                ],
                headers,
            )
        if cursor == "2026-07-16 09:51:28":
            return (
                [
                    {
                        "id": 78927,
                        "nome": "e6d9612bbf3a480e",
                        "email": "c@x.com",
                        "administrador": False,
                        "excluido": False,
                        "ultima_alteracao": "2026-07-17 09:51:25",
                    },
                    {
                        "id": 78929,
                        "nome": "f919f5f29edd432e100eea2fe5dd4776",
                        "email": "d@x.com",
                        "administrador": True,
                        "excluido": False,
                        "ultima_alteracao": "2026-07-17 09:56:37",
                    },
                ],
                headers,
            )
        return ([], headers)

    return fake_get


def test_usuarios_ciclo_3_etapas_completa_e_incrementais(client, monkeypatch):
    """Etapa 1 completa sem alterado_apos; etapas 2 e 3 incrementais com cursor.

    O usuário f919f5f2… (novo) aparece na incremental e entra no catálogo
    acumulado sem perder os anteriores.
    """
    catu = _prep_usuarios(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_usuarios_sandbox(cursores),
    )
    client.post("/mercos/homologacao-ui/acoes/usuarios-reiniciar")
    sessao = client.cookies.get("mercos_usuarios_sessao")

    # Etapa 1 — busca completa (exatamente 1 chamada, sem alterado_apos)
    r1 = client.post("/mercos/homologacao-ui/acoes/usuarios-sincronizar")
    assert r1.status_code == 200
    assert cursores == [None]
    assert "1/3" in r1.text
    assert 'data-tipo-busca="completa"' in r1.text
    assert catu.total(sessao) == 2
    assert catu.obter_ciclo(sessao)["chamadas_completas"] == 1

    # Etapa 2 — incremental com alterado_apos = cursor EXATO da etapa 1
    r2 = client.post("/mercos/homologacao-ui/acoes/usuarios-sincronizar")
    assert r2.status_code == 200
    assert cursores[1] == "2026-07-16 09:51:28"
    assert "2/3" in r2.text
    assert 'data-tipo-busca="incremental"' in r2.text
    # Cartão: Cursor base e alterado_apos enviado exatamente iguais
    assert 'data-cursor-base="2026-07-16 09:51:28"' in r2.text
    assert 'data-alterado-apos-enviado="2026-07-16 09:51:28"' in r2.text
    assert "2026-07-16 09:51:27" not in r2.text
    assert "f919f5f29edd432e100eea2fe5dd4776" in r2.text
    # Catálogo acumulado: mantém anteriores e adiciona novos
    assert catu.total(sessao) == 4
    estado = catu.obter(sessao)
    assert "78809" in estado["usuarios"]  # Arthur preservado
    assert "78929" in estado["usuarios"]  # novo usuário da incremental

    # Etapa 3 — incremental com o cursor EXATO produzido pela etapa 2
    r3 = client.post("/mercos/homologacao-ui/acoes/usuarios-sincronizar")
    assert r3.status_code == 200
    assert cursores[2] == "2026-07-17 09:56:37"
    assert 'data-cursor-base="2026-07-17 09:56:37"' in r3.text
    assert 'data-alterado-apos-enviado="2026-07-17 09:56:37"' in r3.text
    assert "2026-07-17 09:56:36" not in r3.text
    assert "3/3" in r3.text
    ciclo = catu.obter_ciclo(sessao)
    assert ciclo["chamadas_completas"] == 1
    assert ciclo["chamadas_incrementais"] == 2
    assert ciclo["etapa_interna"] == 3
    # Cursor preservado quando a incremental não retorna registros
    assert catu.total(sessao) == 4
    # Cartão operacional sem JSON cru nem token
    assert "Requisições previstas" in r3.text
    assert "Requisições executadas" in r3.text
    assert "CompanyToken" not in r3.text


def test_usuarios_extras_headers_limita_chamadas(monkeypatch):
    """extras=1 → exatamente 2 chamadas; sem 3ª esperando lote vazio."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_EXTRAS,
        listar_usuarios_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    chamadas: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/usuarios"
        chamadas.append((params or {}).get("alterado_apos"))
        assert len(chamadas) <= 2, "não pode existir 3ª chamada"
        if len(chamadas) == 1:
            return (
                [
                    {"id": 1, "nome": "U1", "ultima_alteracao": "2026-07-16 09:00:00"},
                    {"id": 2, "nome": "U2", "ultima_alteracao": "2026-07-16 09:51:28"},
                ],
                {
                    "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                    "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "4",
                    "MEUSPEDIDOS_REQUISICOES_EXTRAS": "1",
                },
            )
        return (
            [
                {"id": 3, "nome": "U3", "ultima_alteracao": "2026-07-17 09:51:25"},
                {"id": 4, "nome": "f919f5f29edd432e100eea2fe5dd4776", "ultima_alteracao": "2026-07-17 09:56:37"},
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_usuarios_paginado_seguro(max_paginas=20, timeout_total=60)
    assert len(chamadas) == 2
    assert chamadas[0] is None
    assert chamadas[1] == "2026-07-16 09:51:28"
    assert out["total"] == 4
    assert out["requisicoes_extras"] == 1
    assert out["requisicoes_previstas"] == 2
    assert out["requisicoes_executadas"] == 2
    assert out["motivo_parada"] == MOTIVO_PARADA_EXTRAS


def test_usuarios_localizar_nao_faz_requisicao_http(client, monkeypatch):
    """Localizar usa só o catálogo local (nome completo ou prefixo); cursor intacto."""
    catu = _prep_usuarios(client, monkeypatch)

    def explode(*_a, **_k):
        raise AssertionError("Localizar usuário não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", explode)
    monkeypatch.setattr("services.mercos_api_client.request_mercos", explode)

    client.post("/mercos/homologacao-ui/acoes/usuarios-reiniciar")
    sessao = client.cookies.get("mercos_usuarios_sessao")
    catu.upsert_incremental(
        sessao,
        [
            {
                "id": 78929,
                "nome": "f919f5f29edd432e100eea2fe5dd4776",
                "email": "d@x.com",
                "administrador": True,
                "excluido": False,
                "ultima_alteracao": "2026-07-17 09:56:37",
            }
        ],
    )
    etapa_antes = catu.obter_ciclo(sessao)["etapa_interna"]

    # Por prefixo (como a Mercos pede: nome começa com f919f5f2)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/usuarios-localizar",
        data={"nome": "f919f5f2"},
    )
    assert resp.status_code == 200
    assert "Usuário localizado" in resp.text
    assert "f919f5f29edd432e100eea2fe5dd4776" in resp.text
    assert "Administrador" in resp.text
    # Não altera cursor nem etapa
    assert resp.cookies.get("mercos_usuarios_cursor") is None
    assert 'data-cursor-fixo="1"' in resp.text
    assert catu.obter_ciclo(sessao)["etapa_interna"] == etapa_antes

    # Por nome completo
    resp2 = client.post(
        "/mercos/homologacao-ui/acoes/usuarios-localizar",
        data={"nome": "f919f5f29edd432e100eea2fe5dd4776"},
    )
    assert "Usuário localizado" in resp2.text


def test_usuarios_buscar_bloqueada_durante_ciclo(client, monkeypatch):
    _prep_usuarios(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.listar_usuarios", called)
    client.post("/mercos/homologacao-ui/acoes/usuarios-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/usuarios")
    assert resp.status_code == 200
    assert "Busca completa bloqueada durante a homologação" in resp.text
    called.assert_not_called()


def test_usuarios_429_retorna_retry_after_e_libera_lock(client, monkeypatch):
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import _SYNC_USUARIOS_LOCK

    _prep_usuarios(client, monkeypatch)

    def sempre_429(path, *, params=None, **_kw):
        raise MercosApiError("429", status_code=429, retry_after=12.0)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", sempre_429
    )
    client.post("/mercos/homologacao-ui/acoes/usuarios-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/usuarios-sincronizar")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "12"
    assert "Aguardando limite da Mercos" in resp.text
    # Lock liberado no finally: nova aquisição funciona
    assert _SYNC_USUARIOS_LOCK.acquire(blocking=False) is True
    _SYNC_USUARIOS_LOCK.release()


def test_usuarios_incremental_envia_cursor_exato(monkeypatch):
    """alterado_apos = cursor base byte a byte, nunca cursor - 1s."""
    from services.mercos_homolog_service import sincronizar_usuarios

    capt: dict = {}

    def fake_listar(alterado_apos=None, **_kw):
        capt["alterado_apos"] = alterado_apos
        return {"itens": [], "paginas_lidas": 1}

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_usuarios_paginado_seguro",
        fake_listar,
    )
    out = sincronizar_usuarios("2026-07-17 09:56:37")
    assert capt["alterado_apos"] == "2026-07-17 09:56:37"
    assert out["cursor_base"] == "2026-07-17 09:56:37"
    assert out["alterado_apos_enviado"] == "2026-07-17 09:56:37"
    assert out["alterado_apos_enviado"] == out["cursor_base"]
    # Cursor preservado quando não vêm registros
    assert out["novo_cursor"] == "2026-07-17 09:56:37"


def test_produtos_e_clientes_mantem_sobreposicao_de_1s(monkeypatch):
    """A correção é só para usuários: produtos/clientes seguem com overlap."""
    from services.mercos_homolog_service import (
        sincronizar_clientes,
        sincronizar_produtos,
    )

    capt: dict = {}

    def fake_listar_clientes(alterado_apos=None, **_kw):
        capt["clientes"] = alterado_apos
        return {"itens": [], "paginas_lidas": 1}

    def fake_listar_produtos(alterado_apos=None, **_kw):
        capt["produtos"] = alterado_apos
        return {"itens": [], "paginas_lidas": 1}

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_clientes", fake_listar_clientes
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", fake_listar_produtos
    )
    out_cli = sincronizar_clientes("2026-07-17 09:56:37")
    out_prod = sincronizar_produtos("2026-07-17 09:56:37")
    assert capt["clientes"] == "2026-07-17 09:56:36"
    assert out_cli["alterado_apos_enviado"] == "2026-07-17 09:56:36"
    assert capt["produtos"] == "2026-07-17 09:56:36"
    assert out_prod["alterado_apos_enviado"] == "2026-07-17 09:56:36"


def test_usuarios_lock_libera_em_erro(monkeypatch):
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import (
        _SYNC_USUARIOS_LOCK,
        sincronizar_usuarios,
    )

    _SYNC_USUARIOS_LOCK.release()
    # Ocupado → 409 sem chamadas concorrentes
    assert _SYNC_USUARIOS_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(MercosApiError) as exc:
            sincronizar_usuarios()
        assert exc.value.status_code == 409
    finally:
        _SYNC_USUARIOS_LOCK.release()

    # Libera no finally mesmo com erro
    def boom(**_k):
        raise MercosApiError("falha", status_code=502)

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_usuarios_paginado_seguro", boom
    )
    with pytest.raises(MercosApiError):
        sincronizar_usuarios()
    assert _SYNC_USUARIOS_LOCK.acquire(blocking=False) is True
    _SYNC_USUARIOS_LOCK.release()


def _prep_pedidos(client, monkeypatch):
    from services import mercos_pedidos_catalogo as catp
    from services.mercos_homolog_service import (
        _reset_rate_limiters_para_testes,
        _reset_resume_clientes_para_testes,
    )

    catp._reset_todos_para_testes()
    _reset_resume_clientes_para_testes()
    _reset_rate_limiters_para_testes()
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    return catp


def test_ui_secao_pedidos_buscar_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    secao = html.split('id="sec-pedidos-buscar"')[1].split("</section>")[0]
    assert 'id="btn-pedidos-reiniciar"' in secao
    assert 'id="btn-pedidos-sincronizar"' in secao
    assert 'id="input-pedidos-razao"' in secao
    assert 'id="btn-pedidos-localizar"' in secao
    assert "Reiniciar ciclo de sincronização" in secao
    assert "Localizar pedido pelo cliente" in secao
    # POST e PUT de pedido preservados na UI
    assert 'id="sec-pedidos-criar"' in html
    assert 'id="sec-pedidos-alterar"' in html


def test_pedidos_reiniciar_nao_chama_mercos(client, monkeypatch):
    catp = _prep_pedidos(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    resp = client.post("/mercos/homologacao-ui/acoes/pedidos-reiniciar")
    assert resp.status_code == 200
    assert "Ciclo de sincronização reiniciado" in resp.text
    assert "0/2" in resp.text
    assert 'data-ciclo-ativo="1"' in resp.text
    called.assert_not_called()
    sessao = client.cookies.get("mercos_pedidos_sessao")
    assert catp.total(sessao) == 0
    assert catp.obter_ciclo(sessao)["etapa_interna"] == 0


def _fake_pedidos_sandbox(cursores_vistos):
    """Mock do contrato real de GET /v1/pedidos (diagnóstico 2026-07-17)."""

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/pedidos"
        params = params or {}
        assert "pagina" not in params
        cursor = params.get("alterado_apos")
        # alterado_apos é filtro estritamente maior: cursor exato, nunca -1s
        assert cursor != "2026-07-06 14:56:54"
        assert cursor != "2026-07-17 10:57:38"
        cursores_vistos.append(cursor)
        headers = {
            "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
            "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "3",
            "MEUSPEDIDOS_REQUISICOES_EXTRAS": "0",
        }
        if cursor is None:
            return (
                [
                    {
                        "id": 2148915,
                        "cliente_id": 9282664,
                        "cliente_razao_social": "cliente-antigo",
                        "total": 79.9,
                        "status": "1",
                        "data_emissao": "2026-07-06",
                        "ultima_alteracao": "2026-07-06 14:56:55",
                    },
                    {
                        "id": 2148916,
                        "cliente_id": 9282665,
                        "cliente_razao_social": "outro-cliente",
                        "total": 120.5,
                        "status": "1",
                        "data_emissao": "2026-07-06",
                        "ultima_alteracao": "2026-07-06 14:56:55",
                    },
                ],
                headers,
            )
        if cursor == "2026-07-06 14:56:55":
            return (
                [
                    {
                        "id": 2150999,
                        "cliente_id": 9291000,
                        "cliente_razao_social": "1f9e362a2b3a4365",
                        "total": 249.9,
                        "status": "1",
                        "data_emissao": "2026-07-17",
                        "ultima_alteracao": "2026-07-17 10:57:39",
                    },
                ],
                headers,
            )
        return ([], headers)

    return fake_get


def test_pedidos_ciclo_2_etapas_completa_e_incremental(client, monkeypatch):
    """Etapa 1 completa sem alterado_apos; etapa 2 incremental com cursor exato.

    O pedido do cliente 1f9e362a2b3a4365 chega na incremental e entra no
    catálogo acumulado sem perder os pedidos anteriores.
    """
    catp = _prep_pedidos(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_pedidos_sandbox(cursores),
    )
    client.post("/mercos/homologacao-ui/acoes/pedidos-reiniciar")
    sessao = client.cookies.get("mercos_pedidos_sessao")

    # Etapa 1 — busca completa (exatamente 1 chamada, sem alterado_apos)
    r1 = client.post("/mercos/homologacao-ui/acoes/pedidos-sincronizar")
    assert r1.status_code == 200
    assert cursores == [None]
    assert "1/2" in r1.text
    assert 'data-tipo-busca="completa"' in r1.text
    assert catp.total(sessao) == 2
    assert catp.obter_ciclo(sessao)["chamadas_completas"] == 1

    # Etapa 2 — incremental com alterado_apos = cursor EXATO da etapa 1
    r2 = client.post("/mercos/homologacao-ui/acoes/pedidos-sincronizar")
    assert r2.status_code == 200
    assert cursores[1] == "2026-07-06 14:56:55"
    assert "2/2" in r2.text
    assert 'data-tipo-busca="incremental"' in r2.text
    assert 'data-cursor-base="2026-07-06 14:56:55"' in r2.text
    assert 'data-alterado-apos-enviado="2026-07-06 14:56:55"' in r2.text
    assert "1f9e362a2b3a4365" in r2.text
    # Catálogo acumulado: mantém anteriores e adiciona o novo
    assert catp.total(sessao) == 3
    estado = catp.obter(sessao)
    assert "2148915" in estado["pedidos"]  # pedido antigo preservado
    assert "2150999" in estado["pedidos"]  # novo pedido da incremental
    ciclo = catp.obter_ciclo(sessao)
    assert ciclo["chamadas_completas"] == 1
    assert ciclo["chamadas_incrementais"] == 1
    assert ciclo["etapa_interna"] == 2
    # Cartão operacional sem JSON cru nem token
    assert "Requisições previstas" in r2.text
    assert "Requisições executadas" in r2.text
    assert "Intervalo mínimo aplicado" in r2.text
    assert "Menor intervalo real entre chamadas" in r2.text
    assert "Throttling respeitado" in r2.text
    assert "CompanyToken" not in r2.text
    assert '"cliente_razao_social"' not in r2.text.split("<textarea")[0]


def test_pedidos_extras_headers_limita_chamadas(monkeypatch):
    """extras=1 → exatamente 2 chamadas; sem 3ª esperando lote vazio."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_EXTRAS,
        listar_pedidos_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    chamadas: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/pedidos"
        chamadas.append((params or {}).get("alterado_apos"))
        assert len(chamadas) <= 2, "não pode existir 3ª chamada"
        if len(chamadas) == 1:
            return (
                [
                    {"id": 1, "cliente_id": 10, "total": 5.0, "ultima_alteracao": "2026-07-06 14:56:55"},
                    {"id": 2, "cliente_id": 11, "total": 6.0, "ultima_alteracao": "2026-07-07 08:00:00"},
                ],
                {
                    "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                    "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "3",
                    "MEUSPEDIDOS_REQUISICOES_EXTRAS": "1",
                },
            )
        return (
            [
                {"id": 3, "cliente_id": 12, "total": 7.0, "ultima_alteracao": "2026-07-17 10:57:39"},
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_pedidos_paginado_seguro(max_paginas=20, timeout_total=60)
    assert len(chamadas) == 2
    assert chamadas[0] is None
    assert chamadas[1] == "2026-07-07 08:00:00"
    assert out["total"] == 3
    assert out["requisicoes_extras"] == 1
    assert out["requisicoes_previstas"] == 2
    assert out["requisicoes_executadas"] == 2
    assert out["motivo_parada"] == MOTIVO_PARADA_EXTRAS


class _RelogioFake:
    """Relógio monotônico controlado para testar o rate limiter."""

    def __init__(self):
        self.t = 0.0
        self.esperas: list[float] = []

    def agora(self) -> float:
        return self.t

    def dormir(self, segundos: float) -> None:
        self.esperas.append(round(float(segundos), 6))
        self.t += float(segundos)


def test_pedidos_rate_limiter_intervalo_minimo_antes_de_cada_request(monkeypatch):
    """Duas páginas (1 + extras) nunca são chamadas antes do intervalo mínimo."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_EXTRAS,
        PEDIDOS_INTERVALO_MINIMO_SEGUNDOS,
        _RateLimiterMercos,
        _reset_resume_clientes_para_testes,
        listar_pedidos_paginado_seguro,
    )

    assert PEDIDOS_INTERVALO_MINIMO_SEGUNDOS == 5.0
    _reset_resume_clientes_para_testes()
    clk = _RelogioFake()
    limiter = _RateLimiterMercos(5.0, relogio=clk.agora, dormir=clk.dormir)
    instantes: list[float] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/pedidos"
        instantes.append(clk.t)
        clk.t += 0.3  # duração variável da requisição
        if len(instantes) == 1:
            return (
                [{"id": 1, "cliente_id": 10, "total": 5.0, "ultima_alteracao": "2026-07-06 14:56:55"}],
                {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "1"},
            )
        return (
            [{"id": 2, "cliente_id": 11, "total": 6.0, "ultima_alteracao": "2026-07-17 10:57:39"}],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_pedidos_paginado_seguro(
        rate_limiter=limiter, max_paginas=20, timeout_total=60
    )
    # Exatamente 1 + extras chamadas válidas
    assert len(instantes) == 2
    assert out["requisicoes_executadas"] == 2
    assert out["motivo_parada"] == MOTIVO_PARADA_EXTRAS
    # A chamada extra respeitou o intervalo mínimo completo (medido do início
    # da requisição anterior, relógio monotônico)
    assert instantes[1] - instantes[0] >= 5.0
    # A espera foi calculada ANTES do request (5.0 - 0.3s de duração)
    assert clk.esperas == [4.7]
    assert out["intervalo_minimo_aplicado"] == 5.0
    assert out["menor_intervalo_real"] >= 5.0
    assert out["throttling_respeitado"] is True


def test_pedidos_rate_limiter_429_respeita_retry_after_e_repete_pagina(monkeypatch):
    """429: Retry-After integral no limiter e a MESMA página é refeita."""
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import (
        _RateLimiterMercos,
        _reset_resume_clientes_para_testes,
        listar_pedidos_paginado_seguro,
    )

    _reset_resume_clientes_para_testes()
    clk = _RelogioFake()
    limiter = _RateLimiterMercos(5.0, relogio=clk.agora, dormir=clk.dormir)
    cursores: list[str | None] = []

    def nao_dormir_local(_s):
        raise AssertionError("Deve usar o rate limiter, não time.sleep local")

    monkeypatch.setattr("services.mercos_homolog_service.time.sleep", nao_dormir_local)

    def fake_get(path, *, params=None, **_kw):
        clk.t += 0.2
        cursor = (params or {}).get("alterado_apos")
        cursores.append(cursor)
        if len(cursores) == 2:
            raise MercosApiError("429", status_code=429, retry_after=7.0)
        if len(cursores) == 1:
            return (
                [{"id": 1, "cliente_id": 10, "total": 5.0, "ultima_alteracao": "2026-07-06 14:56:55"}],
                {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "1"},
            )
        return (
            [{"id": 2, "cliente_id": 11, "total": 6.0, "ultima_alteracao": "2026-07-17 10:57:39"}],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_pedidos_paginado_seguro(
        rate_limiter=limiter, max_paginas=20, timeout_total=60
    )
    # A mesma página (mesmo alterado_apos) é refeita após o 429
    assert len(cursores) == 3
    assert cursores[1] == cursores[2] == "2026-07-06 14:56:55"
    # Retry-After integral aguardado antes de refazer
    assert 7.0 in clk.esperas
    # Só as 2 respostas válidas contam como requisições executadas
    assert out["requisicoes_executadas"] == 2
    assert out["total"] == 2
    assert out["throttling_respeitado"] is True


def test_pedidos_fluxo_completo_intervalo_real_entre_paginas(monkeypatch):
    """Integração (fluxo completo, 2 páginas): >= 5s reais entre os envios HTTP.

    Reproduz o cenário reprovado (requisição de 1.3s de duração): os
    timestamps são registrados imediatamente antes do mock HTTP e a diferença
    deve ser >= 5.0 — com 1.3s este teste falha. Também garante que ambas as
    páginas passam pelo MESMO limiter e que nenhuma chamada ocorre fora dele.
    """
    from services import mercos_homolog_service as svc

    svc._reset_resume_clientes_para_testes()
    svc._reset_rate_limiters_para_testes()
    monkeypatch.setenv("MERCOS_COMPANY_TOKEN", "empresa-teste")
    limiter = svc._rate_limiter_pedidos()
    clk = _RelogioFake()
    limiter._relogio = clk.agora
    limiter._dormir = clk.dormir

    marcas_pre_http: list[float] = []
    lock_preso_durante_http: list[bool] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/pedidos"
        # Timestamp monotônico imediatamente antes do envio HTTP
        marcas_pre_http.append(clk.agora())
        # Nenhuma chamada fora do limiter: o lock global deve estar preso
        lock_preso_durante_http.append(limiter._lock.locked())
        clk.t += 1.3  # duração real observada em produção
        if len(marcas_pre_http) == 1:
            return (
                [{"id": 1, "cliente_id": 10, "total": 5.0, "ultima_alteracao": "2026-07-06 14:56:55"}],
                {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "1"},
            )
        return (
            [{"id": 2, "cliente_id": 11, "total": 6.0, "ultima_alteracao": "2026-07-17 10:57:39"}],
            {},
        )

    monkeypatch.setattr(svc, "get_json_com_headers", fake_get)
    out = svc.sincronizar_pedidos()

    # Exatamente 1 + extras chamadas, todas dentro do limiter
    assert len(marcas_pre_http) == 2
    assert all(lock_preso_durante_http)
    # Intervalo real entre os INÍCIOS das requisições >= 5.0 (nunca 1.3)
    assert marcas_pre_http[1] - marcas_pre_http[0] >= 5.0
    assert out["intervalo_minimo_aplicado"] == 5.0
    assert out["menor_intervalo_real"] >= 5.0
    assert out["throttling_respeitado"] is True
    # Única instância compartilhada por CompanyToken em todo o processo
    assert svc._rate_limiter_pedidos() is limiter
    assert len(svc._RATE_LIMITERS_MERCOS) == 1


def test_pedidos_retry_apos_429_respeita_piso_de_5s(monkeypatch):
    """Regressão do bug de produção: Retry-After curto (1s) não fura o piso.

    A Mercos respondeu 429 com Retry-After 1 e a retentativa saía 1.3s após a
    tentativa anterior. O piso de 5s contado do último início real deve
    prevalecer sobre um Retry-After menor.
    """
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import (
        _RateLimiterMercos,
        _reset_resume_clientes_para_testes,
        listar_pedidos_paginado_seguro,
    )

    _reset_resume_clientes_para_testes()
    clk = _RelogioFake()
    limiter = _RateLimiterMercos(5.0, relogio=clk.agora, dormir=clk.dormir)
    marcas: list[float] = []

    def fake_get(path, *, params=None, **_kw):
        marcas.append(clk.agora())
        clk.t += 0.3
        if len(marcas) == 2:
            raise MercosApiError("429", status_code=429, retry_after=1.0)
        if len(marcas) == 1:
            return (
                [{"id": 1, "cliente_id": 10, "total": 5.0, "ultima_alteracao": "2026-07-06 14:56:55"}],
                {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "1"},
            )
        return (
            [{"id": 2, "cliente_id": 11, "total": 6.0, "ultima_alteracao": "2026-07-17 10:57:39"}],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_pedidos_paginado_seguro(
        rate_limiter=limiter, max_paginas=20, timeout_total=60
    )
    assert len(marcas) == 3
    # TODOS os intervalos reais >= 5.0, inclusive a retentativa pós-429
    for antes, depois in zip(marcas, marcas[1:]):
        assert depois - antes >= 5.0
    assert out["menor_intervalo_real"] >= 5.0
    assert out["throttling_respeitado"] is True


def test_pedidos_rate_limiter_serializa_chamadas_concorrentes():
    """Duas chamadas concorrentes nunca ultrapassam o limite (lock compartilhado)."""
    import threading
    import time as time_mod

    from services.mercos_homolog_service import _RateLimiterMercos

    limiter = _RateLimiterMercos(0.05)  # intervalo real curto p/ teste rápido
    instantes: list[float] = []

    def chamada():
        return "ok"

    def worker():
        limiter.executar(chamada, instantes)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(instantes) == 3
    ordenados = sorted(instantes)
    for a, b in zip(ordenados, ordenados[1:]):
        assert b - a >= 0.05 - 1e-3
    del time_mod


def test_pedidos_rate_limiter_libera_lock_em_erro():
    from services.mercos_homolog_service import _RateLimiterMercos

    clk = _RelogioFake()
    limiter = _RateLimiterMercos(5.0, relogio=clk.agora, dormir=clk.dormir)

    def boom():
        raise RuntimeError("falha na chamada")

    with pytest.raises(RuntimeError):
        limiter.executar(boom)
    # Lock liberado no finally: nova execução funciona
    resultado, _ = limiter.executar(lambda: "ok")
    assert resultado == "ok"


def test_pedidos_sincronizacoes_diferentes_compartilham_limiter(monkeypatch):
    """O controle não é variável local: syncs distintas respeitam o intervalo."""
    from services.mercos_homolog_service import (
        _rate_limiter_pedidos,
        _reset_rate_limiters_para_testes,
    )

    _reset_rate_limiters_para_testes()
    l1 = _rate_limiter_pedidos()
    l2 = _rate_limiter_pedidos()
    assert l1 is l2
    clk = _RelogioFake()
    l1._relogio = clk.agora
    l1._dormir = clk.dormir
    instantes: list[float] = []
    l1.executar(lambda: "sync-1", instantes)
    # Segunda sincronização logo em seguida espera o intervalo restante
    l2.executar(lambda: "sync-2", instantes)
    assert instantes[1] - instantes[0] >= l1.intervalo_minimo


def test_pedidos_incremental_envia_cursor_exato(monkeypatch):
    """alterado_apos = cursor base byte a byte, nunca cursor - 1s."""
    from services.mercos_homolog_service import sincronizar_pedidos

    capt: dict = {}

    def fake_listar(alterado_apos=None, **_kw):
        capt["alterado_apos"] = alterado_apos
        return {"itens": [], "paginas_lidas": 1}

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_pedidos_paginado_seguro",
        fake_listar,
    )
    out = sincronizar_pedidos("2026-07-17 10:57:39")
    assert capt["alterado_apos"] == "2026-07-17 10:57:39"
    assert out["alterado_apos_enviado"] == out["cursor_base"] == "2026-07-17 10:57:39"
    assert out["novo_cursor"] == "2026-07-17 10:57:39"


def test_pedidos_localizar_nao_faz_requisicao_http(client, monkeypatch):
    """Localizar usa só o catálogo local (razão completa ou prefixo); cursor e etapa intactos."""
    catp = _prep_pedidos(client, monkeypatch)

    def explode(*_a, **_k):
        raise AssertionError("Localizar pedido não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", explode)
    monkeypatch.setattr("services.mercos_api_client.request_mercos", explode)

    client.post("/mercos/homologacao-ui/acoes/pedidos-reiniciar")
    sessao = client.cookies.get("mercos_pedidos_sessao")
    catp.upsert_incremental(
        sessao,
        [
            {
                "id": 2150999,
                "cliente_id": 9291000,
                "cliente_razao_social": "1f9e362a2b3a4365",
                "total": 249.9,
                "status": "1",
                "data_emissao": "2026-07-17",
                "ultima_alteracao": "2026-07-17 10:57:39",
            }
        ],
    )
    etapa_antes = catp.obter_ciclo(sessao)["etapa_interna"]

    # Por prefixo
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-localizar",
        data={"razao_social": "1f9e362a"},
    )
    assert resp.status_code == 200
    assert "Pedido localizado" in resp.text
    assert "1f9e362a2b3a4365" in resp.text
    assert "Total do pedido" in resp.text
    assert "249.90" in resp.text
    # Não altera cursor nem etapa
    assert resp.cookies.get("mercos_pedidos_cursor") is None
    assert 'data-cursor-fixo="1"' in resp.text
    assert catp.obter_ciclo(sessao)["etapa_interna"] == etapa_antes

    # Por razão social completa
    resp2 = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-localizar",
        data={"razao_social": "1f9e362a2b3a4365"},
    )
    assert "Pedido localizado" in resp2.text
    assert "249.90" in resp2.text


def test_pedidos_localizar_relaciona_cliente_id_com_catalogo_clientes(
    client, monkeypatch
):
    """Pedido sem razão social usa o catálogo local de clientes para relacionar."""
    from services import mercos_clientes_catalogo as catc

    catp = _prep_pedidos(client, monkeypatch)
    catc._reset_todos_para_testes()

    def explode(*_a, **_k):
        raise AssertionError("Localizar pedido não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_api_client.request_mercos", explode)

    # Catálogo local de clientes já sincronizado
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    sessao_cli = client.cookies.get("mercos_clientes_sessao")
    catc.upsert_incremental(
        sessao_cli,
        [
            {
                "id": 9291000,
                "razao_social": "1f9e362a2b3a4365",
                "ultima_alteracao": "2026-07-17 09:00:00",
            }
        ],
    )

    client.post("/mercos/homologacao-ui/acoes/pedidos-reiniciar")
    sessao = client.cookies.get("mercos_pedidos_sessao")
    catp.upsert_incremental(
        sessao,
        [
            {
                "id": 2150999,
                "cliente_id": 9291000,
                "total": 249.9,
                "status": "1",
                "data_emissao": "2026-07-17",
                "ultima_alteracao": "2026-07-17 10:57:39",
            }
        ],
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-localizar",
        data={"razao_social": "1f9e362a2b3a4365"},
    )
    assert resp.status_code == 200
    assert "Pedido localizado" in resp.text
    assert "1f9e362a2b3a4365" in resp.text
    assert "249.90" in resp.text


def test_pedidos_429_retorna_retry_after_e_libera_lock(client, monkeypatch):
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import _SYNC_PEDIDOS_LOCK

    _prep_pedidos(client, monkeypatch)

    def sempre_429(path, *, params=None, **_kw):
        raise MercosApiError("429", status_code=429, retry_after=7.0)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", sempre_429
    )
    client.post("/mercos/homologacao-ui/acoes/pedidos-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/pedidos-sincronizar")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "7"
    assert "Aguardando limite da Mercos" in resp.text
    # Lock liberado no finally: nova aquisição funciona
    assert _SYNC_PEDIDOS_LOCK.acquire(blocking=False) is True
    _SYNC_PEDIDOS_LOCK.release()


def test_pedidos_lock_libera_em_erro(monkeypatch):
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import (
        _SYNC_PEDIDOS_LOCK,
        sincronizar_pedidos,
    )

    _SYNC_PEDIDOS_LOCK.release()
    # Ocupado → 409 sem chamadas concorrentes
    assert _SYNC_PEDIDOS_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(MercosApiError) as exc:
            sincronizar_pedidos()
        assert exc.value.status_code == 409
    finally:
        _SYNC_PEDIDOS_LOCK.release()

    # Libera no finally mesmo com erro
    def boom(**_k):
        raise MercosApiError("falha", status_code=502)

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_pedidos_paginado_seguro", boom
    )
    with pytest.raises(MercosApiError):
        sincronizar_pedidos()
    assert _SYNC_PEDIDOS_LOCK.acquire(blocking=False) is True
    _SYNC_PEDIDOS_LOCK.release()


def test_pedidos_post_e_put_continuam_funcionando(client, monkeypatch):
    """As ações de Incluir e Alterar pedido não foram afetadas pelo ciclo GET."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_pedido",
        lambda body: {"ok": True, "status_code": 201, "id": 555, "dados": {}},
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.alterar_pedido",
        lambda pid, body: {"ok": True, "status_code": 200, "dados": {"id": pid}},
    )
    r1 = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-criar",
        data={"cliente_id": "9282664", "produto_id": "20386169", "quantidade": "1", "preco": "10.00"},
    )
    assert r1.status_code == 200
    assert "555" in r1.text
    r2 = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-alterar",
        data={"pedido_id": "555", "produto_id": "20386169", "preco": "10.00"},
    )
    assert r2.status_code == 200


def test_ui_pedido_incluir_tem_linhas_de_itens_e_seletor_condicao(client, monkeypatch):
    """A seção Pedido — Incluir mostra pelo menos duas linhas de item e o seletor."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    assert html.count("pedido-item-linha") >= 2
    assert 'id="btn-pedido-item-add"' in html
    assert 'id="select-pedido-condicao"' in html
    assert 'id="btn-pedido-carregar-condicoes"' in html
    # Valores da etapa 3/3 pré-preenchidos
    assert 'value="9290584"' in html
    assert 'value="20400740"' in html
    assert 'value="78.95"' in html
    assert 'value="20400741"' in html
    assert 'value="67.65"' in html


def test_condicoes_opcoes_exige_token(client):
    resp = client.post("/mercos/homologacao-ui/acoes/condicoes-opcoes")
    assert resp.status_code == 403


def test_condicoes_opcoes_lista_nome_e_id(client, monkeypatch):
    """O seletor reutiliza o catálogo de condições, mostrando nome e ID."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    criar = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.criar_pedido", criar)
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_condicoes_pagamento",
        lambda **_k: {
            "ok": True,
            "total": 3,
            "itens": [
                {"id": 3, "nome": "À vista", "excluido": False},
                {"id": 4, "nome": "30 dias", "excluido": False},
                {"id": 5, "nome": "Antiga", "excluido": True},
            ],
        },
    )
    resp = client.post("/mercos/homologacao-ui/acoes/condicoes-opcoes")
    assert resp.status_code == 200
    assert "À vista (ID 3)" in resp.text
    assert "30 dias (ID 4)" in resp.text
    assert "Antiga" not in resp.text  # excluída não aparece
    # Carregar condições nunca envia o pedido
    criar.assert_not_called()


def test_condicoes_opcoes_seleciona_a_vista_sem_acentos(client, monkeypatch):
    """A condição com "vista" no nome (sem acento/maiúsculas) já vem selecionada."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_condicoes_pagamento",
        lambda **_k: {
            "ok": True,
            "total": 2,
            "itens": [
                {"id": 4, "nome": "30 dias", "excluido": False},
                {"id": 7, "nome": "A VISTA", "excluido": False},
            ],
        },
    )
    resp = client.post("/mercos/homologacao-ui/acoes/condicoes-opcoes")
    assert resp.status_code == 200
    assert 'value="7" data-nome="A VISTA" selected' in resp.text
    assert "data-vista-ausente" not in resp.text


def test_condicoes_opcoes_sem_a_vista_avisa(client, monkeypatch):
    """Sem condição à vista ativa, marca data-vista-ausente para a UI avisar."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_condicoes_pagamento",
        lambda **_k: {
            "ok": True,
            "total": 2,
            "itens": [
                # Cenário real do sandbox: todas as condições excluídas
                {"id": 264893, "nome": "Pix", "excluido": True},
                {"id": 264886, "nome": "Pix parcelado em até 9 vezes", "excluido": True},
            ],
        },
    )
    resp = client.post("/mercos/homologacao-ui/acoes/condicoes-opcoes")
    assert resp.status_code == 200
    assert "data-vista-ausente" in resp.text
    assert "Pix" not in resp.text  # excluídas não aparecem


def test_condicoes_opcoes_falha_mostra_cartao_de_erro(client, monkeypatch):
    """Falha na Mercos aparece como cartão amigável, não silenciosamente."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(**_k):
        raise MercosApiError("indisponível", status_code=502)

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_condicoes_pagamento", boom
    )
    resp = client.post("/mercos/homologacao-ui/acoes/condicoes-opcoes")
    assert resp.status_code == 200
    assert "result-card" in resp.text
    assert "Falha na operação" in resp.text


def test_ui_secao_forma_pagamento_incluir_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    assert 'id="sec-formas-pagamento-criar"' in html
    assert "Forma de pagamento — Incluir" in html
    assert 'value="cca8fdd8c4a24557"' in html
    assert 'id="input-forma-pgto-ativo"' in html


def test_botao_formas_pagamento_usa_url_registrada(client, monkeypatch):
    """A URL do botão renderizado na UI e a rota FastAPI são exatamente iguais."""
    import re

    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    m = re.search(r'data-action="([^"]*formas-pagamento-criar[^"]*)"', html)
    assert m, "botão de forma de pagamento sem data-action na UI"
    url = m.group(1)
    assert url == "/mercos/homologacao-ui/acoes/formas-pagamento-criar"

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 90233, "dados": {}},
    )
    resp = client.post(url, data={"nome": "cca8fdd8c4a24557", "ativo": "sim"})
    assert resp.status_code != 404
    assert resp.status_code == 200
    assert "Status 201" in resp.text
    assert "90233" in resp.text


def test_todos_os_botoes_data_action_apontam_para_rotas_existentes(
    client, monkeypatch
):
    """Nenhum botão da UI pode apontar para rota inexistente (404).

    Sem cookie de sessão, toda ação registrada responde 403 (token exigido);
    404 indicaria botão com URL errada ou rota não registrada.
    """
    import re

    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    urls = sorted(set(re.findall(r'data-action="([^"]+)"', html)))
    assert urls, "nenhum botão data-action encontrado na UI"
    from fastapi.testclient import TestClient
    from main import app

    anonimo = TestClient(app)  # sem cookie: espera 403, nunca 404
    for url in urls:
        resp = anonimo.post(url)
        assert resp.status_code != 404, f"rota inexistente para o botão: {url}"


def test_formas_pagamento_criar_exige_token(client):
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-criar",
        data={"nome": "cca8fdd8c4a24557"},
    )
    assert resp.status_code == 403


def test_formas_pagamento_post_payload_e_endpoint_corretos(client, monkeypatch):
    """Um único POST em /v1/formas_pagamento com nome exato e excluido=False."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, body))
        return {"ok": True, "status_code": 201, "id": 90210, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-criar",
        data={"nome": "cca8fdd8c4a24557", "ativo": "sim"},
    )
    assert resp.status_code == 200

    # Um único POST, no endpoint de formas (não o de condições)
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/formas_pagamento"
    assert body == {"nome": "cca8fdd8c4a24557", "excluido": False}

    # Cartão com 201, ID capturado e nome; sem token nem JSON bruto
    html = resp.text
    assert "201" in html
    assert "90210" in html
    assert "cca8fdd8c4a24557" in html
    assert "Ativo" in html and "Sim" in html
    assert '"nome"' not in html
    assert "segredo-ui-homolog" not in html


def test_formas_pagamento_post_ativo_nao_envia_excluido_true(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: chamadas.append((path, body))
        or {"ok": True, "status_code": 201, "id": 90211, "dados": {}},
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-criar",
        data={"nome": "cca8fdd8c4a24557", "ativo": "nao"},
    )
    assert resp.status_code == 200
    assert chamadas[0][1] == {"nome": "cca8fdd8c4a24557", "excluido": True}
    assert "Não" in resp.text


def test_formas_pagamento_post_sem_nome_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-criar",
        data={"nome": "   "},
    )
    assert resp.status_code == 200
    assert "Campos obrigatórios" in resp.text
    post.assert_not_called()


def test_formas_pagamento_post_erro_mercos_mostra_cartao(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError("Dados inválidos", status_code=412)

    monkeypatch.setattr("services.mercos_homolog_service.post_json", boom)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-criar",
        data={"nome": "cca8fdd8c4a24557"},
    )
    assert resp.status_code == 200
    assert "Falha na operação" in resp.text
    assert "412" in resp.text


def test_ui_secao_forma_pagamento_alterar_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-formas-pagamento-alterar"' in html
    assert "Forma de pagamento — Alterar" in html
    assert "Excluir logicamente" in html
    # Valores da etapa 2/3 pré-preenchidos
    assert 'value="90000"' in html
    assert 'value="ad4feae8a8b643d0"' in html


def test_formas_pagamento_put_endpoint_id_na_url_e_payload(client, monkeypatch):
    """Um único PUT em /v1/formas_pagamento/{id}; id fora do corpo; ativo→excluido."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_put_json(path, body):
        chamadas.append((path, body))
        return {"ok": True, "status_code": 200, "dados": {}}

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put_json)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-alterar",
        data={
            "forma_id": "90000",
            "nome": "ad4feae8a8b643d0",
            "ativo": "sim",
        },
    )
    assert resp.status_code == 200

    # Um único PUT, endpoint de formas (não o de condições), id só na URL
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/formas_pagamento/90000"
    assert body == {"nome": "ad4feae8a8b643d0", "excluido": False}
    assert "id" not in body

    html = resp.text
    assert "Status 200" in html
    assert "90000" in html
    assert "ad4feae8a8b643d0" in html
    assert "Mercos Sandbox" in html
    assert '"nome"' not in html  # sem JSON cru
    assert "segredo-ui-homolog" not in html


def test_formas_pagamento_put_exclusao_logica(client, monkeypatch):
    """Excluir logicamente: excluido=true com nome obrigatório, sem DELETE."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.put_json",
        lambda path, body: chamadas.append((path, body))
        or {"ok": True, "status_code": 200, "dados": {}},
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-alterar",
        data={
            "forma_id": "90000",
            "nome": "ad4feae8a8b643d0",
            "excluido": "true",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/formas_pagamento/90000"
    assert body == {"nome": "ad4feae8a8b643d0", "excluido": True}
    assert "Excluído" in resp.text and "Sim" in resp.text


def test_formas_pagamento_put_excluido_prevalece_sobre_ativo(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.put_json",
        lambda path, body: chamadas.append((path, body))
        or {"ok": True, "status_code": 200, "dados": {}},
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-alterar",
        data={
            "forma_id": "90000",
            "nome": "ad4feae8a8b643d0",
            "ativo": "sim",
            "excluido": "true",
        },
    )
    assert resp.status_code == 200
    assert chamadas[0][1]["excluido"] is True


def test_formas_pagamento_put_sem_id_ou_nome_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    put = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.put_json", put)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-alterar",
        data={"forma_id": "90000", "nome": "  "},
    )
    assert resp.status_code == 200
    assert "Campos obrigatórios" in resp.text
    put.assert_not_called()


def test_formas_pagamento_put_erro_412_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError("Dados inválidos", status_code=412)

    monkeypatch.setattr("services.mercos_homolog_service.put_json", boom)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-alterar",
        data={"forma_id": "90000", "nome": "ad4feae8a8b643d0"},
    )
    assert resp.status_code == 200
    assert "Falha na operação" in resp.text
    assert "412" in resp.text


def test_formas_pagamento_post_continua_funcionando_apos_put(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    monkeypatch.setattr(
        "services.mercos_homolog_service.put_json",
        lambda path, body: {"ok": True, "status_code": 200, "dados": {}},
    )
    client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-alterar",
        data={"forma_id": "90000", "nome": "ad4feae8a8b643d0", "ativo": "sim"},
    )
    chamadas_post: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: chamadas_post.append((path, body))
        or {"ok": True, "status_code": 201, "id": 90300, "dados": {}},
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-criar",
        data={"nome": "cca8fdd8c4a24557", "ativo": "sim"},
    )
    assert resp.status_code == 200
    assert chamadas_post[0][0] == "/v1/formas_pagamento"
    assert "Status 201" in resp.text


def test_condicoes_get_intacto_apos_formas_pagamento(client, monkeypatch):
    """O GET de Condições de Pagamento continua funcionando e separado."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 90212, "dados": {}},
    )
    client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-criar",
        data={"nome": "cca8fdd8c4a24557"},
    )
    listar = MagicMock(
        return_value={
            "ok": True,
            "total": 1,
            "itens": [{"id": 264893, "nome": "Pix", "excluido": False}],
        }
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_condicoes_pagamento", listar
    )
    resp = client.post("/mercos/homologacao-ui/acoes/condicoes")
    assert resp.status_code == 200
    assert "Pix" in resp.text
    listar.assert_called_once()


def test_pedido_post_sem_condicao_id_usa_a_vista_pelo_nome(client, monkeypatch):
    """Sem ID de condição selecionado, o pedido vai com condicao_pagamento "a vista"."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[dict] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_pedido",
        lambda body: chamadas.append(body)
        or {"ok": True, "status_code": 201, "id": 779, "dados": {}},
    )
    itens_json = (
        '[{"produto_id": "20400740", "quantidade": "4", "preco": "78.95"},'
        ' {"produto_id": "20400741", "quantidade": "2", "preco": "67.65"}]'
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-criar",
        data={"cliente_id": "9290584", "itens_json": itens_json},
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    body = chamadas[0]
    assert body["condicao_pagamento"] == "a vista"
    assert "condicao_pagamento_id" not in body
    assert len(body["itens"]) == 2
    assert "À vista (pelo nome)" in resp.text


def test_pedido_post_dois_itens_em_um_unico_post(client, monkeypatch):
    """Um único POST com dois itens (4x78.95 e 2x67.65), condição À vista."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[dict] = []

    def fake_criar_pedido(body):
        chamadas.append(body)
        return {"ok": True, "status_code": 201, "id": 777, "dados": {"numero": 42}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_pedido", fake_criar_pedido
    )
    itens_json = (
        '[{"produto_id": "20400740", "quantidade": "4", "preco": "78.95"},'
        ' {"produto_id": "20400741", "quantidade": "2", "preco": "67.65"}]'
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-criar",
        data={
            "cliente_id": "9290584",
            "itens_json": itens_json,
            "condicao_pagamento_id": "3",
            "condicao_pagamento_nome": "À vista",
        },
    )
    assert resp.status_code == 200

    # Um único POST enviado (não dois pedidos)
    assert len(chamadas) == 1
    body = chamadas[0]
    assert body["cliente_id"] == 9290584
    assert body["condicao_pagamento_id"] == 3
    itens = body["itens"]
    assert len(itens) == 2
    assert itens[0] == {
        "produto_id": 20400740,
        "quantidade": 4.0,
        "preco_tabela": 78.95,
    }
    assert itens[1] == {
        "produto_id": 20400741,
        "quantidade": 2.0,
        "preco_tabela": 67.65,
    }
    # Cliente somente no pedido, não dentro dos itens
    assert all("cliente_id" not in item for item in itens)

    html = resp.text
    assert "777" in html
    assert "À vista" in html
    assert "Quantidade de itens" in html
    assert "451.10" in html  # 4*78.95 + 2*67.65
    assert "78.95" in html and "67.65" in html
    # Sem JSON bruto nem token no cartão
    assert '"produto_id"' not in html
    assert "segredo-ui-homolog" not in html


def test_pedido_post_sem_itens_retorna_erro_sem_chamar_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    criar = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.criar_pedido", criar)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-criar",
        data={"cliente_id": "9290584", "itens_json": "[]"},
    )
    assert resp.status_code == 200
    assert "Itens obrigatórios" in resp.text
    criar.assert_not_called()


def test_pedido_post_item_sem_produto_e_ignorado(client, monkeypatch):
    """Linhas sem código de produto não entram no payload; só linhas válidas."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[dict] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_pedido",
        lambda body: chamadas.append(body)
        or {"ok": True, "status_code": 201, "id": 778, "dados": {}},
    )
    itens_json = (
        '[{"produto_id": "", "quantidade": "1", "preco": "5.00"},'
        ' {"produto_id": "20400740", "quantidade": "4", "preco": "78.95"}]'
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-criar",
        data={"cliente_id": "9290584", "itens_json": itens_json},
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    assert len(chamadas[0]["itens"]) == 1
    assert chamadas[0]["itens"][0]["produto_id"] == 20400740


def test_ui_secao_pedido_cancelar_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-pedidos-cancelar"' in html
    assert "Pedido — Cancelar" in html
    assert "Cancelar pedido" in html
    assert 'value="2150137"' in html  # ID da etapa 4/4 pré-preenchido


def test_pedidos_cancelar_endpoint_metodo_e_id_na_url(client, monkeypatch):
    """POST /v1/pedidos/cancelar/{id}: uma única chamada, id só na URL, corpo vazio."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, body))
        return {"ok": True, "status_code": 200, "id": None, "dados": {}}

    monkeypatch.setattr("services.mercos_homolog_service.post_json", fake_post_json)
    # PUT comum e DELETE não podem ser usados no cancelamento
    put = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.put_json", put)

    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-cancelar",
        data={"pedido_id": "2150137"},
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/pedidos/cancelar/2150137"
    assert body == {}  # id nunca no corpo; sem motivo (contrato não aceita)
    put.assert_not_called()

    html = resp.text
    assert "Status HTTP" in html
    assert "2150137" in html
    assert "Cancelado" in html
    assert "Mercos Sandbox" in html
    assert '"pedido_id"' not in html  # sem JSON cru
    assert "segredo-ui-homolog" not in html


def test_pedidos_cancelar_metodo_http_post(monkeypatch):
    """O serviço de cancelamento envia método POST (nunca DELETE)."""
    from services import mercos_homolog_service as homolog

    metodos: list[tuple[str, str]] = []

    class _RespFake:
        status_code = 200
        text = ""
        headers: dict = {}

        def json(self):
            return {}

    def fake_request(metodo, path, **kw):
        metodos.append((metodo, path))
        return _RespFake()

    monkeypatch.setattr(
        "services.mercos_api_client.request_mercos", fake_request
    )
    out = homolog.cancelar_pedido("2150137")
    assert out["status_code"] == 200
    assert metodos == [("POST", "/v1/pedidos/cancelar/2150137")]


def test_pedidos_cancelar_mostra_status_anterior_do_catalogo(client, monkeypatch):
    """Status anterior vem do catálogo local, sem chamada extra à Mercos."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services import mercos_pedidos_catalogo

    mercos_pedidos_catalogo._reset_todos_para_testes()
    mercos_pedidos_catalogo.substituir_completo(
        "sessao-cancelar",
        [{"id": 2150137, "cliente_id": 9290584, "status": "2", "total": 451.10}],
    )
    client.cookies.set("mercos_pedidos_sessao", "sessao-cancelar")
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 200, "id": None, "dados": {}},
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-cancelar",
        data={"pedido_id": "2150137"},
    )
    assert resp.status_code == 200
    assert "Status anterior" in resp.text
    assert "Status atual" in resp.text
    mercos_pedidos_catalogo._reset_todos_para_testes()


def test_pedidos_cancelar_sem_id_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-cancelar", data={"pedido_id": " "}
    )
    assert resp.status_code == 200
    assert "Pedido não informado" in resp.text
    post.assert_not_called()


def test_pedidos_cancelar_inexistente_mostra_erro_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError(
            "Pedido 2150137 inexistente para conta 1234567", status_code=412
        )

    monkeypatch.setattr("services.mercos_homolog_service.post_json", boom)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-cancelar",
        data={"pedido_id": "2150137"},
    )
    assert resp.status_code == 200
    assert "Pedido não encontrado" in resp.text
    assert "412" in resp.text
    assert '"mensagem"' not in resp.text  # sem JSON cru


def test_pedidos_cancelar_ja_cancelado_mostra_erro_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError("Pedido já cancelado", status_code=412)

    monkeypatch.setattr("services.mercos_homolog_service.post_json", boom)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-cancelar",
        data={"pedido_id": "2150137"},
    )
    assert resp.status_code == 200
    assert "Pedido já cancelado" in resp.text


def test_pedidos_get_post_put_intactos_apos_cancelamento(client, monkeypatch):
    """Cancelar não interfere em Pedido GET (localizar), POST e PUT."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 200, "id": None, "dados": {}},
    )
    client.post(
        "/mercos/homologacao-ui/acoes/pedidos-cancelar",
        data={"pedido_id": "2150137"},
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_pedido",
        lambda body: {"ok": True, "status_code": 201, "id": 556, "dados": {}},
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.alterar_pedido",
        lambda pid, body: {"ok": True, "status_code": 200, "dados": {"id": pid}},
    )
    r1 = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-criar",
        data={
            "cliente_id": "9290584",
            "itens_json": '[{"produto_id": "20400740", "quantidade": "4", "preco": "78.95"}]',
        },
    )
    assert r1.status_code == 200 and "556" in r1.text
    r2 = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-alterar",
        data={"pedido_id": "556", "produto_id": "20400740", "preco": "10.00"},
    )
    assert r2.status_code == 200
    r3 = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-localizar",
        data={"razao_social": "qualquer"},
    )
    assert r3.status_code == 200


def test_ui_secao_pedido_faturar_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-pedidos-faturar"' in html
    assert "Pedido — Faturar" in html
    assert "Localizar pedido" in html
    assert "Faturar pedido" in html
    # Valores da etapa 1/1 pré-preenchidos
    assert 'value="19"' in html
    assert 'value="b2aeaa9b298a404b"' in html
    assert 'value="91.51"' in html


def test_faturamento_rotas_registradas_sem_404(client):
    """Botões de faturar apontam para rotas existentes (403 sem token, nunca 404)."""
    from fastapi.testclient import TestClient
    from main import app

    anonimo = TestClient(app)
    for url in (
        "/mercos/homologacao-ui/acoes/pedidos-faturar",
        "/mercos/homologacao-ui/acoes/pedidos-faturar-localizar",
    ):
        resp = anonimo.post(url)
        assert resp.status_code != 404, f"rota inexistente: {url}"


def test_faturamento_servico_metodo_post_endpoint_e_payload(monkeypatch):
    """POST /v1/faturamento com pedido_id, valor_faturado e data_faturamento."""
    from services import mercos_homolog_service as homolog

    chamadas: list[tuple[str, str, dict]] = []

    class _RespFake:
        status_code = 201
        text = ""
        headers: dict = {}

        def json(self):
            return {}

    def fake_request(metodo, path, **kw):
        chamadas.append((metodo, path, kw.get("json_body") or {}))
        return _RespFake()

    monkeypatch.setattr("services.mercos_api_client.request_mercos", fake_request)
    out = homolog.faturar_pedido("2150140", 91.51)
    assert out["status_code"] == 201
    assert len(chamadas) == 1
    metodo, path, body = chamadas[0]
    assert metodo == "POST"  # nunca DELETE nem PUT
    assert path == "/v1/faturamento"
    assert body["pedido_id"] == 2150140
    assert body["valor_faturado"] == 91.51
    assert body["data_faturamento"]  # obrigatório no contrato (AAAA-MM-DD)
    assert len(body["data_faturamento"].split("-")) == 3
    assert "id" not in body


def test_faturamento_localiza_pelo_numero_sem_requisicao_http(client, monkeypatch):
    """Localizar busca só o catálogo local, confere cliente/total e devolve o ID."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services import mercos_pedidos_catalogo

    mercos_pedidos_catalogo._reset_todos_para_testes()
    mercos_pedidos_catalogo.substituir_completo(
        "sessao-faturar",
        [
            {
                "id": 2150140,
                "numero": 19,
                "cliente_id": 9290584,
                "cliente_razao_social": "b2aeaa9b298a404b",
                "total": 91.51,
                "status": "2",
            }
        ],
    )
    client.cookies.set("mercos_pedidos_sessao", "sessao-faturar")

    http = MagicMock(side_effect=AssertionError("não pode chamar a Mercos"))
    monkeypatch.setattr("services.mercos_homolog_service.get_json", http)
    monkeypatch.setattr("services.mercos_homolog_service.post_json", http)

    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-faturar-localizar",
        data={"numero": "19", "cliente": "b2aeaa9b298a404b", "total": "91.51"},
    )
    assert resp.status_code == 200
    html = resp.text
    assert 'data-pedido-faturar-id="2150140"' in html
    assert "b2aeaa9b298a404b" in html
    assert "91.51" in html
    assert html.count("Sim") >= 2  # cliente confere e total conferem
    http.assert_not_called()
    mercos_pedidos_catalogo._reset_todos_para_testes()


def test_faturamento_localizar_fora_do_catalogo_pede_sincronizacao(
    client, monkeypatch
):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services import mercos_pedidos_catalogo

    mercos_pedidos_catalogo._reset_todos_para_testes()
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-faturar-localizar",
        data={"numero": "19"},
    )
    assert resp.status_code == 200
    assert "Sincronize os pedidos antes de faturar." in resp.text


def test_faturamento_um_unico_post_com_valor_91_51(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, body))
        return {"ok": True, "status_code": 201, "id": None, "dados": {}}

    monkeypatch.setattr("services.mercos_homolog_service.post_json", fake_post_json)
    put = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.put_json", put)

    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-faturar",
        data={
            "pedido_id": "2150140",
            "numero": "19",
            "cliente": "b2aeaa9b298a404b",
            "total": "91.51",
            "valor_faturado": "91.51",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/faturamento"
    assert body["pedido_id"] == 2150140
    assert body["valor_faturado"] == 91.51
    put.assert_not_called()

    html = resp.text
    assert "Status HTTP" in html and "201" in html
    assert "Faturado" in html
    assert "b2aeaa9b298a404b" in html
    assert "Mercos Sandbox" in html
    assert '"pedido_id"' not in html  # sem JSON cru
    assert "segredo-ui-homolog" not in html


def test_faturamento_sem_id_localizado_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-faturar",
        data={"pedido_id": "", "valor_faturado": "91.51"},
    )
    assert resp.status_code == 200
    assert "Localizar pedido" in resp.text or "Pedido não localizado" in resp.text
    post.assert_not_called()


def test_faturamento_valor_zero_ou_negativo_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)
    for valor in ("", "0", "-5"):
        resp = client.post(
            "/mercos/homologacao-ui/acoes/pedidos-faturar",
            data={"pedido_id": "2150140", "valor_faturado": valor},
        )
        assert resp.status_code == 200
        assert "Valor faturado inválido" in resp.text
    post.assert_not_called()


def test_faturamento_pedido_cancelado_erro_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError(
            "Não é possível faturar um pedido cancelado", status_code=412
        )

    monkeypatch.setattr("services.mercos_homolog_service.post_json", boom)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-faturar",
        data={"pedido_id": "2150137", "valor_faturado": "91.51"},
    )
    assert resp.status_code == 200
    assert "Pedido cancelado não pode ser faturado" in resp.text
    assert "412" in resp.text


def test_faturamento_pedido_ja_faturado_erro_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError("Pedido já faturado", status_code=412)

    monkeypatch.setattr("services.mercos_homolog_service.post_json", boom)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-faturar",
        data={"pedido_id": "2150140", "valor_faturado": "91.51"},
    )
    assert resp.status_code == 200
    assert "Pedido já faturado" in resp.text


def test_faturamento_erro_412_generico_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError("Não foi possível alterar o faturamento.", status_code=412)

    monkeypatch.setattr("services.mercos_homolog_service.post_json", boom)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-faturar",
        data={"pedido_id": "2150140", "valor_faturado": "91.51"},
    )
    assert resp.status_code == 200
    assert "Não foi possível faturar o pedido" in resp.text
    assert '"mensagem"' not in resp.text  # sem JSON cru


def test_ui_secao_faturamento_alterar_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-faturamento-alterar"' in html
    assert "Faturamento de pedido — Alterar" in html
    assert "Alterar faturamento" in html
    # Valores da etapa 2/2 pré-preenchidos
    assert 'value="2150142"' in html
    assert 'value="20"' in html
    assert 'value="457564bfe6984fc6"' in html
    assert 'value="43.44"' in html
    assert 'value="10.86"' in html


def test_faturamento_put_servico_endpoint_metodo_e_payload(monkeypatch):
    """PUT /v1/faturamento/{id do faturamento} com corpo completo do contrato."""
    from services import mercos_homolog_service as homolog

    chamadas: list[tuple[str, str, dict]] = []

    class _RespFake:
        status_code = 201
        text = ""
        headers: dict = {}

        def json(self):
            return {}

    def fake_request(metodo, path, **kw):
        chamadas.append((metodo, path, kw.get("json_body") or {}))
        return _RespFake()

    monkeypatch.setattr("services.mercos_api_client.request_mercos", fake_request)
    out = homolog.alterar_faturamento("77001", "2150142", 10.86)
    assert out["status_code"] == 201
    assert len(chamadas) == 1
    metodo, path, body = chamadas[0]
    assert metodo == "PUT"  # nunca POST nem DELETE
    assert path == "/v1/faturamento/77001"  # ID do faturamento na URL
    assert body["pedido_id"] == 2150142
    assert body["valor_faturado"] == 10.86
    assert body["data_faturamento"]  # reenviado (obrigatório no contrato)
    assert "id" not in body


def test_faturamento_put_um_unico_put_sem_post(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_put_json(path, body):
        chamadas.append((path, body))
        return {"ok": True, "status_code": 201, "dados": {}}

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put_json)
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)

    resp = client.post(
        "/mercos/homologacao-ui/acoes/faturamento-alterar",
        data={
            "faturamento_id": "77001",
            "pedido_id": "2150142",
            "numero": "20",
            "cliente": "457564bfe6984fc6",
            "total": "43.44",
            "valor_anterior": "43.44",
            "novo_valor": "10.86",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/faturamento/77001"
    assert body["valor_faturado"] == 10.86
    post.assert_not_called()  # nenhuma chamada POST

    html = resp.text
    assert "Status HTTP" in html and "201" in html
    assert "457564bfe6984fc6" in html
    assert "43.44" in html and "10.86" in html
    assert "Faturamento alterado" in html
    assert "Mercos Sandbox" in html
    assert '"pedido_id"' not in html  # sem JSON cru
    assert "segredo-ui-homolog" not in html


def test_faturamento_put_sem_ids_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    put = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.put_json", put)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/faturamento-alterar",
        data={"faturamento_id": "", "pedido_id": "2150142", "novo_valor": "10.86"},
    )
    assert resp.status_code == 200
    assert "Faturamento não identificado" in resp.text
    put.assert_not_called()


def test_faturamento_put_valor_invalido_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    put = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.put_json", put)
    for valor in ("", "0", "-1"):
        resp = client.post(
            "/mercos/homologacao-ui/acoes/faturamento-alterar",
            data={
                "faturamento_id": "77001",
                "pedido_id": "2150142",
                "novo_valor": valor,
            },
        )
        assert resp.status_code == 200
        assert "Valor faturado inválido" in resp.text
    put.assert_not_called()


def test_faturamento_put_erros_amigaveis(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    cenarios = [
        ("Faturamento inexistente para conta 123", 412, "Faturamento não encontrado"),
        ("Recurso não encontrado", 404, "Faturamento não encontrado"),
        (
            "Não é possível alterar faturamento de pedido cancelado",
            412,
            "Pedido cancelado não pode ter faturamento alterado",
        ),
        (
            "Não foi possível alterar o faturamento.",
            412,
            "Não foi possível alterar o faturamento",
        ),
    ]
    for mensagem, status, titulo in cenarios:
        def boom(path, body, _m=mensagem, _s=status):
            raise MercosApiError(_m, status_code=_s)

        monkeypatch.setattr("services.mercos_homolog_service.put_json", boom)
        resp = client.post(
            "/mercos/homologacao-ui/acoes/faturamento-alterar",
            data={
                "faturamento_id": "77001",
                "pedido_id": "2150142",
                "novo_valor": "10.86",
            },
        )
        assert resp.status_code == 200
        assert titulo in resp.text
        assert '"mensagem"' not in resp.text  # sem JSON cru


def test_faturamento_post_expoe_id_do_faturamento(client, monkeypatch):
    """O cartão do POST mostra o ID do faturamento (necessário na etapa PUT)."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 77001, "dados": {}},
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-faturar",
        data={"pedido_id": "2150142", "valor_faturado": "43.44"},
    )
    assert resp.status_code == 200
    assert "ID do faturamento" in resp.text
    assert 'data-faturamento-id="77001"' in resp.text


def test_faturamento_post_continua_funcionando_apos_put(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    monkeypatch.setattr(
        "services.mercos_homolog_service.put_json",
        lambda path, body: {"ok": True, "status_code": 201, "dados": {}},
    )
    client.post(
        "/mercos/homologacao-ui/acoes/faturamento-alterar",
        data={
            "faturamento_id": "77001",
            "pedido_id": "2150142",
            "novo_valor": "10.86",
        },
    )
    chamadas: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: chamadas.append((path, body))
        or {"ok": True, "status_code": 201, "id": 77002, "dados": {}},
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-faturar",
        data={"pedido_id": "2150143", "valor_faturado": "50.00"},
    )
    assert resp.status_code == 200
    assert chamadas[0][0] == "/v1/faturamento"
    assert "Faturado" in resp.text


def test_faturamento_alterar_rota_registrada_sem_404(client):
    from fastapi.testclient import TestClient
    from main import app

    anonimo = TestClient(app)
    resp = anonimo.post("/mercos/homologacao-ui/acoes/faturamento-alterar")
    assert resp.status_code != 404
    assert resp.status_code == 403


def test_pedidos_fluxos_intactos_apos_faturamento(client, monkeypatch):
    """GET (localizar), POST, PUT e Cancelamento seguem funcionando."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": None, "dados": {}},
    )
    client.post(
        "/mercos/homologacao-ui/acoes/pedidos-faturar",
        data={"pedido_id": "2150140", "valor_faturado": "91.51"},
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_pedido",
        lambda body: {"ok": True, "status_code": 201, "id": 557, "dados": {}},
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.alterar_pedido",
        lambda pid, body: {"ok": True, "status_code": 200, "dados": {"id": pid}},
    )
    r1 = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-criar",
        data={
            "cliente_id": "9290584",
            "itens_json": '[{"produto_id": "20400740", "quantidade": "4", "preco": "78.95"}]',
        },
    )
    assert r1.status_code == 200 and "557" in r1.text
    r2 = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-alterar",
        data={"pedido_id": "557", "produto_id": "20400740", "preco": "10.00"},
    )
    assert r2.status_code == 200
    r3 = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-localizar",
        data={"razao_social": "qualquer"},
    )
    assert r3.status_code == 200
    r4 = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-cancelar",
        data={"pedido_id": "2150137"},
    )
    assert r4.status_code == 200


def test_acao_tipos_pedido_exige_token(client):
    resp = client.post("/mercos/homologacao-ui/acoes/tipos-pedido")
    assert resp.status_code == 403


def test_acao_tipos_pedido_sucesso_destaca_19814a3(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_tipos_pedido_descoberta",
        lambda **_k: {
            "ok": True,
            "status_code": 200,
            "path_resolvido": "/v1/pedidos/tipo",
            "paths_testados": ["/v1/pedidos/tipo"],
            "total": 3,
            "itens": [
                {"id": 1, "nome": "19814a3-pedido-especial", "excluido": False},
                {"id": 2, "nome": "198314a3385b4af2", "excluido": False},
                {"id": 3, "nome": "0832f68deadbeef", "excluido": False},
                {
                    "id": 4,
                    "nome": "8df21d6cd7d44fd6",
                    "excluido": True,
                    "ultima_alteracao": "2026-07-14 14:37:38",
                },
                {"id": 5, "nome": "Normal", "excluido": False, "updated_at": "2026-07-01"},
            ],
            "filtros": {
                "alterado_apos": "2026-07-14 00:00:00",
                "excluidos": "true",
            },
        },
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/tipos-pedido",
        data={
            "alterado_apos": "2026-07-14 00:00:00",
            "excluido": "true",
        },
    )
    assert resp.status_code == 200
    html = resp.text
    assert "200" in html
    assert "Filtro usado:" in html
    assert "2026-07-14 00:00:00" in html
    assert "8df21d6cd7d44fd6" in html
    assert ">Sim<" in html
    assert html.count("destaque-homolog") >= 4
    assert "Normal" in html
    assert '"itens"' not in html


def test_acao_tipos_pedido_combinacoes_mostra_filtro_por_registro(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.explorar_filtros_tipos_pedido",
        lambda **_k: {
            "ok": True,
            "status_code": 200,
            "total": 1,
            "itens": [
                {
                    "id": 9,
                    "nome": "8df21d6cd7d44fd6",
                    "excluido": True,
                    "_filtros_encontrados": [
                        "alterado_apos=2026-07-14 00:00:00&excluido=true"
                    ],
                }
            ],
            "tentativas": [
                {
                    "filtro": "alterado_apos=2026-07-14 00:00:00&excluido=true",
                    "ok": True,
                    "total": 1,
                }
            ],
        },
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post("/mercos/homologacao-ui/acoes/tipos-pedido-combinacoes")
    assert resp.status_code == 200
    assert "Combinações testadas" in resp.text
    assert "8df21d6cd7d44fd6" in resp.text
    assert "Filtro que encontrou" in resp.text
    assert "excluido=true" in resp.text
    assert "destaque-homolog" in resp.text


def test_acao_tipos_pedido_todos_404(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_tipos_pedido_descoberta",
        lambda **_k: {
            "ok": False,
            "status_code": 404,
            "paths_testados": [
                "/v1/pedidos/tipo",
                "/v1/tipos_pedido",
                "/v1/tipos_pedidos",
            ],
            "itens": [],
            "total": 0,
            "mensagem": (
                "Não foi possível localizar o endpoint oficial de Tipo de Pedido no sandbox. "
                "Paths testados: /v1/pedidos/tipo, /v1/tipos_pedido, /v1/tipos_pedidos"
            ),
        },
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post("/mercos/homologacao-ui/acoes/tipos-pedido")
    assert resp.status_code == 200
    assert "Não foi possível localizar o endpoint oficial de Tipo de Pedido" in resp.text
    assert "/v1/pedidos/tipo" in resp.text


def test_candidatos_tipos_pedido_prioriza_pedidos_tipo(monkeypatch):
    monkeypatch.delenv("MERCOS_PATH_TIPOS_PEDIDO", raising=False)
    from services.mercos_homolog_service import caminhos_candidatos_tipos_pedido

    paths = caminhos_candidatos_tipos_pedido()
    assert paths[0] == "/v1/pedidos/tipo"
    assert "/v1/tipos_pedido" in paths


def test_ui_form_produto_alterar_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    assert "Produto — Alterar" in html
    assert 'id="input-produto-alt-id"' in html
    assert 'id="input-produto-alt-nome"' in html
    assert 'id="input-produto-alt-codigo"' in html
    assert 'id="input-produto-alt-preco"' in html
    assert 'id="input-produto-alt-estoque"' in html
    assert 'id="input-produto-alt-ativo"' in html
    assert 'id="input-produto-alt-unidade"' in html
    assert "/mercos/homologacao-ui/acoes/produtos-alterar" in html


def test_ui_produtos_alterar_envia_payload_e_cartao(client, monkeypatch):
    capturado: dict = {}

    def fake_put(path, body):
        capturado["path"] = path
        capturado["body"] = dict(body)
        return {
            "ok": True,
            "status_code": 200,
            "sandbox": True,
            "dados": {
                "id": 4321,
                "nome": "Nome Retornado",
                "ultima_alteracao": "2026-07-16 16:30:00",
            },
        }

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/produtos" if chave == "produtos" else f"/v1/{chave}",
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-alterar",
        data={
            "produto_id": "4321",
            "nome": "Produto Novo Nome",
            "codigo": "",
            "preco_tabela": "33.90",
            "saldo_estoque": "",
            "ativo": "true",
            "unidade": "",
        },
    )
    assert resp.status_code == 200
    # ID só na URL; campos vazios não vão no corpo
    assert capturado["path"] == "/v1/produtos/4321"
    assert "id" not in capturado["body"]
    assert capturado["body"]["nome"] == "Produto Novo Nome"
    assert capturado["body"]["preco_tabela"] == 33.9
    assert capturado["body"]["ativo"] is True
    assert "codigo" not in capturado["body"]
    assert "saldo_estoque" not in capturado["body"]
    assert "unidade" not in capturado["body"]
    html = resp.text
    assert "Produto alterado" in html
    assert "Status HTTP" in html
    assert "4321" in html
    assert "Nome Retornado" in html  # valor retornado pela Mercos prevalece
    assert "33.9" in html
    assert "Última alteração" in html
    assert "2026-07-16 16:30:00" in html
    assert "CompanyToken" not in html
    assert '"nome"' not in html  # sem JSON cru


def test_ui_produtos_alterar_valida_id_e_campos(client, monkeypatch):
    api = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.put_json", api)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    sem_id = client.post(
        "/mercos/homologacao-ui/acoes/produtos-alterar",
        data={"produto_id": "", "nome": "X"},
    )
    assert "Produto não informado" in sem_id.text
    sem_campos = client.post(
        "/mercos/homologacao-ui/acoes/produtos-alterar",
        data={"produto_id": "10", "nome": "", "ativo": ""},
    )
    assert "Nada para alterar" in sem_campos.text
    api.assert_not_called()


def test_ui_form_produto_excluir_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    assert 'id="input-produto-alt-excluido"' in html
    assert "Excluir logicamente" in html
    assert "Não alterar" in html


def test_ui_produtos_excluir_logicamente_envia_apenas_excluido(client, monkeypatch):
    """Botão Excluir logicamente: só excluido=true no corpo, ID só na URL."""
    capturado: dict = {}

    def fake_put(path, body):
        capturado["path"] = path
        capturado["body"] = dict(body)
        return {
            "ok": True,
            "status_code": 200,
            "sandbox": True,
            "dados": {
                "id": 20400678,
                "nome": "d9b02dfac23a4192",
                "preco_tabela": 6.13,
                "excluido": True,
                "ativo": True,
                "ultima_alteracao": "2026-07-16 17:00:00",
            },
        }

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put)
    monkeypatch.setattr(
        "services.mercos_homolog_service._path",
        lambda chave: "/v1/produtos" if chave == "produtos" else f"/v1/{chave}",
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-alterar",
        data={"produto_id": "20400678", "excluido": "true"},
    )
    assert resp.status_code == 200
    assert capturado["path"] == "/v1/produtos/20400678"
    assert capturado["body"] == {"excluido": True}  # nada além da exclusão lógica
    assert "id" not in capturado["body"]
    html = resp.text
    assert "Produto excluído logicamente" in html
    assert "Status HTTP" in html
    assert "20400678" in html
    assert "d9b02dfac23a4192" in html
    assert "6.13" in html
    assert "Excluído" in html and "Sim" in html
    assert "Última alteração" in html
    assert "2026-07-16 17:00:00" in html
    assert "CompanyToken" not in html
    assert '"excluido"' not in html  # sem JSON cru


def test_ui_produtos_alterar_excluido_nao_alterar_nao_envia(client, monkeypatch):
    """Excluído em 'Não alterar' (vazio) fica fora do corpo; demais vazios também."""
    capturado: dict = {}

    def fake_put(path, body):
        capturado["body"] = dict(body)
        return {"ok": True, "status_code": 200, "sandbox": True, "dados": {}}

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-alterar",
        data={
            "produto_id": "10",
            "nome": "Só Nome",
            "excluido": "",
            "ativo": "",
            "codigo": "",
        },
    )
    assert resp.status_code == 200
    assert capturado["body"] == {"nome": "Só Nome"}
    assert "excluido" not in capturado["body"]


def test_ui_produtos_alterar_erro_mercos(client, monkeypatch):
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError("Mercos HTTP 400: dados inválidos", status_code=400)

    monkeypatch.setattr("services.mercos_homolog_service.put_json", boom)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-alterar",
        data={"produto_id": "10", "nome": "X"},
    )
    assert resp.status_code == 200
    assert "dados inválidos" in resp.text
    assert "CompanyToken" not in resp.text


def _seed_produto_imagem(client, monkeypatch):
    """Sessão + produto 988c59d30ae54204 no catálogo local de produtos."""
    from services import mercos_produtos_catalogo as catp

    catp._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    sessao = client.cookies.get("mercos_produtos_sessao")
    catp.upsert_incremental(
        sessao,
        [
            {
                "id": 20400682,
                "nome": "988c59d30ae54204",
                "preco_tabela": 9.9,
                "ultima_alteracao": "2026-07-16 10:00:00",
                "ativo": True,
            }
        ],
    )
    return catp, sessao


def test_ui_form_produto_imagens_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    assert "Imagem do Produto — Buscar" in html
    assert 'id="input-produto-imagem-nome"' in html
    assert 'id="btn-produto-imagens"' in html
    assert "988c59d30ae54204" in html


def test_ui_produto_imagens_exige_token(client):
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagens", data={"nome": "x"}
    )
    assert resp.status_code == 403


def test_ui_produto_imagens_localiza_por_nome_e_usa_id(client, monkeypatch):
    catp, sessao = _seed_produto_imagem(client, monkeypatch)
    chamadas: list[dict] = []

    def fake_get(path, *, params=None, **_kw):
        chamadas.append({"path": path, "params": dict(params or {})})
        return [{"produto_id": 20400682, "imagens": ["7a90b5ebfbf044ab"]}]

    monkeypatch.setattr("services.mercos_homolog_service.get_json", fake_get)
    cursor_antes = client.cookies.get("mercos_produtos_cursor")
    etapa_antes = catp.obter_ciclo(sessao)["etapa_interna"]
    ciclo_ativo_antes = catp.obter_ciclo(sessao)["ativo"]

    resp = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagens",
        data={"nome": "988c59d30ae54204"},
    )
    assert resp.status_code == 200
    # Uma única chamada de imagens, com o ID resolvido pelo nome
    assert len(chamadas) == 1
    assert chamadas[0]["path"] == "/v1/imagens_produto"
    assert chamadas[0]["params"] == {"produto_id": "20400682"}
    html = resp.text
    assert "20400682" in html
    assert "988c59d30ae54204" in html
    assert "7a90b5ebfbf044ab" in html  # hash exatamente como retornado
    assert "Hash da imagem" in html
    assert "Status HTTP" in html
    assert "Mercos Sandbox" in html
    assert "destaque-homolog" in html  # produto da homologação destacado
    assert 'data-cursor-fixo="1"' in html
    assert "CompanyToken" not in html
    assert '"produto_id"' not in html  # sem JSON cru
    # Cursor e ciclo intactos
    assert resp.cookies.get("mercos_produtos_cursor") is None
    assert client.cookies.get("mercos_produtos_cursor") == cursor_antes
    assert catp.obter_ciclo(sessao)["etapa_interna"] == etapa_antes
    assert catp.obter_ciclo(sessao)["ativo"] == ciclo_ativo_antes


def test_ui_produto_imagens_multiplas(client, monkeypatch):
    _catp, _sessao = _seed_produto_imagem(client, monkeypatch)

    def fake_get(path, *, params=None, **_kw):
        return [
            {
                "produto_id": 20400682,
                "imagens": ["hash-aaa-111", "hash-bbb-222", "hash-ccc-333"],
            }
        ]

    monkeypatch.setattr("services.mercos_homolog_service.get_json", fake_get)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagens",
        data={"nome": "988c59d30ae54204"},
    )
    assert resp.status_code == 200
    html = resp.text
    assert "hash-aaa-111" in html
    assert "hash-bbb-222" in html
    assert "hash-ccc-333" in html
    assert "Total de imagens" in html


def test_ui_produto_imagens_sem_imagem(client, monkeypatch):
    _catp, _sessao = _seed_produto_imagem(client, monkeypatch)
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json",
        lambda path, *, params=None, **_kw: [
            {"produto_id": 20400682, "imagens": []}
        ],
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagens",
        data={"nome": "988c59d30ae54204"},
    )
    assert resp.status_code == 200
    assert "Produto sem imagem" in resp.text
    assert "não retornou imagens" in resp.text


def test_ui_produto_imagens_produto_nao_encontrado(client, monkeypatch):
    from services import mercos_produtos_catalogo as catp

    catp._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    chamadas: list[str] = []

    def fake_get(path, *, params=None, **_kw):
        chamadas.append(path)
        return []  # consulta controlada sem resultado

    monkeypatch.setattr("services.mercos_homolog_service.get_json", fake_get)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagens",
        data={"nome": "produto-inexistente"},
    )
    assert resp.status_code == 200
    assert "Produto não encontrado" in resp.text
    # Consulta controlada: uma única requisição de produtos, sem paginação
    assert chamadas == ["/v1/produtos"]


def test_ui_produto_imagens_consulta_controlada_pelo_nome(client, monkeypatch):
    """Produto fora do catálogo local: 1 GET de produtos + 1 GET de imagens."""
    from services import mercos_produtos_catalogo as catp

    catp._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    chamadas: list[dict] = []

    def fake_get(path, *, params=None, **_kw):
        chamadas.append({"path": path, "params": dict(params or {})})
        if path == "/v1/produtos":
            return [
                {"id": 1, "nome": "outro"},
                {"id": 20400682, "nome": "988c59d30ae54204"},
            ]
        return [{"produto_id": 20400682, "imagens": ["7a90b5ebfbf044ab"]}]

    monkeypatch.setattr("services.mercos_homolog_service.get_json", fake_get)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagens",
        data={"nome": "988c59d30ae54204"},
    )
    assert resp.status_code == 200
    assert [c["path"] for c in chamadas] == ["/v1/produtos", "/v1/imagens_produto"]
    assert chamadas[1]["params"] == {"produto_id": "20400682"}
    assert "7a90b5ebfbf044ab" in resp.text
    assert "Consulta controlada na Mercos" in resp.text
    # Não altera o catálogo acumulado nem cursor
    sessao = client.cookies.get("mercos_produtos_sessao")
    assert catp.total(sessao) == 0
    assert resp.cookies.get("mercos_produtos_cursor") is None


def test_ui_produto_imagens_erro_404_e_429(client, monkeypatch):
    from services.mercos_api_client import MercosApiError

    _catp, _sessao = _seed_produto_imagem(client, monkeypatch)

    def erro_404(path, *, params=None, **_kw):
        raise MercosApiError("Mercos HTTP 404: nao encontrado", status_code=404)

    monkeypatch.setattr("services.mercos_homolog_service.get_json", erro_404)
    r404 = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagens",
        data={"nome": "988c59d30ae54204"},
    )
    assert r404.status_code == 200
    assert "Imagens não encontradas" in r404.text
    assert "404" in r404.text

    def erro_429(path, *, params=None, **_kw):
        raise MercosApiError("429", status_code=429, retry_after=9.0)

    monkeypatch.setattr("services.mercos_homolog_service.get_json", erro_429)
    r429 = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagens",
        data={"nome": "988c59d30ae54204"},
    )
    assert "Aguardando limite da Mercos" in r429.text
    assert r429.headers.get("Retry-After") == "9"
    assert "CompanyToken" not in r429.text


_PNG_MINIMO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8ffff3f0300050001010502fea70000000049454e44ae426082"
)


def _post_imagem_add(client, monkeypatch, *, arquivo=None, data=None, post_ret=None, hashes=None):
    """Envia o form 'Imagem do Produto — Adicionar' com mocks de POST/GET Mercos."""
    import base64 as b64mod

    capturado: dict = {}

    def fake_post(path, body):
        capturado["path"] = path
        capturado["body"] = dict(body or {})
        if isinstance(post_ret, Exception):
            raise post_ret
        return post_ret or {
            "ok": True,
            "status_code": 201,
            "id": 777,
            "sandbox": True,
            "dados": {},
        }

    def fake_get(path, *, params=None, **_kw):
        capturado["get_path"] = path
        capturado["get_params"] = dict(params or {})
        return [{"produto_id": 20400705, "imagens": list(hashes or [])}]

    monkeypatch.setattr("services.mercos_homolog_service.post_json", fake_post)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", fake_get)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    form = {"produto_id": "20400705", "nome": "c4bfc00b3d2a4ab1"}
    form.update(data or {})
    files = {}
    if arquivo is not None:
        files["imagem"] = arquivo
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagem-adicionar",
        data=form,
        files=files or None,
    )
    capturado["b64_esperado"] = (
        b64mod.b64encode(arquivo[1]).decode("ascii") if arquivo else ""
    )
    return resp, capturado


def test_ui_form_produto_imagem_add_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    assert "Imagem do Produto — Adicionar" in html
    assert 'id="input-produto-img-id"' in html
    assert 'value="20400705"' in html
    assert 'value="c4bfc00b3d2a4ab1"' in html
    assert 'id="input-produto-img-arquivo"' in html
    assert 'accept=".png,.jpg,.jpeg' in html
    assert 'id="btn-produto-imagem-add"' in html


def test_ui_produto_imagem_add_exige_token(client):
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagem-adicionar",
        data={"produto_id": "20400705"},
    )
    assert resp.status_code == 403


def test_ui_produto_imagem_add_sucesso_com_arquivo(client, monkeypatch):
    from services import mercos_produtos_catalogo as catp

    catp._reset_todos_para_testes()
    cursor_antes = client.cookies.get("mercos_produtos_cursor")
    hash_mercos = "cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce"
    resp, cap = _post_imagem_add(
        client,
        monkeypatch,
        arquivo=("foto_homolog.png", _PNG_MINIMO, "image/png"),
        hashes=[hash_mercos],
    )
    assert resp.status_code == 200
    # Payload oficial: produto_id int + imagem_base64, sem URL junto
    assert cap["path"] == "/v1/imagens_produto"
    assert cap["body"]["produto_id"] == 20400705
    assert cap["body"]["imagem_base64"] == cap["b64_esperado"]
    assert "imagem_url" not in cap["body"]
    # Consulta de hash usa o mesmo produto
    assert cap["get_params"] == {"produto_id": "20400705"}
    html = resp.text
    assert "Imagem adicionada ao produto" in html
    assert "Status HTTP" in html and "201" in html
    assert "20400705" in html
    assert "c4bfc00b3d2a4ab1" in html
    assert hash_mercos in html  # hash exatamente como retornado
    assert "Quantidade de imagens" in html
    assert "foto_homolog.png" in html
    assert "Mercos Sandbox" in html
    assert 'data-cursor-fixo="1"' in html
    # Sem base64, JSON cru ou token na tela
    assert cap["b64_esperado"] not in html
    assert '"produto_id"' not in html
    assert "CompanyToken" not in html
    # Cursor do Produto GET intacto
    assert resp.cookies.get("mercos_produtos_cursor") is None
    assert client.cookies.get("mercos_produtos_cursor") == cursor_antes


def test_ui_produto_imagem_add_arquivo_invalido(client, monkeypatch):
    called = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", called)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagem-adicionar",
        data={"produto_id": "20400705", "nome": "c4bfc00b3d2a4ab1"},
        files={"imagem": ("animacao.gif", b"GIF89a...", "image/gif")},
    )
    assert resp.status_code == 200
    assert "Arquivo inválido" in resp.text
    assert "PNG ou JPG" in resp.text
    called.assert_not_called()


def test_ui_produto_imagem_add_muito_grande(client, monkeypatch):
    called = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", called)
    monkeypatch.setattr(
        "services.mercos_homolog_service.IMAGEM_PRODUTO_MAX_BYTES", 10
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagem-adicionar",
        data={"produto_id": "20400705", "nome": "c4bfc00b3d2a4ab1"},
        files={"imagem": ("grande.png", b"x" * 100, "image/png")},
    )
    assert resp.status_code == 200
    assert "Imagem muito grande" in resp.text
    called.assert_not_called()


def test_ui_produto_imagem_add_sem_arquivo_nem_url(client, monkeypatch):
    called = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", called)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produto-imagem-adicionar",
        data={"produto_id": "20400705", "nome": "c4bfc00b3d2a4ab1"},
    )
    assert resp.status_code == 200
    assert "Selecione um arquivo PNG/JPG ou informe a URL" in resp.text
    called.assert_not_called()


def test_ui_produto_imagem_add_erros_mercos(client, monkeypatch):
    from services.mercos_api_client import MercosApiError

    # 404 — produto não encontrado
    r404, _ = _post_imagem_add(
        client,
        monkeypatch,
        arquivo=("foto.png", _PNG_MINIMO, "image/png"),
        post_ret=MercosApiError("nao encontrado", status_code=404),
    )
    assert "Produto não encontrado" in r404.text

    # 412 — dados recusados
    r412, _ = _post_imagem_add(
        client,
        monkeypatch,
        arquivo=("foto.png", _PNG_MINIMO, "image/png"),
        post_ret=MercosApiError("Dados inválidos", status_code=412),
    )
    assert "Dados recusados pela Mercos" in r412.text
    assert "412" in r412.text

    # 429 — Retry-After
    r429, _ = _post_imagem_add(
        client,
        monkeypatch,
        arquivo=("foto.png", _PNG_MINIMO, "image/png"),
        post_ret=MercosApiError("429", status_code=429, retry_after=7.0),
    )
    assert "Aguardando limite da Mercos" in r429.text
    assert r429.headers.get("Retry-After") == "7"


def test_ui_produto_imagem_add_resposta_sem_hash(client, monkeypatch):
    resp, _cap = _post_imagem_add(
        client,
        monkeypatch,
        arquivo=("foto.png", _PNG_MINIMO, "image/png"),
        hashes=[],
    )
    assert resp.status_code == 200
    html = resp.text
    assert "Imagem adicionada ao produto" in html
    assert "ainda não retornou o hash" in html


def test_ui_produto_imagem_add_nao_altera_ciclo(client, monkeypatch):
    from services import mercos_produtos_catalogo as catp

    catp._reset_todos_para_testes()
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    sessao = client.cookies.get("mercos_produtos_sessao")
    etapa_antes = catp.obter_ciclo(sessao)["etapa_interna"]
    ativo_antes = catp.obter_ciclo(sessao)["ativo"]
    resp, _cap = _post_imagem_add(
        client,
        monkeypatch,
        arquivo=("foto.png", _PNG_MINIMO, "image/png"),
        hashes=["abc123"],
    )
    assert resp.status_code == 200
    assert catp.obter_ciclo(sessao)["etapa_interna"] == etapa_antes
    assert catp.obter_ciclo(sessao)["ativo"] == ativo_antes


def test_ui_form_cliente_alterar_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    assert "Cliente — Alterar" in html
    assert 'id="input-cliente-id"' in html
    assert 'id="input-cliente-alt-tipo"' in html
    assert 'id="input-cliente-alt-razao-social"' in html
    assert 'id="input-cliente-alt-fantasia"' in html
    assert 'id="input-cliente-alt-cnpj"' in html
    assert 'id="input-cliente-alt-email"' in html
    assert 'id="input-cliente-alt-ativo"' in html
    # Ativo com opção "Não alterar"
    secao = html.split("sec-clientes-alterar")[1].split("</section>")[0]
    assert "Não alterar" in secao


def test_ui_clientes_alterar_envia_valores_da_homologacao(client, monkeypatch):
    """Etapa Cliente PUT 2/3: ID 9290554 com os valores exatos exigidos."""
    capturado: dict = {}

    def fake_put(path, body):
        capturado["path"] = path
        capturado["body"] = dict(body or {})
        return {
            "ok": True,
            "status_code": 200,
            "sandbox": True,
            "dados": {
                "tipo": "J",
                "razao_social": "6a86449570ab4e4c",
                "nome_fantasia": "606c84cb8015470d",
                "cnpj": "91645924000109",
                "ultima_alteracao": "2026-07-17 09:00:00",
            },
        }

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-alterar",
        data={
            "cliente_id": "9290554",
            "tipo": "J",
            "razao_social": "6a86449570ab4e4c",
            "nome_fantasia": "606c84cb8015470d",
            "cnpj": "91645924000109",
            "email": "",
            "ativo": "",
        },
    )
    assert resp.status_code == 200
    # ID só na URL, nunca no corpo
    assert capturado["path"] == "/v1/clientes/9290554"
    assert "id" not in capturado["body"]
    # Corpo exatamente com os valores preenchidos, sem geração automática
    assert capturado["body"] == {
        "tipo": "J",
        "razao_social": "6a86449570ab4e4c",
        "nome_fantasia": "606c84cb8015470d",
        "cnpj": "91645924000109",
    }
    html = resp.text
    assert "Cliente alterado" in html
    assert "Status HTTP" in html and "200" in html
    assert "9290554" in html
    assert "6a86449570ab4e4c" in html
    assert "606c84cb8015470d" in html
    assert "91645924000109" in html
    assert "Última alteração" in html
    assert "2026-07-17 09:00:00" in html
    assert "Homolog Alterado" not in html  # nada gerado automaticamente
    assert "CompanyToken" not in html
    assert '"razao_social"' not in html  # sem JSON cru


def test_ui_clientes_alterar_campos_vazios_nao_enviados(client, monkeypatch):
    capturado: dict = {}

    def fake_put(path, body):
        capturado["body"] = dict(body or {})
        return {"ok": True, "status_code": 200, "sandbox": True, "dados": {}}

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-alterar",
        data={
            "cliente_id": "9290554",
            "tipo": "",
            "razao_social": "",
            "nome_fantasia": "Novo Nome",
            "cnpj": "",
            "email": "",
            "ativo": "true",
        },
    )
    assert resp.status_code == 200
    assert capturado["body"] == {"nome_fantasia": "Novo Nome", "ativo": True}


def test_ui_clientes_alterar_validacoes(client, monkeypatch):
    called = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.put_json", called)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    # Sem ID
    r1 = client.post(
        "/mercos/homologacao-ui/acoes/clientes-alterar",
        data={"razao_social": "X"},
    )
    assert "Cliente não informado" in r1.text
    # Com ID mas sem nenhum campo
    r2 = client.post(
        "/mercos/homologacao-ui/acoes/clientes-alterar",
        data={"cliente_id": "9290554"},
    )
    assert "Nenhum campo para alterar" in r2.text
    called.assert_not_called()


def test_ui_form_cliente_excluir_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    secao = html.split("sec-clientes-alterar")[1].split("</section>")[0]
    assert 'id="input-cliente-alt-excluido"' in secao
    assert "Excluir logicamente" in secao
    # Botão dedicado envia os campos obrigatórios exigidos pela Mercos
    assert 'id="input-cliente-excluir-flag"' in secao
    assert 'value="6a86449570ab4e4c"' in secao
    assert 'value="606c84cb8015470d"' in secao
    assert 'value="91645924000109"' in secao


def test_ui_clientes_excluir_logicamente_payload_completo(client, monkeypatch):
    """Etapa Cliente PUT 3/3: excluido=true com os obrigatórios, id só na URL."""
    capturado: dict = {}

    def fake_put(path, body):
        capturado["path"] = path
        capturado["body"] = dict(body or {})
        return {
            "ok": True,
            "status_code": 200,
            "sandbox": True,
            "dados": {"excluido": True, "ultima_alteracao": "2026-07-17 09:45:00"},
        }

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-alterar",
        data={
            "cliente_id": "9290554",
            "tipo": "J",
            "razao_social": "6a86449570ab4e4c",
            "nome_fantasia": "606c84cb8015470d",
            "cnpj": "91645924000109",
            "excluido": "true",
        },
    )
    assert resp.status_code == 200
    assert capturado["path"] == "/v1/clientes/9290554"
    assert "id" not in capturado["body"]
    assert capturado["body"] == {
        "tipo": "J",
        "razao_social": "6a86449570ab4e4c",
        "nome_fantasia": "606c84cb8015470d",
        "cnpj": "91645924000109",
        "excluido": True,
    }
    html = resp.text
    assert "Cliente excluído logicamente" in html
    assert "Status HTTP" in html and "200" in html
    assert "9290554" in html
    assert "6a86449570ab4e4c" in html
    assert "606c84cb8015470d" in html
    assert "91645924000109" in html
    assert "<span>Excluído</span><strong>Sim</strong>" in html
    assert "2026-07-17 09:45:00" in html
    assert "CompanyToken" not in html
    assert '"excluido"' not in html  # sem JSON cru


def test_ui_clientes_alterar_excluido_nao_alterar_nao_envia(client, monkeypatch):
    capturado: dict = {}

    def fake_put(path, body):
        capturado["body"] = dict(body or {})
        return {"ok": True, "status_code": 200, "sandbox": True, "dados": {}}

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-alterar",
        data={
            "cliente_id": "9290554",
            "nome_fantasia": "Novo Nome",
            "excluido": "",
        },
    )
    assert resp.status_code == 200
    assert capturado["body"] == {"nome_fantasia": "Novo Nome"}
    assert "Cliente alterado" in resp.text
    assert "Cliente excluído logicamente" not in resp.text


def test_ui_clientes_alterar_erro_mercos(client, monkeypatch):
    from services.mercos_api_client import MercosApiError

    def fake_put(path, body):
        raise MercosApiError("Dados inválidos", status_code=412)

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-alterar",
        data={"cliente_id": "9290554", "razao_social": "6a86449570ab4e4c"},
    )
    assert resp.status_code == 200
    assert "Falha na operação" in resp.text
    assert "412" in resp.text


def test_ui_form_cliente_incluir_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    assert 'id="input-cliente-tipo"' in html
    assert 'id="input-cliente-razao-social"' in html
    assert 'id="input-cliente-fantasia"' in html
    assert 'id="input-cliente-cnpj"' in html
    assert 'id="input-cliente-email"' in html
    assert 'id="input-cliente-ativo"' in html
    assert 'value="J"' in html
    assert 'value="F"' in html


def test_clientes_criar_envia_campos_do_formulario(client, monkeypatch):
    """Os 4 campos obrigatórios da homologação vão exatamente como digitados."""
    capturado: dict = {}

    def fake_criar(body):
        capturado.update(body)
        return {"ok": True, "status_code": 201, "id": 555, "dados": {"id": 555}}

    monkeypatch.setattr("routes.mercos_homolog_ui.homolog.criar_cliente", fake_criar)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-criar",
        data={
            "tipo": "J",
            "razao_social": "682f3a75494c433c",
            "nome_fantasia": "ef8b4befd76f481f",
            "cnpj": "73032604000193",
            "email": "",
            "ativo": "true",
        },
    )
    assert resp.status_code == 200
    assert capturado["tipo"] == "J"
    assert capturado["razao_social"] == "682f3a75494c433c"
    assert capturado["nome_fantasia"] == "ef8b4befd76f481f"
    assert capturado["cnpj"] == "73032604000193"  # sem formatação
    assert capturado["ativo"] is True
    assert "email" not in capturado  # opcional vazio não é enviado
    # Nada gerado automaticamente
    assert "Homolog Xnamai" not in str(capturado)
    html = resp.text
    assert "Status HTTP" in html
    assert "ID criado" in html
    assert "682f3a75494c433c" in html
    assert "ef8b4befd76f481f" in html
    assert "73032604000193" in html
    assert "Última alteração" in html
    assert "CompanyToken" not in html
    assert '"razao_social"' not in html  # sem JSON cru no cartão


def test_clientes_criar_cartao_usa_retorno_com_fallback(client, monkeypatch):
    """Campos retornados pela Mercos prevalecem; ausentes caem no valor enviado."""

    def fake_criar(body):
        return {
            "ok": True,
            "status_code": 201,
            "id": 777,
            "dados": {
                "id": 777,
                "razao_social": "682F3A75494C433C LTDA",
                "ultima_alteracao": "2026-07-16 15:00:00",
            },
        }

    monkeypatch.setattr("routes.mercos_homolog_ui.homolog.criar_cliente", fake_criar)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-criar",
        data={
            "tipo": "J",
            "razao_social": "682f3a75494c433c",
            "nome_fantasia": "ef8b4befd76f481f",
            "cnpj": "73032604000193",
            "email": "contato@homolog.test",
            "ativo": "true",
        },
    )
    assert resp.status_code == 200
    html = resp.text
    assert "777" in html
    # Retornado pela Mercos prevalece
    assert "682F3A75494C433C LTDA" in html
    assert "2026-07-16 15:00:00" in html
    # Não retornados: preserva o que foi enviado
    assert "ef8b4befd76f481f" in html
    assert "73032604000193" in html
    assert "contato@homolog.test" in html


def test_clientes_criar_valida_obrigatorios(client, monkeypatch):
    api = MagicMock()
    monkeypatch.setattr("routes.mercos_homolog_ui.homolog.criar_cliente", api)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-criar",
        data={"tipo": "J", "razao_social": "", "nome_fantasia": "X", "cnpj": ""},
    )
    assert resp.status_code == 200
    assert "Campos obrigatórios ausentes" in resp.text
    assert "Razão social" in resp.text
    assert "CNPJ/CPF" in resp.text
    api.assert_not_called()


# ---------------------------------------------------------------------------
# Tipo de Pedido GET — ciclo de homologação em 3 etapas
# ---------------------------------------------------------------------------


def _prep_tipos(client, monkeypatch):
    from services import mercos_tipos_pedido_catalogo as catt
    from services.mercos_homolog_service import _reset_resume_clientes_para_testes

    catt._reset_todos_para_testes()
    _reset_resume_clientes_para_testes()
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    return catt


def test_ui_secao_tipos_pedido_ciclo_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    secao = html.split('id="sec-tipos"')[1].split("</section>")[0]
    assert 'id="btn-tipos-reiniciar"' in secao
    assert 'id="btn-tipos-sincronizar"' in secao
    assert 'id="input-tipos-nome"' in secao
    assert 'id="btn-tipos-localizar"' in secao
    assert "Reiniciar ciclo de sincronização" in secao
    assert "Localizar tipo de pedido" in secao
    # Botões manuais antigos marcados para bloqueio durante o ciclo
    assert secao.count("tipos-busca-manual") >= 5


def test_tipos_pedido_reiniciar_nao_chama_mercos(client, monkeypatch):
    catt = _prep_tipos(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    resp = client.post("/mercos/homologacao-ui/acoes/tipos-pedido-reiniciar")
    assert resp.status_code == 200
    assert "Ciclo de sincronização reiniciado" in resp.text
    assert "0/3" in resp.text
    assert 'data-ciclo-ativo="1"' in resp.text
    called.assert_not_called()
    sessao = client.cookies.get("mercos_tipos_pedido_sessao")
    assert catt.total(sessao) == 0
    assert catt.obter_ciclo(sessao)["etapa_interna"] == 0


def _fake_tipos_sandbox(cursores_vistos):
    """Contrato real do diagnóstico 2026-07-17: lote de 2, keyset alterado_apos,
    MEUSPEDIDOS_REQUISICOES_EXTRAS informa os lotes restantes da completa."""

    lotes_completa = {
        None: (
            [
                {"id": 47660, "nome": "8cd2e36c38094a83", "excluido": False, "ultima_alteracao": "2026-07-14 14:37:38"},
                {"id": 47659, "nome": "198314a3385b4af2", "excluido": False, "ultima_alteracao": "2026-07-15 14:37:33"},
            ],
            "2",
        ),
        "2026-07-15 14:37:33": (
            [
                {"id": 47661, "nome": "03823f68dbe34e7c", "excluido": False, "ultima_alteracao": "2026-07-15 15:17:48"},
                {"id": 47666, "nome": "ad960ab474d24108", "excluido": False, "ultima_alteracao": "2026-07-15 16:22:51"},
            ],
            "2",
        ),
        "2026-07-15 16:22:51": (
            [
                {"id": 47670, "nome": "0956e338c1d94b28", "excluido": False, "ultima_alteracao": "2026-07-16 10:00:00"},
                {"id": 47671, "nome": "5f00aaaa11112222", "excluido": True, "ultima_alteracao": "2026-07-16 11:00:00"},
            ],
            "2",
        ),
        "2026-07-16 11:00:00": (
            [
                {"id": 47672, "nome": "novotipo9999", "excluido": False, "ultima_alteracao": "2026-07-17 08:00:00"},
            ],
            "0",
        ),
        "2026-07-17 08:00:00": ([], "0"),
    }

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/pedidos/tipo"
        params = params or {}
        assert "pagina" not in params
        cursor = params.get("alterado_apos")
        cursores_vistos.append(cursor)
        itens, extras = lotes_completa[cursor]
        headers = {
            "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
            "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "6",
            "MEUSPEDIDOS_REQUISICOES_EXTRAS": extras,
        }
        return (itens, headers)

    return fake_get


def test_tipos_pedido_ciclo_3_etapas_completa_todos_lotes(client, monkeypatch):
    """Etapa 1 percorre TODOS os lotes (1 + extras) e o registro 0956e338…
    aparece na busca completa; etapas 2 e 3 incrementais com cursor exato."""
    catt = _prep_tipos(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_tipos_sandbox(cursores),
    )
    client.post("/mercos/homologacao-ui/acoes/tipos-pedido-reiniciar")
    sessao = client.cookies.get("mercos_tipos_pedido_sessao")

    # Etapa 1 — busca completa: extras=2 → exatamente 3 chamadas, todos os lotes
    r1 = client.post("/mercos/homologacao-ui/acoes/tipos-pedido-sincronizar")
    assert r1.status_code == 200
    assert cursores == [None, "2026-07-15 14:37:33", "2026-07-15 16:22:51"]
    assert "1/3" in r1.text
    assert 'data-tipo-busca="completa"' in r1.text
    # O registro solicitado pela Mercos veio na completa
    assert "0956e338c1d94b28" in r1.text
    # Registro excluído tratado (mantido no catálogo com a flag)
    assert catt.total(sessao) == 6
    estado = catt.obter(sessao)
    assert "47670" in estado["tipos"]
    assert estado["tipos"]["47671"]["excluido"] is True
    assert catt.obter_ciclo(sessao)["chamadas_completas"] == 1
    assert 'data-requisicoes-executadas="3"' in r1.text

    # Etapa 2 — incremental com alterado_apos = cursor EXATO da etapa 1
    r2 = client.post("/mercos/homologacao-ui/acoes/tipos-pedido-sincronizar")
    assert r2.status_code == 200
    assert cursores[3] == "2026-07-16 11:00:00"
    assert "2/3" in r2.text
    assert 'data-tipo-busca="incremental"' in r2.text
    assert 'data-cursor-base="2026-07-16 11:00:00"' in r2.text
    assert 'data-alterado-apos-enviado="2026-07-16 11:00:00"' in r2.text
    # Sem overlap de 1s (contrato de tipos de pedido é cursor exato)
    assert "2026-07-16 10:59:59" not in r2.text
    # Catálogo acumulado: mantém anteriores e adiciona o novo
    assert catt.total(sessao) == 7
    estado = catt.obter(sessao)
    assert "47660" in estado["tipos"]
    assert "47672" in estado["tipos"]

    # Etapa 3 — incremental com o cursor EXATO produzido pela etapa 2
    r3 = client.post("/mercos/homologacao-ui/acoes/tipos-pedido-sincronizar")
    assert r3.status_code == 200
    assert cursores[4] == "2026-07-17 08:00:00"
    assert 'data-cursor-base="2026-07-17 08:00:00"' in r3.text
    assert 'data-alterado-apos-enviado="2026-07-17 08:00:00"' in r3.text
    assert "3/3" in r3.text
    ciclo = catt.obter_ciclo(sessao)
    assert ciclo["chamadas_completas"] == 1
    assert ciclo["chamadas_incrementais"] == 2
    assert ciclo["etapa_interna"] == 3
    assert catt.total(sessao) == 7
    # Cartão operacional sem JSON cru nem token
    assert "Requisições previstas" in r3.text
    assert "Requisições executadas" in r3.text
    assert "CompanyToken" not in r3.text


def test_tipos_pedido_extras_headers_limita_chamadas(monkeypatch):
    """extras=2 → exatamente 3 chamadas; sem 4ª esperando lote vazio."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_EXTRAS,
        listar_tipos_pedido_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    chamadas: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/pedidos/tipo"
        chamadas.append((params or {}).get("alterado_apos"))
        assert len(chamadas) <= 3, "não pode existir 4ª chamada"
        if len(chamadas) == 1:
            return (
                [
                    {"id": 1, "nome": "T1", "ultima_alteracao": "2026-07-14 14:37:38"},
                    {"id": 2, "nome": "T2", "ultima_alteracao": "2026-07-15 14:37:33"},
                ],
                {
                    "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                    "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "6",
                    "MEUSPEDIDOS_REQUISICOES_EXTRAS": "2",
                },
            )
        if len(chamadas) == 2:
            return (
                [
                    {"id": 3, "nome": "T3", "ultima_alteracao": "2026-07-15 15:17:48"},
                    {"id": 4, "nome": "T4", "ultima_alteracao": "2026-07-15 16:22:51"},
                ],
                {},
            )
        return (
            [
                {"id": 5, "nome": "0956e338c1d94b28", "ultima_alteracao": "2026-07-16 10:00:00"},
                {"id": 6, "nome": "T6", "ultima_alteracao": "2026-07-16 11:00:00"},
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_tipos_pedido_paginado_seguro(max_paginas=20, timeout_total=60)
    assert len(chamadas) == 3
    assert chamadas[0] is None
    assert chamadas[1] == "2026-07-15 14:37:33"
    assert chamadas[2] == "2026-07-15 16:22:51"
    assert out["total"] == 6
    assert out["requisicoes_extras"] == 2
    assert out["requisicoes_previstas"] == 3
    assert out["requisicoes_executadas"] == 3
    assert out["motivo_parada"] == MOTIVO_PARADA_EXTRAS
    nomes = [i.get("nome") for i in out["itens"]]
    assert "0956e338c1d94b28" in nomes


def test_tipos_pedido_localizar_nao_faz_requisicao_http(client, monkeypatch):
    """Localizar usa só o catálogo local (nome completo ou prefixo); cursor intacto."""
    catt = _prep_tipos(client, monkeypatch)

    def explode(*_a, **_k):
        raise AssertionError("Localizar tipo de pedido não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", explode)
    monkeypatch.setattr("services.mercos_api_client.request_mercos", explode)

    client.post("/mercos/homologacao-ui/acoes/tipos-pedido-reiniciar")
    sessao = client.cookies.get("mercos_tipos_pedido_sessao")
    catt.upsert_incremental(
        sessao,
        [
            {
                "id": 47670,
                "nome": "0956e338c1d94b28",
                "excluido": False,
                "ultima_alteracao": "2026-07-16 10:00:00",
            }
        ],
    )
    etapa_antes = catt.obter_ciclo(sessao)["etapa_interna"]

    # Por prefixo (como a Mercos pede: nome começa com 0956e338)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/tipos-pedido-localizar",
        data={"nome": "0956e338"},
    )
    assert resp.status_code == 200
    assert "Tipo de pedido localizado" in resp.text
    assert "0956e338c1d94b28" in resp.text
    assert "Excluído" in resp.text
    # Não altera cursor nem etapa
    assert resp.cookies.get("mercos_tipos_pedido_cursor") is None
    assert 'data-cursor-fixo="1"' in resp.text
    assert catt.obter_ciclo(sessao)["etapa_interna"] == etapa_antes

    # Por nome completo
    resp2 = client.post(
        "/mercos/homologacao-ui/acoes/tipos-pedido-localizar",
        data={"nome": "0956e338c1d94b28"},
    )
    assert "Tipo de pedido localizado" in resp2.text


def test_tipos_pedido_buscas_manuais_bloqueadas_durante_ciclo(client, monkeypatch):
    _prep_tipos(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    monkeypatch.setattr("services.mercos_homolog_service.get_json", called)
    client.post("/mercos/homologacao-ui/acoes/tipos-pedido-reiniciar")

    resp = client.post(
        "/mercos/homologacao-ui/acoes/tipos-pedido",
        data={"alterado_apos": "2026-07-15 00:00:00"},
    )
    assert resp.status_code == 200
    assert "Busca manual bloqueada durante a homologação" in resp.text

    resp2 = client.post("/mercos/homologacao-ui/acoes/tipos-pedido-combinacoes")
    assert resp2.status_code == 200
    assert "Busca manual bloqueada durante a homologação" in resp2.text
    called.assert_not_called()


def test_tipos_pedido_429_retorna_retry_after_e_libera_lock(client, monkeypatch):
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import _SYNC_TIPOS_PEDIDO_LOCK

    _prep_tipos(client, monkeypatch)

    def sempre_429(path, *, params=None, **_kw):
        raise MercosApiError("429", status_code=429, retry_after=12.0)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", sempre_429
    )
    client.post("/mercos/homologacao-ui/acoes/tipos-pedido-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/tipos-pedido-sincronizar")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "12"
    assert "Aguardando limite da Mercos" in resp.text
    # Lock liberado no finally: nova aquisição funciona
    assert _SYNC_TIPOS_PEDIDO_LOCK.acquire(blocking=False) is True
    _SYNC_TIPOS_PEDIDO_LOCK.release()


def test_tipos_pedido_incremental_envia_cursor_exato(monkeypatch):
    """alterado_apos = cursor base byte a byte, sem overlap de 1s."""
    from services.mercos_homolog_service import sincronizar_tipos_pedido

    capt: dict = {}

    def fake_listar(alterado_apos=None, **_kw):
        capt["alterado_apos"] = alterado_apos
        return {"itens": [], "paginas_lidas": 1}

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_tipos_pedido_paginado_seguro",
        fake_listar,
    )
    out = sincronizar_tipos_pedido("2026-07-16 11:00:00")
    assert capt["alterado_apos"] == "2026-07-16 11:00:00"
    assert out["cursor_base"] == "2026-07-16 11:00:00"
    assert out["alterado_apos_enviado"] == "2026-07-16 11:00:00"
    assert out["tipo"] == "incremental"


def test_tipos_pedido_sincronizar_bloqueia_concorrencia(client, monkeypatch):
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import _SYNC_TIPOS_PEDIDO_LOCK

    _prep_tipos(client, monkeypatch)
    assert _SYNC_TIPOS_PEDIDO_LOCK.acquire(blocking=False) is True
    try:
        client.post("/mercos/homologacao-ui/acoes/tipos-pedido-reiniciar")
        resp = client.post("/mercos/homologacao-ui/acoes/tipos-pedido-sincronizar")
        assert resp.status_code == 409
        assert "já em andamento" in resp.text
    finally:
        _SYNC_TIPOS_PEDIDO_LOCK.release()


def test_demais_homologacoes_intactas_apos_tipos_pedido(client, monkeypatch):
    """Ciclos de produtos, clientes, usuários e pedidos continuam registrados."""
    _prep_tipos(client, monkeypatch)
    client.post("/mercos/homologacao-ui/acoes/tipos-pedido-reiniciar")
    for rota in (
        "/mercos/homologacao-ui/acoes/produtos-reiniciar",
        "/mercos/homologacao-ui/acoes/clientes-reiniciar",
        "/mercos/homologacao-ui/acoes/usuarios-reiniciar",
        "/mercos/homologacao-ui/acoes/pedidos-reiniciar",
    ):
        resp = client.post(rota)
        assert resp.status_code == 200, rota
        assert "Ciclo de sincronização reiniciado" in resp.text


# ---------------------------------------------------------------------------
# Pagamento GET — ciclo de homologação em 2 etapas (Mercos Pay)
# ---------------------------------------------------------------------------


def _prep_pagamentos(client, monkeypatch):
    from services import mercos_pagamentos_catalogo as catg
    from services.mercos_homolog_service import _reset_resume_clientes_para_testes

    catg._reset_todos_para_testes()
    _reset_resume_clientes_para_testes()
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    return catg


def test_ui_secao_pagamentos_buscar_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    secao = html.split('id="sec-pagamentos-buscar"')[1].split("</section>")[0]
    assert 'id="btn-pagamentos-reiniciar"' in secao
    assert 'id="btn-pagamentos-sincronizar"' in secao
    assert 'id="input-pagamentos-id"' in secao
    assert 'id="btn-pagamentos-localizar"' in secao
    assert 'id="input-pagamentos-vencimento"' in secao
    assert 'id="btn-pagamentos-localizar-vencimento"' in secao
    assert "Reiniciar ciclo de sincronização" in secao
    assert "Localizar pagamento pelo ID" in secao
    assert "Localizar transação pela data de vencimento" in secao
    assert "Pagamentos — Buscar" in secao
    # Demais seções intactas
    assert 'id="sec-condicoes"' in html
    assert 'id="sec-formas-pagamento-criar"' in html
    assert 'id="sec-titulos-criar"' in html or "Título" in html


def test_pagamentos_reiniciar_nao_chama_mercos(client, monkeypatch):
    catg = _prep_pagamentos(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    resp = client.post("/mercos/homologacao-ui/acoes/pagamentos-reiniciar")
    assert resp.status_code == 200
    assert "Ciclo de sincronização reiniciado" in resp.text
    assert "0/2" in resp.text
    assert 'data-ciclo-ativo="1"' in resp.text
    called.assert_not_called()
    sessao = client.cookies.get("mercos_pagamentos_sessao")
    assert catg.total(sessao) == 0
    assert catg.obter_ciclo(sessao)["etapa_interna"] == 0


def _fake_pagamentos_sandbox(cursores_vistos):
    """Contrato real: completa sem alterado_apos; incremental com cursor exato."""

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/pagamentos"
        params = params or {}
        assert "pagina" not in params
        cursor = params.get("alterado_apos")
        cursores_vistos.append(cursor)
        headers = {
            "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
            "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "2",
            "MEUSPEDIDOS_REQUISICOES_EXTRAS": "0",
        }
        if cursor is None:
            return (
                [
                    {
                        "id": 7716,
                        "valor": 156.0,
                        "pedido_id": 2150165,
                        "cliente_id": 9290646,
                        "data_criacao": "2026-07-18 16:10:50",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-18 16:10:50",
                        "token": "segredo-nao-deve-aparecer",
                    },
                    {
                        "id": 7700,
                        "valor": 10.5,
                        "pedido_id": 2150001,
                        "cliente_id": 9290001,
                        "data_criacao": "2026-07-17 10:00:00",
                        "excluido": True,
                        "ultima_alteracao": "2026-07-17 11:00:00",
                    },
                ],
                headers,
            )
        if cursor == "2026-07-18 16:10:50":
            return (
                [
                    {
                        "id": 7800,
                        "valor": 99.9,
                        "pedido_id": 2150999,
                        "cliente_id": 9290999,
                        "data_criacao": "2026-07-19 09:00:00",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-19 09:00:00",
                    }
                ],
                headers,
            )
        return ([], headers)

    return fake_get


def test_pagamentos_ciclo_2_etapas_completa_e_incremental(client, monkeypatch):
    """Etapa 1 completa traz o ID 7716; etapa 2 incremental com cursor exato."""
    catg = _prep_pagamentos(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_pagamentos_sandbox(cursores),
    )
    client.post("/mercos/homologacao-ui/acoes/pagamentos-reiniciar")
    sessao = client.cookies.get("mercos_pagamentos_sessao")

    r1 = client.post("/mercos/homologacao-ui/acoes/pagamentos-sincronizar")
    assert r1.status_code == 200
    assert cursores == [None]
    assert "1/2" in r1.text
    assert 'data-tipo-busca="completa"' in r1.text
    assert "7716" in r1.text
    assert "156.00" in r1.text or "156" in r1.text
    assert catg.total(sessao) == 2
    assert catg.obter(sessao)["pagamentos"]["7700"]["excluido"] is True
    assert catg.obter_ciclo(sessao)["chamadas_completas"] == 1
    # Token de link de pagamento nunca aparece na UI
    assert "segredo-nao-deve-aparecer" not in r1.text
    assert "CompanyToken" not in r1.text

    r2 = client.post("/mercos/homologacao-ui/acoes/pagamentos-sincronizar")
    assert r2.status_code == 200
    assert cursores[1] == "2026-07-18 16:10:50"
    assert "2/2" in r2.text
    assert 'data-tipo-busca="incremental"' in r2.text
    assert 'data-cursor-base="2026-07-18 16:10:50"' in r2.text
    assert 'data-alterado-apos-enviado="2026-07-18 16:10:50"' in r2.text
    assert "2026-07-18 16:10:49" not in r2.text
    assert catg.total(sessao) == 3
    estado = catg.obter(sessao)
    assert "7716" in estado["pagamentos"]
    assert "7800" in estado["pagamentos"]
    ciclo = catg.obter_ciclo(sessao)
    assert ciclo["chamadas_completas"] == 1
    assert ciclo["chamadas_incrementais"] == 1
    assert ciclo["etapa_interna"] == 2
    assert "Requisições previstas" in r2.text
    assert "Requisições executadas" in r2.text


def test_pagamentos_extras_headers_limita_chamadas(monkeypatch):
    """extras=1 → exatamente 2 chamadas; sem 3ª esperando lote vazio."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_EXTRAS,
        listar_pagamentos_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    chamadas: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/pagamentos"
        chamadas.append((params or {}).get("alterado_apos"))
        assert len(chamadas) <= 2, "não pode existir 3ª chamada"
        if len(chamadas) == 1:
            return (
                [
                    {
                        "id": 7716,
                        "valor": 156.0,
                        "ultima_alteracao": "2026-07-18 16:10:50",
                    },
                    {
                        "id": 7700,
                        "valor": 10.5,
                        "ultima_alteracao": "2026-07-17 11:00:00",
                    },
                ],
                {
                    "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                    "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "3",
                    "MEUSPEDIDOS_REQUISICOES_EXTRAS": "1",
                },
            )
        return (
            [
                {
                    "id": 7800,
                    "valor": 99.9,
                    "ultima_alteracao": "2026-07-19 09:00:00",
                }
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_pagamentos_paginado_seguro(max_paginas=20, timeout_total=60)
    assert len(chamadas) == 2
    assert chamadas[0] is None
    assert chamadas[1] == "2026-07-18 16:10:50"
    assert out["total"] == 3
    assert out["requisicoes_extras"] == 1
    assert out["requisicoes_previstas"] == 2
    assert out["requisicoes_executadas"] == 2
    assert out["motivo_parada"] == MOTIVO_PARADA_EXTRAS
    ids = [i.get("id") for i in out["itens"]]
    assert 7716 in ids


def test_pagamentos_localizar_id_7716_sem_http(client, monkeypatch):
    """Localiza o ID 7716 só no catálogo local; não chama Mercos nem altera cursor."""
    catg = _prep_pagamentos(client, monkeypatch)

    def explode(*_a, **_k):
        raise AssertionError("Localizar pagamento não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", explode)
    monkeypatch.setattr("services.mercos_api_client.request_mercos", explode)

    client.post("/mercos/homologacao-ui/acoes/pagamentos-reiniciar")
    sessao = client.cookies.get("mercos_pagamentos_sessao")
    catg.upsert_incremental(
        sessao,
        [
            {
                "id": 7716,
                "valor": 156.0,
                "pedido_id": 2150165,
                "cliente_id": 9290646,
                "data_criacao": "2026-07-18 16:10:50",
                "excluido": False,
                "ultima_alteracao": "2026-07-18 16:10:50",
            }
        ],
    )
    etapa_antes = catg.obter_ciclo(sessao)["etapa_interna"]

    resp = client.post(
        "/mercos/homologacao-ui/acoes/pagamentos-localizar",
        data={"pagamento_id": "7716"},
    )
    assert resp.status_code == 200
    assert "Pagamento localizado" in resp.text
    assert "7716" in resp.text
    assert "156.00" in resp.text
    assert "Pedido 2150165" in resp.text
    assert "Cliente 9290646" in resp.text
    assert 'data-cursor-intacto="1"' in resp.text
    assert resp.cookies.get("mercos_pagamentos_cursor") is None
    assert catg.obter_ciclo(sessao)["etapa_interna"] == etapa_antes


def test_pagamentos_incremental_envia_cursor_exato(monkeypatch):
    from services.mercos_homolog_service import sincronizar_pagamentos

    capt: dict = {}

    def fake_listar(alterado_apos=None, **_kw):
        capt["alterado_apos"] = alterado_apos
        return {"itens": [], "paginas_lidas": 1}

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_pagamentos_paginado_seguro",
        fake_listar,
    )
    out = sincronizar_pagamentos("2026-07-18 16:10:50")
    assert capt["alterado_apos"] == "2026-07-18 16:10:50"
    assert out["cursor_base"] == "2026-07-18 16:10:50"
    assert out["alterado_apos_enviado"] == "2026-07-18 16:10:50"
    assert out["tipo"] == "incremental"


def test_pagamentos_429_retorna_retry_after_e_libera_lock(client, monkeypatch):
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import _SYNC_PAGAMENTOS_LOCK

    _prep_pagamentos(client, monkeypatch)

    def sempre_429(path, *, params=None, **_kw):
        raise MercosApiError("429", status_code=429, retry_after=12.0)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", sempre_429
    )
    client.post("/mercos/homologacao-ui/acoes/pagamentos-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/pagamentos-sincronizar")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "12"
    assert "Aguardando limite da Mercos" in resp.text
    assert _SYNC_PAGAMENTOS_LOCK.acquire(blocking=False) is True
    _SYNC_PAGAMENTOS_LOCK.release()


def test_pagamentos_sincronizar_bloqueia_concorrencia(client, monkeypatch):
    from services.mercos_homolog_service import _SYNC_PAGAMENTOS_LOCK

    _prep_pagamentos(client, monkeypatch)
    assert _SYNC_PAGAMENTOS_LOCK.acquire(blocking=False) is True
    try:
        client.post("/mercos/homologacao-ui/acoes/pagamentos-reiniciar")
        resp = client.post("/mercos/homologacao-ui/acoes/pagamentos-sincronizar")
        assert resp.status_code == 409
        assert "já em andamento" in resp.text
    finally:
        _SYNC_PAGAMENTOS_LOCK.release()


def test_demais_fluxos_intactos_apos_pagamentos(client, monkeypatch):
    """Condições, formas, faturamento, títulos e demais ciclos permanecem intactos."""
    _prep_pagamentos(client, monkeypatch)
    client.post("/mercos/homologacao-ui/acoes/pagamentos-reiniciar")

    # Condições GET intacto
    listar = MagicMock(
        return_value={"ok": True, "itens": [{"id": 1, "nome": "À vista"}], "total": 1}
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_condicoes_pagamento", listar
    )
    r_cond = client.post("/mercos/homologacao-ui/acoes/condicoes")
    assert r_cond.status_code == 200
    listar.assert_called()

    # Formas POST intacto
    criar_forma = MagicMock(return_value={"id": 9, "nome": "Pix"})
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.homolog.criar_forma_pagamento", criar_forma
    )
    r_forma = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-criar",
        data={"nome": "Pix", "ativo": "sim"},
    )
    assert r_forma.status_code == 200
    criar_forma.assert_called()

    # Ciclos GET de outras entidades
    for rota in (
        "/mercos/homologacao-ui/acoes/produtos-reiniciar",
        "/mercos/homologacao-ui/acoes/clientes-reiniciar",
        "/mercos/homologacao-ui/acoes/usuarios-reiniciar",
        "/mercos/homologacao-ui/acoes/pedidos-reiniciar",
        "/mercos/homologacao-ui/acoes/tipos-pedido-reiniciar",
    ):
        resp = client.post(rota)
        assert resp.status_code == 200, rota
        assert "Ciclo de sincronização reiniciado" in resp.text

    # Rotas de faturamento e títulos continuam registradas (sem 404)
    for rota in (
        "/mercos/homologacao-ui/acoes/pedidos-faturar",
        "/mercos/homologacao-ui/acoes/faturamento-alterar",
        "/mercos/homologacao-ui/acoes/titulos-criar",
    ):
        resp = client.post(rota, data={})
        assert resp.status_code != 404, rota


def _catalogar_transacao_vencimento_7716(catg, sessao):
    catg.substituir_completo(
        sessao,
        [
            {
                "id": 7716,
                "valor": 156.0,
                "pedido_id": 2150165,
                "cliente_id": 9290646,
                "data_criacao": "2026-07-18 16:10:50",
                "excluido": False,
                "ultima_alteracao": "2026-07-19 16:10:50",
                "transacoes": [
                    {
                        "transacao_id": "pay_1006121739",
                        "data_vencimento": "2026-08-18",
                        "status": "confirmado",
                        "valor": 100.0,
                    },
                    {
                        "transacao_id": "pay_3257771107",
                        "data_vencimento": "2026-09-17",
                        "status": "pendente",
                        "valor": 56.0,
                    },
                ],
            }
        ],
        meta={
            "tipo": "incremental",
            "cursor_base": "2026-07-18 16:10:50",
            "alterado_apos_enviado": "2026-07-18 16:10:50",
            "novo_cursor": "2026-07-19 16:10:50",
            "status_sync": "Concluída",
            "total_lote": 1,
        },
    )


def test_pagamentos_localiza_transacao_por_data_br_e_status_exato(client, monkeypatch):
    """18/08/2026 encontra a transação aninhada e mantém status sem tradução."""
    catg = _prep_pagamentos(client, monkeypatch)

    def explode(*_a, **_k):
        raise AssertionError("Localizador por vencimento não pode chamar a Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", explode)
    monkeypatch.setattr("services.mercos_api_client.request_mercos", explode)
    client.post("/mercos/homologacao-ui/acoes/pagamentos-reiniciar")
    sessao = client.cookies.get("mercos_pagamentos_sessao")
    _catalogar_transacao_vencimento_7716(catg, sessao)
    etapa_antes = catg.obter_ciclo(sessao)["etapa_interna"]

    resp = client.post(
        "/mercos/homologacao-ui/acoes/pagamentos-localizar-vencimento",
        data={"data_vencimento": "18/08/2026"},
    )

    assert resp.status_code == 200
    assert "Transação localizada" in resp.text
    assert "7716" in resp.text
    assert "pay_1006121739" in resp.text
    assert "2026-08-18" in resp.text
    assert "confirmado" in resp.text
    assert "Confirmado" not in resp.text
    assert 'data-status-transacao="confirmado"' in resp.text
    assert "100.00" in resp.text
    assert "2150165" in resp.text
    assert "9290646" in resp.text
    assert 'data-cursor-intacto="1"' in resp.text
    assert catg.obter_ciclo(sessao)["etapa_interna"] == etapa_antes


def test_pagamentos_localiza_transacao_por_data_iso_sem_http(client, monkeypatch):
    """2026-08-18 é aceito e a pesquisa permanece exclusivamente local."""
    catg = _prep_pagamentos(client, monkeypatch)
    http = MagicMock(side_effect=AssertionError("não pode chamar HTTP"))
    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", http)
    monkeypatch.setattr("services.mercos_api_client.request_mercos", http)
    client.post("/mercos/homologacao-ui/acoes/pagamentos-reiniciar")
    sessao = client.cookies.get("mercos_pagamentos_sessao")
    _catalogar_transacao_vencimento_7716(catg, sessao)
    ciclo_antes = catg.obter_ciclo(sessao)
    cookie_antes = client.cookies.get("mercos_pagamentos_cursor")

    resp = client.post(
        "/mercos/homologacao-ui/acoes/pagamentos-localizar-vencimento",
        data={"data_vencimento": "2026-08-18"},
    )

    assert resp.status_code == 200
    assert "pay_1006121739" in resp.text
    assert "confirmado" in resp.text
    http.assert_not_called()
    assert client.cookies.get("mercos_pagamentos_cursor") == cookie_antes
    assert catg.obter_ciclo(sessao) == ciclo_antes


def test_pagamentos_etapa_2_incremental_preserva_transacoes(client, monkeypatch):
    """A etapa 2 usa alterado_apos exato e persiste a lista aninhada."""
    catg = _prep_pagamentos(client, monkeypatch)
    cursores: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/pagamentos"
        cursor = (params or {}).get("alterado_apos")
        cursores.append(cursor)
        headers = {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "0"}
        if cursor is None:
            return (
                [
                    {
                        "id": 7716,
                        "valor": 156.0,
                        "ultima_alteracao": "2026-07-18 16:10:50",
                        "transacoes": [],
                    }
                ],
                headers,
            )
        return (
            [
                {
                    "id": 7716,
                    "valor": 156.0,
                    "pedido_id": 2150165,
                    "cliente_id": 9290646,
                    "ultima_alteracao": "2026-07-19 16:10:50",
                    "transacoes": [
                        {
                            "transacao_id": "pay_1006121739",
                            "data_vencimento": "2026-08-18",
                            "status": "confirmado",
                            "valor": 100.0,
                        }
                    ],
                }
            ],
            headers,
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    client.post("/mercos/homologacao-ui/acoes/pagamentos-reiniciar")
    sessao = client.cookies.get("mercos_pagamentos_sessao")
    r1 = client.post("/mercos/homologacao-ui/acoes/pagamentos-sincronizar")
    r2 = client.post("/mercos/homologacao-ui/acoes/pagamentos-sincronizar")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert cursores == [None, "2026-07-18 16:10:50"]
    assert 'data-tipo-busca="incremental"' in r2.text
    assert 'data-alterado-apos-enviado="2026-07-18 16:10:50"' in r2.text
    assert catg.obter_ciclo(sessao)["etapa_interna"] == 2
    transacoes = catg.obter(sessao)["pagamentos"]["7716"]["transacoes"]
    assert transacoes[0]["data_vencimento"] == "2026-08-18"
    assert transacoes[0]["status"] == "confirmado"


# ---------------------------------------------------------------------------
# Promoções GET — ciclo de homologação em 2 etapas
# ---------------------------------------------------------------------------


def _prep_promocoes(client, monkeypatch):
    from services import mercos_promocoes_catalogo as catg
    from services.mercos_homolog_service import _reset_resume_clientes_para_testes

    catg._reset_todos_para_testes()
    _reset_resume_clientes_para_testes()
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    return catg


def test_ui_secao_promocoes_buscar_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    secao = html.split('id="sec-promocoes-buscar"')[1].split("</section>")[0]
    assert 'id="btn-promocoes-reiniciar"' in secao
    assert 'id="btn-promocoes-sincronizar"' in secao
    assert 'id="input-promocoes-slug"' in secao
    assert 'id="btn-promocoes-localizar"' in secao
    assert "Reiniciar ciclo de sincronização" in secao
    assert "Localizar promoção pelo slug" in secao
    assert "Promoções — Buscar" in secao
    assert "mercos_promocoes_cursor" in html
    assert "mercos_promocoes_catalogo" in html
    assert 'id="sec-pagamentos-buscar"' in html
    assert 'id="sec-produtos"' in html


def test_promocoes_botoes_rotas_registradas_sem_404(client, monkeypatch):
    _prep_promocoes(client, monkeypatch)
    for rota in (
        "/mercos/homologacao-ui/acoes/promocoes-reiniciar",
        "/mercos/homologacao-ui/acoes/promocoes-sincronizar",
        "/mercos/homologacao-ui/acoes/promocoes-localizar",
    ):
        resp = client.post(rota)
        assert resp.status_code != 404, rota


def test_promocoes_reiniciar_nao_chama_mercos(client, monkeypatch):
    catg = _prep_promocoes(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    resp = client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    assert resp.status_code == 200
    assert "Ciclo de sincronização reiniciado" in resp.text
    assert "0/2" in resp.text
    assert 'data-ciclo-ativo="1"' in resp.text
    called.assert_not_called()
    sessao = client.cookies.get("mercos_promocoes_sessao")
    assert catg.total(sessao) == 0
    assert catg.obter_ciclo(sessao)["etapa_interna"] == 0


def _form_produto_homolog() -> dict:
    return {
        "nome": "Produto Homolog",
        "codigo": "HOM-P-01",
        "preco_tabela": "19.90",
        "saldo_estoque": "5",
        "ativo": "true",
        "unidade": "UN",
    }


def _fake_criar_produto_ok():
    def fake_criar(body):
        return {
            "ok": True,
            "status_code": 201,
            "id": 555,
            "dados": {"id": 555, "nome": body["nome"], "codigo": body["codigo"]},
        }

    return fake_criar


def test_modo_exclusivo_bloqueia_produto_post_durante_sincronizacao(client, monkeypatch):
    """Enquanto uma sincronização GET de Promoções está em andamento, o Produto
    POST recebe 409 amigável e NÃO chama a Mercos."""
    from services import mercos_promocoes_catalogo as catg

    _prep_promocoes(client, monkeypatch)
    criar = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.criar_produto", criar)

    # Simula o sync GET realmente em execução (etapa 1/2).
    catg.iniciar_modo_exclusivo("1/2")
    try:
        bloqueada = client.post(
            "/mercos/homologacao-ui/acoes/produtos-criar",
            data=_form_produto_homolog(),
        )
    finally:
        catg.finalizar_modo_exclusivo()
    assert bloqueada.status_code == 409
    assert "Homologação de Promoções em andamento" in bloqueada.text
    criar.assert_not_called()

    # Localizar no catálogo local continua permitido durante o sync.
    catg.iniciar_modo_exclusivo("2/2")
    try:
        local = client.post(
            "/mercos/homologacao-ui/acoes/promocoes-localizar",
            data={"token": "segredo-ui-homolog", "slug": "inexistente"},
        )
    finally:
        catg.finalizar_modo_exclusivo()
    assert local.status_code == 200


def test_modo_exclusivo_liberado_apos_etapa_2_2(client, monkeypatch):
    """Concluída a etapa 2/2 do GET, o modo exclusivo fica inativo e o Produto
    POST volta a funcionar."""
    from services import mercos_promocoes_catalogo as catg

    _prep_promocoes(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_promocoes_sandbox(cursores),
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_produto", _fake_criar_produto_ok()
    )
    client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    client.post("/mercos/homologacao-ui/acoes/promocoes-sincronizar")  # etapa 1/2
    resp2 = client.post("/mercos/homologacao-ui/acoes/promocoes-sincronizar")  # 2/2
    assert resp2.status_code == 200
    assert catg.modo_exclusivo_ativo() is False

    criado = client.post(
        "/mercos/homologacao-ui/acoes/produtos-criar",
        data=_form_produto_homolog(),
    )
    assert criado.status_code == 200
    assert "Produto cadastrado" in criado.text


def test_reiniciar_ciclo_libera_produto_post(client, monkeypatch):
    """Reiniciar o ciclo limpa o modo exclusivo; Produto POST não é bloqueado."""
    from services import mercos_promocoes_catalogo as catg

    _prep_promocoes(client, monkeypatch)
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_produto", _fake_criar_produto_ok()
    )
    # Deixa o modo exclusivo "preso" (como no bug relatado) e reinicia.
    catg.iniciar_modo_exclusivo("2/2")
    reinit = client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    assert reinit.status_code == 200
    assert catg.modo_exclusivo_ativo() is False

    criado = client.post(
        "/mercos/homologacao-ui/acoes/produtos-criar",
        data=_form_produto_homolog(),
    )
    assert criado.status_code == 200
    assert "Produto cadastrado" in criado.text


def test_erro_durante_sincronizacao_libera_lock_no_finally(client, monkeypatch):
    """Se a sincronização falhar, o modo exclusivo é liberado no finally."""
    from services import mercos_promocoes_catalogo as catg

    _prep_promocoes(client, monkeypatch)

    def explode(*_a, **_k):
        raise RuntimeError("falha simulada no sync")

    monkeypatch.setattr("services.mercos_homolog_service.sincronizar_promocoes", explode)
    resp = client.post("/mercos/homologacao-ui/acoes/promocoes-sincronizar")
    assert resp.status_code == 200  # cartão de erro amigável
    assert catg.modo_exclusivo_ativo() is False

    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_produto", _fake_criar_produto_ok()
    )
    criado = client.post(
        "/mercos/homologacao-ui/acoes/produtos-criar",
        data=_form_produto_homolog(),
    )
    assert criado.status_code == 200


def test_catalogo_e_cursor_nao_ativam_modo_exclusivo(client, monkeypatch):
    """Catálogo/cursor existentes (sem sync em execução) não bloqueiam Produto POST."""
    from services import mercos_promocoes_catalogo as catg

    _prep_promocoes(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_promocoes_sandbox(cursores),
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.criar_produto", _fake_criar_produto_ok()
    )
    client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    client.post("/mercos/homologacao-ui/acoes/promocoes-sincronizar")
    # Há catálogo e cursor, mas nenhum sync em execução.
    assert catg.modo_exclusivo_ativo() is False

    criado = client.post(
        "/mercos/homologacao-ui/acoes/produtos-criar",
        data=_form_produto_homolog(),
    )
    assert criado.status_code == 200


def test_reiniciar_nao_chama_mercos_e_limpa_exclusivo(client, monkeypatch):
    """Reiniciar não chama a Mercos e desliga o modo exclusivo."""
    from services import mercos_promocoes_catalogo as catg

    _prep_promocoes(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", called)
    catg.iniciar_modo_exclusivo("1/2")
    resp = client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    assert resp.status_code == 200
    called.assert_not_called()
    assert catg.modo_exclusivo_ativo() is False


def _fake_promocoes_sandbox(cursores_vistos):
    """Contrato real: completa sem alterado_apos; incremental com cursor exato."""

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/promocoes"
        params = params or {}
        assert "pagina" not in params
        cursor = params.get("alterado_apos")
        cursores_vistos.append(cursor)
        headers_base = {
            "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
            "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "3",
            "MEUSPEDIDOS_REQUISICOES_EXTRAS": "1",
        }
        if cursor is None:
            return (
                [
                    {
                        "id": 110471,
                        "representada_id": 1,
                        "nome": "4968442715c948da",
                        "slug": "228d165932574cab",
                        "data_inicial": "2026-01-01",
                        "data_final": "2026-12-31",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-15 10:00:00",
                        "regras": [{"tipo": "desconto"}],
                    },
                    {
                        "id": 110500,
                        "nome": "promo-excluida",
                        "slug": "abc123excluida",
                        "data_inicial": "2026-02-01",
                        "data_final": "2026-06-30",
                        "excluido": True,
                        "ultima_alteracao": "2026-07-14 09:00:00",
                    },
                ],
                headers_base,
            )
        if cursor == "2026-07-15 10:00:00":
            return (
                [
                    {
                        "id": 110600,
                        "nome": "promo-lote2",
                        "slug": "lote2slug",
                        "data_inicial": "2026-03-01",
                        "data_final": "2026-09-30",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-16 11:00:00",
                    }
                ],
                {},
            )
        if cursor == "2026-07-16 11:00:00":
            return (
                [
                    {
                        "id": 110700,
                        "nome": "promo-incremental",
                        "slug": "incslug99",
                        "data_inicial": "2026-04-01",
                        "data_final": "2026-10-31",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-19 08:00:00",
                    }
                ],
                {
                    "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "1",
                },
            )
        return ([], {})

    return fake_get


def test_promocoes_ciclo_2_etapas_completa_e_incremental(client, monkeypatch):
    """Etapa 1 completa percorre lotes com extras; etapa 2 incremental com cursor exato."""
    catg = _prep_promocoes(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_promocoes_sandbox(cursores),
    )
    client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    sessao = client.cookies.get("mercos_promocoes_sessao")

    r1 = client.post("/mercos/homologacao-ui/acoes/promocoes-sincronizar")
    assert r1.status_code == 200
    assert cursores[0] is None
    assert cursores[1] == "2026-07-15 10:00:00"
    assert len(cursores) == 2
    assert "1/2" in r1.text
    assert 'data-tipo-busca="completa"' in r1.text
    assert "228d165932574cab" in r1.text
    assert "110471" in r1.text
    assert catg.total(sessao) == 3
    assert catg.obter(sessao)["promocoes"]["110500"]["excluido"] is True
    assert catg.obter_ciclo(sessao)["chamadas_completas"] == 1

    r2 = client.post("/mercos/homologacao-ui/acoes/promocoes-sincronizar")
    assert r2.status_code == 200
    assert cursores[2] == "2026-07-16 11:00:00"
    assert "2/2" in r2.text
    assert 'data-tipo-busca="incremental"' in r2.text
    assert 'data-cursor-base="2026-07-16 11:00:00"' in r2.text
    assert 'data-alterado-apos-enviado="2026-07-16 11:00:00"' in r2.text
    assert "2026-07-16 11:00:59" not in r2.text
    assert catg.total(sessao) == 4
    estado = catg.obter(sessao)
    assert "110471" in estado["promocoes"]
    assert "110700" in estado["promocoes"]
    ciclo = catg.obter_ciclo(sessao)
    assert ciclo["chamadas_completas"] == 1
    assert ciclo["chamadas_incrementais"] == 1
    assert ciclo["etapa_interna"] == 2
    assert "Requisições previstas" in r2.text
    assert "Requisições executadas" in r2.text


def test_promocoes_extras_headers_limita_chamadas(monkeypatch):
    """Paginação dinâmica: para quando o lote atual não indica mais registros
    (headers sem extras/limitou) — aqui após 2 chamadas."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_FIM,
        listar_promocoes_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    chamadas: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/promocoes"
        chamadas.append((params or {}).get("alterado_apos"))
        assert len(chamadas) <= 2, "não pode existir 3ª chamada"
        if len(chamadas) == 1:
            return (
                [
                    {
                        "id": 110471,
                        "slug": "228d165932574cab",
                        "nome": "4968442715c948da",
                        "ultima_alteracao": "2026-07-15 10:00:00",
                    },
                    {
                        "id": 110500,
                        "slug": "abc123excluida",
                        "excluido": True,
                        "ultima_alteracao": "2026-07-14 09:00:00",
                    },
                ],
                {
                    "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                    "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "3",
                    "MEUSPEDIDOS_REQUISICOES_EXTRAS": "1",
                },
            )
        return (
            [
                {
                    "id": 110600,
                    "slug": "lote2slug",
                    "ultima_alteracao": "2026-07-16 11:00:00",
                }
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_promocoes_paginado_seguro(max_paginas=20, timeout_total=60)
    assert len(chamadas) == 2
    assert chamadas[0] is None
    assert chamadas[1] == "2026-07-15 10:00:00"
    assert out["total"] == 3
    assert out["requisicoes_extras"] == 1
    assert out["requisicoes_executadas"] == 2
    assert out["motivo_parada"] == MOTIVO_PARADA_FIM
    ids = [i.get("id") for i in out["itens"]]
    assert 110471 in ids


def test_promocoes_localizar_slug_sem_http(client, monkeypatch):
    """Localiza pelo slug só no catálogo local; não chama Mercos nem altera cursor."""
    catg = _prep_promocoes(client, monkeypatch)

    def explode(*_a, **_k):
        raise AssertionError("Localizar promoção não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", explode)
    monkeypatch.setattr("services.mercos_api_client.request_mercos", explode)

    client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    sessao = client.cookies.get("mercos_promocoes_sessao")
    catg.upsert_incremental(
        sessao,
        [
            {
                "id": 110471,
                "nome": "4968442715c948da",
                "slug": "228d165932574cab",
                "data_inicial": "2026-01-01",
                "data_final": "2026-12-31",
                "excluido": False,
                "ultima_alteracao": "2026-07-15 10:00:00",
            }
        ],
    )
    etapa_antes = catg.obter_ciclo(sessao)["etapa_interna"]

    resp = client.post(
        "/mercos/homologacao-ui/acoes/promocoes-localizar",
        data={"slug": "228d165932574cab"},
    )
    assert resp.status_code == 200
    assert "Promoção ativa localizada" in resp.text
    assert "110471" in resp.text
    assert "228d165932574cab" in resp.text
    assert "4968442715c948da" in resp.text
    assert 'data-cursor-intacto="1"' in resp.text
    assert resp.cookies.get("mercos_promocoes_cursor") is None
    assert catg.obter_ciclo(sessao)["etapa_interna"] == etapa_antes


def test_promocoes_incremental_envia_cursor_exato(monkeypatch):
    from services.mercos_homolog_service import sincronizar_promocoes

    capt: dict = {}

    def fake_listar(alterado_apos=None, **_kw):
        capt["alterado_apos"] = alterado_apos
        return {"itens": [], "paginas_lidas": 1}

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_promocoes_paginado_seguro",
        fake_listar,
    )
    out = sincronizar_promocoes("2026-07-16 11:00:00")
    assert capt["alterado_apos"] == "2026-07-16 11:00:00"
    assert out["cursor_base"] == "2026-07-16 11:00:00"
    assert out["alterado_apos_enviado"] == "2026-07-16 11:00:00"
    assert out["tipo"] == "incremental"


def test_promocoes_429_retorna_retry_after_e_libera_lock(client, monkeypatch):
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import _SYNC_PROMOCOES_LOCK

    _prep_promocoes(client, monkeypatch)

    def sempre_429(path, *, params=None, **_kw):
        raise MercosApiError("429", status_code=429, retry_after=12.0)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", sempre_429
    )
    client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/promocoes-sincronizar")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "12"
    assert "Aguardando limite da Mercos" in resp.text
    assert _SYNC_PROMOCOES_LOCK.acquire(blocking=False) is True
    _SYNC_PROMOCOES_LOCK.release()


def test_promocoes_sincronizar_bloqueia_concorrencia(client, monkeypatch):
    from services.mercos_homolog_service import _SYNC_PROMOCOES_LOCK

    _prep_promocoes(client, monkeypatch)
    assert _SYNC_PROMOCOES_LOCK.acquire(blocking=False) is True
    try:
        client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
        resp = client.post("/mercos/homologacao-ui/acoes/promocoes-sincronizar")
        assert resp.status_code == 409
        assert "já em andamento" in resp.text
    finally:
        _SYNC_PROMOCOES_LOCK.release()


def test_demais_fluxos_intactos_apos_promocoes(client, monkeypatch):
    """Produtos, condições e tabelas permanecem intactos após promoções."""
    _prep_promocoes(client, monkeypatch)
    client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")

    for rota in (
        "/mercos/homologacao-ui/acoes/produtos-reiniciar",
        "/mercos/homologacao-ui/acoes/condicoes-reiniciar",
        "/mercos/homologacao-ui/acoes/tabelas-preco-reiniciar",
        "/mercos/homologacao-ui/acoes/pagamentos-reiniciar",
    ):
        resp = client.post(rota)
        assert resp.status_code == 200, rota
        assert "Ciclo de sincronização reiniciado" in resp.text


# ---------------------------------------------------------------------------
# Promoções GET — throttling (rate limiter global por CompanyToken)
# ---------------------------------------------------------------------------


def test_promocoes_rate_limiter_intervalo_minimo_antes_de_cada_request(monkeypatch):
    """Etapa 1 (1 + extras): a chamada extra passa pelo MESMO limiter e só sai
    após o intervalo mínimo de 6.5s; a promoção alvo aparece no lote."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_FIM,
        PEDIDOS_INTERVALO_MINIMO_SEGUNDOS,
        _RateLimiterMercos,
        _reset_resume_clientes_para_testes,
        listar_promocoes_paginado_seguro,
    )

    assert PEDIDOS_INTERVALO_MINIMO_SEGUNDOS == 5.0
    _reset_resume_clientes_para_testes()
    clk = _RelogioFake()
    limiter = _RateLimiterMercos(5.0, relogio=clk.agora, dormir=clk.dormir)
    instantes: list[float] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/promocoes"
        assert "pagina" not in (params or {})
        # Lock do limiter deve estar preso durante toda a chamada HTTP.
        assert limiter._lock.locked()
        instantes.append(clk.t)
        clk.t += 0.3  # duração variável da requisição
        if len(instantes) == 1:
            return (
                [
                    {
                        "id": 110471,
                        "slug": "228d165932574cab",
                        "nome": "4968442715c948da",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-15 10:00:00",
                    }
                ],
                {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "1"},
            )
        return (
            [
                {
                    "id": 110600,
                    "slug": "lote2slug",
                    "excluido": True,
                    "ultima_alteracao": "2026-07-16 11:00:00",
                }
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_promocoes_paginado_seguro(
        rate_limiter=limiter, max_paginas=20, timeout_total=60
    )
    # Duas respostas válidas: o 2º lote sem headers de continuação encerra.
    assert len(instantes) == 2
    assert out["requisicoes_executadas"] == 2
    assert out["motivo_parada"] == MOTIVO_PARADA_FIM
    # Intervalo real entre os INÍCIOS das requisições >= 8.0 (margem segura).
    assert instantes[1] - instantes[0] >= 8.0
    # Espera calculada ANTES do envio (8.0 - 0.3s de duração).
    assert clk.esperas == [7.7]
    assert out["intervalo_minimo_aplicado"] == 8.0
    assert out["menor_intervalo_real"] >= 8.0
    assert out["throttling_respeitado"] is True
    # A promoção alvo (slug/ID) foi capturada.
    ids = [i.get("id") for i in out["itens"]]
    assert 110471 in ids


def test_promocoes_rate_limiter_429_retry_after_menor_que_5s_nao_reduz_piso(monkeypatch):
    """429 com Retry-After 1s (< piso): o piso de 5s prevalece e a MESMA página
    é refeita; apenas as respostas válidas contam."""
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import (
        _RateLimiterMercos,
        _reset_resume_clientes_para_testes,
        listar_promocoes_paginado_seguro,
    )

    _reset_resume_clientes_para_testes()
    clk = _RelogioFake()
    limiter = _RateLimiterMercos(5.0, relogio=clk.agora, dormir=clk.dormir)
    instantes: list[float] = []
    cursores: list[str | None] = []

    def nao_dormir_local(_s):
        raise AssertionError("Deve usar o rate limiter, não time.sleep local")

    monkeypatch.setattr("services.mercos_homolog_service.time.sleep", nao_dormir_local)

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/promocoes"
        assert limiter._lock.locked()
        instantes.append(clk.t)
        clk.t += 0.2
        cursor = (params or {}).get("alterado_apos")
        cursores.append(cursor)
        if len(cursores) == 2:
            # Retry-After MENOR que o piso de 5s.
            raise MercosApiError("429", status_code=429, retry_after=1.0)
        if len(cursores) == 1:
            return (
                [
                    {
                        "id": 110471,
                        "slug": "228d165932574cab",
                        "nome": "4968442715c948da",
                        "ultima_alteracao": "2026-07-15 10:00:00",
                    }
                ],
                {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "1"},
            )
        return (
            [
                {
                    "id": 110600,
                    "slug": "lote2slug",
                    "ultima_alteracao": "2026-07-16 11:00:00",
                }
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_promocoes_paginado_seguro(
        rate_limiter=limiter, max_paginas=20, timeout_total=60
    )
    # A MESMA página (mesmo alterado_apos) é refeita após o 429.
    assert len(cursores) == 3
    assert cursores[1] == cursores[2] == "2026-07-15 10:00:00"
    # Retry-After de 1s NUNCA antecipa o piso: 2ª→3ª chamada respeita >= 8.0s.
    assert instantes[2] - instantes[1] >= 8.0
    # Apenas as 2 respostas válidas contam como requisições executadas.
    assert out["requisicoes_executadas"] == 2
    assert out["total"] == 2
    assert out["throttling_respeitado"] is True


def test_promocoes_rate_limiter_compartilhado_mesmo_company_token(monkeypatch):
    """Reutiliza o limiter GLOBAL keyed por CompanyToken (mesma instância dos
    demais GET); nenhuma chamada ocorre fora do limiter."""
    from services import mercos_homolog_service as svc

    svc._reset_resume_clientes_para_testes()
    svc._reset_rate_limiters_para_testes()
    monkeypatch.setenv("MERCOS_COMPANY_TOKEN", "empresa-promocoes")
    limiter = svc._rate_limiter_pedidos()
    clk = _RelogioFake()
    limiter._relogio = clk.agora
    limiter._dormir = clk.dormir

    marcas_pre_http: list[float] = []
    lock_preso: list[bool] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/promocoes"
        marcas_pre_http.append(clk.agora())
        lock_preso.append(limiter._lock.locked())
        clk.t += 1.3  # duração real observada em produção
        if len(marcas_pre_http) == 1:
            return (
                [
                    {
                        "id": 110471,
                        "slug": "228d165932574cab",
                        "nome": "4968442715c948da",
                        "ultima_alteracao": "2026-07-15 10:00:00",
                    }
                ],
                {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "1"},
            )
        return (
            [
                {
                    "id": 110600,
                    "slug": "lote2slug",
                    "ultima_alteracao": "2026-07-16 11:00:00",
                }
            ],
            {},
        )

    monkeypatch.setattr(svc, "get_json_com_headers", fake_get)
    out = svc.sincronizar_promocoes()

    # Exatamente 1 + extras chamadas, todas dentro do limiter.
    assert len(marcas_pre_http) == 2
    assert all(lock_preso)
    assert marcas_pre_http[1] - marcas_pre_http[0] >= 8.0
    assert out["intervalo_minimo_aplicado"] == 8.0
    assert out["menor_intervalo_real"] >= 8.0
    assert out["throttling_respeitado"] is True
    # Mesma instância compartilhada por CompanyToken em todo o processo.
    assert svc._rate_limiter_pedidos() is limiter
    assert len(svc._RATE_LIMITERS_MERCOS) == 1


def test_promocoes_rate_limiter_libera_lock_em_erro():
    """Exceção na chamada HTTP não deixa o lock do limiter preso."""
    from services.mercos_homolog_service import _RateLimiterMercos

    clk = _RelogioFake()
    limiter = _RateLimiterMercos(5.0, relogio=clk.agora, dormir=clk.dormir)

    def explode():
        raise RuntimeError("falha simulada")

    with pytest.raises(RuntimeError):
        limiter.executar(explode)
    assert limiter._lock.locked() is False


def test_promocoes_localiza_slug_alvo_como_id_apos_throttling(client, monkeypatch):
    """Após a busca completa com throttling, localizar por slug retorna o ID."""
    catg = _prep_promocoes(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_promocoes_sandbox(cursores),
    )
    client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    sessao = client.cookies.get("mercos_promocoes_sessao")
    client.post("/mercos/homologacao-ui/acoes/promocoes-sincronizar")

    def explode(*_a, **_k):
        raise AssertionError("Localizar promoção não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    etapa_antes = catg.obter_ciclo(sessao)["etapa_interna"]
    resp = client.post(
        "/mercos/homologacao-ui/acoes/promocoes-localizar",
        data={"slug": "228d165932574cab"},
    )
    assert resp.status_code == 200
    assert "Promoção ativa localizada" in resp.text
    assert "110471" in resp.text
    assert catg.obter_ciclo(sessao)["etapa_interna"] == etapa_antes


def test_promocoes_localizar_prioriza_ativo_ignorando_excluido(client, monkeypatch):
    """Dois registros do mesmo slug (um excluído, um ativo): retorna o ATIVO."""
    catg = _prep_promocoes(client, monkeypatch)

    def explode(*_a, **_k):
        raise AssertionError("Localizar promoção não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", explode)

    client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    sessao = client.cookies.get("mercos_promocoes_sessao")
    catg.upsert_incremental(
        sessao,
        [
            {
                "id": 110473,
                "nome": "promo-excluida",
                "slug": "55c218df0edd4bef",
                "data_inicial": "2026-02-01",
                "data_final": "2026-06-30",
                "excluido": True,
                "ultima_alteracao": "2026-07-18 09:00:00",
            },
            {
                "id": 110480,
                "nome": "promo-ativa",
                "slug": "55c218df0edd4bef",
                "data_inicial": "2026-03-01",
                "data_final": "2026-12-31",
                "excluido": False,
                "ultima_alteracao": "2026-07-19 10:00:00",
            },
        ],
    )
    etapa_antes = catg.obter_ciclo(sessao)["etapa_interna"]

    resp = client.post(
        "/mercos/homologacao-ui/acoes/promocoes-localizar",
        data={"slug": "55c218df0edd4bef"},
    )
    assert resp.status_code == 200
    # Retorna o registro ATIVO; nunca o excluído como ativo.
    assert "Promoção ativa localizada" in resp.text
    assert "110480" in resp.text
    # O card principal exibe o ID ativo, não o excluído.
    card_ativo = resp.text.split("Promoção ativa localizada")[1].split("</ul>")[0]
    assert "110480" in card_ativo
    assert "110473" not in card_ativo
    # Ambos os registros aparecem na tabela de correspondências.
    assert "promo-excluida" in resp.text
    assert "promo-ativa" in resp.text
    # Localização não altera cursor nem etapa e não chama HTTP.
    assert 'data-cursor-intacto="1"' in resp.text
    assert catg.obter_ciclo(sessao)["etapa_interna"] == etapa_antes


def test_promocoes_localizar_slug_so_excluido_sem_ativo(client, monkeypatch):
    """Slug só com registro excluído: mostra mensagem de nenhuma promoção ativa."""
    catg = _prep_promocoes(client, monkeypatch)

    def explode(*_a, **_k):
        raise AssertionError("Localizar promoção não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)

    client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    sessao = client.cookies.get("mercos_promocoes_sessao")
    catg.upsert_incremental(
        sessao,
        [
            {
                "id": 110473,
                "nome": "promo-excluida",
                "slug": "55c218df0edd4bef",
                "excluido": True,
                "ultima_alteracao": "2026-07-18 09:00:00",
            }
        ],
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/promocoes-localizar",
        data={"slug": "55c218df0edd4bef"},
    )
    assert resp.status_code == 200
    assert "Nenhuma promoção ativa encontrada para este slug." in resp.text
    assert 'data-cursor-intacto="1"' in resp.text


# ---------------------------------------------------------------------------
# Promoções GET — margem segura de 8.0s no throttling global por CompanyToken
# ---------------------------------------------------------------------------


def test_promocoes_intervalo_minimo_8s_entre_paginas(monkeypatch):
    """Etapa 1 (1 + extras): a 2ª página só sai >= 8.0s após a 1ª (não 5.0)."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_FIM,
        PROMOCOES_INTERVALO_MINIMO_SEGUNDOS,
        _RateLimiterMercos,
        _reset_resume_clientes_para_testes,
        listar_promocoes_paginado_seguro,
    )

    assert PROMOCOES_INTERVALO_MINIMO_SEGUNDOS == 8.0
    _reset_resume_clientes_para_testes()
    clk = _RelogioFake()
    # Instância com piso padrão 5.0: o override de 8.0 deve prevalecer.
    limiter = _RateLimiterMercos(5.0, relogio=clk.agora, dormir=clk.dormir)
    instantes: list[float] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/promocoes"
        assert limiter._lock.locked()
        instantes.append(clk.t)
        clk.t += 0.3
        if len(instantes) == 1:
            return (
                [
                    {
                        "id": 110474,
                        "slug": "55c218df0edd4bef",
                        "nome": "ativa",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-15 10:00:00",
                    }
                ],
                {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "1"},
            )
        return (
            [
                {
                    "id": 110600,
                    "slug": "lote2slug",
                    "ultima_alteracao": "2026-07-16 11:00:00",
                }
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_promocoes_paginado_seguro(
        rate_limiter=limiter, max_paginas=20, timeout_total=60
    )
    assert len(instantes) == 2
    assert out["motivo_parada"] == MOTIVO_PARADA_FIM
    assert instantes[1] - instantes[0] >= 8.0
    assert clk.esperas == [7.7]  # 8.0 - 0.3 de duração
    assert out["intervalo_minimo_aplicado"] == 8.0
    assert out["menor_intervalo_real"] >= 8.0
    assert out["throttling_respeitado"] is True


def test_promocoes_intervalo_8s_entre_etapa1_e_etapa2_mesmo_limiter(monkeypatch):
    """O gap entre a última chamada da etapa 1 e a primeira da etapa 2 (mesmo
    limiter global por CompanyToken) é medido e respeita >= 8.0s."""
    from services import mercos_homolog_service as svc

    svc._reset_resume_clientes_para_testes()
    svc._reset_rate_limiters_para_testes()
    monkeypatch.setenv("MERCOS_COMPANY_TOKEN", "empresa-promo-65")
    limiter = svc._rate_limiter_pedidos()
    clk = _RelogioFake()
    limiter._relogio = clk.agora
    limiter._dormir = clk.dormir

    chamadas: list[tuple[float, str | None]] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/promocoes"
        cursor = (params or {}).get("alterado_apos")
        chamadas.append((clk.t, cursor))
        clk.t += 0.3
        if cursor is None:
            # Etapa 1, 1º lote: extras=1 → haverá um 2º lote.
            return (
                [
                    {
                        "id": 110474,
                        "slug": "55c218df0edd4bef",
                        "nome": "ativa",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-15 10:00:00",
                    }
                ],
                {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "1"},
            )
        if cursor == "2026-07-15 10:00:00":
            # Etapa 1, 2º (último) lote da busca completa.
            return (
                [
                    {
                        "id": 110600,
                        "slug": "lote2",
                        "ultima_alteracao": "2026-07-16 11:00:00",
                    }
                ],
                {},
            )
        if cursor == "2026-07-16 11:00:00":
            # Etapa 2 incremental: um lote e para.
            return (
                [
                    {
                        "id": 110700,
                        "slug": "lote3",
                        "ultima_alteracao": "2026-07-19 08:00:00",
                    }
                ],
                {"MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "1"},
            )
        return ([], {})

    monkeypatch.setattr(svc, "get_json_com_headers", fake_get)

    etapa1 = svc.sincronizar_promocoes()
    assert etapa1["intervalo_minimo_aplicado"] == 8.0
    etapa2 = svc.sincronizar_promocoes("2026-07-16 11:00:00")
    # A 1ª chamada da etapa 2 só ocorreu >= 8.0s após a última da etapa 1.
    inicio_etapa2 = next(t for t, c in chamadas if c == "2026-07-16 11:00:00")
    ultima_etapa1 = max(t for t, c in chamadas if c == "2026-07-15 10:00:00")
    assert inicio_etapa2 - ultima_etapa1 >= 8.0
    assert etapa2["intervalo_global_anterior"] >= 8.0
    assert etapa2["throttling_respeitado"] is True
    # Limiter compartilhado (mesma instância) entre as duas sincronizações.
    assert svc._rate_limiter_pedidos() is limiter
    assert len(svc._RATE_LIMITERS_MERCOS) == 1


def test_promocoes_limiter_compartilhado_entre_rotas_mesmo_company_token(monkeypatch):
    """Promoções e Pedidos usam a MESMA instância de limiter por CompanyToken;
    o gap entre chamadas de rotas diferentes também é respeitado."""
    from services import mercos_homolog_service as svc

    svc._reset_resume_clientes_para_testes()
    svc._reset_rate_limiters_para_testes()
    monkeypatch.setenv("MERCOS_COMPANY_TOKEN", "empresa-compartilhada")
    limiter = svc._rate_limiter_pedidos()
    clk = _RelogioFake()
    limiter._relogio = clk.agora
    limiter._dormir = clk.dormir

    def fake_promo(path, *, params=None, **_kw):
        clk.t += 0.3
        return (
            [
                {
                    "id": 110474,
                    "slug": "55c218df0edd4bef",
                    "excluido": False,
                    "ultima_alteracao": "2026-07-15 10:00:00",
                }
            ],
            {"MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "1"},
        )

    monkeypatch.setattr(svc, "get_json_com_headers", fake_promo)
    svc.listar_promocoes_paginado_seguro(max_paginas=20, timeout_total=60)
    inicio_pedidos_ref = limiter.ultimo_inicio()
    assert inicio_pedidos_ref is not None

    def fake_pedidos(path, *, params=None, **_kw):
        assert path == "/v1/pedidos"
        clk.t += 0.3
        return (
            [
                {
                    "id": 1,
                    "cliente_id": 10,
                    "total": 5.0,
                    "ultima_alteracao": "2026-07-17 10:00:00",
                }
            ],
            {"MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "1"},
        )

    monkeypatch.setattr(svc, "get_json_com_headers", fake_pedidos)
    out = svc.listar_pedidos_paginado_seguro(max_paginas=20, timeout_total=60)
    # A chamada de pedidos reutilizou o MESMO limiter (mesma instância) e viu o
    # último início registrado pela chamada de promoções.
    assert svc._rate_limiter_pedidos() is limiter
    assert len(svc._RATE_LIMITERS_MERCOS) == 1
    assert out["intervalo_global_anterior"] is not None
    assert out["intervalo_global_anterior"] >= 5.0


def test_promocoes_429_retry_after_menor_que_8_nao_reduz_piso(monkeypatch):
    """429 com Retry-After 2s (< piso 8.0): o piso de 8.0s prevalece e a MESMA
    página é refeita."""
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import (
        _RateLimiterMercos,
        _reset_resume_clientes_para_testes,
        listar_promocoes_paginado_seguro,
    )

    _reset_resume_clientes_para_testes()
    clk = _RelogioFake()
    limiter = _RateLimiterMercos(5.0, relogio=clk.agora, dormir=clk.dormir)
    instantes: list[float] = []
    cursores: list[str | None] = []

    def nao_dormir_local(_s):
        raise AssertionError("Deve usar o rate limiter, não time.sleep local")

    monkeypatch.setattr("services.mercos_homolog_service.time.sleep", nao_dormir_local)

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/promocoes"
        assert limiter._lock.locked()
        instantes.append(clk.t)
        clk.t += 0.2
        cursor = (params or {}).get("alterado_apos")
        cursores.append(cursor)
        if len(cursores) == 2:
            raise MercosApiError("429", status_code=429, retry_after=2.0)
        if len(cursores) == 1:
            return (
                [
                    {
                        "id": 110474,
                        "slug": "55c218df0edd4bef",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-15 10:00:00",
                    }
                ],
                {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "1"},
            )
        return (
            [
                {
                    "id": 110600,
                    "slug": "lote2",
                    "ultima_alteracao": "2026-07-16 11:00:00",
                }
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_promocoes_paginado_seguro(
        rate_limiter=limiter, max_paginas=20, timeout_total=60
    )
    # A MESMA página é refeita após o 429.
    assert len(cursores) == 3
    assert cursores[1] == cursores[2] == "2026-07-15 10:00:00"
    # Retry-After de 2s NUNCA antecipa o piso de 8.0s.
    assert instantes[2] - instantes[1] >= 8.0
    assert out["requisicoes_executadas"] == 2
    assert out["throttling_respeitado"] is True


def test_promocoes_id_ativo_localizado_apos_margem_8(client, monkeypatch):
    """Com a margem de 8.0s, a busca completa continua localizando o ID ativo."""
    catg = _prep_promocoes(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_promocoes_sandbox(cursores),
    )
    client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    client.post("/mercos/homologacao-ui/acoes/promocoes-sincronizar")

    def explode(*_a, **_k):
        raise AssertionError("Localizar promoção não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/promocoes-localizar",
        data={"slug": "228d165932574cab"},
    )
    assert resp.status_code == 200
    assert "Promoção ativa localizada" in resp.text
    assert "110471" in resp.text
    assert "Intervalo mínimo aplicado" in resp.text


# ---------------------------------------------------------------------------
# Promoções GET — paginação dinâmica (continua enquanto houver lotes)
# ---------------------------------------------------------------------------


def _fake_promocoes_tres_lotes(chamadas, *, com_429=False):
    """3 lotes: cada um dos dois primeiros informa extras=1/limitou=1; o 3º
    (sem headers de continuação) traz o slug d55f7ed60b424563 e encerra."""
    estado = {"quatro_zero_dois_ja_429": False}

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/promocoes"
        assert "pagina" not in (params or {})
        cursor = (params or {}).get("alterado_apos")
        chamadas.append(cursor)
        if cursor is None:
            # Lote 1: ainda há mais (extras=1, limitou=1).
            return (
                [
                    {
                        "id": 110471,
                        "slug": "228d165932574cab",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-20 16:41:42",
                    },
                    {
                        "id": 110472,
                        "slug": "4301603538cd4803",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-21 09:57:35",
                    },
                ],
                {
                    "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                    "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "6",
                    "MEUSPEDIDOS_REQUISICOES_EXTRAS": "1",
                },
            )
        if cursor == "2026-07-21 09:57:35":
            if com_429 and not estado["quatro_zero_dois_ja_429"]:
                estado["quatro_zero_dois_ja_429"] = True
                from services.mercos_api_client import MercosApiError

                raise MercosApiError("429", status_code=429, retry_after=2.0)
            # Lote 2: continua indicando mais lotes (extras=1, limitou=1).
            return (
                [
                    {
                        "id": 110473,
                        "slug": "55c218df0edd4bef",
                        "excluido": True,
                        "ultima_alteracao": "2026-07-21 10:02:04",
                    },
                    {
                        "id": 110474,
                        "slug": "55c218df0edd4bef",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-21 10:05:00",
                    },
                ],
                {
                    "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                    "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "4",
                    "MEUSPEDIDOS_REQUISICOES_EXTRAS": "1",
                },
            )
        if cursor == "2026-07-21 10:05:00":
            # Lote 3 (último): sem headers de continuação → encerra aqui.
            return (
                [
                    {
                        "id": 110480,
                        "slug": "d55f7ed60b424563",
                        "excluido": False,
                        "ultima_alteracao": "2026-07-21 10:30:00",
                    }
                ],
                {"MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "1"},
            )
        return ([], {})

    return fake_get


def test_promocoes_paginacao_dinamica_tres_lotes_traz_slug(monkeypatch):
    """Reproduz o bug: 3 lotes; extras=1 nos dois primeiros; o slug alvo vem no
    3º. A paginação dinâmica consulta os três e não fixa em 2 chamadas."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_FIM,
        _reset_resume_clientes_para_testes,
        listar_promocoes_paginado_seguro,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    chamadas: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_promocoes_tres_lotes(chamadas),
    )
    out = listar_promocoes_paginado_seguro(max_paginas=20, timeout_total=60)
    # Os TRÊS lotes foram consultados e o cursor avançou corretamente.
    assert chamadas == [None, "2026-07-21 09:57:35", "2026-07-21 10:05:00"]
    assert out["requisicoes_executadas"] == 3
    assert out["motivo_parada"] == MOTIVO_PARADA_FIM
    assert out["total"] == 5
    slugs = [i.get("slug") for i in out["itens"]]
    assert "d55f7ed60b424563" in slugs
    ids = [i.get("id") for i in out["itens"]]
    assert 110480 in ids


def test_promocoes_paginacao_dinamica_protege_cursor_parado(monkeypatch):
    """Servidor indica mais lotes (extras=1) mas o cursor não avança: erro
    amigável, sem loop infinito."""
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import (
        _reset_resume_clientes_para_testes,
        listar_promocoes_paginado_seguro,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    chamadas: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        chamadas.append((params or {}).get("alterado_apos"))
        assert len(chamadas) <= 5, "cursor parado deveria interromper sem loop"
        # Sempre a MESMA ultima_alteracao e sempre indicando mais lotes.
        return (
            [
                {
                    "id": 110471,
                    "slug": "228d165932574cab",
                    "excluido": False,
                    "ultima_alteracao": "2026-07-20 16:41:42",
                }
            ],
            {
                "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                "MEUSPEDIDOS_REQUISICOES_EXTRAS": "1",
            },
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    with pytest.raises(MercosApiError) as exc:
        listar_promocoes_paginado_seguro(max_paginas=20, timeout_total=60)
    assert "cursor" in str(exc.value).lower()


def test_promocoes_paginacao_dinamica_429_repete_mesmo_lote(monkeypatch):
    """429 no 2º lote: repete o MESMO lote (mesmo cursor), não avança e não
    conta como lote válido; ao final os 3 lotes são obtidos."""
    from services.mercos_homolog_service import (
        _RateLimiterMercos,
        _reset_resume_clientes_para_testes,
        listar_promocoes_paginado_seguro,
    )

    _reset_resume_clientes_para_testes()
    clk = _RelogioFake()
    limiter = _RateLimiterMercos(5.0, relogio=clk.agora, dormir=clk.dormir)

    def nao_dormir_local(_s):
        raise AssertionError("Deve usar o rate limiter, não time.sleep local")

    monkeypatch.setattr("services.mercos_homolog_service.time.sleep", nao_dormir_local)
    chamadas: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_promocoes_tres_lotes(chamadas, com_429=True),
    )
    out = listar_promocoes_paginado_seguro(
        rate_limiter=limiter, max_paginas=20, timeout_total=60
    )
    # O cursor do 2º lote aparece duas vezes (429 + repetição do MESMO lote).
    assert chamadas.count("2026-07-21 09:57:35") == 2
    # A ordem preserva: lote1, lote2(429), lote2(ok), lote3.
    assert chamadas == [
        None,
        "2026-07-21 09:57:35",
        "2026-07-21 09:57:35",
        "2026-07-21 10:05:00",
    ]
    # Só os lotes válidos contam (3), o 429 não conta.
    assert out["requisicoes_executadas"] == 3
    assert out["total"] == 5
    assert out["throttling_respeitado"] is True
    slugs = [i.get("slug") for i in out["itens"]]
    assert "d55f7ed60b424563" in slugs


def test_promocoes_paginacao_dinamica_localiza_ativo_no_catalogo_final(client, monkeypatch):
    """Fluxo UI completo: após a busca completa (3 lotes), localizar o slug alvo
    retorna a promoção ATIVA no catálogo final."""
    catg = _prep_promocoes(client, monkeypatch)
    chamadas: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_promocoes_tres_lotes(chamadas),
    )
    client.post("/mercos/homologacao-ui/acoes/promocoes-reiniciar")
    sessao = client.cookies.get("mercos_promocoes_sessao")
    r1 = client.post("/mercos/homologacao-ui/acoes/promocoes-sincronizar")
    assert r1.status_code == 200
    # Os três lotes foram consultados e o catálogo substituído com os 5 itens.
    assert len(chamadas) == 3
    assert catg.total(sessao) == 5

    def explode(*_a, **_k):
        raise AssertionError("Localizar promoção não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    # Slug d55f... (recém-criado) agora está no catálogo final.
    resp = client.post(
        "/mercos/homologacao-ui/acoes/promocoes-localizar",
        data={"slug": "d55f7ed60b424563"},
    )
    assert resp.status_code == 200
    assert "Promoção ativa localizada" in resp.text
    assert "110480" in resp.text

    # Slug com dois registros (55c218...): prioriza o ATIVO (110474), não o
    # excluído (110473).
    resp2 = client.post(
        "/mercos/homologacao-ui/acoes/promocoes-localizar",
        data={"slug": "55c218df0edd4bef"},
    )
    assert resp2.status_code == 200
    assert "Promoção ativa localizada" in resp2.text
    card_ativo = resp2.text.split("Promoção ativa localizada")[1].split("</ul>")[0]
    assert "110474" in card_ativo
    assert "110473" not in card_ativo


# ---------------------------------------------------------------------------
# Condição de Pagamento GET — ciclo de homologação em 3 etapas
# ---------------------------------------------------------------------------


def _prep_condicoes(client, monkeypatch):
    from services import mercos_condicoes_pagamento_catalogo as catc
    from services.mercos_homolog_service import _reset_resume_clientes_para_testes

    catc._reset_todos_para_testes()
    _reset_resume_clientes_para_testes()
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    return catc


def test_ui_secao_condicoes_ciclo_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    secao = html.split('id="sec-condicoes"')[1].split("</section>")[0]
    assert 'id="btn-condicoes-reiniciar"' in secao
    assert 'id="btn-condicoes-sincronizar"' in secao
    assert 'id="input-condicoes-nome"' in secao
    assert 'id="btn-condicoes-localizar"' in secao
    assert "Reiniciar ciclo de sincronização" in secao
    assert "Localizar condição pelo nome" in secao
    # Busca simples antiga marcada para bloqueio durante o ciclo
    assert "condicoes-busca-manual" in secao


def test_condicoes_reiniciar_nao_chama_mercos(client, monkeypatch):
    catc = _prep_condicoes(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    monkeypatch.setattr("services.mercos_homolog_service.get_json", called)
    resp = client.post("/mercos/homologacao-ui/acoes/condicoes-reiniciar")
    assert resp.status_code == 200
    assert "Ciclo de sincronização reiniciado" in resp.text
    assert "0/3" in resp.text
    assert 'data-ciclo-ativo="1"' in resp.text
    called.assert_not_called()
    sessao = client.cookies.get("mercos_condicoes_pagamento_sessao")
    assert catc.total(sessao) == 0
    assert catc.obter_ciclo(sessao)["etapa_interna"] == 0


def _fake_condicoes_sandbox(cursores_vistos):
    """Contrato real do diagnóstico 2026-07-19: lote de 2, keyset alterado_apos
    estritamente maior, MEUSPEDIDOS_REQUISICOES_EXTRAS informa lotes restantes
    (total 5 → extras 2 → 3 chamadas na completa)."""

    lotes = {
        None: (
            [
                {"id": 264893, "nome": "Pix", "valor_minimo": 50.0, "disponivel_b2b": True, "excluido": True, "ultima_alteracao": "2026-07-06 15:01:35"},
                {"id": 264886, "nome": "Pix parcelado em até 9 vezes", "valor_minimo": 1000.0, "disponivel_b2b": True, "excluido": True, "ultima_alteracao": "2026-07-06 15:01:39"},
            ],
            "2",
        ),
        "2026-07-06 15:01:39": (
            [
                {"id": 265144, "nome": "232fb9e7ac644f4f", "valor_minimo": None, "disponivel_b2b": True, "excluido": False, "ultima_alteracao": "2026-07-19 17:12:43"},
                {"id": 265145, "nome": "72c550394aa04cf4", "valor_minimo": None, "disponivel_b2b": True, "excluido": False, "ultima_alteracao": "2026-07-19 17:12:48"},
            ],
            "1",
        ),
        "2026-07-19 17:12:48": (
            [
                {"id": 265150, "nome": "30 dias", "valor_minimo": 200.0, "disponivel_b2b": False, "excluido": False, "ultima_alteracao": "2026-07-19 17:20:00"},
            ],
            "0",
        ),
        "2026-07-19 17:20:00": (
            [
                {"id": 265151, "nome": "60 dias", "valor_minimo": 300.0, "disponivel_b2b": True, "excluido": False, "ultima_alteracao": "2026-07-19 18:00:00"},
            ],
            "0",
        ),
        "2026-07-19 18:00:00": ([], "0"),
    }

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/condicoes_pagamento"
        params = params or {}
        assert "pagina" not in params
        cursor = params.get("alterado_apos")
        cursores_vistos.append(cursor)
        itens, extras = lotes[cursor]
        headers = {
            "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
            "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "5",
            "MEUSPEDIDOS_REQUISICOES_EXTRAS": extras,
        }
        return (itens, headers)

    return fake_get


def test_condicoes_ciclo_3_etapas_completa_todos_lotes(client, monkeypatch):
    """Etapa 1 percorre TODOS os lotes (1 + extras) e o registro 232fb9e7…
    aparece na completa; etapas 2 e 3 incrementais com cursor exato."""
    catc = _prep_condicoes(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_condicoes_sandbox(cursores),
    )
    client.post("/mercos/homologacao-ui/acoes/condicoes-reiniciar")
    sessao = client.cookies.get("mercos_condicoes_pagamento_sessao")

    # Etapa 1 — busca completa: extras=2 → exatamente 3 chamadas, todos os lotes
    r1 = client.post("/mercos/homologacao-ui/acoes/condicoes-sincronizar")
    assert r1.status_code == 200
    assert cursores == [None, "2026-07-06 15:01:39", "2026-07-19 17:12:48"]
    assert "1/3" in r1.text
    assert 'data-tipo-busca="completa"' in r1.text
    # O registro solicitado pela Mercos veio na completa
    assert "232fb9e7ac644f4f" in r1.text
    # Registros excluídos preservados com a flag
    assert catc.total(sessao) == 5
    estado = catc.obter(sessao)
    assert "265144" in estado["condicoes"]
    assert estado["condicoes"]["264893"]["excluido"] is True
    assert catc.obter_ciclo(sessao)["chamadas_completas"] == 1
    assert 'data-requisicoes-executadas="3"' in r1.text

    # Etapa 2 — incremental com alterado_apos = cursor EXATO da etapa 1
    r2 = client.post("/mercos/homologacao-ui/acoes/condicoes-sincronizar")
    assert r2.status_code == 200
    assert cursores[3] == "2026-07-19 17:20:00"
    assert "2/3" in r2.text
    assert 'data-tipo-busca="incremental"' in r2.text
    assert 'data-cursor-base="2026-07-19 17:20:00"' in r2.text
    assert 'data-alterado-apos-enviado="2026-07-19 17:20:00"' in r2.text
    # Sem overlap de 1s (cursor exato confirmado no diagnóstico)
    assert "2026-07-19 17:19:59" not in r2.text
    # Catálogo acumulado: mantém anteriores e adiciona o novo
    assert catc.total(sessao) == 6
    estado = catc.obter(sessao)
    assert "264893" in estado["condicoes"]
    assert "265151" in estado["condicoes"]

    # Etapa 3 — incremental com o cursor EXATO produzido pela etapa 2
    r3 = client.post("/mercos/homologacao-ui/acoes/condicoes-sincronizar")
    assert r3.status_code == 200
    assert cursores[4] == "2026-07-19 18:00:00"
    assert 'data-cursor-base="2026-07-19 18:00:00"' in r3.text
    assert 'data-alterado-apos-enviado="2026-07-19 18:00:00"' in r3.text
    assert "3/3" in r3.text
    ciclo = catc.obter_ciclo(sessao)
    assert ciclo["chamadas_completas"] == 1
    assert ciclo["chamadas_incrementais"] == 2
    assert ciclo["etapa_interna"] == 3
    assert catc.total(sessao) == 6
    # Cartão operacional sem JSON cru nem token
    assert "Requisições previstas" in r3.text
    assert "Requisições executadas" in r3.text
    assert "CompanyToken" not in r3.text


def test_condicoes_extras_headers_limita_chamadas(monkeypatch):
    """extras=2 → exatamente 3 chamadas; sem 4ª esperando lote vazio."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_EXTRAS,
        listar_condicoes_pagamento_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    chamadas: list[str | None] = []

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/condicoes_pagamento"
        chamadas.append((params or {}).get("alterado_apos"))
        assert len(chamadas) <= 3, "não pode existir 4ª chamada"
        if len(chamadas) == 1:
            return (
                [
                    {"id": 1, "nome": "Pix", "ultima_alteracao": "2026-07-06 15:01:35"},
                    {"id": 2, "nome": "Pix parcelado", "ultima_alteracao": "2026-07-06 15:01:39"},
                ],
                {
                    "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
                    "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "5",
                    "MEUSPEDIDOS_REQUISICOES_EXTRAS": "2",
                },
            )
        if len(chamadas) == 2:
            return (
                [
                    {"id": 3, "nome": "232fb9e7ac644f4f", "ultima_alteracao": "2026-07-19 17:12:43"},
                    {"id": 4, "nome": "72c550394aa04cf4", "ultima_alteracao": "2026-07-19 17:12:48"},
                ],
                {},
            )
        return (
            [
                {"id": 5, "nome": "30 dias", "ultima_alteracao": "2026-07-19 17:20:00"},
            ],
            {},
        )

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", fake_get
    )
    out = listar_condicoes_pagamento_paginado_seguro(max_paginas=20, timeout_total=60)
    assert len(chamadas) == 3
    assert chamadas[0] is None
    assert chamadas[1] == "2026-07-06 15:01:39"
    assert chamadas[2] == "2026-07-19 17:12:48"
    assert out["total"] == 5
    assert out["requisicoes_extras"] == 2
    assert out["requisicoes_previstas"] == 3
    assert out["requisicoes_executadas"] == 3
    assert out["motivo_parada"] == MOTIVO_PARADA_EXTRAS
    nomes = [i.get("nome") for i in out["itens"]]
    assert "232fb9e7ac644f4f" in nomes


def test_condicoes_localizar_nao_faz_requisicao_http(client, monkeypatch):
    """Localizar usa só o catálogo local (nome completo ou prefixo); cursor intacto."""
    catc = _prep_condicoes(client, monkeypatch)

    def explode(*_a, **_k):
        raise AssertionError("Localizar condição não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", explode)
    monkeypatch.setattr("services.mercos_api_client.request_mercos", explode)

    client.post("/mercos/homologacao-ui/acoes/condicoes-reiniciar")
    sessao = client.cookies.get("mercos_condicoes_pagamento_sessao")
    catc.upsert_incremental(
        sessao,
        [
            {
                "id": 265144,
                "nome": "232fb9e7ac644f4f",
                "valor_minimo": 150.0,
                "disponivel_b2b": True,
                "excluido": False,
                "ultima_alteracao": "2026-07-19 17:12:43",
            }
        ],
    )
    etapa_antes = catc.obter_ciclo(sessao)["etapa_interna"]

    # Por prefixo (como a Mercos pede: nome começa com 232fb9e7)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-localizar",
        data={"nome": "232fb9e7"},
    )
    assert resp.status_code == 200
    assert "Condição de pagamento localizada" in resp.text
    assert "232fb9e7ac644f4f" in resp.text
    assert "Valor mínimo" in resp.text
    assert "150.00" in resp.text
    assert "Disponível B2B" in resp.text
    assert "Excluído" in resp.text
    # Não altera cursor nem etapa
    assert resp.cookies.get("mercos_condicoes_pagamento_cursor") is None
    assert 'data-cursor-fixo="1"' in resp.text
    assert catc.obter_ciclo(sessao)["etapa_interna"] == etapa_antes

    # Por nome completo
    resp2 = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-localizar",
        data={"nome": "232fb9e7ac644f4f"},
    )
    assert "Condição de pagamento localizada" in resp2.text


def test_condicoes_busca_simples_bloqueada_durante_ciclo(client, monkeypatch):
    _prep_condicoes(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    monkeypatch.setattr("services.mercos_homolog_service.get_json", called)
    client.post("/mercos/homologacao-ui/acoes/condicoes-reiniciar")

    resp = client.post("/mercos/homologacao-ui/acoes/condicoes")
    assert resp.status_code == 200
    assert "Busca manual bloqueada durante a homologação" in resp.text
    called.assert_not_called()


def test_condicoes_429_retorna_retry_after_e_libera_lock(client, monkeypatch):
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import _SYNC_CONDICOES_PAGAMENTO_LOCK

    _prep_condicoes(client, monkeypatch)

    def sempre_429(path, *, params=None, **_kw):
        raise MercosApiError("429", status_code=429, retry_after=12.0)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", sempre_429
    )
    client.post("/mercos/homologacao-ui/acoes/condicoes-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/condicoes-sincronizar")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "12"
    assert "Aguardando limite da Mercos" in resp.text
    # Lock liberado no finally: nova aquisição funciona
    assert _SYNC_CONDICOES_PAGAMENTO_LOCK.acquire(blocking=False) is True
    _SYNC_CONDICOES_PAGAMENTO_LOCK.release()


def test_condicoes_incremental_envia_cursor_exato(monkeypatch):
    """alterado_apos = cursor base byte a byte, sem overlap de 1s."""
    from services.mercos_homolog_service import sincronizar_condicoes_pagamento

    capt: dict = {}

    def fake_listar(alterado_apos=None, **_kw):
        capt["alterado_apos"] = alterado_apos
        return {"itens": [], "paginas_lidas": 1}

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_condicoes_pagamento_paginado_seguro",
        fake_listar,
    )
    out = sincronizar_condicoes_pagamento("2026-07-19 17:20:00")
    assert capt["alterado_apos"] == "2026-07-19 17:20:00"
    assert out["cursor_base"] == "2026-07-19 17:20:00"
    assert out["alterado_apos_enviado"] == "2026-07-19 17:20:00"
    assert out["tipo"] == "incremental"


def test_condicoes_sincronizar_bloqueia_concorrencia(client, monkeypatch):
    from services.mercos_homolog_service import _SYNC_CONDICOES_PAGAMENTO_LOCK

    _prep_condicoes(client, monkeypatch)
    assert _SYNC_CONDICOES_PAGAMENTO_LOCK.acquire(blocking=False) is True
    try:
        client.post("/mercos/homologacao-ui/acoes/condicoes-reiniciar")
        resp = client.post("/mercos/homologacao-ui/acoes/condicoes-sincronizar")
        assert resp.status_code == 409
        assert "já em andamento" in resp.text
    finally:
        _SYNC_CONDICOES_PAGAMENTO_LOCK.release()


def test_demais_homologacoes_intactas_apos_condicoes(client, monkeypatch):
    """Formas de Pagamento e demais ciclos continuam registrados e funcionais."""
    _prep_condicoes(client, monkeypatch)
    client.post("/mercos/homologacao-ui/acoes/condicoes-reiniciar")
    for rota in (
        "/mercos/homologacao-ui/acoes/produtos-reiniciar",
        "/mercos/homologacao-ui/acoes/clientes-reiniciar",
        "/mercos/homologacao-ui/acoes/usuarios-reiniciar",
        "/mercos/homologacao-ui/acoes/pedidos-reiniciar",
        "/mercos/homologacao-ui/acoes/tipos-pedido-reiniciar",
        "/mercos/homologacao-ui/acoes/pagamentos-reiniciar",
    ):
        resp = client.post(rota)
        assert resp.status_code == 200, rota
        assert "Ciclo de sincronização reiniciado" in resp.text
    # Formas de Pagamento (entidade distinta) continua com rota registrada
    resp_fp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-criar", data={"nome": ""}
    )
    assert resp_fp.status_code == 200
    assert "Campos obrigatórios" in resp_fp.text


# ---------------------------------------------------------------------------
# Categoria de Produto GET — ciclo de 3 etapas (busca completa + 2 incrementais)
# ---------------------------------------------------------------------------


def _prep_categorias(client, monkeypatch):
    from services import mercos_categorias_catalogo as catc
    from services.mercos_homolog_service import _reset_resume_clientes_para_testes

    catc._reset_todos_para_testes()
    _reset_resume_clientes_para_testes()
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    return catc


def test_ui_secao_categorias_ciclo_presente(client):
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    secao = html.split('id="sec-categorias"')[1].split("</section>")[0]
    assert "Categoria de produto — Buscar" in secao
    assert 'id="btn-categorias-reiniciar"' in secao
    assert 'id="btn-categorias-sincronizar"' in secao
    assert 'id="input-categorias-nome"' in secao
    assert 'id="btn-categorias-localizar"' in secao
    assert "Reiniciar ciclo de sincronização" in secao
    assert "Sincronizar próxima etapa" in secao
    assert "Localizar categoria pelo nome" in secao
    assert "categorias-busca-manual" in secao
    assert "mercos_categorias_cursor" in html
    assert "mercos_categorias_catalogo" in html


def test_categorias_botoes_rotas_registradas_sem_404(client, monkeypatch):
    """Botões do ciclo e busca simples apontam para rotas FastAPI existentes."""
    import re

    _prep_categorias(client, monkeypatch)
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    secao = html.split('id="sec-categorias"')[1].split("</section>")[0]
    assert 'data-action="/mercos/homologacao-ui/acoes/categorias"' in secao
    assert "/mercos/homologacao-ui/acoes/categorias-reiniciar" in html
    assert "/mercos/homologacao-ui/acoes/categorias-sincronizar" in html
    assert "/mercos/homologacao-ui/acoes/categorias-localizar" in html

    from fastapi.testclient import TestClient
    from main import app

    anonimo = TestClient(app)
    for url in (
        "/mercos/homologacao-ui/acoes/categorias",
        "/mercos/homologacao-ui/acoes/categorias-reiniciar",
        "/mercos/homologacao-ui/acoes/categorias-sincronizar",
        "/mercos/homologacao-ui/acoes/categorias-localizar",
    ):
        resp = anonimo.post(url)
        assert resp.status_code != 404, f"rota inexistente: {url}"

    # data-action da busca simples também cobre o contrato geral
    m = re.search(r'data-action="([^"]*acoes/categorias)"', secao)
    assert m and m.group(1) == "/mercos/homologacao-ui/acoes/categorias"


def test_categorias_reiniciar_nao_chama_mercos(client, monkeypatch):
    catc = _prep_categorias(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    monkeypatch.setattr("services.mercos_homolog_service.get_json", called)
    resp = client.post("/mercos/homologacao-ui/acoes/categorias-reiniciar")
    assert resp.status_code == 200
    assert "Ciclo de sincronização reiniciado" in resp.text
    assert "0/3" in resp.text
    assert 'data-ciclo-ativo="1"' in resp.text
    called.assert_not_called()
    sessao = client.cookies.get("mercos_categorias_sessao")
    assert catc.total(sessao) == 0
    assert catc.obter_ciclo(sessao)["etapa_interna"] == 0


def _fake_categorias_sandbox(cursores_vistos):
    """Contrato real do diagnóstico 2026-07-20: GET /v1/categorias, lote de 2,
    keyset alterado_apos estritamente maior, total 9 → extras 4 → 5 chamadas
    na completa. Sem pagina/offset."""

    lotes = {
        None: (
            [
                {
                    "id": 1001,
                    "nome": "Geral",
                    "excluido": True,
                    "ultima_alteracao": "2026-01-01 10:00:01",
                    "representada_id": 1,
                },
                {
                    "id": 1002,
                    "nome": "Acessórios",
                    "excluido": False,
                    "ultima_alteracao": "2026-01-01 10:00:02",
                    "representada_id": 1,
                },
            ],
            "4",
        ),
        "2026-01-01 10:00:02": (
            [
                {
                    "id": 1003,
                    "nome": "49d2ecfa-categoria-homolog",
                    "categoria_pai_id": 1001,
                    "excluido": False,
                    "ultima_alteracao": "2026-01-02 10:00:03",
                    "representada_id": 1,
                },
                {
                    "id": 1004,
                    "nome": "Outra",
                    "excluido": False,
                    "ultima_alteracao": "2026-01-02 10:00:04",
                    "representada_id": 1,
                },
            ],
            "3",
        ),
        "2026-01-02 10:00:04": (
            [
                {
                    "id": 1005,
                    "nome": "Lote3a",
                    "excluido": False,
                    "ultima_alteracao": "2026-01-03 10:00:05",
                },
                {
                    "id": 1006,
                    "nome": "Lote3b",
                    "excluido": False,
                    "ultima_alteracao": "2026-01-03 10:00:06",
                },
            ],
            "2",
        ),
        "2026-01-03 10:00:06": (
            [
                {
                    "id": 1007,
                    "nome": "Lote4a",
                    "excluido": False,
                    "ultima_alteracao": "2026-01-04 10:00:07",
                },
                {
                    "id": 1008,
                    "nome": "Lote4b",
                    "excluido": False,
                    "ultima_alteracao": "2026-01-04 10:00:08",
                },
            ],
            "1",
        ),
        "2026-01-04 10:00:08": (
            [
                {
                    "id": 1009,
                    "nome": "Lote5",
                    "excluido": False,
                    "ultima_alteracao": "2026-01-05 10:00:09",
                },
            ],
            "0",
        ),
        "2026-01-05 10:00:09": (
            [
                {
                    "id": 1010,
                    "nome": "Incremental etapa2",
                    "excluido": False,
                    "ultima_alteracao": "2026-01-06 11:00:00",
                },
            ],
            "0",
        ),
        "2026-01-06 11:00:00": ([], "0"),
    }

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/categorias"
        params = params or {}
        assert "pagina" not in params
        assert "offset" not in params
        cursor = params.get("alterado_apos")
        cursores_vistos.append(cursor)
        itens, extras = lotes[cursor]
        headers = {
            "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
            "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "9",
            "MEUSPEDIDOS_REQUISICOES_EXTRAS": extras,
        }
        return (itens, headers)

    return fake_get


def test_categorias_ciclo_3_etapas_completa_todos_lotes(client, monkeypatch):
    """Etapa 1 percorre TODOS os lotes (1 + extras); 49d2ecfa aparece;
    etapas 2 e 3 usam alterado_apos exato; catálogo acumulado; excluídos ok."""
    catc = _prep_categorias(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_categorias_sandbox(cursores),
    )
    client.post("/mercos/homologacao-ui/acoes/categorias-reiniciar")
    sessao = client.cookies.get("mercos_categorias_sessao")

    # Etapa 1 — completa: extras=4 → exatamente 5 chamadas
    r1 = client.post("/mercos/homologacao-ui/acoes/categorias-sincronizar")
    assert r1.status_code == 200
    assert cursores == [
        None,
        "2026-01-01 10:00:02",
        "2026-01-02 10:00:04",
        "2026-01-03 10:00:06",
        "2026-01-04 10:00:08",
    ]
    assert "1/3" in r1.text
    assert 'data-tipo-busca="completa"' in r1.text
    assert "49d2ecfa-categoria-homolog" in r1.text
    assert catc.total(sessao) == 9
    estado = catc.obter(sessao)
    assert "1003" in estado["categorias"]
    assert estado["categorias"]["1001"]["excluido"] is True
    assert catc.obter_ciclo(sessao)["chamadas_completas"] == 1
    assert 'data-requisicoes-executadas="5"' in r1.text
    assert 'data-requisicoes-previstas="5"' in r1.text

    # Etapa 2 — incremental com cursor EXATO
    r2 = client.post("/mercos/homologacao-ui/acoes/categorias-sincronizar")
    assert r2.status_code == 200
    assert cursores[5] == "2026-01-05 10:00:09"
    assert "2/3" in r2.text
    assert 'data-tipo-busca="incremental"' in r2.text
    assert 'data-cursor-base="2026-01-05 10:00:09"' in r2.text
    assert 'data-alterado-apos-enviado="2026-01-05 10:00:09"' in r2.text
    assert "2026-01-05 10:00:08" not in r2.text
    assert catc.total(sessao) == 10
    estado = catc.obter(sessao)
    assert "1001" in estado["categorias"]
    assert "1010" in estado["categorias"]
    assert estado["categorias"]["1001"]["excluido"] is True

    # Etapa 3 — incremental com cursor da etapa 2
    r3 = client.post("/mercos/homologacao-ui/acoes/categorias-sincronizar")
    assert r3.status_code == 200
    assert cursores[6] == "2026-01-06 11:00:00"
    assert 'data-cursor-base="2026-01-06 11:00:00"' in r3.text
    assert 'data-alterado-apos-enviado="2026-01-06 11:00:00"' in r3.text
    assert "3/3" in r3.text
    ciclo = catc.obter_ciclo(sessao)
    assert ciclo["chamadas_completas"] == 1
    assert ciclo["chamadas_incrementais"] == 2
    assert ciclo["etapa_interna"] == 3
    assert catc.total(sessao) == 10
    assert "Requisições previstas" in r3.text
    assert "Requisições executadas" in r3.text
    assert "CompanyToken" not in r3.text
    assert '"itens"' not in r3.text


def test_categorias_extras_headers_limita_chamadas(monkeypatch):
    """extras=4 → exatamente 5 chamadas; sem 6ª esperando lote vazio."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_EXTRAS,
        listar_categorias_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    chamadas: list[str | None] = []
    cursores: list[str | None] = []
    fake = _fake_categorias_sandbox(cursores)

    def counting_get(path, *, params=None, **kw):
        chamadas.append((params or {}).get("alterado_apos"))
        assert len(chamadas) <= 5, "não pode existir 6ª chamada"
        return fake(path, params=params, **kw)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", counting_get
    )
    out = listar_categorias_paginado_seguro(max_paginas=20, timeout_total=60)
    assert len(chamadas) == 5
    assert chamadas[0] is None
    assert out["total"] == 9
    assert out["requisicoes_extras"] == 4
    assert out["requisicoes_previstas"] == 5
    assert out["requisicoes_executadas"] == 5
    assert out["motivo_parada"] == MOTIVO_PARADA_EXTRAS
    nomes = [i.get("nome") for i in out["itens"]]
    assert any(str(n).startswith("49d2ecfa") for n in nomes)


def test_categorias_localizar_nao_faz_requisicao_http(client, monkeypatch):
    """Localizar usa só o catálogo local; não altera cursor nem etapa."""
    catc = _prep_categorias(client, monkeypatch)

    def explode(*_a, **_k):
        raise AssertionError("Localizar categoria não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", explode)
    monkeypatch.setattr("services.mercos_api_client.request_mercos", explode)

    client.post("/mercos/homologacao-ui/acoes/categorias-reiniciar")
    sessao = client.cookies.get("mercos_categorias_sessao")
    catc.upsert_incremental(
        sessao,
        [
            {
                "id": 1003,
                "nome": "49d2ecfa-categoria-homolog",
                "categoria_pai_id": 1001,
                "excluido": False,
                "ultima_alteracao": "2026-01-02 10:00:03",
            }
        ],
    )
    etapa_antes = catc.obter_ciclo(sessao)["etapa_interna"]

    resp = client.post(
        "/mercos/homologacao-ui/acoes/categorias-localizar",
        data={"nome": "49d2ecfa"},
    )
    assert resp.status_code == 200
    assert "Categoria de produto localizada" in resp.text
    assert "49d2ecfa-categoria-homolog" in resp.text
    assert "Categoria pai" in resp.text
    assert "1001" in resp.text
    assert "Excluído" in resp.text
    assert "Última alteração" in resp.text
    assert resp.cookies.get("mercos_categorias_cursor") is None
    assert 'data-cursor-fixo="1"' in resp.text
    assert catc.obter_ciclo(sessao)["etapa_interna"] == etapa_antes

    resp2 = client.post(
        "/mercos/homologacao-ui/acoes/categorias-localizar",
        data={"nome": "49d2ecfa-categoria-homolog"},
    )
    assert "Categoria de produto localizada" in resp2.text


def test_categorias_busca_simples_bloqueada_durante_ciclo(client, monkeypatch):
    _prep_categorias(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    monkeypatch.setattr("services.mercos_homolog_service.get_json", called)
    client.post("/mercos/homologacao-ui/acoes/categorias-reiniciar")

    resp = client.post("/mercos/homologacao-ui/acoes/categorias")
    assert resp.status_code == 200
    assert "Busca manual bloqueada durante a homologação" in resp.text
    called.assert_not_called()


def test_categorias_429_retorna_retry_after_e_libera_lock(client, monkeypatch):
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import _SYNC_CATEGORIAS_LOCK

    _prep_categorias(client, monkeypatch)

    def sempre_429(path, *, params=None, **_kw):
        raise MercosApiError("429", status_code=429, retry_after=12.0)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", sempre_429
    )
    client.post("/mercos/homologacao-ui/acoes/categorias-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/categorias-sincronizar")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "12"
    assert "Aguardando limite da Mercos" in resp.text
    assert _SYNC_CATEGORIAS_LOCK.acquire(blocking=False) is True
    _SYNC_CATEGORIAS_LOCK.release()


def test_categorias_incremental_envia_cursor_exato(monkeypatch):
    from services.mercos_homolog_service import sincronizar_categorias

    capt: dict = {}

    def fake_listar(alterado_apos=None, **_kw):
        capt["alterado_apos"] = alterado_apos
        return {"itens": [], "paginas_lidas": 1}

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_categorias_paginado_seguro",
        fake_listar,
    )
    out = sincronizar_categorias("2026-01-05 10:00:09")
    assert capt["alterado_apos"] == "2026-01-05 10:00:09"
    assert out["cursor_base"] == "2026-01-05 10:00:09"
    assert out["alterado_apos_enviado"] == "2026-01-05 10:00:09"
    assert out["tipo"] == "incremental"


def test_categorias_sincronizar_bloqueia_concorrencia(client, monkeypatch):
    from services.mercos_homolog_service import _SYNC_CATEGORIAS_LOCK

    _prep_categorias(client, monkeypatch)
    assert _SYNC_CATEGORIAS_LOCK.acquire(blocking=False) is True
    try:
        client.post("/mercos/homologacao-ui/acoes/categorias-reiniciar")
        resp = client.post("/mercos/homologacao-ui/acoes/categorias-sincronizar")
        assert resp.status_code == 409
        assert "já em andamento" in resp.text
    finally:
        _SYNC_CATEGORIAS_LOCK.release()


def test_produto_get_e_demais_intactos_apos_categorias(client, monkeypatch):
    """Produto GET e demais homologações permanecem intactos."""
    _prep_categorias(client, monkeypatch)
    client.post("/mercos/homologacao-ui/acoes/categorias-reiniciar")
    for rota in (
        "/mercos/homologacao-ui/acoes/produtos-reiniciar",
        "/mercos/homologacao-ui/acoes/clientes-reiniciar",
        "/mercos/homologacao-ui/acoes/usuarios-reiniciar",
        "/mercos/homologacao-ui/acoes/pedidos-reiniciar",
        "/mercos/homologacao-ui/acoes/tipos-pedido-reiniciar",
        "/mercos/homologacao-ui/acoes/pagamentos-reiniciar",
        "/mercos/homologacao-ui/acoes/condicoes-reiniciar",
    ):
        resp = client.post(rota)
        assert resp.status_code == 200, rota
        assert "Ciclo de sincronização reiniciado" in resp.text

    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-produtos"' in html
    assert "Produto" in html
    assert 'id="btn-produtos-sincronizar"' in html
    assert 'id="sec-categorias"' in html
    assert "Categoria de produto — Buscar" in html


# ---------------------------------------------------------------------------
# Categoria de Produto POST — incluir
# ---------------------------------------------------------------------------


def test_ui_secao_categoria_produto_incluir_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-categorias-criar"' in html
    assert "Categoria de produto — Incluir" in html
    assert 'value="a608c2993e3042bb"' in html
    assert "Incluir categoria" in html
    # Ciclo GET preservado
    assert 'id="btn-categorias-sincronizar"' in html
    assert 'id="sec-categorias"' in html
    # Produto permanece distinto
    assert 'id="sec-produtos"' in html
    assert 'id="sec-produtos-criar"' in html


def test_botao_categorias_criar_usa_url_registrada(client, monkeypatch):
    """A URL do botão renderizado na UI e a rota FastAPI são exatamente iguais."""
    import re

    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    m = re.search(r'data-action="([^"]*categorias-criar[^"]*)"', html)
    assert m, "botão de categoria sem data-action na UI"
    url = m.group(1)
    assert url == "/mercos/homologacao-ui/acoes/categorias-criar"

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 50100, "dados": {}},
    )
    resp = client.post(
        url,
        data={
            "nome": "a608c2993e3042bb",
            "categoria_pai_id": "",
            "ativo": "sim",
        },
    )
    assert resp.status_code != 404
    assert resp.status_code == 200
    assert "Status 201" in resp.text
    assert "50100" in resp.text


def test_categorias_post_payload_e_endpoint_corretos(client, monkeypatch):
    """Um único POST em /v1/categorias com nome exato; sem ID no corpo; sem cliente."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        return {"ok": True, "status_code": 201, "id": 50101, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/categorias-criar",
        data={
            "nome": "a608c2993e3042bb",
            "categoria_pai_id": "",
            "ativo": "sim",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/categorias"
    assert path != "/v1/produtos"
    assert path != "/v1/clientes_categorias"
    assert "id" not in body
    assert "cliente_id" not in body
    assert "categorias_liberadas" not in body
    assert body["nome"] == "a608c2993e3042bb"
    assert body["excluido"] is False
    assert "categoria_pai_id" not in body

    html = resp.text
    assert "201" in html
    assert "50101" in html
    assert "a608c2993e3042bb" in html
    assert "Categoria de produto criada" in html
    assert "Mercos Sandbox" in html
    assert '"nome"' not in html
    assert "segredo-ui-homolog" not in html
    assert "CompanyToken" not in html


def test_categorias_post_somente_um_post_por_clique(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[str] = []

    def fake_post_json(path, body):
        chamadas.append(path)
        return {"ok": True, "status_code": 201, "id": 1, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    client.post(
        "/mercos/homologacao-ui/acoes/categorias-criar",
        data={"nome": "a608c2993e3042bb", "ativo": "sim"},
    )
    assert chamadas == ["/v1/categorias"]


def test_categorias_post_captura_id_do_header(monkeypatch):
    """post_json captura MeusPedidosID; criar_categoria propaga o ID."""
    from services.mercos_homolog_service import criar_categoria

    def fake_post_json(path, body):
        assert path == "/v1/categorias"
        return {"ok": True, "status_code": 201, "id": "50999", "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    out = criar_categoria({"nome": "a608c2993e3042bb", "excluido": False})
    assert out["id"] == "50999"
    assert out["status_code"] == 201


def test_categorias_post_erro_412_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError("Dados inválidos", status_code=412)

    monkeypatch.setattr("services.mercos_homolog_service.post_json", boom)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/categorias-criar",
        data={"nome": "a608c2993e3042bb", "ativo": "sim"},
    )
    assert resp.status_code == 200
    assert "Falha na operação" in resp.text
    assert "412" in resp.text
    assert '{"mensagem"' not in resp.text
    assert "CompanyToken" not in resp.text


def test_categorias_post_sem_nome_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/categorias-criar",
        data={"nome": "   ", "ativo": "sim"},
    )
    assert resp.status_code == 200
    assert "Campos obrigatórios" in resp.text
    post.assert_not_called()


def test_categorias_get_continua_apos_post(client, monkeypatch):
    """Ciclo GET de categorias permanece funcional após o POST."""
    catc = _prep_categorias(client, monkeypatch)
    called_get = MagicMock(
        return_value=(
            [
                {
                    "id": 1,
                    "nome": "Geral",
                    "excluido": True,
                    "ultima_alteracao": "2026-01-01 10:00:01",
                }
            ],
            {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "0"},
        )
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called_get
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 9, "dados": {}},
    )
    client.post(
        "/mercos/homologacao-ui/acoes/categorias-criar",
        data={"nome": "a608c2993e3042bb", "ativo": "sim"},
    )
    client.post("/mercos/homologacao-ui/acoes/categorias-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/categorias-sincronizar")
    assert resp.status_code == 200
    assert "1/3" in resp.text
    assert called_get.called
    sessao = client.cookies.get("mercos_categorias_sessao")
    assert catc.obter_ciclo(sessao)["chamadas_completas"] == 1


def test_produto_get_post_put_intactos_apos_categoria_post(client, monkeypatch):
    """Produto GET/POST/PUT permanecem intactos após POST de categoria."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-produtos"' in html
    assert 'id="btn-produtos-sincronizar"' in html
    assert 'id="sec-produtos-criar"' in html
    assert 'data-action="/mercos/homologacao-ui/acoes/produtos-criar"' in html
    assert 'id="sec-produtos-alterar"' in html or "produtos-alterar" in html

    resp = client.post("/mercos/homologacao-ui/acoes/produtos-reiniciar")
    assert resp.status_code == 200
    assert "Ciclo de sincronização reiniciado" in resp.text


# ---------------------------------------------------------------------------
# Condição de Pagamento POST — incluir (etapa 1/1)
# ---------------------------------------------------------------------------


def test_ui_secao_condicao_pagamento_incluir_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-condicoes-criar"' in html
    assert "Condição de pagamento — Incluir" in html
    assert 'value="29135d66c2ec4f49"' in html
    assert "Incluir condição de pagamento" in html
    # Ciclo GET preservado
    assert 'id="btn-condicoes-sincronizar"' in html
    # Formas de Pagamento intacta e distinta
    assert 'id="sec-formas-pagamento-criar"' in html


def test_botao_condicoes_criar_usa_url_registrada(client, monkeypatch):
    """A URL do botão renderizado na UI e a rota FastAPI são exatamente iguais."""
    import re

    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    m = re.search(r'data-action="([^"]*condicoes-criar[^"]*)"', html)
    assert m, "botão de condição de pagamento sem data-action na UI"
    url = m.group(1)
    assert url == "/mercos/homologacao-ui/acoes/condicoes-criar"

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 265200, "dados": {}},
    )
    resp = client.post(
        url,
        data={
            "nome": "29135d66c2ec4f49",
            "disponivel_b2b": "sim",
            "ativo": "sim",
        },
    )
    assert resp.status_code != 404
    assert resp.status_code == 200
    assert "Status 201" in resp.text
    assert "265200" in resp.text


def test_condicoes_post_payload_e_endpoint_corretos(client, monkeypatch):
    """Um único POST em /v1/condicoes_pagamento com nome exato; sem ID no corpo."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        return {"ok": True, "status_code": 201, "id": 265201, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-criar",
        data={
            "nome": "29135d66c2ec4f49",
            "valor_minimo": "",
            "disponivel_b2b": "sim",
            "considerar_limite_credito": "",
            "ativo": "sim",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/condicoes_pagamento"
    assert path != "/v1/formas_pagamento"
    assert "id" not in body
    assert body["nome"] == "29135d66c2ec4f49"
    assert body["excluido"] is False
    assert body["disponivel_b2b"] is True
    assert "valor_minimo" not in body
    assert "considerar_limite_credito" not in body

    html = resp.text
    assert "201" in html
    assert "265201" in html
    assert "29135d66c2ec4f49" in html
    assert "Condição de pagamento criada" in html
    assert "Mercos Sandbox" in html
    assert '"nome"' not in html
    assert "segredo-ui-homolog" not in html
    assert "CompanyToken" not in html


def test_condicoes_post_somente_um_post_por_clique(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[str] = []

    def fake_post_json(path, body):
        chamadas.append(path)
        return {"ok": True, "status_code": 201, "id": 1, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    client.post(
        "/mercos/homologacao-ui/acoes/condicoes-criar",
        data={"nome": "29135d66c2ec4f49", "ativo": "sim", "disponivel_b2b": "sim"},
    )
    assert chamadas == ["/v1/condicoes_pagamento"]


def test_condicoes_post_captura_id_do_header(monkeypatch):
    """post_json captura MeusPedidosID; criar_condicao_pagamento propaga o ID."""
    from services.mercos_homolog_service import criar_condicao_pagamento

    def fake_post_json(path, body):
        assert path == "/v1/condicoes_pagamento"
        return {"ok": True, "status_code": 201, "id": "265999", "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    out = criar_condicao_pagamento({"nome": "29135d66c2ec4f49", "excluido": False})
    assert out["id"] == "265999"
    assert out["status_code"] == 201


def test_condicoes_post_erro_412_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError("Dados inválidos", status_code=412)

    monkeypatch.setattr("services.mercos_homolog_service.post_json", boom)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-criar",
        data={"nome": "29135d66c2ec4f49", "ativo": "sim"},
    )
    assert resp.status_code == 200
    assert "Falha na operação" in resp.text
    assert "412" in resp.text
    assert '{"mensagem"' not in resp.text
    assert "CompanyToken" not in resp.text


def test_condicoes_post_sem_nome_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-criar",
        data={"nome": "   ", "ativo": "sim"},
    )
    assert resp.status_code == 200
    assert "Campos obrigatórios" in resp.text
    post.assert_not_called()


def test_condicoes_get_continua_apos_post(client, monkeypatch):
    """Ciclo GET de condições permanece funcional após o POST."""
    catc = _prep_condicoes(client, monkeypatch)
    called_get = MagicMock(
        return_value=(
            [{"id": 1, "nome": "Pix", "excluido": True, "ultima_alteracao": "2026-07-06 15:01:35"}],
            {"MEUSPEDIDOS_REQUISICOES_EXTRAS": "0"},
        )
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called_get
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 10, "dados": {}},
    )
    # POST não quebra reinício/sincronização do GET
    r_post = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-criar",
        data={"nome": "29135d66c2ec4f49", "ativo": "sim", "disponivel_b2b": "sim"},
    )
    assert r_post.status_code == 200
    r_reini = client.post("/mercos/homologacao-ui/acoes/condicoes-reiniciar")
    assert r_reini.status_code == 200
    assert "0/3" in r_reini.text
    r_sync = client.post("/mercos/homologacao-ui/acoes/condicoes-sincronizar")
    assert r_sync.status_code == 200
    assert called_get.called
    sessao = client.cookies.get("mercos_condicoes_pagamento_sessao")
    assert catc.obter_ciclo(sessao)["etapa_interna"] == 1


def test_formas_pagamento_intactas_apos_condicoes_post(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        return {"ok": True, "status_code": 201, "id": 90250, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-criar",
        data={"nome": "cca8fdd8c4a24557", "ativo": "sim"},
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    assert chamadas[0][0] == "/v1/formas_pagamento"
    assert chamadas[0][1] == {"nome": "cca8fdd8c4a24557", "excluido": False}


# ---------------------------------------------------------------------------
# Condição de Pagamento PUT — alterar / exclusão lógica (etapas 2/3 e 3/3)
# ---------------------------------------------------------------------------


def test_ui_secao_condicao_pagamento_alterar_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    secao = html.split('id="sec-condicoes-alterar"')[1].split("</section>")[0]
    assert "Condição de pagamento — Alterar" in secao
    assert 'value="265148"' in secao
    assert 'value="c7a9fdd429ca4080"' in secao
    assert 'value="265149"' not in secao
    assert "Excluir logicamente" in secao
    assert "Alterar condição de pagamento" in secao
    # GET e POST preservados
    assert 'id="btn-condicoes-sincronizar"' in html
    assert 'id="sec-condicoes-criar"' in html


def test_botao_condicoes_alterar_usa_url_registrada(client, monkeypatch):
    import re

    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    m = re.search(r'data-action="([^"]*condicoes-alterar[^"]*)"', html)
    assert m, "botão de alterar condição sem data-action na UI"
    url = m.group(1)
    assert url == "/mercos/homologacao-ui/acoes/condicoes-alterar"

    monkeypatch.setattr(
        "services.mercos_homolog_service.put_json",
        lambda path, body: {"ok": True, "status_code": 201, "dados": {}},
    )
    resp = client.post(
        url,
        data={
            "condicao_id": "265148",
            "nome": "c7a9fdd429ca4080",
            "disponivel_b2b": "sim",
            "ativo": "sim",
        },
    )
    assert resp.status_code != 404
    assert resp.status_code == 200
    assert "Status 201" in resp.text
    assert "265148" in resp.text


def test_condicoes_put_endpoint_id_na_url_e_payload(client, monkeypatch):
    """Um único PUT em /v1/condicoes_pagamento/{id}; id fora do corpo."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_put_json(path, body):
        chamadas.append((path, dict(body)))
        return {"ok": True, "status_code": 201, "dados": {}}

    monkeypatch.setattr("services.mercos_homolog_service.put_json", fake_put_json)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-alterar",
        data={
            "condicao_id": "265148",
            "nome": "c7a9fdd429ca4080",
            "valor_minimo": "",
            "disponivel_b2b": "sim",
            "considerar_limite_credito": "",
            "ativo": "sim",
            "excluido": "",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/condicoes_pagamento/265148"
    assert path != "/v1/formas_pagamento/265148"
    assert "id" not in body
    assert body["nome"] == "c7a9fdd429ca4080"
    assert body["excluido"] is False
    assert body["disponivel_b2b"] is True
    assert "valor_minimo" not in body
    assert "considerar_limite_credito" not in body

    html = resp.text
    assert "Status 201" in html
    assert "265148" in html
    assert "c7a9fdd429ca4080" in html
    assert "Disponível B2B" in html
    assert "Ativo" in html and "Sim" in html
    assert "Excluído" in html and "Não" in html
    assert "Mercos Sandbox" in html
    assert '"nome"' not in html
    assert "segredo-ui-homolog" not in html
    assert "265149" not in html


def test_condicoes_put_exclusao_logica(client, monkeypatch):
    """Excluir logicamente: excluido=true com nome obrigatório, sem DELETE."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.put_json",
        lambda path, body: chamadas.append((path, dict(body)))
        or {"ok": True, "status_code": 201, "dados": {}},
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-alterar",
        data={
            "condicao_id": "265148",
            "nome": "c7a9fdd429ca4080",
            "disponivel_b2b": "sim",
            "excluido": "true",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/condicoes_pagamento/265148"
    assert body["nome"] == "c7a9fdd429ca4080"
    assert body["excluido"] is True
    assert "Excluído" in resp.text and "Sim" in resp.text


def test_condicoes_put_excluido_prevalece_sobre_ativo(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.put_json",
        lambda path, body: chamadas.append((path, dict(body)))
        or {"ok": True, "status_code": 201, "dados": {}},
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-alterar",
        data={
            "condicao_id": "265148",
            "nome": "c7a9fdd429ca4080",
            "ativo": "sim",
            "excluido": "true",
        },
    )
    assert resp.status_code == 200
    assert chamadas[0][1]["excluido"] is True


def test_condicoes_put_sem_id_ou_nome_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    put = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.put_json", put)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-alterar",
        data={"condicao_id": "", "nome": "c7a9fdd429ca4080"},
    )
    assert resp.status_code == 200
    assert "Campos obrigatórios" in resp.text
    put.assert_not_called()

    resp2 = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-alterar",
        data={"condicao_id": "265148", "nome": "  "},
    )
    assert "Campos obrigatórios" in resp2.text
    put.assert_not_called()


def test_condicoes_put_erro_412_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError("Dados inválidos", status_code=412)

    monkeypatch.setattr("services.mercos_homolog_service.put_json", boom)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-alterar",
        data={
            "condicao_id": "265148",
            "nome": "c7a9fdd429ca4080",
            "ativo": "sim",
        },
    )
    assert resp.status_code == 200
    assert "Falha na operação" in resp.text
    assert "412" in resp.text
    assert '{"mensagem"' not in resp.text


def test_condicoes_get_e_post_intactos_apos_put(client, monkeypatch):
    """GET (ciclo) e POST continuam funcionando após o PUT."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    monkeypatch.setattr(
        "services.mercos_homolog_service.put_json",
        lambda path, body: {"ok": True, "status_code": 201, "dados": {}},
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 99, "dados": {}},
    )
    r_put = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-alterar",
        data={
            "condicao_id": "265148",
            "nome": "c7a9fdd429ca4080",
            "disponivel_b2b": "sim",
            "ativo": "sim",
        },
    )
    assert r_put.status_code == 200

    r_post = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-criar",
        data={"nome": "29135d66c2ec4f49", "ativo": "sim", "disponivel_b2b": "sim"},
    )
    assert r_post.status_code == 200
    assert "Condição de pagamento criada" in r_post.text

    r_reini = client.post("/mercos/homologacao-ui/acoes/condicoes-reiniciar")
    assert r_reini.status_code == 200
    assert "0/3" in r_reini.text


def test_formas_pagamento_intactas_apos_condicoes_put(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.put_json",
        lambda path, body: chamadas.append((path, dict(body)))
        or {"ok": True, "status_code": 200, "dados": {}},
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/formas-pagamento-alterar",
        data={"forma_id": "90000", "nome": "ad4feae8a8b643d0", "ativo": "sim"},
    )
    assert resp.status_code == 200
    assert chamadas[0][0] == "/v1/formas_pagamento/90000"


# ---------------------------------------------------------------------------
# Tabela de Preço POST — incluir (homologação etapa 2/3)
# ---------------------------------------------------------------------------


def test_ui_secao_tabela_preco_incluir_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-tabelas-criar"' in html
    assert "Tabela de preço — Incluir" in html
    assert 'value="153271fca35044de"' in html
    assert 'value="P"' in html or 'option value="P" selected' in html
    assert "Incluir tabela de preço" in html
    # GET e Pedido preservados
    assert 'id="sec-tabelas"' in html
    assert 'id="sec-pedidos-criar"' in html
    assert 'id="sec-pedidos-buscar"' in html


def test_botao_tabelas_preco_criar_usa_url_registrada(client, monkeypatch):
    import re

    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    m = re.search(r'data-action="([^"]*tabelas-preco-criar[^"]*)"', html)
    assert m, "botão de tabela de preço sem data-action na UI"
    url = m.group(1)
    assert url == "/mercos/homologacao-ui/acoes/tabelas-preco-criar"

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 501001, "dados": {}},
    )
    resp = client.post(
        url,
        data={"tipo": "P", "nome": "153271fca35044de", "ativo": "sim"},
    )
    assert resp.status_code != 404
    assert resp.status_code == 200
    assert "Status 201" in resp.text
    assert "501001" in resp.text


def test_tabelas_preco_post_payload_e_endpoint_corretos(client, monkeypatch):
    """Um único POST em /v1/tabelas_preco com tipo P e nome exato; sem ID no corpo."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        return {"ok": True, "status_code": 201, "id": 501002, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/tabelas-preco-criar",
        data={
            "tipo": "P",
            "nome": "153271fca35044de",
            "acrescimo": "",
            "desconto": "",
            "ativo": "sim",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/tabelas_preco"
    assert path != "/v2/pedidos"
    assert "id" not in body
    assert body == {
        "nome": "153271fca35044de",
        "tipo": "P",
        "excluido": False,
    }

    html = resp.text
    assert "201" in html
    assert "501002" in html
    assert "153271fca35044de" in html
    assert "Tabela de preço criada" in html
    assert "Mercos Sandbox" in html
    assert '"nome"' not in html
    assert "segredo-ui-homolog" not in html
    assert "CompanyToken" not in html
    # Não vincula cliente nesta etapa
    assert "9290655" not in html


def test_tabelas_preco_post_somente_um_post_por_clique(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[str] = []

    def fake_post_json(path, body):
        chamadas.append(path)
        return {"ok": True, "status_code": 201, "id": 1, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    client.post(
        "/mercos/homologacao-ui/acoes/tabelas-preco-criar",
        data={"tipo": "P", "nome": "153271fca35044de", "ativo": "sim"},
    )
    assert chamadas == ["/v1/tabelas_preco"]


def test_tabelas_preco_post_captura_id_do_header(monkeypatch):
    from services.mercos_homolog_service import criar_tabela_preco

    def fake_post_json(path, body):
        assert path == "/v1/tabelas_preco"
        return {"ok": True, "status_code": 201, "id": "501999", "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    out = criar_tabela_preco(
        {"nome": "153271fca35044de", "tipo": "P", "excluido": False}
    )
    assert out["id"] == "501999"
    assert out["status_code"] == 201


def test_tabelas_preco_post_erro_412_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    def boom(path, body):
        raise MercosApiError("Dados inválidos", status_code=412)

    monkeypatch.setattr("services.mercos_homolog_service.post_json", boom)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/tabelas-preco-criar",
        data={"tipo": "P", "nome": "153271fca35044de", "ativo": "sim"},
    )
    assert resp.status_code == 200
    assert "Falha na operação" in resp.text
    assert "412" in resp.text
    assert '{"mensagem"' not in resp.text
    assert "CompanyToken" not in resp.text


def test_tabelas_preco_post_campos_obrigatorios_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)

    resp = client.post(
        "/mercos/homologacao-ui/acoes/tabelas-preco-criar",
        data={"tipo": "P", "nome": "   ", "ativo": "sim"},
    )
    assert resp.status_code == 200
    assert "Campos obrigatórios" in resp.text
    post.assert_not_called()

    resp2 = client.post(
        "/mercos/homologacao-ui/acoes/tabelas-preco-criar",
        data={"tipo": "", "nome": "153271fca35044de", "ativo": "sim"},
    )
    assert "Campos obrigatórios" in resp2.text
    post.assert_not_called()


def test_tabelas_preco_get_preservado_apos_post(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    listar = MagicMock(
        return_value={
            "itens": [{"id": 1, "nome": "Tabela X", "excluido": False}],
            "total": 1,
        }
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_tabelas_preco", listar
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 10, "dados": {}},
    )
    r_post = client.post(
        "/mercos/homologacao-ui/acoes/tabelas-preco-criar",
        data={"tipo": "P", "nome": "153271fca35044de", "ativo": "sim"},
    )
    assert r_post.status_code == 200
    r_get = client.post("/mercos/homologacao-ui/acoes/tabelas-preco")
    assert r_get.status_code == 200
    assert listar.called
    assert "Tabela X" in r_get.text


# ---------------------------------------------------------------------------
# Tabela de Preço GET — ciclo de homologação (3 etapas)
# ---------------------------------------------------------------------------


def _prep_tabelas_preco(client, monkeypatch):
    from services import mercos_tabelas_preco_catalogo as tpc
    from services.mercos_homolog_service import _reset_resume_clientes_para_testes

    tpc._reset_todos_para_testes()
    _reset_resume_clientes_para_testes()
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    return tpc


def test_ui_secao_tabelas_preco_ciclo_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    resp = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = resp.text
    secao = html.split('id="sec-tabelas"')[1].split("</section>")[0]
    assert "Tabela de preço — Buscar" in secao
    assert 'id="btn-tabelas-preco-reiniciar"' in secao
    assert 'id="btn-tabelas-preco-sincronizar"' in secao
    assert 'id="input-tabelas-preco-nome"' in secao
    assert 'id="btn-tabelas-preco-localizar"' in secao
    assert "Reiniciar ciclo de sincronização" in secao
    assert "Sincronizar próxima etapa" in secao
    assert "Localizar tabela pelo nome" in secao
    assert "tabelas-preco-busca-manual" in secao
    assert "mercos_tabelas_preco_cursor" in html
    assert "mercos_tabelas_preco_catalogo" in html


def test_tabelas_preco_botoes_rotas_registradas_sem_404(client, monkeypatch):
    """Botões do ciclo e busca simples apontam para rotas FastAPI existentes."""
    import re

    _prep_tabelas_preco(client, monkeypatch)
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    secao = html.split('id="sec-tabelas"')[1].split("</section>")[0]
    assert 'data-action="/mercos/homologacao-ui/acoes/tabelas-preco"' in secao
    assert "/mercos/homologacao-ui/acoes/tabelas-preco-reiniciar" in html
    assert "/mercos/homologacao-ui/acoes/tabelas-preco-sincronizar" in html
    assert "/mercos/homologacao-ui/acoes/tabelas-preco-localizar" in html

    from fastapi.testclient import TestClient
    from main import app

    anonimo = TestClient(app)
    for url in (
        "/mercos/homologacao-ui/acoes/tabelas-preco",
        "/mercos/homologacao-ui/acoes/tabelas-preco-reiniciar",
        "/mercos/homologacao-ui/acoes/tabelas-preco-sincronizar",
        "/mercos/homologacao-ui/acoes/tabelas-preco-localizar",
    ):
        resp = anonimo.post(url)
        assert resp.status_code != 404, f"rota inexistente: {url}"

    m = re.search(r'data-action="([^"]*acoes/tabelas-preco)"', secao)
    assert m and m.group(1) == "/mercos/homologacao-ui/acoes/tabelas-preco"


def test_tabelas_preco_reiniciar_nao_chama_mercos(client, monkeypatch):
    tpc = _prep_tabelas_preco(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    monkeypatch.setattr("services.mercos_homolog_service.get_json", called)
    resp = client.post("/mercos/homologacao-ui/acoes/tabelas-preco-reiniciar")
    assert resp.status_code == 200
    assert "Ciclo de sincronização reiniciado" in resp.text
    assert "0/3" in resp.text
    assert 'data-ciclo-ativo="1"' in resp.text
    called.assert_not_called()
    sessao = client.cookies.get("mercos_tabelas_preco_sessao")
    assert tpc.total(sessao) == 0
    assert tpc.obter_ciclo(sessao)["etapa_interna"] == 0


def _fake_tabelas_preco_sandbox(cursores_vistos):
    """Contrato real do diagnóstico 2026-07-20: GET /v1/tabelas_preco, lote de 2,
    keyset alterado_apos estritamente maior, total 4 → extras 1 → 2 chamadas
    na completa. Sem pagina/offset."""

    lotes = {
        None: (
            [
                {
                    "id": 3001,
                    "nome": "Geral",
                    "tipo": "P",
                    "excluido": True,
                    "ultima_alteracao": "2026-02-01 10:00:01",
                },
                {
                    "id": 3002,
                    "nome": "6e04f9d0bfef4d5f",
                    "tipo": "A",
                    "acrescimo": 5.0,
                    "excluido": False,
                    "ultima_alteracao": "2026-02-01 10:00:02",
                },
            ],
            "1",
        ),
        "2026-02-01 10:00:02": (
            [
                {
                    "id": 3003,
                    "nome": "Desconto X",
                    "tipo": "D",
                    "desconto": 10.0,
                    "excluido": False,
                    "ultima_alteracao": "2026-02-02 10:00:03",
                },
                {
                    "id": 3004,
                    "nome": "Outra",
                    "tipo": "P",
                    "excluido": False,
                    "ultima_alteracao": "2026-02-02 10:00:04",
                },
            ],
            "0",
        ),
        "2026-02-02 10:00:04": (
            [
                {
                    "id": 3005,
                    "nome": "Incremental etapa2",
                    "tipo": "P",
                    "excluido": False,
                    "ultima_alteracao": "2026-02-03 11:00:00",
                },
            ],
            "0",
        ),
        "2026-02-03 11:00:00": ([], "0"),
    }

    def fake_get(path, *, params=None, **_kw):
        assert path == "/v1/tabelas_preco"
        params = params or {}
        assert "pagina" not in params
        assert "offset" not in params
        cursor = params.get("alterado_apos")
        cursores_vistos.append(cursor)
        itens, extras = lotes[cursor]
        headers = {
            "MEUSPEDIDOS_LIMITOU_REGISTROS": "1",
            "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS": "4",
            "MEUSPEDIDOS_REQUISICOES_EXTRAS": extras,
        }
        return (itens, headers)

    return fake_get


def test_tabelas_preco_ciclo_3_etapas_completa_todos_lotes(client, monkeypatch):
    """Etapa 1 percorre TODOS os lotes (1 + extras); 6e04f9d0 aparece;
    etapas 2 e 3 usam alterado_apos exato; catálogo acumulado; excluídos ok."""
    tpc = _prep_tabelas_preco(client, monkeypatch)
    cursores: list[str | None] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers",
        _fake_tabelas_preco_sandbox(cursores),
    )
    client.post("/mercos/homologacao-ui/acoes/tabelas-preco-reiniciar")
    sessao = client.cookies.get("mercos_tabelas_preco_sessao")

    r1 = client.post("/mercos/homologacao-ui/acoes/tabelas-preco-sincronizar")
    assert r1.status_code == 200
    assert cursores == [None, "2026-02-01 10:00:02"]
    assert "1/3" in r1.text
    assert 'data-tipo-busca="completa"' in r1.text
    assert "6e04f9d0bfef4d5f" in r1.text
    assert tpc.total(sessao) == 4
    estado = tpc.obter(sessao)
    assert "3002" in estado["tabelas"]
    assert estado["tabelas"]["3001"]["excluido"] is True
    assert tpc.obter_ciclo(sessao)["chamadas_completas"] == 1
    assert 'data-requisicoes-executadas="2"' in r1.text
    assert 'data-requisicoes-previstas="2"' in r1.text

    r2 = client.post("/mercos/homologacao-ui/acoes/tabelas-preco-sincronizar")
    assert r2.status_code == 200
    assert cursores[2] == "2026-02-02 10:00:04"
    assert "2/3" in r2.text
    assert 'data-tipo-busca="incremental"' in r2.text
    assert 'data-cursor-base="2026-02-02 10:00:04"' in r2.text
    assert 'data-alterado-apos-enviado="2026-02-02 10:00:04"' in r2.text
    assert 'data-alterado-apos-enviado="2026-02-02 10:00:03"' not in r2.text
    assert tpc.total(sessao) == 5
    estado = tpc.obter(sessao)
    assert "3001" in estado["tabelas"]
    assert "3005" in estado["tabelas"]
    assert estado["tabelas"]["3001"]["excluido"] is True

    r3 = client.post("/mercos/homologacao-ui/acoes/tabelas-preco-sincronizar")
    assert r3.status_code == 200
    assert cursores[3] == "2026-02-03 11:00:00"
    assert 'data-cursor-base="2026-02-03 11:00:00"' in r3.text
    assert 'data-alterado-apos-enviado="2026-02-03 11:00:00"' in r3.text
    assert "3/3" in r3.text
    ciclo = tpc.obter_ciclo(sessao)
    assert ciclo["chamadas_completas"] == 1
    assert ciclo["chamadas_incrementais"] == 2
    assert ciclo["etapa_interna"] == 3
    assert tpc.total(sessao) == 5
    assert "Requisições previstas" in r3.text
    assert "Requisições executadas" in r3.text
    assert "CompanyToken" not in r3.text
    assert '"itens"' not in r3.text


def test_tabelas_preco_extras_headers_limita_chamadas(monkeypatch):
    """extras=1 → exatamente 2 chamadas; sem 3ª esperando lote vazio."""
    from services.mercos_homolog_service import (
        MOTIVO_PARADA_EXTRAS,
        listar_tabelas_preco_paginado_seguro,
        _reset_resume_clientes_para_testes,
    )

    _reset_resume_clientes_para_testes()
    monkeypatch.setattr(
        "services.mercos_homolog_service.time.sleep", lambda *_a, **_k: None
    )
    chamadas: list[str | None] = []
    cursores: list[str | None] = []
    fake = _fake_tabelas_preco_sandbox(cursores)

    def counting_get(path, *, params=None, **kw):
        chamadas.append((params or {}).get("alterado_apos"))
        assert len(chamadas) <= 2, "não pode existir 3ª chamada"
        return fake(path, params=params, **kw)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", counting_get
    )
    out = listar_tabelas_preco_paginado_seguro(max_paginas=20, timeout_total=60)
    assert len(chamadas) == 2
    assert chamadas[0] is None
    assert out["total"] == 4
    assert out["requisicoes_extras"] == 1
    assert out["requisicoes_previstas"] == 2
    assert out["requisicoes_executadas"] == 2
    assert out["motivo_parada"] == MOTIVO_PARADA_EXTRAS
    nomes = [i.get("nome") for i in out["itens"]]
    assert any(str(n).startswith("6e04f9d0") for n in nomes)


def test_tabelas_preco_localizar_nao_faz_requisicao_http(client, monkeypatch):
    """Localizar usa só o catálogo local; não altera cursor nem etapa."""
    tpc = _prep_tabelas_preco(client, monkeypatch)

    def explode(*_a, **_k):
        raise AssertionError("Localizar tabela não pode chamar a API Mercos")

    monkeypatch.setattr("services.mercos_homolog_service.get_json_com_headers", explode)
    monkeypatch.setattr("services.mercos_homolog_service.get_json", explode)
    monkeypatch.setattr("services.mercos_api_client.request_mercos", explode)

    client.post("/mercos/homologacao-ui/acoes/tabelas-preco-reiniciar")
    sessao = client.cookies.get("mercos_tabelas_preco_sessao")
    tpc.upsert_incremental(
        sessao,
        [
            {
                "id": 3002,
                "nome": "6e04f9d0bfef4d5f",
                "tipo": "A",
                "acrescimo": 5.0,
                "excluido": False,
                "ultima_alteracao": "2026-02-01 10:00:02",
            }
        ],
    )
    etapa_antes = tpc.obter_ciclo(sessao)["etapa_interna"]

    resp = client.post(
        "/mercos/homologacao-ui/acoes/tabelas-preco-localizar",
        data={"nome": "6e04f9d0"},
    )
    assert resp.status_code == 200
    assert "Tabela de preço localizada" in resp.text
    assert "6e04f9d0bfef4d5f" in resp.text
    assert "Tipo" in resp.text
    assert "Acréscimo" in resp.text
    assert "Desconto" in resp.text
    assert "Excluído" in resp.text
    assert "Última alteração" in resp.text
    assert resp.cookies.get("mercos_tabelas_preco_cursor") is None
    assert 'data-cursor-fixo="1"' in resp.text
    assert tpc.obter_ciclo(sessao)["etapa_interna"] == etapa_antes

    resp2 = client.post(
        "/mercos/homologacao-ui/acoes/tabelas-preco-localizar",
        data={"nome": "6e04f9d0bfef4d5f"},
    )
    assert "Tabela de preço localizada" in resp2.text


def test_tabelas_preco_busca_simples_bloqueada_durante_ciclo(client, monkeypatch):
    _prep_tabelas_preco(client, monkeypatch)
    called = MagicMock()
    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", called
    )
    monkeypatch.setattr("services.mercos_homolog_service.get_json", called)
    client.post("/mercos/homologacao-ui/acoes/tabelas-preco-reiniciar")

    resp = client.post("/mercos/homologacao-ui/acoes/tabelas-preco")
    assert resp.status_code == 200
    assert "Busca manual bloqueada durante a homologação" in resp.text
    called.assert_not_called()


def test_tabelas_preco_429_retorna_retry_after_e_libera_lock(client, monkeypatch):
    from services.mercos_api_client import MercosApiError
    from services.mercos_homolog_service import _SYNC_TABELAS_PRECO_LOCK

    _prep_tabelas_preco(client, monkeypatch)

    def sempre_429(path, *, params=None, **_kw):
        raise MercosApiError("429", status_code=429, retry_after=12.0)

    monkeypatch.setattr(
        "services.mercos_homolog_service.get_json_com_headers", sempre_429
    )
    client.post("/mercos/homologacao-ui/acoes/tabelas-preco-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/tabelas-preco-sincronizar")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "12"
    assert "Aguardando limite da Mercos" in resp.text
    assert _SYNC_TABELAS_PRECO_LOCK.acquire(blocking=False) is True
    _SYNC_TABELAS_PRECO_LOCK.release()


def test_tabelas_preco_incremental_envia_cursor_exato(monkeypatch):
    from services.mercos_homolog_service import sincronizar_tabelas_preco

    capt: dict = {}

    def fake_listar(alterado_apos=None, **_kw):
        capt["alterado_apos"] = alterado_apos
        return {"itens": [], "paginas_lidas": 1}

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_tabelas_preco_paginado_seguro",
        fake_listar,
    )
    out = sincronizar_tabelas_preco("2026-02-02 10:00:04")
    assert capt["alterado_apos"] == "2026-02-02 10:00:04"
    assert out["cursor_base"] == "2026-02-02 10:00:04"
    assert out["alterado_apos_enviado"] == "2026-02-02 10:00:04"
    assert out["tipo"] == "incremental"


def test_tabelas_preco_sincronizar_bloqueia_concorrencia(client, monkeypatch):
    from services.mercos_homolog_service import _SYNC_TABELAS_PRECO_LOCK

    _prep_tabelas_preco(client, monkeypatch)
    assert _SYNC_TABELAS_PRECO_LOCK.acquire(blocking=False) is True
    try:
        client.post("/mercos/homologacao-ui/acoes/tabelas-preco-reiniciar")
        resp = client.post("/mercos/homologacao-ui/acoes/tabelas-preco-sincronizar")
        assert resp.status_code == 409
        assert "já em andamento" in resp.text
    finally:
        _SYNC_TABELAS_PRECO_LOCK.release()


def test_tabelas_preco_post_e_demais_intactos_apos_ciclo(client, monkeypatch):
    """Tabela POST, liberar tabelas cliente, Produto e Pedido permanecem intactos."""
    _prep_tabelas_preco(client, monkeypatch)
    client.post("/mercos/homologacao-ui/acoes/tabelas-preco-reiniciar")
    for rota in (
        "/mercos/homologacao-ui/acoes/produtos-reiniciar",
        "/mercos/homologacao-ui/acoes/pedidos-reiniciar",
    ):
        resp = client.post(rota)
        assert resp.status_code == 200, rota
        assert "Ciclo de sincronização reiniciado" in resp.text

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 201, "id": 501001, "dados": {}},
    )
    r_post = client.post(
        "/mercos/homologacao-ui/acoes/tabelas-preco-criar",
        data={"tipo": "P", "nome": "153271fca35044de", "ativo": "sim"},
    )
    assert r_post.status_code == 200
    assert "Tabela de preço criada" in r_post.text

    r_lib = client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-tabelas-preco",
        data={
            "cliente_id": "9290655",
            "cnpj": "12441875000108",
            "razao_social": "b675d90e7cc144c0",
        },
    )
    assert r_lib.status_code != 404

    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-tabelas-criar"' in html
    assert 'id="sec-produtos"' in html
    assert 'id="sec-pedidos-buscar"' in html


def test_pedidos_intactos_apos_tabelas_preco_post(client, monkeypatch):
    """Pedido GET/POST/PUT continuam registrados e não usam tabelas_preco."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-pedidos-buscar"' in html
    assert 'id="sec-pedidos-criar"' in html
    assert 'id="sec-pedidos-alterar"' in html

    # Rotas de pedido respondem (não 404); validação local sem chamar Mercos
    r_criar = client.post(
        "/mercos/homologacao-ui/acoes/pedidos-criar", data={"cliente_id": ""}
    )
    assert r_criar.status_code != 404
    assert r_criar.status_code == 200

    r_buscar = client.post("/mercos/homologacao-ui/acoes/pedidos-reiniciar")
    assert r_buscar.status_code == 200
    assert "Ciclo de sincronização reiniciado" in r_buscar.text


# ---------------------------------------------------------------------------
# Liberar todas as tabelas de preço para o cliente — POST (etapa 3/3)
# ---------------------------------------------------------------------------


def test_ui_secao_cliente_liberar_tabelas_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    secao = html.split('id="sec-clientes-liberar-tabelas"')[1].split("</section>")[0]
    assert "Cliente — Liberar todas as tabelas de preço" in secao
    assert 'value="9290655"' in secao
    assert 'value="12441875000108"' in secao
    assert 'value="b675d90e7cc144c0"' in secao
    assert "Liberar todas as tabelas" in secao
    assert 'id="sec-clientes-criar"' in html
    assert 'id="sec-tabelas-criar"' in html


def test_botao_liberar_tabelas_usa_url_registrada(client, monkeypatch):
    import re

    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    m = re.search(
        r'data-action="([^"]*clientes-liberar-tabelas-preco[^"]*)"', html
    )
    assert m, "botão liberar tabelas sem data-action na UI"
    url = m.group(1)
    assert url == "/mercos/homologacao-ui/acoes/clientes-liberar-tabelas-preco"

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 200, "dados": {}},
    )
    resp = client.post(
        url,
        data={
            "cliente_id": "9290655",
            "cnpj": "12441875000108",
            "razao_social": "b675d90e7cc144c0",
        },
    )
    assert resp.status_code != 404
    assert resp.status_code == 200
    assert "Status 200" in resp.text


def test_liberar_tabelas_endpoint_e_payload_corretos(client, monkeypatch):
    """Um único POST em /v1/clientes_tabela_preco/liberar_todas; ID no corpo."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        return {"ok": True, "status_code": 200, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-tabelas-preco",
        data={
            "cliente_id": "9290655",
            "cnpj": "12441875000108",
            "razao_social": "b675d90e7cc144c0",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/clientes_tabela_preco/liberar_todas"
    assert body == {"cliente_id": 9290655}
    # Não cria cliente nem tabela neste clique
    assert path != "/v1/clientes"
    assert path != "/v1/tabelas_preco"
    assert path != "/v2/pedidos"

    html = resp.text
    assert "Status 200" in html
    assert "9290655" in html
    assert "12441875000108" in html
    assert "b675d90e7cc144c0" in html
    assert "Todas liberadas" in html
    assert "Mercos Sandbox" in html
    assert '"cliente_id"' not in html
    assert "segredo-ui-homolog" not in html
    assert "CompanyToken" not in html


def test_liberar_tabelas_somente_uma_chamada(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[str] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: chamadas.append(path)
        or {"ok": True, "status_code": 200, "dados": {}},
    )
    client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-tabelas-preco",
        data={"cliente_id": "9290655"},
    )
    assert chamadas == ["/v1/clientes_tabela_preco/liberar_todas"]


def test_liberar_tabelas_sem_id_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-tabelas-preco",
        data={"cliente_id": "  "},
    )
    assert resp.status_code == 200
    assert "Campos obrigatórios" in resp.text
    post.assert_not_called()


def test_liberar_tabelas_erro_404_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: (_ for _ in ()).throw(
            MercosApiError("Não encontrado", status_code=404)
        ),
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-tabelas-preco",
        data={"cliente_id": "9290655"},
    )
    assert resp.status_code == 200
    assert "Cliente não encontrado" in resp.text
    assert "404" in resp.text
    assert '{"mensagem"' not in resp.text


def test_liberar_tabelas_erro_412_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: (_ for _ in ()).throw(
            MercosApiError("Dados inválidos", status_code=412)
        ),
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-tabelas-preco",
        data={"cliente_id": "9290655"},
    )
    assert resp.status_code == 200
    assert "Dados inválidos" in resp.text
    assert "412" in resp.text
    assert '{"mensagem"' not in resp.text


def test_cliente_post_e_tabela_post_intactos_apos_liberar(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        return {"ok": True, "status_code": 201, "id": 99, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )

    # Liberar
    r_lib = client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-tabelas-preco",
        data={"cliente_id": "9290655"},
    )
    assert r_lib.status_code == 200
    assert chamadas[-1][0] == "/v1/clientes_tabela_preco/liberar_todas"

    # Tabela POST continua
    r_tab = client.post(
        "/mercos/homologacao-ui/acoes/tabelas-preco-criar",
        data={"tipo": "P", "nome": "153271fca35044de", "ativo": "sim"},
    )
    assert r_tab.status_code == 200
    assert chamadas[-1][0] == "/v1/tabelas_preco"

    # Cliente POST continua registrado (validação local)
    r_cli = client.post(
        "/mercos/homologacao-ui/acoes/clientes-criar",
        data={"razao_social": ""},
    )
    assert r_cli.status_code != 404
    assert r_cli.status_code == 200


# ---------------------------------------------------------------------------
# Vincular categoria de produto ao cliente — POST (etapa 3/3)
# ---------------------------------------------------------------------------


def test_ui_secao_cliente_vincular_categoria_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    secao = html.split('id="sec-clientes-vincular-categoria"')[1].split("</section>")[0]
    assert "Cliente — Vincular categoria de produto" in secao
    assert 'value="9290664"' in secao
    assert 'value="a7d9e81fb7c8454d"' in secao
    assert 'value="321414"' in secao
    assert 'value="a608c2993e3042bb"' in secao
    assert "Vincular categoria" in secao
    assert 'id="sec-clientes-criar"' in html
    assert 'id="sec-categorias"' in html
    assert 'id="sec-categorias-criar"' in html


def test_botao_vincular_categoria_usa_url_registrada(client, monkeypatch):
    import re

    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    m = re.search(
        r'data-action="([^"]*clientes-vincular-categoria[^"]*)"', html
    )
    assert m, "botão vincular categoria sem data-action na UI"
    url = m.group(1)
    assert url == "/mercos/homologacao-ui/acoes/clientes-vincular-categoria"

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 200, "dados": {}},
    )
    resp = client.post(
        url,
        data={
            "cliente_id": "9290664",
            "razao_social": "a7d9e81fb7c8454d",
            "categoria_id": "321414",
            "categoria_nome": "a608c2993e3042bb",
        },
    )
    assert resp.status_code != 404
    assert resp.status_code == 200
    assert "Status 200" in resp.text
    assert "Vínculo realizado" in resp.text


def test_vincular_categoria_endpoint_e_payload_corretos(client, monkeypatch):
    """Um único POST em /v1/clientes_categorias; IDs no corpo."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        return {"ok": True, "status_code": 200, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-categoria",
        data={
            "cliente_id": "9290664",
            "razao_social": "a7d9e81fb7c8454d",
            "categoria_id": "321414",
            "categoria_nome": "a608c2993e3042bb",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/clientes_categorias"
    assert body == {
        "cliente_id": 9290664,
        "categorias_liberadas": [321414],
    }
    assert path != "/v1/clientes"
    assert path != "/v1/categorias"
    assert path != "/v1/clientes_categorias/liberar_todas"

    html = resp.text
    assert "Status 200" in html
    assert "9290664" in html
    assert "a7d9e81fb7c8454d" in html
    assert "321414" in html
    assert "a608c2993e3042bb" in html
    assert "Vínculo realizado" in html
    assert "Mercos Sandbox" in html
    assert '"cliente_id"' not in html
    assert "segredo-ui-homolog" not in html
    assert "CompanyToken" not in html


def test_vincular_categoria_somente_uma_chamada(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[str] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: chamadas.append(path)
        or {"ok": True, "status_code": 200, "dados": {}},
    )
    client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-categoria",
        data={
            "cliente_id": "9290664",
            "categoria_id": "321414",
        },
    )
    assert chamadas == ["/v1/clientes_categorias"]


def test_vincular_categoria_sem_ids_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-categoria",
        data={"cliente_id": "", "categoria_id": ""},
    )
    assert resp.status_code == 200
    assert "Campos obrigatórios" in resp.text
    post.assert_not_called()


def test_vincular_categoria_erro_404_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        MagicMock(side_effect=MercosApiError("Não encontrado", status_code=404)),
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-categoria",
        data={"cliente_id": "9290664", "categoria_id": "321414"},
    )
    assert resp.status_code == 200
    assert "404" in resp.text
    assert "não encontrado" in resp.text.lower()
    assert '{"mensagem"' not in resp.text
    assert "CompanyToken" not in resp.text


def test_vincular_categoria_erro_412_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        MagicMock(side_effect=MercosApiError("Dados inválidos", status_code=412)),
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-categoria",
        data={"cliente_id": "9290664", "categoria_id": "321414"},
    )
    assert resp.status_code == 200
    assert "Dados inválidos" in resp.text
    assert "412" in resp.text
    assert '{"mensagem"' not in resp.text


def test_cliente_post_e_categoria_get_post_intactos_apos_vincular(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        code = 200 if path == "/v1/clientes_categorias" else 201
        return {"ok": True, "status_code": code, "id": 99, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )

    r_vinc = client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-categoria",
        data={"cliente_id": "9290664", "categoria_id": "321414"},
    )
    assert r_vinc.status_code == 200
    assert chamadas[-1][0] == "/v1/clientes_categorias"
    assert "Status 200" in r_vinc.text

    r_cat = client.post(
        "/mercos/homologacao-ui/acoes/categorias-criar",
        data={"nome": "a608c2993e3042bb", "ativo": "sim"},
    )
    assert r_cat.status_code == 200
    assert chamadas[-1][0] == "/v1/categorias"

    r_cli = client.post(
        "/mercos/homologacao-ui/acoes/clientes-criar",
        data={"razao_social": ""},
    )
    assert r_cli.status_code != 404
    assert r_cli.status_code == 200

    r_get = client.post("/mercos/homologacao-ui/acoes/categorias-reiniciar")
    assert r_get.status_code == 200
    assert "Ciclo de sincronização reiniciado" in r_get.text


# ---------------------------------------------------------------------------
# Liberar todas as categorias de produto para o cliente — POST
# ---------------------------------------------------------------------------


def test_ui_secao_cliente_liberar_categorias_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    secao = html.split('id="sec-clientes-liberar-categorias"')[1].split("</section>")[0]
    assert "Cliente — Liberar todas as categorias de produto" in secao
    assert 'value="9290668"' in secao
    assert 'value="f6c1d128589642a8"' in secao
    assert 'value="41540880000176"' in secao
    assert "Liberar todas as categorias" in secao
    assert 'id="sec-clientes-criar"' in html
    assert 'id="sec-clientes-vincular-categoria"' in html
    assert 'id="sec-categorias-criar"' in html


def test_botao_liberar_categorias_usa_url_registrada(client, monkeypatch):
    import re

    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    m = re.search(
        r'data-action="([^"]*clientes-liberar-categorias[^"]*)"', html
    )
    assert m, "botão liberar categorias sem data-action na UI"
    url = m.group(1)
    assert url == "/mercos/homologacao-ui/acoes/clientes-liberar-categorias"

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 200, "dados": {}},
    )
    resp = client.post(
        url,
        data={
            "cliente_id": "9290668",
            "cnpj": "41540880000176",
            "razao_social": "f6c1d128589642a8",
        },
    )
    assert resp.status_code != 404
    assert resp.status_code == 200
    assert "Status 200" in resp.text
    assert "Todas as categorias liberadas" in resp.text


def test_liberar_categorias_endpoint_e_payload_corretos(client, monkeypatch):
    """Um único POST em /v1/clientes_categorias/liberar_todas; só cliente_id."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        return {"ok": True, "status_code": 200, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-categorias",
        data={
            "cliente_id": "9290668",
            "cnpj": "41540880000176",
            "razao_social": "f6c1d128589642a8",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/clientes_categorias/liberar_todas"
    assert body == {"cliente_id": 9290668}
    assert "categorias_liberadas" not in body
    assert path != "/v1/clientes"
    assert path != "/v1/categorias"
    assert path != "/v1/clientes_categorias"

    html = resp.text
    assert "Status 200" in html
    assert "9290668" in html
    assert "41540880000176" in html
    assert "f6c1d128589642a8" in html
    assert "Todas as categorias liberadas" in html
    assert "Mercos Sandbox" in html
    assert '"cliente_id"' not in html
    assert "segredo-ui-homolog" not in html
    assert "CompanyToken" not in html


def test_liberar_categorias_somente_uma_chamada(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[str] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: chamadas.append(path)
        or {"ok": True, "status_code": 200, "dados": {}},
    )
    client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-categorias",
        data={"cliente_id": "9290668"},
    )
    assert chamadas == ["/v1/clientes_categorias/liberar_todas"]


def test_liberar_categorias_sem_id_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-categorias",
        data={"cliente_id": ""},
    )
    assert resp.status_code == 200
    assert "Campos obrigatórios" in resp.text
    post.assert_not_called()


def test_liberar_categorias_erro_404_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        MagicMock(side_effect=MercosApiError("Não encontrado", status_code=404)),
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-categorias",
        data={"cliente_id": "9290668"},
    )
    assert resp.status_code == 200
    assert "404" in resp.text
    assert "não foi encontrado" in resp.text.lower() or "não encontrado" in resp.text.lower()
    assert '{"mensagem"' not in resp.text
    assert "CompanyToken" not in resp.text


def test_liberar_categorias_erro_412_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        MagicMock(side_effect=MercosApiError("Dados inválidos", status_code=412)),
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-categorias",
        data={"cliente_id": "9290668"},
    )
    assert resp.status_code == 200
    assert "Dados inválidos" in resp.text
    assert "412" in resp.text
    assert '{"mensagem"' not in resp.text


def test_demais_fluxos_intactos_apos_liberar_categorias(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        code = 200 if "liberar" in path or path.endswith("clientes_categorias") else 201
        return {"ok": True, "status_code": code, "id": 99, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )

    r_lib = client.post(
        "/mercos/homologacao-ui/acoes/clientes-liberar-categorias",
        data={"cliente_id": "9290668"},
    )
    assert r_lib.status_code == 200
    assert chamadas[-1][0] == "/v1/clientes_categorias/liberar_todas"
    assert "categorias_liberadas" not in chamadas[-1][1]

    r_vinc = client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-categoria",
        data={"cliente_id": "9290664", "categoria_id": "321414"},
    )
    assert r_vinc.status_code == 200
    assert chamadas[-1][0] == "/v1/clientes_categorias"

    r_cat = client.post(
        "/mercos/homologacao-ui/acoes/categorias-criar",
        data={"nome": "a608c2993e3042bb", "ativo": "sim"},
    )
    assert r_cat.status_code == 200
    assert chamadas[-1][0] == "/v1/categorias"

    r_cli = client.post(
        "/mercos/homologacao-ui/acoes/clientes-criar",
        data={"razao_social": ""},
    )
    assert r_cli.status_code != 404
    assert r_cli.status_code == 200


# ---------------------------------------------------------------------------
# Vincular condição de pagamento ao cliente — POST (etapa 3/3)
# ---------------------------------------------------------------------------


def test_ui_secao_cliente_vincular_condicao_presente(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    secao = html.split('id="sec-clientes-vincular-condicao"')[1].split("</section>")[0]
    assert "Cliente — Vincular condição de pagamento" in secao
    assert 'value="9290675"' in secao
    assert 'value="fdfa92fa09814f3f"' in secao
    assert 'value="78121331000177"' in secao
    assert 'value="265174"' in secao
    assert 'value="9a221eb10df24148"' in secao
    assert "Vincular condição" in secao
    assert 'id="sec-clientes-criar"' in html
    assert 'id="sec-condicoes"' in html
    assert 'id="sec-condicoes-criar"' in html
    assert 'id="sec-condicoes-alterar"' in html


def test_botao_vincular_condicao_usa_url_registrada(client, monkeypatch):
    import re

    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    m = re.search(
        r'data-action="([^"]*clientes-vincular-condicao[^"]*)"', html
    )
    assert m, "botão vincular condição sem data-action na UI"
    url = m.group(1)
    assert url == "/mercos/homologacao-ui/acoes/clientes-vincular-condicao"

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: {"ok": True, "status_code": 200, "dados": {}},
    )
    resp = client.post(
        url,
        data={
            "cliente_id": "9290675",
            "razao_social": "fdfa92fa09814f3f",
            "cnpj": "78121331000177",
            "condicao_id": "265174",
            "condicao_nome": "9a221eb10df24148",
        },
    )
    assert resp.status_code != 404
    assert resp.status_code == 200
    assert "Status 200" in resp.text
    assert "Vínculo realizado" in resp.text


def test_vincular_condicao_endpoint_e_payload_corretos(client, monkeypatch):
    """Um único POST em /v1/clientes_condicoes_pagamento; IDs no corpo."""
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        return {"ok": True, "status_code": 200, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-condicao",
        data={
            "cliente_id": "9290675",
            "razao_social": "fdfa92fa09814f3f",
            "cnpj": "78121331000177",
            "condicao_id": "265174",
            "condicao_nome": "9a221eb10df24148",
        },
    )
    assert resp.status_code == 200
    assert len(chamadas) == 1
    path, body = chamadas[0]
    assert path == "/v1/clientes_condicoes_pagamento"
    assert body == {
        "cliente_id": 9290675,
        "condicoes_pagamento_liberadas": [265174],
    }
    assert path != "/v1/clientes"
    assert path != "/v1/condicoes_pagamento"
    assert "condicao_pagamento_id" not in body

    html = resp.text
    assert "Status 200" in html
    assert "9290675" in html
    assert "fdfa92fa09814f3f" in html
    assert "265174" in html
    assert "9a221eb10df24148" in html
    assert "Vínculo realizado" in html
    assert "Mercos Sandbox" in html
    assert '"cliente_id"' not in html
    assert "segredo-ui-homolog" not in html
    assert "CompanyToken" not in html


def test_vincular_condicao_somente_uma_chamada(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[str] = []
    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        lambda path, body: chamadas.append(path)
        or {"ok": True, "status_code": 200, "dados": {}},
    )
    client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-condicao",
        data={"cliente_id": "9290675", "condicao_id": "265174"},
    )
    assert chamadas == ["/v1/clientes_condicoes_pagamento"]


def test_vincular_condicao_sem_ids_nao_chama_mercos(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    post = MagicMock()
    monkeypatch.setattr("services.mercos_homolog_service.post_json", post)
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-condicao",
        data={"cliente_id": "", "condicao_id": ""},
    )
    assert resp.status_code == 200
    assert "Campos obrigatórios" in resp.text
    post.assert_not_called()


def test_vincular_condicao_erro_404_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        MagicMock(side_effect=MercosApiError("Não encontrado", status_code=404)),
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-condicao",
        data={"cliente_id": "9290675", "condicao_id": "265174"},
    )
    assert resp.status_code == 200
    assert "404" in resp.text
    assert "não encontrado" in resp.text.lower()
    assert '{"mensagem"' not in resp.text
    assert "CompanyToken" not in resp.text


def test_vincular_condicao_erro_412_amigavel(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    from services.mercos_api_client import MercosApiError

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json",
        MagicMock(side_effect=MercosApiError("Dados inválidos", status_code=412)),
    )
    resp = client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-condicao",
        data={"cliente_id": "9290675", "condicao_id": "265174"},
    )
    assert resp.status_code == 200
    assert "Dados inválidos" in resp.text
    assert "412" in resp.text
    assert '{"mensagem"' not in resp.text


def test_cliente_e_condicao_fluxos_intactos_apos_vincular(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    chamadas: list[tuple[str, dict]] = []

    def fake_post_json(path, body):
        chamadas.append((path, dict(body)))
        code = 200 if path == "/v1/clientes_condicoes_pagamento" else 201
        return {"ok": True, "status_code": code, "id": 99, "dados": {}}

    monkeypatch.setattr(
        "services.mercos_homolog_service.post_json", fake_post_json
    )

    r_vinc = client.post(
        "/mercos/homologacao-ui/acoes/clientes-vincular-condicao",
        data={"cliente_id": "9290675", "condicao_id": "265174"},
    )
    assert r_vinc.status_code == 200
    assert chamadas[-1][0] == "/v1/clientes_condicoes_pagamento"
    assert chamadas[-1][0] != "/v1/clientes"
    assert chamadas[-1][0] != "/v1/condicoes_pagamento"

    r_cond = client.post(
        "/mercos/homologacao-ui/acoes/condicoes-criar",
        data={"nome": "9a221eb10df24148", "ativo": "sim", "disponivel_b2b": "sim"},
    )
    assert r_cond.status_code == 200
    assert chamadas[-1][0] == "/v1/condicoes_pagamento"

    r_cli = client.post(
        "/mercos/homologacao-ui/acoes/clientes-criar",
        data={"razao_social": ""},
    )
    assert r_cli.status_code != 404
    assert r_cli.status_code == 200

    r_get = client.post("/mercos/homologacao-ui/acoes/condicoes-reiniciar")
    assert r_get.status_code == 200
    assert "Ciclo de sincronização reiniciado" in r_get.text

    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="sec-condicoes-alterar"' in html
    assert 'data-action="/mercos/homologacao-ui/acoes/condicoes-alterar"' in html

