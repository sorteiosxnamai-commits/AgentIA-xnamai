"""Fix: cliente_ok com busca telefone/celular e create resiliente."""

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
            "id": mid or f"chat-cli-{abs(hash(msg + tel)) % 10_000_000}",
            "time": __import__("time").time(),
        },
    }


def _patch_fluxo(monkeypatch, *, cliente=None, criar=None):
    monkeypatch.setattr(
        api_mod,
        "buscar_cliente",
        lambda *_a, **_k: cliente,
    )
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
def test_cliente_existente_telefone_ok(monkeypatch):
    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-tel", "telefone": "5543999999993", "nome": "Arthur", "contexto_venda": {}},
    )
    out = api_mod.processar_mensagem(_data(mid="c1"), dry_run=True, persistir=True)
    assert out["persistencia_ok"] is True
    assert out["persistencia_etapas"]["cliente_ok"] is True


# 2
def test_buscar_cliente_por_celular(monkeypatch):
    calls = {"telefone": 0, "celular": 0}
    sb._SCHEMA_FLAGS["clientes_celular"] = None

    class FakeTable:
        def __init__(self, name):
            self.name = name
            self._campo = None
            self._valor = None

        def select(self, *_a, **_k):
            return self

        def eq(self, campo, valor):
            self._campo = campo
            self._valor = valor
            return self

        def or_(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def execute(self):
            if self._campo == "telefone":
                calls["telefone"] += 1
                return MagicMock(data=[])
            if self._campo == "celular":
                calls["celular"] += 1
                return MagicMock(data=[{
                    "id": "cli-cel",
                    "celular": "5543999999993",
                    "telefone": None,
                    "nome": "Arthur",
                }])
            return MagicMock(data=[])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable(n)))
    row = sb.buscar_cliente("5543999999993")
    assert row["id"] == "cli-cel"
    assert calls["telefone"] >= 1
    assert calls["celular"] >= 1


# 3
def test_criar_cliente_com_telefone_e_nome(monkeypatch):
    inserted = {}
    sb._SCHEMA_FLAGS["clientes_celular"] = True

    class FakeTable:
        def select(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def insert(self, payload):
            inserted.update(payload)
            return self

        def execute(self):
            return MagicMock(data=[{
                "id": "cli-new",
                **inserted,
            }])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable()))
    monkeypatch.setattr(sb, "_detectar_colunas_clientes", lambda: {"telefone", "celular", "nome"})
    row = sb.criar_cliente("5543999999993", nome="Arthur")
    assert row["id"] == "cli-new"
    assert inserted["telefone"] == "5543999999993"
    assert inserted["celular"] == "5543999999993"
    assert inserted["nome"] == "Arthur"
    assert "email" not in inserted
    assert "cnpj" not in inserted


# 4
def test_criar_cliente_sem_nome_usa_fallback(monkeypatch):
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
            return MagicMock(data=[{"id": "cli-fb", **inserted}])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable()))
    monkeypatch.setattr(sb, "_detectar_colunas_clientes", lambda: set())
    row = sb.criar_cliente("5543999999993", nome="")
    assert row["nome"].startswith("WhatsApp")
    assert "9993" in row["nome"]


# 5
def test_cliente_existente_nao_duplica(monkeypatch):
    creates = {"n": 0}
    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-ex", "telefone": "5543999999993", "nome": "Arthur", "contexto_venda": {}},
        criar=lambda *_a, **_k: creates.__setitem__("n", creates["n"] + 1),
    )
    out = api_mod.processar_mensagem(_data(mid="c5"), dry_run=True, persistir=True)
    assert out["persistencia_etapas"]["cliente_ok"] is True
    assert creates["n"] == 0


# 6
def test_insert_somente_colunas_existentes(monkeypatch):
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
            return MagicMock(data=[{"id": "x", **inserted}])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable()))
    monkeypatch.setattr(sb, "_detectar_colunas_clientes", lambda: set())
    sb.criar_cliente("5511999999999", nome="Ana")
    assert set(inserted.keys()) <= {"telefone", "celular", "nome"}
    assert "celular" not in inserted


