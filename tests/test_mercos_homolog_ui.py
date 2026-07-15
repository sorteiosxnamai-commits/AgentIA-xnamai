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
    assert "btn-produtos-sincronizar" in body


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
    resp = client.post("/mercos/homologacao-ui/acoes/produtos-sincronizar")
    assert resp.status_code == 200
    assert capturado["kwargs"].get("alterado_apos") in (None, "")
    html = resp.text
    assert "Tipo da busca" in html
    assert "Completa" in html
    assert "Alterado após enviado" in html
    assert "Novo cursor salvo" in html
    assert "2026-07-15 12:30:00" in html
    assert "Total retornado" in html
    from urllib.parse import unquote

    cookie_raw = (resp.cookies.get("mercos_produtos_cursor") or "").strip('"')
    assert unquote(cookie_raw) == "2026-07-15 12:30:00"
    assert "data-novo-cursor=\"2026-07-15 12:30:00\"" in html
    assert '"itens"' not in html


def test_produtos_sync_segunda_com_cursor_anterior(client, monkeypatch):
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
    cursor_anterior = "2026-07-15 12:30:00"
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-sincronizar",
        data={"cursor": cursor_anterior},
    )
    assert resp.status_code == 200
    assert capturado["kwargs"].get("alterado_apos") == cursor_anterior
    html = resp.text
    assert "Incremental" in html
    assert cursor_anterior in html
    assert "2026-07-16 08:00:00" in html
    from urllib.parse import unquote

    cookie_raw = (resp.cookies.get("mercos_produtos_cursor") or "").strip('"')
    assert unquote(cookie_raw) == "2026-07-16 08:00:00"


def test_produtos_sync_preserva_cursor_sem_registros(client, monkeypatch):
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_configurado", lambda: True
    )
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )

    def fake_listar(**kwargs):
        return {"ok": True, "total": 0, "itens": []}

    monkeypatch.setattr(
        "services.mercos_homolog_service.listar_produtos", fake_listar
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
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
    assert "4c2e97e74c634ea4" in html


def test_produtos_reiniciar_ciclo_nao_chama_mercos(client, monkeypatch):
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
    called.assert_not_called()


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
