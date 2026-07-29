"""POST /chat — busca 'adaptador de tomada' usa catálogo ranqueado (sem Supabase real)."""

from __future__ import annotations

import routes.api as api_mod
from services.intent_service import classificar_intencao
from services.product_service import buscar_por_intencao, normalizar_produto_servico
from services.vendas.respostas import (
    cliente_quer_ver_catalogo,
    mensagem_tem_produto_especifico,
    resposta_busca_produtos,
)
from services.xnamai_script import cliente_perguntou_estoque

MSG = (
    "Estou procurando um adaptador de tomada. "
    "Quais opcoes voce tem com estoque?"
)

CATALOGO = [
    {
        "nome": "Adaptador de Tomada Universal",
        "preco": 12.9,
        "saldo_estoque": 420,
        "codigo": "ADT-UNI",
        "categoria": "adaptadores",
    },
    {
        "nome": "Adaptador de Tomada Benjamin",
        "preco": 18.5,
        "saldo_estoque": 477,
        "codigo": "ADT-BEN",
        "categoria": "adaptadores",
    },
    {
        "nome": "Adaptador de Tomada Cubo",
        "preco": 24.9,
        "saldo_estoque": 221,
        "codigo": "ADT-CUB",
        "categoria": "adaptadores",
    },
    {
        "nome": "Pilha Recarregável AA",
        "preco": 29.9,
        "saldo_estoque": 50,
        "codigo": "PIL-AA",
        "categoria": "pilhas",
    },
    {
        "nome": "Mochila Notebook Premium",
        "preco": 199.9,
        "saldo_estoque": 10,
        "codigo": "MOC-NB",
        "categoria": "mochilas",
    },
    {
        "nome": "Adaptador de Tomada Sem Estoque",
        "preco": 9.9,
        "saldo_estoque": 0,
        "codigo": "ADT-ZERO",
        "categoria": "adaptadores",
    },
]


def _data(msg=MSG, tel="5543000000001", mid=None, nome="Arthur Teste"):
    return {
        "event_type": "message_received",
        "provider": "chat_teste",
        "data": {
            "from": tel,
            "body": msg,
            "pushname": nome,
            "fromMe": False,
            "type": "chat",
            "id": mid or f"chat-adt-{abs(hash(msg + tel)) % 10_000_000}",
            "time": __import__("time").time(),
        },
    }


