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
    assert "Clientes únicos no catálogo" in r1.text

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
    paginas_vistas: list[int] = []

    def fake_get(path, *, params=None, **_kw):
        pagina = int((params or {}).get("pagina") or 1)
        paginas_vistas.append(pagina)
        if pagina == 1:
            return [
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
            ]
        if pagina == 2:
            return [
                {
                    "id": 3,
                    "razao_social": "77eb21774dd340ff",
                    "nome_fantasia": "Homolog",
                    "cnpj": "11.111.111/0001-11",
                    "email": "h@test.com",
                    "ultima_alteracao": "2026-07-16 09:00:00",
                    "ativo": True,
                },
                {
                    "id": 3,
                    "razao_social": "77eb21774dd340ff",
                    "ultima_alteracao": "2026-07-16 09:00:00",
                    "ativo": True,
                },
            ]
        if pagina == 3:
            return [
                {
                    "id": 4,
                    "razao_social": "Ultimo",
                    "ultima_alteracao": "2026-07-10 08:00:00",
                    "ativo": True,
                }
            ]
        return []

    monkeypatch.setattr("services.mercos_homolog_service.get_json", fake_get)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert resp.status_code == 200
    html = resp.text
    assert "Completa" in html
    assert "Total de páginas consultadas" in html
    assert 'data-paginas-lidas="4"' in html
    # Com page_size_hint=0: p1(2), p2(2), p3(1), p4([]) → 4 páginas
    assert paginas_vistas == [1, 2, 3, 4]
    assert "Total retornado em todas as páginas" in html
    assert 'data-catalogo-total="4"' in html
    assert "77eb21774dd340ff" in html
    assert "Clientes únicos no catálogo" in html
    assert "Motivo da parada" in html
    assert "Lote vazio" in html or "Todas as páginas" in html or "Limite de páginas" in html
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
    fase = {"n": 0}
    paginas_inc: list[int] = []

    def fake_get(path, *, params=None, **_kw):
        params = params or {}
        pagina = int(params.get("pagina") or 1)
        if "alterado_apos" not in params:
            # Completa: 1 página
            return [
                {
                    "id": 1,
                    "razao_social": "Base",
                    "ultima_alteracao": "2026-07-15 10:00:00",
                    "ativo": True,
                }
            ] if pagina == 1 else []
        # Incremental multi-página
        paginas_inc.append(pagina)
        if pagina == 1:
            return [
                {
                    "id": 2,
                    "razao_social": "Inc A",
                    "ultima_alteracao": "2026-07-15 12:00:00",
                    "ativo": True,
                }
            ]
        if pagina == 2:
            return [
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
            ]
        return []

    monkeypatch.setattr("services.mercos_homolog_service.get_json", fake_get)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    r1 = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert r1.status_code == 200
    r2 = client.post(
        "/mercos/homologacao-ui/acoes/clientes-sincronizar",
        data={"cursor": "2026-07-15 10:00:00"},
    )
    assert r2.status_code == 200
    assert paginas_inc == [1, 2, 3]  # p3 vazia
    html = r2.text
    assert "Incremental" in html
    assert "Total de páginas consultadas" in html
    assert "77eb21774dd340ff" in html
    cookie_raw = (r2.cookies.get("mercos_clientes_cursor") or "").strip('"')
    assert unquote(cookie_raw) == "2026-07-16 15:30:00"
    sessao = client.cookies.get("mercos_clientes_sessao")
    assert cat.total(sessao) == 3
    assert html.split("mercos-clientes-catalogo-blob")[0].count("77eb21774dd340ff") == 1


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
        pagina = int((params or {}).get("pagina") or 1)
        chamadas.append(pagina)
        lote = [
            {
                "id": 1,
                "razao_social": "Mesmo",
                "ultima_alteracao": "2026-07-15 10:00:00",
                "ativo": True,
            }
        ]
        return lote  # página 1 e 2 iguais → para

    monkeypatch.setattr("services.mercos_homolog_service.get_json", fake_get)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/clientes-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/clientes-sincronizar")
    assert resp.status_code == 200
    assert MOTIVO_PARADA_REPETIDA in resp.text
    assert "Concluída" in resp.text or "concluida" in resp.text.lower()
    assert "500" not in resp.text
    assert chamadas == [1, 2]
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
        pagina = int((params or {}).get("pagina") or 1)
        if pagina == 1:
            return [
                {"id": 1, "razao_social": "A", "ultima_alteracao": "2026-07-15 10:00:00"},
                {"id": 2, "razao_social": "B", "ultima_alteracao": "2026-07-15 11:00:00"},
            ]
        # Mesmos IDs, assinatura diferente (outra ordem / alteração) → nenhum ID novo
        return [
            {"id": 2, "razao_social": "B2", "ultima_alteracao": "2026-07-15 12:00:00"},
            {"id": 1, "razao_social": "A2", "ultima_alteracao": "2026-07-15 12:01:00"},
        ]

    monkeypatch.setattr("services.mercos_homolog_service.get_json", fake_get)
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
            return [
                {
                    "id": 1,
                    "razao_social": "Parcial",
                    "ultima_alteracao": "2026-07-15 10:00:00",
                }
            ]
        raise MercosApiError("Timeout na chamada à Mercos.", status_code=504)

    monkeypatch.setattr("services.mercos_homolog_service.get_json", fake_get)
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

    def fake_get(path, *, params=None, **_kw):
        pagina = int((params or {}).get("pagina") or 1)
        return [
            {
                "id": pagina,
                "razao_social": f"C{pagina}",
                "ultima_alteracao": f"2026-07-15 10:{pagina:02d}:00",
            }
        ]

    monkeypatch.setattr("services.mercos_homolog_service.get_json", fake_get)
    out = listar_clientes_paginado_seguro(max_paginas=20, timeout_total=60)
    assert out["paginas_lidas"] == 20
    assert out["total"] == 20
    assert out["motivo_parada"] == MOTIVO_PARADA_LIMITE
    assert out["status"] == "concluida"


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