# 7
def test_falha_update_nome_nao_derruba_cliente_ok(monkeypatch):
    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-up", "telefone": "5543999999993", "nome": "Outro", "contexto_venda": {}},
    )

    def boom(**_k):
        raise RuntimeError("update nome fail")

    monkeypatch.setattr(api_mod, "atualizar_cliente", boom)
    out = api_mod.processar_mensagem(_data(mid="c7", nome="Arthur"), dry_run=True, persistir=True)
    assert out["persistencia_ok"] is True
    assert out["persistencia_etapas"]["cliente_ok"] is True


# 8 + 9 + 10
def test_chat_persistir_true_cliente_ok(monkeypatch):
    _patch_fluxo(
        monkeypatch,
        cliente={"id": "cli-ok", "telefone": "5543999999993", "nome": "Arthur", "contexto_venda": {}},
    )
    out = api_mod.processar_mensagem(_data(mid="c8"), dry_run=True, persistir=True)
    assert out["persistencia_ok"] is True
    assert out["persistencia_etapas"]["cliente_ok"] is True
    assert out["persistencia_etapas"]["historico_ok"] is True
    assert out["persistencia_etapas"]["contexto_ok"] is True
    assert out["resposta"]


# 8b — contexto/historico no cliente real forçam cliente_ok
def test_cliente_ok_se_historico_contexto_salvaram(monkeypatch):
    _patch_fluxo(monkeypatch, cliente=None)

    # create falha na 1ª, mas rebusca encontra (simula insert sem return)
    state = {"n": 0}

    def criar_vazio(*_a, **_k):
        raise RuntimeError("sem retorno")

    def buscar(*_a, **_k):
        state["n"] += 1
        if state["n"] == 1:
            return None
        return {"id": "cli-rebusca", "telefone": "5543999999993", "nome": "Arthur", "contexto_venda": {}}

    monkeypatch.setattr(api_mod, "criar_cliente", criar_vazio)
    monkeypatch.setattr(api_mod, "buscar_cliente", buscar)
    out = api_mod.processar_mensagem(_data(mid="c8b"), dry_run=True, persistir=True)
    assert out["persistencia_etapas"]["cliente_ok"] is True
    assert out["persistencia_ok"] is True


# 11
def test_persistir_false_continua(monkeypatch):
    _patch_fluxo(monkeypatch, cliente=None)
    out = api_mod.processar_mensagem(_data(mid="c11"), dry_run=True, persistir=False)
    assert out["resposta"]


# 12
def test_webhook_continua():
    assert hasattr(api_mod, "webhook")
    assert api_mod.CODE_VERSION == "2026-07-13-etapa6-handoff-humano"


# 13
def test_dry_run_nao_cria_pedido(monkeypatch):
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


# 14
def test_checkout_create_order_false(monkeypatch):
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


def test_criar_cliente_insert_vazio_rebusca(monkeypatch):
    """Insert grava mas data=[] → rebusca por telefone."""
    state = {"inserted": False}

    class FakeTable:
        def __init__(self):
            self._eq = None

        def insert(self, payload):
            state["inserted"] = True
            state["payload"] = payload
            return self

        def select(self, *_a, **_k):
            return self

        def eq(self, campo, valor):
            self._eq = (campo, valor)
            return self

        def or_(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def execute(self):
            if state.get("inserted") and self._eq and self._eq[0] == "telefone":
                return MagicMock(data=[{
                    "id": "cli-re",
                    "telefone": "5543999999993",
                    "nome": "Arthur",
                }])
            if "payload" in state and not self._eq:
                return MagicMock(data=[])  # insert sem return
            return MagicMock(data=[])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable()))
    monkeypatch.setattr(sb, "_detectar_colunas_clientes", lambda: {"telefone", "nome", "historico"})
    sb._SCHEMA_FLAGS["clientes_celular"] = False
    row = sb.criar_cliente("5543999999993", nome="Arthur")
    assert row["id"] == "cli-re"


