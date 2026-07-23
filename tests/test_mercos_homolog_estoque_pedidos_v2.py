"""Homologação Mercos: Ajuste de estoque (PUT) e Pedidos GET v2."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("DIAGNOSTICOS_ABERTOS", "false")
    monkeypatch.setenv("SYNC_TOKEN", "segredo-ui-homolog")
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    from main import app

    return TestClient(app)


def test_ajuste_estoque_nao_chama_put_produto(monkeypatch):
    from services import mercos_homolog_service as svc

    svc._reset_ajuste_estoque_para_testes()
    chamado = []

    def fake_put(path, body, **kw):
        chamado.append((path, body, kw))
        return {"ok": True, "status_code": 200, "sandbox": True, "dados": {}, "throttle": {}}

    monkeypatch.setattr(svc, "put_json", fake_put)
    out = svc.ajustar_estoque(20400705, 12)
    assert out["ok"] is True
    assert len(chamado) == 1
    path, body, kw = chamado[0]
    assert path == "/v1/ajustar_estoque"
    assert not str(path).startswith("/v1/produtos/")
    assert "/produtos/" not in path
    assert kw.get("max_retries_429") == 0
    assert kw.get("intervalo_minimo") == svc.piso_ajuste_estoque()


def test_ajuste_estoque_payload_produto_e_quantidade(monkeypatch):
    from services import mercos_homolog_service as svc

    svc._reset_ajuste_estoque_para_testes()
    capturado = {}

    def fake_put(path, body, **kw):
        capturado["path"] = path
        capturado["body"] = body
        return {"ok": True, "status_code": 200, "sandbox": True, "dados": {}, "throttle": {}}

    monkeypatch.setattr(svc, "put_json", fake_put)
    out = svc.ajustar_estoque("99", "7,5", saldo_anterior="3")
    assert capturado["path"] == "/v1/ajustar_estoque"
    assert isinstance(capturado["body"], dict)
    assert not isinstance(capturado["body"], list)
    assert capturado["body"] == {"produto_id": 99, "novo_saldo": 7.5}
    assert out["produto_id"] == 99
    assert out["novo_saldo"] == 7.5
    assert out["saldo_anterior"] == 3.0
    assert out["method"] == "PUT"
    assert out["entidade"] == "Ajuste de estoque"
    assert out["payload_enviado"] == {"produto_id": 99, "novo_saldo": 7.5}


def test_ajuste_estoque_payload_e_dict_nao_lista():
    from services.mercos_homolog_service import montar_payload_ajuste_estoque

    payload = montar_payload_ajuste_estoque(20406596, 109)
    assert isinstance(payload, dict)
    assert not isinstance(payload, list)
    assert payload == {"produto_id": 20406596, "novo_saldo": 109.0}
    assert set(payload.keys()) == {"produto_id", "novo_saldo"}


def test_alterar_produto_remove_saldo_estoque(monkeypatch):
    from services import mercos_homolog_service as svc

    capturado = {}

    def fake_put(path, body, **kw):
        capturado["path"] = path
        capturado["body"] = dict(body)
        return {"ok": True, "status_code": 200, "dados": {}}

    monkeypatch.setattr(svc, "put_json", fake_put)
    svc.alterar_produto(1, {"nome": "X", "saldo_estoque": 99})
    assert capturado["path"] == "/v1/produtos/1"
    assert "saldo_estoque" not in capturado["body"]
    assert capturado["body"]["nome"] == "X"


def test_ajuste_estoque_ui_mostra_422_sem_token(client, monkeypatch):
    from services.mercos_api_client import MercosApiError

    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )

    def boom(*a, **k):
        raise MercosApiError(
            'Mercos HTTP 422: {"message":"Estrutura JSON inválida.","error":"expected a dictionary"}',
            status_code=422,
        )

    monkeypatch.setattr("services.mercos_homolog_service.ajustar_estoque", boom)
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-ajustar-estoque",
        data={"produto_id": "20406596", "novo_saldo": "109"},
    )
    assert resp.status_code == 200
    assert "422" in resp.text
    assert "expected a dictionary" in resp.text
    assert "CompanyToken" not in resp.text
    assert "ApplicationToken" not in resp.text


def test_ajuste_estoque_retry_nao_duplica_concorrente(monkeypatch):
    from services import mercos_homolog_service as svc
    from services.mercos_api_client import MercosApiError

    svc._reset_ajuste_estoque_para_testes()
    liberar = threading.Event()
    chamadas = {"n": 0}

    def fake_put(path, body, **kw):
        chamadas["n"] += 1
        liberar.wait(timeout=2)
        return {"ok": True, "status_code": 200, "dados": {}, "throttle": {}}

    monkeypatch.setattr(svc, "put_json", fake_put)
    erros = []

    def worker():
        try:
            svc.ajustar_estoque(55, 10)
        except MercosApiError as exc:
            erros.append(exc.status_code)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    time.sleep(0.05)
    t2.start()
    liberar.set()
    t1.join(timeout=3)
    t2.join(timeout=3)
    assert chamadas["n"] == 1
    assert 409 in erros


def test_ajuste_estoque_ui_cartao(client, monkeypatch):
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.ajustar_estoque",
        lambda *a, **k: {
            "ok": True,
            "status_code": 200,
            "path": "/v1/ajustar_estoque",
            "produto_id": 11,
            "novo_saldo": 4.0,
            "saldo_anterior": 1.0,
            "payload_enviado": {"produto_id": 11, "novo_saldo": 4.0},
            "chamadas_mercos": 1,
            "deduplicado": False,
            "cliente_interno": "mercos_homolog_service.ajustar_estoque",
            "evidencia_throttle": {
                "chamada_global_anterior": "POST /v1/produtos",
                "timestamp_anterior": 1000.0,
                "intervalo_aplicado": 20.0,
                "intervalo_real": 25.0,
                "endpoint_seguinte": None,
                "chamadas_mercos": 1,
                "sem_chamada_posterior_automatica": True,
            },
            "throttle": {
                "intervalo_minimo": 20.0,
                "intervalo_desde_anterior": 25.0,
                "anterior_metodo": "POST",
                "anterior_endpoint": "/v1/produtos",
                "anterior_ts": 1000.0,
                "hash_abrev": "abc",
            },
        },
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    resp = client.post(
        "/mercos/homologacao-ui/acoes/produtos-ajustar-estoque",
        data={"produto_id": "11", "novo_saldo": "4", "saldo_anterior": "1"},
    )
    assert resp.status_code == 200
    html = resp.text
    assert "PUT Ajuste de estoque" in html
    assert "/v1/ajustar_estoque" in html
    assert "Throttling global respeitado" in html
    assert "Novo saldo" in html or "Quantidade ajustada" in html
    assert "Produto ID" in html
    assert "JSON enviado" in html
    assert "Chamadas Mercos nesta ação" in html
    assert "Intervalo aplicado" in html
    assert "Intervalo real" in html
    assert "Endpoint seguinte" in html
    assert "20.0s" in html or "20s" in html
    assert "Evidência homologação estoque" in html


def test_ajuste_estoque_passa_piso_20_ao_put_json(monkeypatch):
    from services import mercos_homolog_service as svc

    svc._reset_ajuste_estoque_para_testes()
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "10")
    monkeypatch.setenv("MERCOS_HOMOLOG_ESTOQUE_INTERVALO_SEGUNDOS", "20")
    capturado = {}

    def fake_put(path, body, **kw):
        capturado["path"] = path
        capturado["body"] = body
        capturado["kw"] = kw
        return {
            "ok": True,
            "status_code": 200,
            "dados": {},
            "throttle": {
                "intervalo_minimo": 20.0,
                "intervalo_desde_anterior": 21.0,
                "anterior_metodo": "POST",
                "anterior_endpoint": "/v1/produtos",
                "anterior_ts": 1.0,
            },
        }

    monkeypatch.setattr(svc, "put_json", fake_put)
    out = svc.ajustar_estoque(77, 104, acao_id="evid-1")
    assert capturado["path"] == "/v1/ajustar_estoque"
    assert capturado["body"] == {"produto_id": 77, "novo_saldo": 104.0}
    assert capturado["kw"].get("max_retries_429") == 0
    assert capturado["kw"].get("intervalo_minimo") == 20.0
    assert out["chamadas_mercos"] == 1
    assert out["evidencia_throttle"]["intervalo_aplicado"] == 20.0
    assert out["evidencia_throttle"]["endpoint_seguinte"] is None
    assert out["evidencia_throttle"]["sem_chamada_posterior_automatica"] is True


def test_ajuste_estoque_piso_respeita_global_maior(monkeypatch):
    from services import mercos_homolog_service as svc

    svc._reset_ajuste_estoque_para_testes()
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "30")
    monkeypatch.setenv("MERCOS_HOMOLOG_ESTOQUE_INTERVALO_SEGUNDOS", "20")
    capturado = {}

    def fake_put(path, body, **kw):
        capturado["kw"] = kw
        return {"ok": True, "status_code": 200, "dados": {}, "throttle": {}}

    monkeypatch.setattr(svc, "put_json", fake_put)
    svc.ajustar_estoque(88, 1)
    assert capturado["kw"].get("intervalo_minimo") == 30.0


def test_outro_fluxo_put_nao_usa_piso_estoque(monkeypatch):
    """Alterar produto continua com throttle global padrão (sem piso 20 de estoque)."""
    from services import mercos_homolog_service as svc

    monkeypatch.setenv("MERCOS_HOMOLOG_ESTOQUE_INTERVALO_SEGUNDOS", "20")
    capturado = {}

    def fake_put(path, body, **kw):
        capturado["path"] = path
        capturado["kw"] = kw
        return {"ok": True, "status_code": 200, "dados": {}}

    monkeypatch.setattr(svc, "put_json", fake_put)
    svc.alterar_produto(1, {"nome": "Y"})
    assert capturado["path"] == "/v1/produtos/1"
    assert "intervalo_minimo" not in capturado["kw"]


def test_ajuste_estoque_200_sem_retry_e_sem_get(monkeypatch):
    from services import mercos_homolog_service as svc

    svc._reset_ajuste_estoque_para_testes()
    puts = []
    gets = []

    def fake_put(path, body, **kw):
        puts.append((path, kw))
        return {"ok": True, "status_code": 200, "dados": {}, "throttle": {"intervalo_desde_anterior": 22.0}}

    def boom_get(*a, **k):
        gets.append(a)
        raise AssertionError("GET não permitido após ajuste")

    monkeypatch.setattr(svc, "put_json", fake_put)
    monkeypatch.setattr(svc, "get_json", boom_get)
    out = svc.ajustar_estoque(9, 3, acao_id="once")
    assert out["status_code"] == 200
    assert len(puts) == 1
    assert puts[0][1].get("max_retries_429") == 0
    assert gets == []
    # Segunda submissão idêntica: sem novo PUT (duplo clique / reenvio)
    out2 = svc.ajustar_estoque(9, 3, acao_id="once")
    assert out2["deduplicado"] is True
    assert len(puts) == 1


def test_ajuste_estoque_sequencia_criar_espera_um_put_sem_chamadas_seguintes(monkeypatch):
    """Homologação: POST produto → espera ≥10s → um único PUT ajustar_estoque →
    nenhuma chamada Mercos nos 10s seguintes (sem GET de confirmação)."""
    from services import mercos_homolog_service as svc

    svc._reset_ajuste_estoque_para_testes()
    wall = {"t": 1000.0}
    sequencia: list[tuple[str, str, float]] = []

    def fake_post(path, body, **kw):
        sequencia.append(("POST", path, wall["t"]))
        return {
            "ok": True,
            "status_code": 201,
            "id": 9001,
            "dados": {"id": 9001},
            "throttle": {},
        }

    def fake_put(path, body, **kw):
        sequencia.append(("PUT", path, wall["t"]))
        assert path == "/v1/ajustar_estoque"
        assert body == {"produto_id": 9001, "novo_saldo": 15.0}
        return {"ok": True, "status_code": 200, "dados": {}, "throttle": {}}

    def boom_get(*a, **k):
        sequencia.append(("GET", str(a[0]) if a else "?", wall["t"]))
        raise AssertionError("GET Mercos não deve ocorrer após ajuste de estoque")

    monkeypatch.setattr(svc, "post_json", fake_post)
    monkeypatch.setattr(svc, "put_json", fake_put)
    monkeypatch.setattr(svc, "get_json", boom_get)

    svc.criar_produto({"nome": "homolog-ajuste", "codigo": "AJ-1", "ativo": True, "preco_tabela": 1})
    assert sequencia == [("POST", "/v1/produtos", 1000.0)]

    # Espera mínima global entre criação e ajuste (simulada).
    wall["t"] += 10.0
    out = svc.ajustar_estoque(9001, 15)
    assert out["ok"] is True
    assert out["chamadas_mercos"] == 1
    assert out["deduplicado"] is False
    assert [c[:2] for c in sequencia] == [
        ("POST", "/v1/produtos"),
        ("PUT", "/v1/ajustar_estoque"),
    ]
    assert sequencia[1][2] - sequencia[0][2] >= 10.0

    # Janela de 10s após o PUT: nenhuma chamada automática (GET/sync/retry).
    wall["t"] += 10.0
    assert len(sequencia) == 2
    assert all(c[0] != "GET" for c in sequencia)


def test_ajuste_estoque_422_depois_apenas_um_put_corrigido(monkeypatch):
    """Primeiro PUT 422; após correção/reinício e intervalo, só um novo PUT."""
    from services import mercos_homolog_service as svc
    from services.mercos_api_client import MercosApiError

    svc._reset_ajuste_estoque_para_testes()
    wall = {"t": 2000.0}
    puts: list[tuple[float, dict]] = []

    def fake_put(path, body, **kw):
        puts.append((wall["t"], dict(body)))
        if len(puts) == 1:
            raise MercosApiError(
                'Mercos HTTP 422: {"error":"expected a dictionary"}',
                status_code=422,
            )
        return {"ok": True, "status_code": 200, "dados": {}, "throttle": {}}

    monkeypatch.setattr(svc, "put_json", fake_put)

    with pytest.raises(MercosApiError) as exc:
        svc.ajustar_estoque(20406596, 109)
    assert exc.value.status_code == 422
    assert len(puts) == 1

    # Intervalo suficiente (reinício/correção) antes do novo PUT.
    wall["t"] += 646.0
    out = svc.ajustar_estoque(20406596, 109, acao_id="homolog-ajuste-1")
    assert out["ok"] is True
    assert out["status_code"] == 200
    assert len(puts) == 2
    assert puts[1][0] - puts[0][0] >= 10.0
    assert puts[1][1] == {"produto_id": 20406596, "novo_saldo": 109.0}

    # Mesma submissão / mesmo saldo recente: sem terceiro PUT.
    out2 = svc.ajustar_estoque(20406596, 109, acao_id="homolog-ajuste-1")
    assert out2["deduplicado"] is True
    assert out2["chamadas_mercos"] == 0
    assert len(puts) == 2


def test_ajuste_estoque_acao_id_nao_duplica_put(monkeypatch):
    from services import mercos_homolog_service as svc

    svc._reset_ajuste_estoque_para_testes()
    n = {"puts": 0}

    def fake_put(path, body, **kw):
        n["puts"] += 1
        return {"ok": True, "status_code": 200, "dados": {}, "throttle": {}}

    monkeypatch.setattr(svc, "put_json", fake_put)
    a = svc.ajustar_estoque(44, 3, acao_id="uuid-dup")
    b = svc.ajustar_estoque(44, 3, acao_id="uuid-dup")
    assert a["chamadas_mercos"] == 1
    assert b["deduplicado"] is True
    assert n["puts"] == 1


def test_ui_ajuste_estoque_tem_protecao_duplo_clique(client):
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    html = client.get("/mercos/homologacao-ui?token=segredo-ui-homolog").text
    assert 'id="btn-ajuste-estoque"' in html
    assert 'data-sem-retry="1"' in html
    assert 'data-idempotent="1"' in html
    assert "_acoesEmVoo" in html
    assert "acao_id" in html
    assert "produtos-ajustar-estoque" in html


def test_pedidos_get_usa_v2_nao_v1(monkeypatch):
    from services import mercos_homolog_service as svc

    paths = []

    def fake_listar(**kw):
        paths.append(kw.get("path"))
        return {
            "ok": True,
            "path": kw.get("path"),
            "itens": [
                {
                    "id": 1,
                    "valor_total": 100,
                    "status": 2,
                    "data_criacao": "2026-07-20 10:00:00",
                    "cliente_id": 9,
                    "itens": [{"produto_id": 1, "quantidade": 2}],
                }
            ],
            "paginas_lidas": 1,
            "status": "concluida",
            "motivo_parada": "fim",
            "throttling_respeitado": True,
        }

    monkeypatch.setattr(svc, "_listar_paginado_seguro", fake_listar)
    out = svc.listar_pedidos_paginado_seguro(max_paginas=1)
    assert paths == ["/v2/pedidos"]
    assert "/v1/pedidos" not in paths
    assert out["versao"] == "v2"
    assert out["path"] == "/v2/pedidos"
    assert out["itens"][0]["total"] == 100
    assert out["itens"][0]["status"] == "2"
    assert out["itens"][0]["ultima_alteracao"]


def test_adaptar_pedido_v2_campos():
    from services.mercos_homolog_service import adaptar_pedido_v2

    raw = {
        "id": 77,
        "numero": 12,
        "status": 0,
        "status_faturamento": 2,
        "valor_total": 50.5,
        "cliente_id": 3,
        "cliente_razao_social": "ACME",
        "data_emissao": "2026-07-01",
        "itens": [{"id": 1, "produto_id": 9, "quantidade": 1}],
    }
    out = adaptar_pedido_v2(raw)
    assert out["id"] == 77
    assert out["total"] == 50.5
    assert out["status"] == "0"
    assert out["status_faturamento"] == 2
    assert out["itens"][0]["produto_id"] == 9
    assert out["ultima_alteracao"] == "2026-07-01"


def test_pedidos_paginacao_v2_passa_registros_por_pagina(monkeypatch):
    from services import mercos_homolog_service as svc

    capturado = {}

    def fake_listar(**kw):
        capturado.update(kw)
        return {
            "ok": True,
            "path": kw["path"],
            "itens": [],
            "paginas_lidas": 1,
            "status": "concluida",
        }

    monkeypatch.setattr(svc, "_listar_paginado_seguro", fake_listar)
    svc.listar_pedidos_paginado_seguro(max_paginas=3)
    assert capturado["path"] == "/v2/pedidos"
    assert capturado["params_extra"]["registros_por_pagina"] == 20


def test_pedidos_v2_erro_propagado(monkeypatch):
    from services import mercos_homolog_service as svc
    from services.mercos_api_client import MercosApiError

    def boom(**kw):
        raise MercosApiError("Mercos HTTP 500: falha", status_code=500)

    monkeypatch.setattr(svc, "_listar_paginado_seguro", boom)
    with pytest.raises(MercosApiError) as exc:
        svc.listar_pedidos_paginado_seguro()
    assert exc.value.status_code == 500


def test_sincronizar_pedidos_retorna_versao_v2(monkeypatch):
    from services import mercos_homolog_service as svc

    monkeypatch.setattr(
        svc,
        "listar_pedidos_paginado_seguro",
        lambda **kw: {
            "itens": [{"id": 1, "ultima_alteracao": "2026-07-21 12:00:00"}],
            "path": "/v2/pedidos",
            "versao": "v2",
            "paginas_lidas": 1,
            "status": "concluida",
            "motivo_parada": "fim",
            "throttling_respeitado": True,
            "filtros": {},
        },
    )
    # libera lock se ficou preso
    try:
        svc._SYNC_PEDIDOS_LOCK.release()
    except Exception:
        pass
    out = svc.sincronizar_pedidos()
    assert out["versao"] == "v2"
    assert out["path"] == "/v2/pedidos"


def test_ui_pedidos_sincronizar_mostra_v2(client, monkeypatch):
    from services import mercos_pedidos_catalogo as catp

    catp._reset_todos_para_testes()
    monkeypatch.setattr("routes.mercos_homolog_ui.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "routes.mercos_homolog_ui.mercos_ambiente_sandbox", lambda: True
    )
    monkeypatch.setattr(
        "services.mercos_homolog_service.sincronizar_pedidos",
        lambda *a, **k: {
            "ok": True,
            "tipo": "completa",
            "cursor_base": None,
            "alterado_apos_enviado": None,
            "novo_cursor": "2026-07-21 12:00:00",
            "total": 1,
            "itens": [
                {
                    "id": 2148915,
                    "cliente_id": 1,
                    "cliente_razao_social": "ACME",
                    "total": 10,
                    "status": "2",
                    "data_emissao": "2026-07-21",
                    "ultima_alteracao": "2026-07-21 12:00:00",
                }
            ],
            "path": "/v2/pedidos",
            "versao": "v2",
            "paginas_lidas": 1,
            "status": "concluida",
            "motivo_parada": "fim",
            "throttling_respeitado": True,
        },
    )
    client.get("/mercos/homologacao-ui?token=segredo-ui-homolog")
    client.post("/mercos/homologacao-ui/acoes/pedidos-reiniciar")
    resp = client.post("/mercos/homologacao-ui/acoes/pedidos-sincronizar")
    assert resp.status_code == 200
    assert "GET Pedidos" in resp.text
    assert "Versão utilizada" in resp.text
    assert "/v2/pedidos" in resp.text
    assert "Throttling global respeitado" in resp.text


def test_demais_homologacoes_paths_intactos():
    from services.mercos_homolog_service import PATHS

    assert PATHS["produtos"] == "/v1/produtos"
    assert PATHS["pedidos"] == "/v1/pedidos"  # PUT/cancel ainda v1
    assert PATHS["pedidos_v2"] == "/v2/pedidos"
    assert PATHS["pedidos_cancelar"] == "/v1/pedidos/cancelar"
    assert PATHS["faturamento"] == "/v1/faturamento"
    assert PATHS["ajustar_estoque"] == "/v1/ajustar_estoque"


def test_throttle_module_nao_alterado():
    from pathlib import Path

    src = Path("services/mercos_throttle.py").read_text(encoding="utf-8")
    assert "ajustar_estoque" not in src
    assert "pedidos_v2" not in src