def _patch_persistencia(monkeypatch):
    gravacoes = {
        "cliente": 0,
        "historico": 0,
        "lead": 0,
        "whatsapp": 0,
        "mensagem": 0,
    }

    def _inc(chave):
        def _fn(*_a, **_k):
            gravacoes[chave] += 1
            if chave == "cliente":
                return {"id": "cli-adt", "telefone": "5543000000001", "nome": "Arthur"}
            if chave == "whatsapp":
                return {"ok": True}
            if chave == "lead":
                return {"notificado": False}
            return {"ok": True}

        return _fn

    monkeypatch.setattr(api_mod, "buscar_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "criar_cliente", _inc("cliente"))
    monkeypatch.setattr(api_mod, "atualizar_cliente", lambda **_k: None)
    monkeypatch.setattr(api_mod, "buscar_historico", lambda *_a, **_k: [])
    monkeypatch.setattr(api_mod, "salvar_mensagem", _inc("mensagem"))
    monkeypatch.setattr(api_mod, "atualizar_historico_json", _inc("historico"))
    monkeypatch.setattr(api_mod, "atualizar_thread_conversa", lambda *_a, **_k: True)
    monkeypatch.setattr(api_mod, "espelhar_mensagem_cliente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "espelhar_mensagem_agente", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "enviar_mensagem", _inc("whatsapp"))
    monkeypatch.setattr(api_mod, "processar_lead_e_notificar", _inc("lead"))
    monkeypatch.setattr(api_mod, "resolver_estado_venda", lambda *_a, **_k: "negociando")
    monkeypatch.setattr(api_mod, "eh_saudacao", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "extrair_nome_do_historico", lambda *_a, **_k: "Arthur")
    monkeypatch.setattr(api_mod, "cliente_quer_nova_venda", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "negociacao_nova_apos_fechamento", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "produtos_com_foto_disponivel", lambda *_a, **_k: [])
    monkeypatch.setattr(api_mod, "cliente_pediu_foto", lambda *_a, **_k: False)
    monkeypatch.setattr(api_mod, "finalizar_mensagem", lambda *_a, **_k: None)
    monkeypatch.setattr(api_mod, "perguntar_ia", lambda **_k: "FALLBACK_IA_NAO_DEVERIA")

    import services.vendas.memoria as mem

    monkeypatch.setattr(mem, "persistir_sessao", lambda *_a, **_k: True)
    from services.webhook_service import _IDS_PROCESSADOS
    from services import webhook_guard as wg

    _IDS_PROCESSADOS.clear()
    wg._IDS_ESTADO.clear()
    monkeypatch.setattr("services.supabase_service.mensagem_ja_existe", lambda *_a, **_k: False)
    return gravacoes


def _patch_catalogo(monkeypatch):
    monkeypatch.setattr(
        "services.vendas.catalogo.buscar_produtos",
        lambda: list(CATALOGO),
    )
    monkeypatch.setattr(
        "services.vendas.catalogo._usar_somente_supabase",
        lambda: True,
    )
    monkeypatch.setattr(
        "services.vendas.catalogo._amostra_produtos_reais",
        lambda limite=4: [
            {"nome": "Headset Gamer X", "preco": 99.0, "saldo_estoque": 1}
        ],
    )


def test_mensagem_nao_e_catalogo_geral_nem_estoque_unitario():
    assert mensagem_tem_produto_especifico(MSG) is True
    assert cliente_quer_ver_catalogo(MSG) is False
    assert cliente_perguntou_estoque(MSG) is False
    intent = classificar_intencao(MSG)
    assert intent["intent"] == "BUSCA_PRODUTO"
    assert intent.get("category") == "adaptador"
    assert "adaptador" in (intent.get("product_query") or "").lower()


def test_buscar_por_intencao_so_adaptadores_com_estoque(monkeypatch):
    _patch_catalogo(monkeypatch)
    r = buscar_por_intencao(
        mensagem=MSG,
        intent="BUSCA_PRODUTO",
        product_query=MSG,
        categoria_ativa="adaptador",
        limite=20,
    )
    assert r["found"] is True
    nomes = [p["name"] for p in r["products"]]
    assert all("adaptador" in n.lower() and "tomada" in n.lower() for n in nomes)
    assert all("pilha" not in n.lower() for n in nomes)
    assert all("mochila" not in n.lower() for n in nomes)
    assert "Adaptador de Tomada Sem Estoque" not in nomes
    assert len(nomes) >= 3
    # Com estoque: Cubo/Benjamin/Universal antes de qualquer zerado
    assert all(
        (p.get("stock_quantity") or 0) > 0 for p in r["products"]
    )


def test_resposta_busca_adaptador_continuacao_relacionada():
    produtos = [
        normalizar_produto_servico(p, source="supabase") for p in CATALOGO[:3]
    ]
    texto = resposta_busca_produtos(
        nome_cliente="Arthur Teste",
        produtos=produtos,
        mensagem=MSG,
        categoria="adaptador",
    )
    baixa = texto.lower()
    assert "adaptador" in baixa
    assert "pilha" not in baixa
    assert "mochila" not in baixa
    assert "pessoal, trabalho ou gamer" not in baixa
    assert "10a" in baixa or "20a" in baixa or "universal" in baixa


def test_processar_mensagem_chat_adaptador_dry_run(monkeypatch):
    gravacoes = _patch_persistencia(monkeypatch)
    _patch_catalogo(monkeypatch)

    out = api_mod.processar_mensagem(
        _data(mid="adt-chat-1"), dry_run=True, persistir=False
    )
    assert out is not None
    resp = (out.get("resposta") or out.get("reply") or "").lower()
    assert "adaptador" in resp
    assert "pilha" not in resp
    assert "mochila" not in resp
    assert "pessoal, trabalho ou gamer" not in resp
    assert "fallback_ia_nao_deveria" not in resp
    assert "10a" in resp or "20a" in resp or "universal" in resp
    bullets = [ln for ln in (out.get("resposta") or "").splitlines() if ln.strip().startswith("•")]
    assert len(bullets) <= 3
    # dry_run + persistir=false: sem gravação / WhatsApp
    assert gravacoes["cliente"] == 0
    assert gravacoes["historico"] == 0
    assert gravacoes["lead"] == 0
    assert gravacoes["whatsapp"] == 0
    assert gravacoes["mensagem"] == 0


def test_catalogo_geral_ainda_funciona(monkeypatch):
    _patch_catalogo(monkeypatch)
    assert cliente_quer_ver_catalogo("mande o catálogo") is True
    r = buscar_por_intencao(
        mensagem="mande o catálogo",
        intent="CATALOGO_GERAL",
        product_query="",
        limite=5,
    )
    assert r["found"] is True
    assert len(r["products"]) >= 1


def test_sem_resultado_mantem_fallback(monkeypatch):
    monkeypatch.setattr(
        "services.vendas.catalogo.buscar_produtos",
        lambda: list(CATALOGO),
    )
    monkeypatch.setattr(
        "services.vendas.catalogo._usar_somente_supabase",
        lambda: True,
    )
    monkeypatch.setattr(
        "services.vendas.catalogo._amostra_produtos_reais",
        lambda limite=4: [
            {"nome": "Headset Gamer X", "preco": 99.0, "saldo_estoque": 1}
        ],
    )
    from services.vendas.catalogo import montar_contexto_catalogo

    ctx = montar_contexto_catalogo("toalha de banho rosa", "")
    assert ctx["produtos"] == []
    assert ctx["sem_match"] is True
    assert ctx["amostra_disponivel"]
