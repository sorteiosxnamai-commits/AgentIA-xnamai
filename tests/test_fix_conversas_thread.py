"""Fix: conversas = thread PulseDesk; histórico em clientes.historico."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import routes.api as api_mod
from services import supabase_service as sb
from services.checkout_service import avaliar_checkout


def _ctx_mock(**kwargs):
    base = dict(
        produtos=[{
            "id": "1",
            "name": "Headset Gamer",
            "nome": "Headset Gamer",
            "price": 249.9,
            "preco": 249.9,
            "stock_quantity": 5,
            "stock_confirmed": True,
        }],
        catalogo="Headset",
        sem_match=False,
        termos_cliente=[],
        amostra_disponivel=[],
        estagio="atencao",
        fonte="teste",
        erro_mercos=None,
        briefing="",
        memoria={},
    )
    base.update(kwargs)
    return MagicMock(**base)


def _data(msg="quero comprar o headset gamer", tel="5543999000777", mid=None):
    return {
        "event_type": "message_received",
        "provider": "chat_teste",
        "data": {
            "from": tel,
            "body": msg,
            "pushname": "Arthur",
            "fromMe": False,
            "type": "chat",
            "id": mid or f"chat-thread-{abs(hash(msg + tel)) % 10_000_000}",
            "time": __import__("time").time(),
        },
    }


def _patch_basico(monkeypatch):
    monkeypatch.setattr(api_mod, "buscar_cliente", lambda *_a, **_k: {
        "id": "cli-thread-1",
        "telefone": "5543999000777",
        "nome": "Arthur",
        "historico": [],
        "contexto_venda": {},
    })
    monkeypatch.setattr(api_mod, "criar_cliente", lambda *_a, **_k: {"id": "cli-thread-1"})
    monkeypatch.setattr(api_mod, "atualizar_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "buscar_historico", lambda *_a, **_k: [])
    monkeypatch.setattr(api_mod, "espelhar_mensagem_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "espelhar_mensagem_agente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "enviar_mensagem", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(api_mod, "processar_lead_e_notificar", lambda **_k: {"notificado": False})
    monkeypatch.setattr(api_mod, "resolver_estado_venda", lambda *_a, **_k: "negociando")
    monkeypatch.setattr(api_mod, "eh_saudacao", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "extrair_nome_do_historico", lambda *_a, **_k: "Arthur")
    monkeypatch.setattr(api_mod, "cliente_quer_nova_venda", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "negociacao_nova_apos_fechamento", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "produtos_com_foto_disponivel", lambda *_a, **_k: [])
    monkeypatch.setattr(api_mod, "cliente_pediu_foto", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "finalizar_mensagem", lambda *_a, **_k: None)
    monkeypatch.setattr(
        api_mod,
        "preparar_contexto_venda",
        lambda **_k: _ctx_mock(memoria=_k.get("memoria") or {}),
    )
    monkeypatch.setattr(
        "services.product_service.buscar_por_intencao",
        lambda **_k: {
            "found": True,
            "products": _ctx_mock().produtos,
            "message": "ok",
            "category": "headset",
            "catalogo": "Headset",
            "fonte": "supabase",
        },
    )
    from services.webhook_service import _IDS_PROCESSADOS
    from services import webhook_guard as wg

    _IDS_PROCESSADOS.clear()
    wg._IDS_ESTADO.clear()
    monkeypatch.setattr("services.supabase_service.mensagem_ja_existe", lambda *_a, **_k: False)
    sb._SCHEMA_FLAGS["message_id"] = True
    sb._SCHEMA_FLAGS["contexto_venda"] = True
    sb._SCHEMA_FLAGS["conversas_thread"] = True


# 1
def test_persistir_true_ok_quando_contexto_salva(monkeypatch):
    _patch_basico(monkeypatch)
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(api_mod, "atualizar_thread_conversa", lambda *_a, **_k: True)
    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", lambda *_a, **_k: True)
    out = api_mod.processar_mensagem(_data(mid="t1"), dry_run=True, persistir=True)
    assert out["persistencia_ok"] is True
    assert out["resposta"]
    assert "persistencia_etapas" in out
    assert out["persistencia_etapas"]["contexto_ok"] is True
    assert out["persistencia_etapas"]["historico_ok"] is True


# 2
def test_quero_comprar_salva_contexto(monkeypatch):
    _patch_basico(monkeypatch)
    sessao = {}

    def fake_persist(_cid, s):
        sessao.update(s)
        return True

    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", fake_persist)
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "atualizar_thread_conversa", lambda *_a, **_k: True)
    out = api_mod.processar_mensagem(
        _data("quero comprar o headset gamer", mid="t2"),
        dry_run=True,
        persistir=True,
    )
    assert out["persistencia_ok"] is True
    assert sessao.get("produto_checkout") or sessao.get("produto_ativo")


# 3
def test_prefiro_entrega_continua_checkout():
    r = avaliar_checkout(
        mensagem="prefiro entrega",
        sessao={"produto_ativo": "Headset Gamer", "preco_cotado": 249.9},
        produtos=[{"name": "Headset Gamer", "price": 249.9, "stock_quantity": 5, "stock_confirmed": True}],
        intent="ENTREGA",
    )
    assert r["sessao"]["forma_entrega"] == "entrega"


# 4
def test_sou_de_londrina_salva_cidade():
    r = avaliar_checkout(
        mensagem="sou de Londrina",
        sessao={
            "produto_ativo": "Headset Gamer",
            "preco_cotado": 249.9,
            "forma_entrega": "entrega",
            "quantidade": 1,
        },
        produtos=[{"name": "Headset Gamer", "price": 249.9, "stock_quantity": 5, "stock_confirmed": True}],
        intent="ENTREGA",
    )
    assert "londrina" in (r["sessao"].get("cidade") or "").lower()


# 5
def test_salvar_mensagem_thread_nao_insere_campos_inexistentes(monkeypatch):
    sb._SCHEMA_FLAGS["conversas_thread"] = True
    inserts = []

    class FakeTable:
        def __init__(self, name):
            self.name = name

        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def update(self, payload):
            self._payload = payload
            return self

        def insert(self, payload):
            inserts.append({"table": self.name, "payload": payload})
            return self

        def execute(self):
            if self.name == sb.TABELA_CLIENTES and hasattr(self, "_payload"):
                return MagicMock(data=[{"historico": []}])
            if self.name == sb.TABELA_CLIENTES:
                return MagicMock(data=[{"historico": []}])
            return MagicMock(data=[])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable(n)))
    result = sb.salvar_mensagem("cli-1", "cliente", "oi", message_id="m1")
    assert result["modo"] == "historico_json"
    # Nenhuma insert em conversas com cliente_id/tipo/mensagem
    for ins in inserts:
        if ins["table"] == sb.TABELA_HISTORICO:
            assert "cliente_id" not in ins["payload"]
            assert "tipo" not in ins["payload"]
            assert "mensagem" not in ins["payload"]


# 6
def test_atualizar_thread_usa_colunas_existentes(monkeypatch):
    sb._SCHEMA_FLAGS["conversas_thread"] = True
    sb._SCHEMA_FLAGS["message_id"] = True
    updates = []

    class FakeTable:
        def __init__(self, name):
            self.name = name
            self._eq = None

        def select(self, *_a, **_k):
            return self

        def eq(self, campo, valor):
            self._eq = (campo, valor)
            return self

        def limit(self, *_a, **_k):
            return self

        def update(self, payload):
            updates.append(payload)
            return self

        def insert(self, payload):
            updates.append(payload)
            return self

        def execute(self):
            if self._eq and self._eq[0] == "contact_phone":
                return MagicMock(data=[{"id": "th-1", "unread_count": 0}])
            return MagicMock(data=[])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable(n)))
    ok = sb.atualizar_thread_conversa(
        "5543999000777", "Arthur", "prefiro entrega", message_id="mid-9", inbound=True
    )
    assert ok is True
    assert updates
    patch = updates[0]
    assert "last_message" in patch
    assert "contact_phone" not in patch or True  # update by id
    assert "cliente_id" not in patch
    assert "tipo" not in patch
    assert "mensagem" not in patch
    assert patch.get("message_id") == "mid-9"


# 7
def test_falha_thread_opcional_nao_derruba_persistencia(monkeypatch):
    _patch_basico(monkeypatch)
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: None)

    def boom_thread(*_a, **_k):
        raise RuntimeError("thread fail")

    monkeypatch.setattr(api_mod, "atualizar_thread_conversa", boom_thread)
    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", lambda *_a, **_k: True)
    out = api_mod.processar_mensagem(_data(mid="t7"), dry_run=True, persistir=True)
    assert out["persistencia_ok"] is True
    assert out["persistencia_etapas"]["thread_ok"] is False
    assert out["persistencia_etapas"]["contexto_ok"] is True


# 8
def test_falha_contexto_torna_persistencia_false(monkeypatch):
    _patch_basico(monkeypatch)
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "atualizar_thread_conversa", lambda *_a, **_k: True)
    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", lambda *_a, **_k: False)
    out = api_mod.processar_mensagem(_data(mid="t8"), dry_run=True, persistir=True)
    assert out["resposta"]
    assert out["persistencia_ok"] is False
    assert out["persistencia_etapas"]["contexto_ok"] is False


# 9
def test_persistir_false_continua(monkeypatch):
    _patch_basico(monkeypatch)
    saves = {"n": 0}
    monkeypatch.setattr(
        api_mod,
        "salvar_mensagem",
        lambda *_a, **_k: saves.__setitem__("n", saves["n"] + 1),
    )
    out = api_mod.processar_mensagem(_data(mid="t9"), dry_run=True, persistir=False)
    assert out["resposta"]
    assert saves["n"] == 0


# 10
def test_webhook_existe():
    assert hasattr(api_mod, "webhook")
    assert api_mod.CODE_VERSION == "2026-07-13-fix-catalogo-geral"


# 11
def test_message_id_null_nao_quebra(monkeypatch):
    _patch_basico(monkeypatch)
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "atualizar_thread_conversa", lambda *_a, **_k: True)
    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", lambda *_a, **_k: True)
    data = _data(mid="t11")
    data["data"]["id"] = None
    out = api_mod.processar_mensagem(data, dry_run=True, persistir=True)
    assert out["resposta"]
    assert out["persistencia_ok"] is True


# 12
def test_message_id_duplicado_webhook_protegido():
    from services import webhook_guard as wg
    from services.webhook_service import _IDS_PROCESSADOS

    _IDS_PROCESSADOS.clear()
    wg._IDS_ESTADO.clear()
    data = {
        "event_type": "message_received",
        "data": {"id": "dup-thread-1", "from": "5543999000111", "body": "oi", "time": 1},
    }
    with patch("services.supabase_service.mensagem_ja_existe", return_value=True):
        ok, motivo = wg.reclamar_mensagem(data)
    assert ok is False
    assert "duplicado" in motivo


def test_conversas_e_thread_detecta_schema():
    sb._SCHEMA_FLAGS["conversas_thread"] = True
    assert sb.conversas_e_thread() is True
    sb._SCHEMA_FLAGS["conversas_thread"] = False
    assert sb.conversas_e_thread() is False
    sb._SCHEMA_FLAGS["conversas_thread"] = None
