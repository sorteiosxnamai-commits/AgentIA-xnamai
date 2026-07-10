"""Limpeza técnica e segurança (pré-Etapa 3)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


def test_env_nao_rastreado():
    out = subprocess.check_output(
        ["git", "ls-files", "--", ".env", ".env.local", ".env.production"],
        cwd=ROOT,
        text=True,
    ).strip()
    assert out == ""


def test_gitignore_cobre_segredos_e_cache():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for item in (".env", ".env.*", "__pycache__/", "*.pyc", ".pytest_cache/", "venv/", ".venv/", "dist/", "build/"):
        assert item in gi
    assert "!.env.example" in gi
    assert (ROOT / ".env.example").exists()


def test_arquivo_lixo_findstr_nao_rastreado():
    tracked = subprocess.check_output(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
    )
    assert "findstr" not in tracked.lower()
    assert "Uf07c" not in tracked
    # Nenhum arquivo com esse nome no working tree
    for p in ROOT.iterdir():
        assert "findstr" not in p.name.lower()


def test_nenhum_pyc_rastreado():
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    for line in tracked.splitlines():
        assert "__pycache__" not in line
        assert not line.endswith(".pyc")


def test_requirements_sem_bom():
    raw = (ROOT / "requirements.txt").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "supabase==2.31.0" in text
    assert "fastapi" in text


def test_database_supabase_carrega_env_corretamente():
    src = (ROOT / "database" / "supabase.py").read_text(encoding="utf-8")
    assert "load_dotenv" in src
    assert "override=False" in src
    assert "override=True" not in src
    assert "SUPABASE_URL" in src
    assert "SUPABASE_KEY" in src


def test_env_loader_nao_usa_override_true(monkeypatch):
    from services import env_loader

    env_loader._LOADED = False
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    seen = {}

    def fake_load_dotenv(*, override=None, **_k):
        seen["override"] = override
        return True

    with patch("services.env_loader.load_dotenv", side_effect=fake_load_dotenv):
        env_loader.carregar_env()
    assert seen.get("override") is False
    env_loader._LOADED = False


def test_env_loader_pula_no_render(monkeypatch):
    from services import env_loader

    env_loader._LOADED = False
    monkeypatch.setenv("RENDER", "true")
    called = {"n": 0}

    def fake_load_dotenv(**_k):
        called["n"] += 1
        return True

    with patch("services.env_loader.load_dotenv", side_effect=fake_load_dotenv):
        env_loader.carregar_env()
    assert called["n"] == 0
    env_loader._LOADED = False


def test_webhook_nao_loga_payload_completo(capsys):
    from routes.api import _log_webhook_recebido

    payload = {
        "type": "ReceivedCallback",
        "phone": "5543999887766",
        "messageId": "mid-sec-1",
        "text": {"message": "segredo do cliente nao deve aparecer"},
        "token": "NAO_LOGAR_TOKEN",
    }
    _log_webhook_recebido(payload)
    out = capsys.readouterr().out
    assert "segredo do cliente" not in out
    assert "NAO_LOGAR_TOKEN" not in out
    assert "5543999887766" not in out
    assert "webhook_recebido" in out
    assert "mid-sec-1" in out
    assert "***" in out


def test_chat_persistir_false_nao_salva(monkeypatch):
    from routes import api as api_mod

    calls = {"salvar": 0, "lead": 0, "hist": 0, "criar": 0}

    monkeypatch.setattr(api_mod, "buscar_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(
        api_mod,
        "criar_cliente",
        lambda *a, **k: calls.__setitem__("criar", calls["criar"] + 1) or {"id": 1},
    )

    def fake_salvar(*_a, **_k):
        calls["salvar"] += 1

    monkeypatch.setattr(api_mod, "salvar_mensagem", fake_salvar)
    monkeypatch.setattr(
        api_mod,
        "atualizar_historico_json",
        lambda *_a, **_k: calls.__setitem__("hist", calls["hist"] + 1),
    )
    monkeypatch.setattr(
        api_mod,
        "processar_lead_e_notificar",
        lambda **_k: calls.__setitem__("lead", calls["lead"] + 1) or {"notificado": False},
    )
    monkeypatch.setattr(api_mod, "espelhar_mensagem_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "espelhar_mensagem_agente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "enviar_mensagem", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(api_mod, "buscar_historico", lambda *_a, **_k: [])
    monkeypatch.setattr(
        api_mod,
        "perguntar_ia",
        lambda **_k: "Resposta de teste sem persistir",
    )
    monkeypatch.setattr(api_mod, "preparar_contexto_venda", lambda **_k: MagicMock(
        produtos=[],
        catalogo="",
        sem_match=False,
        termos_cliente=[],
        amostra_disponivel=[],
        estagio="atencao",
        fonte="teste",
        erro_mercos=None,
        briefing="",
        memoria={},
    ))

    # Simplifica: força saudação → resposta determinística sem OpenAI
    monkeypatch.setattr(api_mod, "eh_saudacao", lambda *_a, **_k: True)
    monkeypatch.setattr(api_mod, "resposta_saudacao", lambda nome: f"Olá {nome or ''}!")
    monkeypatch.setattr(api_mod, "resolver_estado_venda", lambda *_a, **_k: "negociando")
    monkeypatch.setattr(api_mod, "extrair_nome_do_historico", lambda *_a, **_k: "Teste")
    monkeypatch.setattr(api_mod, "cliente_quer_nova_venda", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "negociacao_nova_apos_fechamento", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "produtos_com_foto_disponivel", lambda *_a, **_k: [])
    monkeypatch.setattr(api_mod, "cliente_pediu_foto", lambda *_a, **_k: False)

    from services.webhook_service import _IDS_PROCESSADOS
    from services import webhook_guard as wg

    _IDS_PROCESSADOS.clear()
    wg._IDS_ESTADO.clear()

    monkeypatch.setattr(
        "services.supabase_service.mensagem_ja_existe",
        lambda *_a, **_k: False,
    )

    data = {
        "event_type": "message_received",
        "provider": "chat_teste",
        "data": {
            "from": "5543999000111",
            "body": "oi",
            "pushname": "Teste",
            "fromMe": False,
            "type": "chat",
            "id": "persist-false-msg-1",
            "time": __import__("time").time(),
        },
    }
    resp = api_mod.processar_mensagem(data, dry_run=True, persistir=False)
    texto = resp.get("resposta") if isinstance(resp, dict) else resp
    assert texto
    assert calls["salvar"] == 0
    assert calls["hist"] == 0
    assert calls["lead"] == 0
    assert calls["criar"] == 0


def test_message_id_duplicado_banco_ignora():
    from services import webhook_guard as wg
    from services.webhook_service import _IDS_PROCESSADOS

    _IDS_PROCESSADOS.clear()
    wg._IDS_ESTADO.clear()

    data = {
        "event_type": "message_received",
        "data": {"id": "db-dup-99", "from": "5543999000222", "body": "oi", "time": 1},
    }

    with patch("services.supabase_service.mensagem_ja_existe", return_value=True):
        ok, motivo = wg.reclamar_mensagem(data)
    assert ok is False
    assert "duplicado_banco" in motivo


def test_message_id_duplicado_memoria_continua():
    from services import webhook_guard as wg
    from services.webhook_service import _IDS_PROCESSADOS

    _IDS_PROCESSADOS.clear()
    wg._IDS_ESTADO.clear()

    data = {
        "event_type": "message_received",
        "data": {"id": "mem-dup-77", "from": "5543999000333", "body": "oi", "time": 1},
    }
    with patch("services.supabase_service.mensagem_ja_existe", return_value=False):
        ok1, _ = wg.reclamar_mensagem(data)
        ok2, motivo2 = wg.reclamar_mensagem(data)
    assert ok1 is True
    assert ok2 is False
    assert "duplicado" in motivo2 or "em_processamento" in motivo2
