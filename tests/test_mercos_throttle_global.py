"""Testes do throttling GLOBAL e persistente da Mercos (mercos_throttle).

Cobrem os requisitos de sobreviver a reinícios, serializar processos, contabilizar
chamadas de outras entidades e aplicar o piso de 10s a GET/POST/PUT e às
retentativas após 429 — sempre dentro do limiter (nenhuma chamada HTTP fora dele).
"""

from __future__ import annotations

import os
import threading
import time
from unittest.mock import MagicMock

import pytest

from services import mercos_throttle
from services.mercos_api_client import request_mercos


class _Wall:
    """Relógio de parede (wall clock) controlado, persistível, com sono fake."""

    def __init__(self, t: float = 1000.0):
        self.t = float(t)
        self.sleeps: list[float] = []

    def agora(self) -> float:
        return self.t

    def dormir(self, segundos: float) -> None:
        if segundos > 0:
            self.sleeps.append(round(float(segundos), 6))
            self.t += float(segundos)


def _resp_ok() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "[]"
    resp.headers = {}
    resp.json.return_value = []
    return resp


def _prep_request(monkeypatch, company: str = "empresa-throttle") -> None:
    monkeypatch.setattr("services.mercos_api_client.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "services.mercos_api_client._application_tokens", lambda: ["app-token"]
    )
    monkeypatch.setenv("MERCOS_COMPANY_TOKEN", company)


def test_primeira_chamada_apos_restart_espera_tempo_restante(monkeypatch):
    """O estado persistido em disco sobrevive ao 'reinício' do processo: a
    primeira chamada após reiniciar aguarda apenas o tempo que falta para o piso."""
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "10")
    wall = _Wall(t=1000.0)
    mercos_throttle.configurar_para_testes(relogio=wall.agora, dormir=wall.dormir)

    # Processo "anterior": registra o início da última chamada (persistido).
    mercos_throttle.executar("GET", "/v1/pedidos", lambda: "ok")
    ts_anterior = wall.t
    assert ts_anterior == 1000.0

    # "Reinício do Uvicorn": zera memória do módulo, mas o disco permanece.
    mercos_throttle._reset_para_testes()
    wall2 = _Wall(t=ts_anterior + 3.0)  # já se passaram 3s desde a última
    mercos_throttle.configurar_para_testes(relogio=wall2.agora, dormir=wall2.dormir)

    executou_em: list[float] = []
    mercos_throttle.executar(
        "GET", "/v1/promocoes", lambda: executou_em.append(wall2.t)
    )
    # Esperou só o restante (10 - 3 = 7s), medido do timestamp PERSISTIDO em disco.
    assert wall2.sleeps == [7.0]
    assert executou_em == [ts_anterior + 10.0]


def test_lock_de_arquivo_serializa_processos_concorrentes(tmp_path):
    """Dois 'processos' (threads com lock de arquivo) nunca entram ao mesmo tempo."""
    from services.mercos_throttle import _LockArquivo

    lock = str(tmp_path / "empresa.lock")
    adquiriu: list[float] = []

    with _LockArquivo(lock):
        def concorrente():
            with _LockArquivo(lock, timeout=5.0):
                adquiriu.append(time.monotonic())

        th = threading.Thread(target=concorrente)
        th.start()
        time.sleep(0.3)
        # Enquanto seguramos o lock, o concorrente NÃO consegue entrar.
        assert adquiriu == []

    th.join(timeout=5.0)
    # Só após liberarmos o lock o concorrente entra.
    assert len(adquiriu) == 1


def test_chamada_de_outra_entidade_antes_de_promocoes_e_considerada(monkeypatch):
    """Uma chamada de outra entidade (clientes) atrasa a primeira de Promoções:
    o piso global é medido a partir da última chamada persistida, qualquer que
    seja a entidade."""
    _prep_request(monkeypatch)
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "10")
    wall = _Wall(t=1000.0)
    mercos_throttle.configurar_para_testes(relogio=wall.agora, dormir=wall.dormir)

    marcas: list[tuple[str, str, float]] = []

    def _req(method, url, **_kw):
        marcas.append((method, url, wall.t))
        return _resp_ok()

    monkeypatch.setattr("services.mercos_api_client.requests.request", _req)

    request_mercos("GET", "/v1/clientes")
    request_mercos("GET", "/v1/promocoes")

    assert marcas[0][2] == 1000.0
    assert "clientes" in marcas[0][1]
    assert "promocoes" in marcas[1][1]
    # Promoções só saiu >= 10s após a chamada de clientes (outra entidade).
    assert marcas[1][2] - marcas[0][2] >= 10.0


def test_post_e_put_passam_pelo_limiter_global(monkeypatch):
    """POST e PUT também respeitam o piso global entre chamadas."""
    _prep_request(monkeypatch)
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "10")
    wall = _Wall(t=1000.0)
    mercos_throttle.configurar_para_testes(relogio=wall.agora, dormir=wall.dormir)

    marcas: list[tuple[str, float]] = []

    def _req(method, url, **_kw):
        marcas.append((method, wall.t))
        return _resp_ok()

    monkeypatch.setattr("services.mercos_api_client.requests.request", _req)

    request_mercos("POST", "/v1/produtos", json_body={"nome": "x"})
    request_mercos("PUT", "/v1/produtos/1", json_body={"nome": "y"})

    assert marcas[0][0] == "POST"
    assert marcas[1][0] == "PUT"
    assert marcas[1][1] - marcas[0][1] >= 10.0


