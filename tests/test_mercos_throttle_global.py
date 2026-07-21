"""Testes do throttling GLOBAL e persistente da Mercos (mercos_throttle).

Cobrem os requisitos de sobreviver a reinícios, serializar processos, contabilizar
chamadas de outras entidades e aplicar o piso de 8s a GET/POST/PUT e às
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
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "8")
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
    # Esperou só o restante (8 - 3 = 5s), medido do timestamp PERSISTIDO em disco.
    assert wall2.sleeps == [5.0]
    assert executou_em == [ts_anterior + 8.0]


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
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "8")
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
    # Promoções só saiu >= 8s após a chamada de clientes (outra entidade).
    assert marcas[1][2] - marcas[0][2] >= 8.0


def test_post_e_put_passam_pelo_limiter_global(monkeypatch):
    """POST e PUT também respeitam o piso global entre chamadas."""
    _prep_request(monkeypatch)
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "8")
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
    assert marcas[1][1] - marcas[0][1] >= 8.0


def test_retentativa_429_mantem_piso_de_8s(monkeypatch):
    """429 com Retry-After 2s (< piso): a próxima tentativa só sai >= 8s depois."""
    _prep_request(monkeypatch)
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "8")
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
    # O Retry-After de 2s NUNCA reduz o piso de 8s entre os INÍCIOS.
    assert marcas[1] - marcas[0] >= 8.0


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
