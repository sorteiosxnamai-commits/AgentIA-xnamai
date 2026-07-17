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
