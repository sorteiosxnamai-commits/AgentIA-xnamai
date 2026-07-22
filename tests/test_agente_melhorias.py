"""Testes das melhorias do agente de vendas xNamai (memória, AGENT_VERSION, áudio)."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock


def test_agent_version_novo_chama_vendas(monkeypatch):
    monkeypatch.setenv("AGENT_VERSION", "novo")
    from services import openai_service

    chamado = {"ns": 0, "legado": 0}

    def fake_sync(**kwargs):
        chamado["ns"] += 1
        return "resposta-vendas"

    def fake_legado(**kwargs):
        chamado["legado"] += 1
        return "resposta-legado"

    monkeypatch.setattr("agents.vendas.processar_mensagem_sync", fake_sync)
    monkeypatch.setattr(openai_service, "_perguntar_ia_legado", fake_legado)
    monkeypatch.setattr(
        "services.intent_service.sanitizar_frases_comerciais",
        lambda t, stock_confirmed=False: t,
    )

    out = openai_service.perguntar_ia(
        mensagem="oi",
        catalogo="",
        memoria_sessao={"telefone": "11999999999"},
    )
    assert out == "resposta-vendas"
    assert chamado["ns"] == 1
    assert chamado["legado"] == 0


def test_agent_version_legado_nao_chama_vendas(monkeypatch):
    monkeypatch.setenv("AGENT_VERSION", "legado")
    from services import openai_service

    chamado = {"ns": 0, "legado": 0}

    def fake_sync(**kwargs):
        chamado["ns"] += 1
        return "ns"

    def fake_legado(**kwargs):
        chamado["legado"] += 1
        return "legado-ok"

    monkeypatch.setattr("agents.vendas.processar_mensagem_sync", fake_sync)
    monkeypatch.setattr(openai_service, "_perguntar_ia_legado", fake_legado)
    monkeypatch.setattr(
        "services.intent_service.sanitizar_frases_comerciais",
        lambda t, stock_confirmed=False: t,
    )

    out = openai_service.perguntar_ia(mensagem="oi", catalogo="")
    assert out == "legado-ok"
    assert chamado["legado"] == 1
    assert chamado["ns"] == 0


def test_agent_version_invalido_usa_novo(monkeypatch):
    monkeypatch.setenv("AGENT_VERSION", "xyz")
    from services import openai_service

    monkeypatch.setattr(
        "agents.vendas.processar_mensagem_sync",
        lambda **kw: "novo-default",
    )
    monkeypatch.setattr(
        "services.intent_service.sanitizar_frases_comerciais",
        lambda t, stock_confirmed=False: t,
    )
    assert openai_service.perguntar_ia(mensagem="oi", catalogo="") == "novo-default"


def test_tools_padrao_ok_error_e_sem_http_direto():
    import agents.vendas.tools as tools

    src = inspect.getsource(tools)
    assert "requests." not in src
    assert "httpx" not in src

    out = tools._err("falha")
    assert out == {"ok": False, "data": None, "error": "falha"}
    assert tools._ok({"a": 1})["ok"] is True


def test_search_products_usa_mercos(monkeypatch):
    from agents.vendas import tools

    fake = MagicMock(return_value=[{"nome": "X", "codigo": "1", "preco": 10, "estoque": 1}])
    monkeypatch.setattr("services.mercos_service.mercos_configurado", lambda: True)
    monkeypatch.setattr("services.mercos_service.buscar_produtos_por_termo", fake)
    monkeypatch.setattr("services.mercos_service.montar_catalogo_texto", lambda p: "cat")
    out = tools.execute_tool("search_products", {"query": "x"})
    assert out["ok"] is True
    assert out["data"]["products"][0]["name"] == "X"
    fake.assert_called_once()


def test_check_inventory_usa_mercos(monkeypatch):
    from agents.vendas import tools

    bruto = {"nome": "Y", "codigo": "2", "estoque": 3}
    monkeypatch.setattr("services.mercos_service.mercos_configurado", lambda: True)
    monkeypatch.setattr(
        "services.mercos_service.buscar_produto_bruto_por_mensagem",
        lambda q: bruto,
    )
    monkeypatch.setattr(
        "services.mercos_service.normalizar_produto",
        lambda p: {"nome": "Y", "codigo": "2", "estoque": 3},
    )
    monkeypatch.setattr("services.mercos_service.estoque_confirmado", lambda p: True)
    out = tools.execute_tool("check_inventory", {"query": "y"})
    assert out["ok"] is True
    assert out["data"]["found"] is True


def test_nenhuma_http_direta_mercos_em_tools():
    import agents.vendas.tools as tools

    src = inspect.getsource(tools)
    assert "mercos.com" not in src
    assert "requests." not in src
    assert "httpx" not in src


def test_memoria_grava_e_recupera_sem_apagar(monkeypatch):
    from agents.vendas import memory, memory_repository

    memory.limpar_cache_para_testes()
    historico_existente = [
        {"role": "user", "content": "oi antigo", "timestamp": "2026-01-01T00:00:00Z"},
        {"role": "assistant", "content": "ola", "timestamp": "2026-01-01T00:00:01Z"},
    ]
    estado = {"historico": list(historico_existente)}

    class _FakeTable:
        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def update(self, payload):
            self._payload = payload
            return self

        def execute(self):
            if hasattr(self, "_payload"):
                estado["historico"] = self._payload["historico"]
            return MagicMock(data=[{"historico": estado["historico"], "id": "c1"}])

    monkeypatch.setattr(
        "services.supabase_service.buscar_cliente",
        lambda tel: {
            "id": "c1",
            "telefone": tel,
            "nome": "Ana",
            "historico": estado["historico"],
        },
    )
    monkeypatch.setattr("services.supabase_service.clientes_tem_historico", lambda: True)
    monkeypatch.setattr(
        "services.supabase_service.extrair_contexto_do_historico_json",
        lambda h: {},
    )
    monkeypatch.setattr("database.supabase.supabase.table", lambda *_: _FakeTable())

    memory.atualizar_memoria(
        "11988887777",
        nome="Arthur",
        interesse="produto",
        produto="Relogio",
        orcamento="2000",
        etapa="busca_produto",
        persistir=True,
        mensagem_cliente="pode me chamar de Arthur",
        mensagem_agente="Combinado, Arthur!",
        message_id="mid-1",
    )

    assert "oi antigo" in str(estado["historico"])
    assert any(
        isinstance(m, dict) and m.get("role") == "_xnamai_sales_memory"
        for m in estado["historico"]
    )

    memory.limpar_cache_para_testes()
    monkeypatch.setattr(
        memory_repository,
        "carregar_memoria_persistida",
        lambda tel: next(
            m["content"]
            for m in estado["historico"]
            if isinstance(m, dict) and m.get("role") == "_xnamai_sales_memory"
        ),
    )
    mem2 = memory.carregar_memoria("11988887777")
    assert mem2.get("nome") == "Arthur"


def test_memoria_migra_ns_agent_memory():
    from agents.vendas.memory_repository import _extrair_memoria

    hist = [
        {"role": "user", "content": "oi"},
        {"role": "_ns_agent_memory", "content": {"nome": "Legacy"}},
    ]
    assert _extrair_memoria(hist).get("nome") == "Legacy"


def test_falha_supabase_mantem_memoria_temporaria(monkeypatch):
    from agents.vendas import memory

    memory.limpar_cache_para_testes()
    monkeypatch.setattr(
        "agents.vendas.memory.persistir_memoria",
        lambda *a, **k: {"ok": False, "error": "supabase_down"},
    )
    out = memory.atualizar_memoria("11977776666", nome="Bia", persistir=True)
    assert out.get("nome") == "Bia"
    assert memory.carregar_memoria("11977776666").get("nome") == "Bia"


def test_audio_tmp_removido(monkeypatch):
    from services import audio_service

    criado = {}

    class _FakeTranscriptions:
        def create(self, **kwargs):
            return MagicMock(text="ola mundo")

    class _FakeAudio:
        transcriptions = _FakeTranscriptions()

    class _FakeClient:
        audio = _FakeAudio()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    import openai

    monkeypatch.setattr(openai, "OpenAI", lambda api_key=None: _FakeClient())

    real_mkstemp = audio_service.tempfile.mkstemp

    def tracking_mkstemp(*a, **k):
        fd, name = real_mkstemp(*a, **k)
        criado["path"] = name
        return fd, name

    monkeypatch.setattr(audio_service.tempfile, "mkstemp", tracking_mkstemp)
    texto = audio_service.transcrever_audio_bytes(b"fake-bytes", filename="a.ogg")
    assert texto == "ola mundo"
    assert criado.get("path")
    assert not Path(criado["path"]).exists()


def test_audio_falha_resposta_segura(monkeypatch):
    from services import audio_service

    monkeypatch.setattr(
        audio_service,
        "baixar_audio",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("audio_vazio")),
    )
    out = audio_service.transcrever_audio_url("https://example.com/a.ogg")
    assert out["ok"] is False


def test_normalizer_aceita_audio_ultramsg():
    from services.webhook_normalizer import analisar_webhook

    payload = {
        "event_type": "message_received",
        "data": {
            "from": "5511999999999@c.us",
            "type": "ptt",
            "media": "https://example.com/voice.ogg",
            "id": "aud-1",
            "pushname": "Ana",
        },
    }
    diag = analisar_webhook(payload)
    assert diag["ok"] is True
    assert diag["payload"]["data"]["type"] == "audio"


def test_idempotencia_nao_libera_apos_envio():
    from services import webhook_guard as wg

    data = {"data": {"id": "msg-dup-vendas-1", "from": "5511999", "body": "oi"}}
    ok1, _ = wg.reclamar_mensagem(data)
    assert ok1 is True
    wg.marcar_envio_concluido(data, message_id="msg-dup-vendas-1")
    wg.finalizar_mensagem(data, sucesso=False)
    ok2, motivo = wg.reclamar_mensagem(data)
    assert ok2 is False
    assert "enviado" in motivo or "duplicado" in motivo


def test_throttle_piso_10s_intacto():
    from services import mercos_throttle

    assert mercos_throttle.INTERVALO_MINIMO_GLOBAL_SEGUNDOS == 10.0


def test_mercos_homolog_ui_rota_registrada():
    from main import app

    paths = sorted(app.openapi().get("paths", {}))
    assert any(p.startswith("/mercos/homologacao-ui") for p in paths)


def test_conversas_ausente_nao_quebra_memoria(monkeypatch):
    from agents.vendas import memory_repository as mr

    monkeypatch.setattr("services.supabase_service.clientes_tem_historico", lambda: True)
    monkeypatch.setattr("services.supabase_service.buscar_cliente", lambda tel: None)
    out = mr.persistir_memoria("11999990000", {"nome": "X"})
    assert out["ok"] is False
    assert out["error"] == "cliente_inexistente"


def test_nenhum_arquivo_mercos_alterado():
    import subprocess

    out = subprocess.check_output(
        ["git", "diff", "--name-only", "--", "services/mercos_api_client.py",
         "services/mercos_service.py", "services/mercos_homolog_service.py",
         "services/mercos_throttle.py"],
        cwd=str(Path(__file__).resolve().parents[1]),
        text=True,
    )
    assert out.strip() == ""
