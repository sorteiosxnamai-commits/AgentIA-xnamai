"""Integração: JSON /chat.resposta realmente formatado (não só debug)."""

from __future__ import annotations

import routes.api as api_mod
from fastapi.testclient import TestClient
from services.texto_seguro import (
    aplicar_formatador_final,
    tem_espaco_colado,
)
from services.whatsapp_service import enviar_mensagem


PRODUTOS_FAKE = [
    {"nome": "HD Externo 1 TB", "preco": 429.9, "saldo_estoque": 33},
    {"nome": "Headset Gamer", "preco": 249.9, "saldo_estoque": 50},
    {"nome": "Hub USB 4 Portas", "preco": 69.9, "saldo_estoque": 29},
]

_RUINS = (
    "algumasopções",
    "algumasopcoes",
    "algumasop",
    "algumasopÃ",
    "parauso",
    ")(",
    ")(temos",
)


def _assert_json_resposta_limpa(texto: str) -> None:
    assert texto
    for ruim in _RUINS:
        assert ruim not in texto, f"JSON resposta ainda tem {ruim!r}: {texto!r}"
    assert tem_espaco_colado(texto) is False


def test_code_version_retorno_formatado():
    assert api_mod.CODE_VERSION == "2026-07-13-fix-ultramsg-webhook-parser"


def test_detector_ve_soft_hyphen_e_zwsp():
    assert tem_espaco_colado("algumas\u00adopções") is True
    assert tem_espaco_colado("algumas\u200bopções") is True
    assert tem_espaco_colado("algumasopÃ§Ãµes") is True
    limpo, dbg = aplicar_formatador_final(
        "mostrar algumas\u00adopções (R$ 1)(temos 2) parauso"
    )
    _assert_json_resposta_limpa(limpo)
    assert dbg["tem_espaco_colado_depois"] is False
    assert "algumas opções" in limpo
    assert ") (" in limpo


def test_chat_json_resposta_sem_colagem(monkeypatch):
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    monkeypatch.setattr(
        "services.vendas.catalogo.montar_catalogo_geral",
        lambda limite=20: {
            "produtos": PRODUTOS_FAKE[:limite],
            "catalogo": "fake",
            "fonte": "supabase",
        },
    )
    monkeypatch.setattr(
        "services.product_service.listar_produtos_catalogo",
        lambda limit=8: {
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
                for p in PRODUTOS_FAKE
            ],
            "message": "ok",
            "fonte": "supabase",
        },
    )

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
    assert resp.status_code == 200
    data = resp.json()
    assert data["code_version"] == "2026-07-13-fix-ultramsg-webhook-parser"
    # Valida o campo JSON, não variável interna
    _assert_json_resposta_limpa(data["resposta"])
    assert data["formatacao_debug"]["formatador_final_aplicado"] is True
    assert data["formatacao_debug"]["tem_espaco_colado_depois"] is False
    # Debug deve refletir a MESMA string do JSON
    assert data["formatacao_debug"]["amostra_resposta_final"] in data["resposta"] or data[
        "resposta"
    ].startswith(data["formatacao_debug"]["amostra_resposta_final"][:20])


def test_chat_atualiza_resultado_resposta_mesmo_com_sujeira(monkeypatch):
    """processar_mensagem devolve colado; /chat deve sobrescrever resultado['resposta']."""
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")

    sujo = (
        "Claro, Tironi. Posso te mostrar algumas\u00adopções do nosso catálogo. "
        "Hub USB 4 Portas (R$ 69,90)(temos 29 unidades). "
        "Você procura algo parauso pessoal, trabalho ou gamer?"
    )

    def _fake_processar(*_a, **_k):
        return {
            "resposta": sujo,
            "persistencia_ok": True,
            "formatacao_debug": {
                "formatador_final_aplicado": True,
                "tinha_espaco_colado_antes": False,  # detector antigo mentia
                "tem_espaco_colado_depois": False,
            },
        }

    monkeypatch.setattr(api_mod, "processar_mensagem", _fake_processar)

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
    _assert_json_resposta_limpa(data["resposta"])
    assert "algumas opções" in data["resposta"]
    assert "(R$ 69,90) (temos 29 unidades)" in data["resposta"]
    assert "para uso pessoal" in data["resposta"]
    assert data["formatacao_debug"]["tem_espaco_colado_depois"] is False
    assert data["formatacao_debug"]["tinha_espaco_colado_antes"] is True


def test_whatsapp_envio_filtra_json_equivalente(monkeypatch):
    capturado = {}

    def _fake_ultra(numero, mensagem):
        capturado["mensagem"] = mensagem
        return {"ok": True}

    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    monkeypatch.setattr("services.ultramsg_service.ultramsg_configurado", lambda: True)
    monkeypatch.setattr("services.ultramsg_service.enviar_mensagem", _fake_ultra)

    enviar_mensagem(
        "5543999999999",
        "algumas\u00adopções (R$ 10,00)(temos 2) parauso",
    )
    _assert_json_resposta_limpa(capturado["mensagem"])
