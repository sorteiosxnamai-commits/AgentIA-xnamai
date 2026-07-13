"""Fix: cliente_ok/etapas honestos (banco vs fallback ephemeral)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import routes.api as api_mod
from services import supabase_service as sb
from services.checkout_service import avaliar_checkout, criar_pedido_se_permitido


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


def _data(msg="quero comprar o headset gamer", tel="5543999999993", mid=None, nome="Arthur"):
    return {
        "event_type": "message_received",
        "provider": "chat_teste",
        "data": {
            "from": tel,
            "body": msg,
            "pushname": nome,
            "fromMe": False,
            "type": "chat",
            "id": mid or f"chat-etapas-{abs(hash(msg + tel + str(nome))) % 10_000_000}",
            "time": __import__("time").time(),
        },
    }


def _patch_fluxo(monkeypatch, *, cliente=None, criar=None):
    monkeypatch.setattr(api_mod, "buscar_cliente", lambda *_a, **_k: cliente)
    if criar is not None:
        monkeypatch.setattr(api_mod, "criar_cliente", criar)
    else:
        monkeypatch.setattr(
            api_mod,
            "criar_cliente",
            lambda tel, nome="": {"id": "cli-new", "telefone": tel, "nome": nome or "WhatsApp"},
        )
    monkeypatch.setattr(api_mod, "atualizar_cliente", lambda **_k: None)
    monkeypatch.setattr(api_mod, "buscar_historico", lambda *_a, **_k: [])
    monkeypatch.setattr(api_mod, "salvar_mensagem", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(api_mod, "atualizar_historico_json", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "atualizar_thread_conversa", lambda *_a, **_k: True)
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
    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", lambda *_a, **_k: True)
    from services.webhook_service import _IDS_PROCESSADOS
    from services import webhook_guard as wg

    _IDS_PROCESSADOS.clear()
    wg._IDS_ESTADO.clear()
    monkeypatch.setattr("services.supabase_service.mensagem_ja_existe", lambda *_a, **_k: False)


# 1
def test_cliente_telefone_ok(monkeypatch):
    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-tel", "telefone": "5543999999993", "nome": "Arthur", "contexto_venda": {}},
    )
    out = api_mod.processar_mensagem(_data(mid="e1"), dry_run=True, persistir=True)
    assert out["persistencia_etapas"]["cliente_ok"] is True
    assert out["persistencia_ok"] is True


# 2
def test_cliente_celular_ok(monkeypatch):
    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-cel", "telefone": None, "celular": "5543999999993", "nome": "Arthur"},
    )
    out = api_mod.processar_mensagem(_data(mid="e2"), dry_run=True, persistir=True)
    assert out["persistencia_etapas"]["cliente_ok"] is True


# 3
def test_insert_vazio_rebusca_ok(monkeypatch):
    _patch_fluxo(monkeypatch, cliente=None)
    state = {"n": 0}

    def criar(*_a, **_k):
        raise RuntimeError("sem retorno")

    def buscar(*_a, **_k):
        state["n"] += 1
        if state["n"] == 1:
            return None
        return {"id": "cli-re", "telefone": "5543999999993", "nome": "Arthur"}

    monkeypatch.setattr(api_mod, "criar_cliente", criar)
    monkeypatch.setattr(api_mod, "buscar_cliente", buscar)
    out = api_mod.processar_mensagem(_data(mid="e3"), dry_run=True, persistir=True)
    assert out["persistencia_etapas"]["cliente_ok"] is True
    assert out["persistencia_ok"] is True


# 4
def test_update_nome_opcional(monkeypatch):
    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-up", "telefone": "5543999999993", "nome": "Outro"},
    )
    monkeypatch.setattr(
        api_mod,
        "atualizar_cliente",
        lambda **_k: (_ for _ in ()).throw(RuntimeError("nome fail")),
    )
    out = api_mod.processar_mensagem(_data(mid="e4"), dry_run=True, persistir=True)
    assert out["persistencia_etapas"]["cliente_ok"] is True
    assert out["persistencia_ok"] is True


# 5
def test_contexto_banco_ok(monkeypatch):
    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-ctx", "telefone": "5543999999993", "nome": "Arthur"},
    )
    out = api_mod.processar_mensagem(_data(mid="e5"), dry_run=True, persistir=True)
    assert out["persistencia_etapas"]["contexto_ok"] is True


# 6
def test_contexto_fallback_ephemeral_nao_ok(monkeypatch):
    """Ephemeral/cache não pode marcar contexto_ok de persistência real."""
    _patch_fluxo(monkeypatch, cliente=None)

    def boom(*_a, **_k):
        raise RuntimeError("create fail")

    monkeypatch.setattr(api_mod, "criar_cliente", boom)
    monkeypatch.setattr(api_mod, "buscar_cliente", lambda *_a, **_k: None)
    out = api_mod.processar_mensagem(_data(mid="e6"), dry_run=True, persistir=True)
    assert out["resposta"]
    assert out["persistencia_etapas"]["cliente_ok"] is False
    assert out["persistencia_etapas"]["contexto_ok"] is False
    assert out["persistencia_ok"] is False


# 7
def test_historico_banco_ok(monkeypatch):
    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-h", "telefone": "5543999999993", "nome": "Arthur"},
    )
    out = api_mod.processar_mensagem(_data(mid="e7"), dry_run=True, persistir=True)
    assert out["persistencia_etapas"]["historico_ok"] is True


# 8
def test_historico_fallback_ephemeral_nao_ok(monkeypatch):
    _patch_fluxo(monkeypatch, cliente=None)
    monkeypatch.setattr(api_mod, "criar_cliente", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(api_mod, "buscar_cliente", lambda *_a, **_k: None)
    out = api_mod.processar_mensagem(_data(mid="e8"), dry_run=True, persistir=True)
    assert out["persistencia_etapas"]["historico_ok"] is False


# 9 + 10
def test_chat_persistir_true_ok(monkeypatch):
    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-ok", "telefone": "5543999999993", "nome": "Arthur"},
    )
    out = api_mod.processar_mensagem(_data(mid="e9"), dry_run=True, persistir=True)
    assert out["persistencia_ok"] is True
    assert out["persistencia_etapas"]["cliente_ok"] is True


# 11
def test_sequencia_checkout_persistencia(monkeypatch):
    sessao_store = {}

    def buscar(*_a, **_k):
        return {
            "id": "cli-seq",
            "telefone": "5543999999993",
            "nome": "Arthur",
            "contexto_venda": dict(sessao_store),
        }

    _patch_fluxo(monkeypatch, cliente={"id": "cli-seq", "telefone": "5543999999993", "nome": "Arthur"})
    monkeypatch.setattr(api_mod, "buscar_cliente", buscar)

    import services.vendas.memoria as mem

    def fake_persist(cid, sessao):
        sessao_store.clear()
        sessao_store.update(sessao)
        return True

    def fake_carregar(cliente, cid):
        base = mem.sessao_vazia()
        base.update(sessao_store)
        return base

    monkeypatch.setattr(mem, "persistir_sessao", fake_persist)
    monkeypatch.setattr(mem, "carregar_sessao", fake_carregar)

    out1 = api_mod.processar_mensagem(
        _data("quero comprar o headset gamer", mid="e11a"),
        dry_run=True,
        persistir=True,
    )
    assert out1["persistencia_ok"] is True
    out2 = api_mod.processar_mensagem(
        _data("prefiro entrega", mid="e11b"),
        dry_run=True,
        persistir=True,
    )
    assert out2["persistencia_ok"] is True
    assert "cidade" in (out2["resposta"] or "").lower() or "entrega" in (out2["resposta"] or "").lower()
    out3 = api_mod.processar_mensagem(
        _data("sou de Londrina", mid="e11c"),
        dry_run=True,
        persistir=True,
    )
    assert out3["persistencia_ok"] is True
    assert out3["persistencia_etapas"]["cliente_ok"] is True
    assert out3["persistencia_etapas"]["contexto_ok"] is True
    assert out3["persistencia_etapas"]["historico_ok"] is True


def test_cliente_debug_dry_run(monkeypatch):
    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-dbg", "telefone": "5543999999993", "nome": "Arthur"},
    )
    out = api_mod.processar_mensagem(_data(mid="e-dbg"), dry_run=True, persistir=True)
    dbg = out.get("cliente_debug") or {}
    assert dbg.get("tem_cliente_id") is True
    assert dbg.get("origem_cliente") == "telefone"
    assert dbg.get("cliente_ok_final") is True
    assert dbg.get("contexto_salvo_em") == "banco"
    assert dbg.get("historico_salvo_em") == "banco"
    assert "5543999999993" not in str(dbg)


def test_ephemeral_nao_finge_historico_contexto_ok(monkeypatch):
    """Regressão prod: etapas não podem ficar True por valor inicial no fallback."""
    _patch_fluxo(monkeypatch, cliente=None)
    monkeypatch.setattr(api_mod, "criar_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "buscar_cliente", lambda *_a, **_k: None)
    out = api_mod.processar_mensagem(_data(mid="e-eph"), dry_run=True, persistir=True)
    et = out["persistencia_etapas"]
    assert et["cliente_ok"] is False
    assert et["contexto_ok"] is False
    assert et["historico_ok"] is False
    assert out["persistencia_ok"] is False
    assert (out.get("cliente_debug") or {}).get("origem_cliente") == "ephemeral"


# 12
def test_persistir_false(monkeypatch):
    _patch_fluxo(monkeypatch, cliente=None)
    out = api_mod.processar_mensagem(_data(mid="e12"), dry_run=True, persistir=False)
    assert out["resposta"]


# 13
def test_webhook_e_version():
    assert hasattr(api_mod, "webhook")
    assert api_mod.CODE_VERSION == "2026-07-13-fix-catalogo-geral"


# 14
def test_dry_run_sem_pedido(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "true")
    r = avaliar_checkout(
        mensagem="ok",
        sessao={
            "produto_ativo": "Headset",
            "preco_cotado": 10,
            "forma_entrega": "retirada",
            "quantidade": 1,
            "forma_pagamento": "PIX",
        },
        produtos=[{"name": "Headset", "price": 10, "stock_quantity": 5, "stock_confirmed": True}],
        intent="COMPRA",
        dry_run=True,
        persistir=True,
    )
    with patch("services.pedido_mercos_service.criar_pedido_fechamento_mercos") as m:
        out = criar_pedido_se_permitido(
            resultado={**r, "can_create_order": True},
            historico_texto="",
            cliente_supabase={"id": "1"},
            telefone="5511",
            dry_run=True,
            persistir=True,
        )
        m.assert_not_called()
        assert out.get("pedido") is None


# 15
def test_create_order_false(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    r = avaliar_checkout(
        mensagem="ok",
        sessao={
            "produto_ativo": "Headset",
            "preco_cotado": 10,
            "forma_entrega": "retirada",
            "quantidade": 1,
            "forma_pagamento": "PIX",
        },
        produtos=[{"name": "Headset", "price": 10, "stock_quantity": 5, "stock_confirmed": True}],
        intent="COMPRA",
        dry_run=False,
        persistir=True,
    )
    assert r["can_create_order"] is False


def test_criar_cliente_insert_minimo_sem_celular(monkeypatch):
    inserted = {}
    sb._SCHEMA_FLAGS["clientes_celular"] = False

    class FakeTable:
        def select(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def insert(self, payload):
            inserted.update(payload)
            return self

        def execute(self):
            return MagicMock(data=[{"id": "cli-min", **inserted}])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable()))
    # evita detect sobrescrever flag
    monkeypatch.setattr(sb, "_detectar_colunas_clientes", lambda: set())
    row = sb.criar_cliente("5543999999993", nome="Arthur")
    assert "celular" not in inserted
    assert inserted["telefone"] == "5543999999993"
    assert inserted["nome"] == "Arthur"
    assert row["id"] == "cli-min"