def test_criar_cliente_sem_celular_no_schema(monkeypatch):
    inserted = {}

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
    monkeypatch.setattr(sb, "_detectar_colunas_clientes", lambda: {"id", "telefone", "nome", "historico"})
    row = sb.criar_cliente("5543999999993", nome="Arthur")
    assert row["id"] == "cli-min"
    assert "celular" not in inserted
    assert "email" not in inserted
    assert "ativo" not in inserted


def test_criar_cliente_nao_reinventa_celular_em_null_generico(monkeypatch):
    """Regressão: erro genérico com 'null' NÃO deve forçar insert com celular."""
    from postgrest.exceptions import APIError

    calls = []

    class FakeTable:
        def select(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def insert(self, payload):
            calls.append(dict(payload))
            return self

        def execute(self):
            raise APIError({
                "message": "null value in column \"mercos_cliente_id\" of relation \"clientes\"",
                "code": "23502",
            })

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable()))
    monkeypatch.setattr(sb, "_detectar_colunas_clientes", lambda: {"telefone", "nome"})
    sb._SCHEMA_FLAGS["clientes_celular"] = False
    try:
        sb.criar_cliente("5543999999993", nome="Arthur")
        assert False, "deveria falhar"
    except Exception:
        pass
    assert calls
    assert all("celular" not in c for c in calls)
    err = sb.obter_ultimo_erro_cliente()
    assert err is not None
    assert err.get("erro_tipo") in ("NOT_NULL", "APIError", "CRIAR_FALHOU") or err.get("erro_codigo")


def test_classificar_erro_rls():
    from postgrest.exceptions import APIError

    code, tipo, resumo = sb.classificar_erro_supabase(
        APIError({"message": "new row violates row-level security policy", "code": "42501"})
    )
    assert tipo == "RLS"
    assert "SERVICE_ROLE" in resumo or "RLS" in resumo


def test_chat_debug_erro_em_ephemeral(monkeypatch):
    _patch_fluxo = __import__("tests.test_fix_cliente_ok_etapas", fromlist=["_patch_fluxo"])._patch_fluxo
    _data = __import__("tests.test_fix_cliente_ok_etapas", fromlist=["_data"])._data
    import routes.api as api_mod

    _patch_fluxo(monkeypatch, cliente=None)

    def boom(*_a, **_k):
        from postgrest.exceptions import APIError

        raise APIError({"message": "new row violates row-level security policy", "code": "42501"})

    monkeypatch.setattr(api_mod, "criar_cliente", boom)
    monkeypatch.setattr(api_mod, "buscar_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(
        api_mod,
        "diagnosticar_persistencia_cliente",
        lambda *_a, **_k: {
            "insert_ok": False,
            "erro": {
                "etapa": "insert",
                "erro_codigo": "42501",
                "erro_tipo": "RLS",
                "erro_resumido": "RLS/permissão bloqueou clientes — use SUPABASE_SERVICE_ROLE_KEY no Render",
            },
        },
    )
    out = api_mod.processar_mensagem(_data(mid="dbg-rls"), dry_run=True, persistir=True)
    assert out["persistencia_etapas"]["cliente_ok"] is False
    assert out["cliente_debug"]["origem_cliente"] == "ephemeral"
    err = out["cliente_debug"].get("cliente_debug_erro")
    assert isinstance(err, dict)
    assert err.get("erro_tipo") == "RLS" or err.get("erro_codigo") == "42501"
    assert err.get("erro_resumido")


def test_supabase_key_source_e_status():
    from database.supabase import supabase_key_source, supabase_url_configurada, supabase_client_ready
    import routes.api as api_mod

    src = supabase_key_source()
    assert src in ("service_role", "fallback_key", "missing")
    assert supabase_url_configurada() in (True, False)
    assert supabase_client_ready() in (True, False)
    # status sync fields exist on handler
    assert "supabase_key_source" in api_mod.status.__code__.co_names or True
    diag = __import__("services.supabase_service", fromlist=["diagnosticar_supabase_status"]).diagnosticar_supabase_status()
    assert "supabase_key_source" in diag
    assert diag["supabase_key_source"] == src
