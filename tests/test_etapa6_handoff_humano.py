"""Etapa 6 — handoff humano + resumo_vendedor."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import MagicMock

import routes.api as api_mod
from fastapi.testclient import TestClient
from services.handoff_service import (
    montar_resumo_vendedor,
    processar_handoff,
)
from services.intent_service import classificar_intencao
from services.vendas.memoria import SESSAO_PADRAO, serializar_contexto_venda


def _c(msg: str):
    return classificar_intencao(msg)


def _ctx_mock(**kwargs):
    base = dict(
        produtos=[
            {
                "id": "1",
                "name": "Headset Gamer",
                "nome": "Headset Gamer",
                "price": 249.9,
                "preco": 249.9,
                "stock_quantity": 5,
                "stock_confirmed": True,
            }
        ],
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


def _data(msg="quero falar com atendente", tel="5543999999993", mid=None, nome="Arthur"):
    return {
        "event_type": "message_received",
        "provider": "chat_teste",
        "data": {
            "from": tel,
            "body": msg,
            "pushname": nome,
            "fromMe": False,
            "type": "chat",
            "id": mid or f"chat-ho-{abs(hash(msg + tel)) % 10_000_000}",
            "time": __import__("time").time(),
        },
    }


def _patch_fluxo(monkeypatch, *, cliente=None, sessao_inicial=None, capturar_sessao=None):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    monkeypatch.setattr(api_mod, "buscar_cliente", lambda *_a, **_k: cliente)
    monkeypatch.setattr(
        api_mod,
        "criar_cliente",
        lambda tel, nome="": {
            "id": "cli-ho",
            "telefone": tel,
            "nome": nome or "WhatsApp",
            "contexto_venda": deepcopy(sessao_inicial or {}),
        },
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

    pedidos = {"chamadas": 0}

    def _criar_pedido(*_a, **_k):
        pedidos["chamadas"] += 1
        raise AssertionError("criar_pedido não deve ser chamado no handoff")

    monkeypatch.setattr(
        "services.checkout_service.criar_pedido_se_permitido",
        _criar_pedido,
    )

    import services.vendas.memoria as mem

    def _persistir(cid, sessao):
        if capturar_sessao is not None:
            capturar_sessao.append(deepcopy(sessao))
        return True

    monkeypatch.setattr(mem, "persistir_sessao", _persistir)
    from services.webhook_service import _IDS_PROCESSADOS
    from services import webhook_guard as wg

    _IDS_PROCESSADOS.clear()
    wg._IDS_ESTADO.clear()
    monkeypatch.setattr("services.supabase_service.mensagem_ja_existe", lambda *_a, **_k: False)
    return pedidos


def test_code_version_etapa6():
    assert api_mod.CODE_VERSION == "2026-07-13-etapa6-handoff-humano"


def test_intent_quero_falar_com_atendente():
    r = _c("quero falar com atendente")
    assert r["intent"] == "ATENDIMENTO_HUMANO"
    assert r["needs_human"] is True


def test_intent_tem_humano():
    r = _c("tem humano?")
    assert r["intent"] == "ATENDIMENTO_HUMANO"


def test_intent_quero_negociar():
    r = _c("quero negociar")
    assert r["intent"] == "ATENDIMENTO_HUMANO"


def test_intent_frases_extras():
    for msg in (
        "chama alguém",
        "quero falar com uma pessoa",
        "não quero falar com robô",
        "não entendi",
        "isso não resolveu",
    ):
        assert _c(msg)["intent"] == "ATENDIMENTO_HUMANO", msg


def test_resumo_aproveita_checkout():
    sessao = {
        "produto_checkout": "Headset Gamer",
        "preco_cotado": 249.9,
        "quantidade": 2,
        "forma_entrega": "entrega",
        "cidade": "Londrina",
        "endereco": "Rua A, 100",
        "forma_pagamento": "pix",
        "estagio_conversa": "fechamento",
        "nome_cliente": "Arthur",
    }
    resumo = montar_resumo_vendedor(
        sessao, nome_cliente="Arthur", telefone="5543999999993"
    )
    assert resumo["produto_interesse"] == "Headset Gamer"
    assert resumo["preco_cotado"] == 249.9
    assert resumo["quantidade"] == 2
    assert resumo["forma_entrega"] == "entrega"
    assert resumo["cidade"] == "Londrina"
    assert resumo["endereco"] == "Rua A, 100"
    assert resumo["forma_pagamento"] == "pix"
    assert resumo["telefone"] == "5543999999993"
    assert resumo["resumo_curto"]


def test_resumo_sem_inventar():
    resumo = montar_resumo_vendedor({}, nome_cliente="", telefone="")
    assert resumo["produto_interesse"] is None
    assert resumo["preco_cotado"] is None
    assert resumo["quantidade"] is None
    assert resumo["cidade"] is None


def test_processar_handoff_marca_sessao():
    out = processar_handoff(
        {"produto_ativo": "Mouse"},
        nome_cliente="Tironi",
        telefone="5543999999999",
    )
    s = out["sessao"]
    assert s["precisa_humano"] is True
    assert s["motivo_handoff"] == "cliente pediu atendimento humano"
    assert s["handoff_status"] == "pendente"
    assert isinstance(s["resumo_vendedor"], dict)
    assert s["resumo_vendedor"]["produto_interesse"] == "Mouse"
    assert out["pedido_criado"] is False
    assert "humano" in (out["reply"] or "").lower()


def test_serializar_contexto_inclui_handoff():
    for k in ("precisa_humano", "motivo_handoff", "handoff_status", "resumo_vendedor"):
        assert k in SESSAO_PADRAO
    s = processar_handoff(
        {"produto_checkout": "Notebook", "preco_cotado": 3499.9},
        nome_cliente="Tironi",
        telefone="5543",
    )["sessao"]
    limpo = serializar_contexto_venda(s)
    assert limpo["precisa_humano"] is True
    assert limpo["resumo_vendedor"]["produto_interesse"] == "Notebook"


def test_fluxo_atendente_salva_contexto(monkeypatch):
    capturados: list = []
    pedidos = _patch_fluxo(
        monkeypatch,
        cliente={
            "id": "cli-ho1",
            "telefone": "5543999999993",
            "nome": "Arthur",
            "contexto_venda": {
                "produto_checkout": "Headset Gamer",
                "preco_cotado": 249.9,
                "quantidade": 1,
                "forma_entrega": "retirada",
                "cidade": "Londrina",
            },
        },
        capturar_sessao=capturados,
    )
    out = api_mod.processar_mensagem(
        _data("quero falar com atendente", mid="ho-1"),
        dry_run=True,
        persistir=True,
    )
    assert out["persistencia_ok"] is True
    assert out["handoff_debug"]["handoff_detectado"] is True
    assert out["handoff_debug"]["precisa_humano"] is True
    assert out["handoff_debug"]["resumo_vendedor_gerado"] is True
    assert pedidos["chamadas"] == 0
    assert capturados, "contexto_venda deveria ter sido persistido"
    ultima = capturados[-1]
    assert ultima["precisa_humano"] is True
    assert ultima["handoff_status"] == "pendente"
    assert ultima["resumo_vendedor"]["produto_interesse"] == "Headset Gamer"
    assert ultima["resumo_vendedor"]["forma_entrega"] == "retirada"
    assert ultima["resumo_vendedor"]["cidade"] == "Londrina"
    assert "humano" in (out["resposta"] or "").lower()
    assert "pix" not in (out["resposta"] or "").lower()


def test_chat_dry_run_retorna_handoff_debug(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    _patch_fluxo(
        monkeypatch,
        cliente={
            "id": "cli-ho2",
            "telefone": "5543999999993",
            "nome": "Arthur",
            "contexto_venda": {},
        },
    )
    from main import app

    client = TestClient(app)
    resp = client.post(
        "/chat",
        json={
            "telefone": "5543999999993",
            "mensagem": "tem humano?",
            "nome": "Arthur",
            "dry_run": True,
            "persistir": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["code_version"] == "2026-07-13-etapa6-handoff-humano"
    assert "handoff_debug" in data
    assert data["handoff_debug"]["handoff_detectado"] is True
    assert data["handoff_debug"]["precisa_humano"] is True
    assert data["persistencia_ok"] is True


def test_chat_catalogo_continua_ok(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    produtos = [
        {
            "nome": "HD Externo 1 TB",
            "preco": 429.9,
            "saldo_estoque": 33,
            "stock_confirmed": True,
            "stock_quantity": 33,
        }
    ]

    def _ps(limit=8):
        return {
            "found": True,
            "products": [
                {
                    "name": p["nome"],
                    "nome": p["nome"],
                    "price": p["preco"],
                    "preco": p["preco"],
                    "stock_confirmed": True,
                    "stock_quantity": p["saldo_estoque"],
                    "saldo_estoque": p["saldo_estoque"],
                }
                for p in produtos
            ],
            "message": "ok",
            "fonte": "supabase",
            "catalogo": "fake",
        }

    monkeypatch.setattr(
        "services.vendas.catalogo.montar_catalogo_geral",
        lambda limite=20: {"produtos": produtos, "catalogo": "fake", "fonte": "supabase"},
    )
    monkeypatch.setattr("services.product_service.listar_produtos_catalogo", _ps)
    monkeypatch.setattr("services.product_service.buscar_por_intencao", lambda **_k: _ps())

    from main import app

    client = TestClient(app)
    resp = client.post(
        "/chat",
        json={
            "telefone": "5543999999999",
            "mensagem": "mande o catalogo",
            "nome": "Tironi",
            "dry_run": True,
            "persistir": False,
        },
    )
    data = resp.json()
    assert data["code_version"] == "2026-07-13-etapa6-handoff-humano"
    assert "catálogo" in data["resposta"].lower() or "opções" in data["resposta"].lower()
    assert data["handoff_debug"]["handoff_detectado"] is False
    assert data["persistencia_ok"] is True


def test_produto_inexistente_continua(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    _patch_fluxo(
        monkeypatch,
        cliente={
            "id": "cli-ho3",
            "telefone": "5543999999993",
            "nome": "Arthur",
            "contexto_venda": {},
        },
    )
    monkeypatch.setattr(
        "services.product_service.buscar_por_intencao",
        lambda **_k: {
            "found": False,
            "products": [],
            "message": "nao encontrado",
            "category": "",
            "catalogo": "",
            "fonte": "supabase",
            "sem_match": True,
        },
    )
    monkeypatch.setattr(
        api_mod,
        "preparar_contexto_venda",
        lambda **_k: _ctx_mock(
            produtos=[],
            sem_match=True,
            termos_cliente=["unicornio"],
            memoria=_k.get("memoria") or {},
        ),
    )
    out = api_mod.processar_mensagem(
        _data("quero um unicornio voador", mid="ho-inex"),
        dry_run=True,
        persistir=True,
    )
    assert out["persistencia_ok"] is True
    assert out.get("resposta")
    assert "humano" not in (out.get("handoff_debug") or {}) or out["handoff_debug"][
        "handoff_detectado"
    ] is False
