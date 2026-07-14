"""Garante preenchimento de conversas.cliente_id (uuid) sem remover cliente_mercos_id."""

from unittest.mock import MagicMock

import services.supabase_service as sb


def test_resolver_cliente_id_por_mercos(monkeypatch):
    monkeypatch.setattr(
        sb,
        "_executar",
        lambda fn, *_a, **_k: MagicMock(data=[{"id": "uuid-cliente-1"}]),
    )
    monkeypatch.setattr(sb, "buscar_cliente", lambda *_a, **_k: None)
    cid = sb.resolver_cliente_id_conversa(cliente_mercos_id="9255263", telefone=None)
    assert cid == "uuid-cliente-1"


def test_resolver_cliente_id_por_telefone_quando_sem_mercos(monkeypatch):
    monkeypatch.setattr(
        sb,
        "buscar_cliente",
        lambda tel: {"id": "uuid-por-tel", "telefone": tel},
    )
    cid = sb.resolver_cliente_id_conversa(
        cliente_mercos_id=None,
        telefone="5543999000111",
    )
    assert cid == "uuid-por-tel"


def test_resolver_cliente_id_null_quando_nao_existe(monkeypatch):
    monkeypatch.setattr(
        sb,
        "_executar",
        lambda *_a, **_k: MagicMock(data=[]),
    )
    monkeypatch.setattr(sb, "buscar_cliente", lambda *_a, **_k: None)
    assert (
        sb.resolver_cliente_id_conversa(
            cliente_mercos_id="999",
            telefone="5543000000000",
        )
        is None
    )


def test_conversa_nova_preenche_cliente_id_quando_cliente_existe(monkeypatch):
    sb._SCHEMA_FLAGS["conversas_thread"] = True
    sb._SCHEMA_FLAGS["conversas_cliente_id_uuid"] = True
    sb._SCHEMA_FLAGS["message_id"] = False

    inserts: list[dict] = []

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

        def insert(self, payload):
            inserts.append(dict(payload))
            return self

        def update(self, payload):
            return self

        def execute(self):
            if self.name == "clientes":
                if self._eq and self._eq[0] in ("telefone", "celular"):
                    return MagicMock(
                        data=[
                            {
                                "id": "cli-uuid-99",
                                "telefone": self._eq[1],
                                "mercos_id": 9255263,
                            }
                        ]
                    )
                return MagicMock(data=[])
            # conversas: nenhuma thread prévia → INSERT
            return MagicMock(data=[])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable(n)))
    monkeypatch.setenv("PULSEDESK_AGENT_CANAL_ID", "")

    ok = sb.atualizar_thread_conversa(
        "5543999000111",
        "Cliente Teste",
        "quero orçamento",
        message_id=None,
        inbound=True,
    )
    assert ok is True
    assert inserts, "deveria criar conversa nova"
    payload = inserts[0]
    assert payload["cliente_id"] == "cli-uuid-99"


def test_conversa_nova_com_mercos_preenche_cliente_id_e_mantem_mercos(monkeypatch):
    sb._SCHEMA_FLAGS["conversas_thread"] = True
    sb._SCHEMA_FLAGS["conversas_cliente_id_uuid"] = True
    sb._SCHEMA_FLAGS["message_id"] = False

    inserts: list[dict] = []

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

        def insert(self, payload):
            inserts.append(dict(payload))
            return self

        def update(self, payload):
            return self

        def execute(self):
            if self.name == sb.TABELA_CLIENTES or self.name == "clientes":
                if self._eq and self._eq[0] == "mercos_id" and int(self._eq[1]) == 9255263:
                    return MagicMock(data=[{"id": "cli-uuid-mercos"}])
                return MagicMock(data=[])
            return MagicMock(data=[])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable(n)))
    monkeypatch.setattr(sb, "buscar_cliente", lambda *_a, **_k: None)
    monkeypatch.setenv("PULSEDESK_AGENT_CANAL_ID", "")

    ok = sb.atualizar_thread_conversa(
        "5543999000222",
        "Mercos Cliente",
        "oi",
        inbound=True,
        cliente_mercos_id="9255263",
    )
    assert ok is True
    assert inserts
    assert inserts[0]["cliente_id"] == "cli-uuid-mercos"
    assert inserts[0]["cliente_mercos_id"] == "9255263"


def test_conversa_nova_sem_cliente_deixa_cliente_id_ausente(monkeypatch):
    sb._SCHEMA_FLAGS["conversas_thread"] = True
    sb._SCHEMA_FLAGS["conversas_cliente_id_uuid"] = True
    sb._SCHEMA_FLAGS["message_id"] = False

    inserts: list[dict] = []

    class FakeTable:
        def __init__(self, name):
            self.name = name

        def select(self, *_a, **_k):
            return self

        def eq(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def insert(self, payload):
            inserts.append(dict(payload))
            return self

        def execute(self):
            return MagicMock(data=[])

    monkeypatch.setattr(sb, "supabase", MagicMock(table=lambda n: FakeTable(n)))
    monkeypatch.setattr(sb, "buscar_cliente", lambda *_a, **_k: None)
    monkeypatch.setenv("PULSEDESK_AGENT_CANAL_ID", "")

    ok = sb.atualizar_thread_conversa(
        "5543999000333", "Novo", "ola", inbound=True
    )
    assert ok is True
    assert inserts
    assert "cliente_id" not in inserts[0]