def test_retentativa_429_mantem_piso_de_10s(monkeypatch):
    """429 com Retry-After 2s (< piso): a próxima tentativa só sai >= 10s depois."""
    _prep_request(monkeypatch)
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "10")
    wall = _Wall(t=1000.0)
    mercos_throttle.configurar_para_testes(relogio=wall.agora, dormir=wall.dormir)

    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.text = "throttling"
    resp_429.headers = {"Retry-After": "2"}
    respostas = [resp_429, _resp_ok()]
    marcas: list[float] = []

    def _req(method, url, **_kw):
        marcas.append(wall.t)
        return respostas.pop(0)

    monkeypatch.setattr("services.mercos_api_client.requests.request", _req)

    request_mercos("GET", "/v1/promocoes")

    assert len(marcas) == 2  # 1 tentativa 429 + 1 tentativa OK
    # O Retry-After de 2s NUNCA reduz o piso de 10s entre os INÍCIOS.
    assert marcas[1] - marcas[0] >= 10.0


def test_nenhuma_chamada_http_ocorre_fora_do_limiter(monkeypatch):
    """A requisição HTTP só acontece com o lock de arquivo do limiter preso."""
    _prep_request(monkeypatch, company="empresa-lock")
    base = os.environ["MERCOS_THROTTLE_DIR"]
    ch = mercos_throttle.hash_company()
    lock_dir = os.path.join(base, f"{ch}.lock")

    lock_preso: list[bool] = []

    def _req(method, url, **_kw):
        lock_preso.append(os.path.isdir(lock_dir))
        return _resp_ok()

    monkeypatch.setattr("services.mercos_api_client.requests.request", _req)

    request_mercos("GET", "/v1/promocoes")
    request_mercos("POST", "/v1/produtos", json_body={})

    assert lock_preso == [True, True]


def test_auditoria_persistida_sem_segredos(monkeypatch):
    """A auditoria registra horário/método/endpoint/intervalo/origem — sem token."""
    _prep_request(monkeypatch, company="empresa-auditoria-secreta")
    monkeypatch.setattr("services.mercos_api_client.requests.request", lambda *a, **k: _resp_ok())

    mercos_throttle.definir_origem("/mercos/homologacao-ui/acoes/promocoes-sincronizar")
    request_mercos("GET", "/v1/promocoes")

    registros = mercos_throttle.auditoria(limite=10)
    assert registros
    entrada = registros[0]
    assert entrada["metodo"] == "GET"
    assert entrada["endpoint"] == "/v1/promocoes"
    assert "origem" in entrada
    # Nunca aparece o CompanyToken real; só o hash em disco.
    texto = str(registros) + mercos_throttle.estado_atual()["company_hash"]
    assert "empresa-auditoria-secreta" not in texto


def test_produto_post_passa_pelo_throttler_e_registra_auditoria(monkeypatch):
    """Produto POST (criar_produto → post_json → request_mercos) passa pelo
    throttler global: gera auditoria POST /v1/produtos, considera a chamada
    anterior de outra entidade (>= 10s) e retorna 201."""
    from services import mercos_homolog_service as svc

    _prep_request(monkeypatch)
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "10")
    wall = _Wall(t=1000.0)
    mercos_throttle.configurar_para_testes(relogio=wall.agora, dormir=wall.dormir)

    def _req(method, url, **_kw):
        resp = MagicMock()
        resp.status_code = 201
        resp.text = "{}"
        resp.headers = {"MeusPedidosID": "20405071"}
        resp.json.return_value = {"id": 20405071}
        return resp

    monkeypatch.setattr("services.mercos_api_client.requests.request", _req)

    # Chamada anterior de OUTRA entidade (clientes) fixa o início global.
    svc.get_json("/v1/clientes")
    ts_clientes = wall.t

    out = svc.criar_produto(
        {"nome": "ebc2b8af8bcb41a0", "codigo": "HOM-P-01", "ativo": True, "preco_tabela": 7.90}
    )
    assert out["status_code"] == 201
    assert str(out["id"]) == "20405071"

    registros = mercos_throttle.auditoria(limite=10)
    post_produtos = [
        r for r in registros if r["metodo"] == "POST" and r["endpoint"] == "/v1/produtos"
    ]
    assert post_produtos, "Produto POST não gerou entrada de auditoria (fora do limiter)"
    # O POST só saiu >= 10s após a chamada anterior de clientes.
    assert post_produtos[0]["intervalo_desde_anterior"] >= 10.0
    assert wall.t - ts_clientes >= 10.0


def test_cliente_direto_do_mercos_service_passa_pelo_limiter(monkeypatch):
    """O cliente HTTP direto (mercos_service) também passa pelo throttler: a
    chamada HTTP ocorre com o lock de arquivo preso e gera auditoria."""
    from services import mercos_service

    _prep_request(monkeypatch, company="empresa-serv-direto")
    base = os.environ["MERCOS_THROTTLE_DIR"]
    ch = mercos_throttle.hash_company()
    lock_dir = os.path.join(base, f"{ch}.lock")
    lock_preso: list[bool] = []

    def _req(method, url, **_kw):
        lock_preso.append(os.path.isdir(lock_dir))
        resp = MagicMock()
        resp.status_code = 201
        resp.text = "{}"
        resp.headers = {"MeusPedidosID": "999"}
        resp.json.return_value = {"id": 999}
        return resp

    monkeypatch.setattr("services.mercos_service.requests.request", _req)

    novo_id = mercos_service.criar_cliente_mercos("Cliente Teste", telefone="1199999")
    assert novo_id == 999
    assert lock_preso == [True]

    registros = mercos_throttle.auditoria(limite=10)
    assert any(
        r["metodo"] == "POST" and r["endpoint"] == "/v1/clientes" for r in registros
    )
