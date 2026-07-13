"""Integração: formatador final no /chat e no envio WhatsApp."""

from __future__ import annotations

from unittest.mock import patch

import routes.api as api_mod
from fastapi.testclient import TestClient
from services.texto_seguro import (
    aplicar_formatador_final,
    garantir_espacos_whatsapp,
    tem_espaco_colado,
)
from services.whatsapp_service import enviar_mensagem


PRODUTOS_FAKE = [
    {"nome": "HD Externo 1 TB", "preco": 429.9, "saldo_estoque": 33},
    {"nome": "Headset Gamer", "preco": 249.9, "saldo_estoque": 50},
    {"nome": "Hub USB 4 Portas", "preco": 69.9, "saldo_estoque": 29},
]


def _assert_sem_colagem(texto: str) -> None:
    assert texto
    for ruim in (
        "algumasopções",
        "algumasopcoes",
        "algumasop",
        "parauso",
        ")(",
        ")(temos",
    ):
        assert ruim not in texto, f"encontrou {ruim!r} em {texto!r}"
    assert "algumas opções" in texto or "opções do nosso catálogo" in texto or "categoria" in texto.lower()


def test_code_version_formatador_final():
    assert api_mod.CODE_VERSION == "2026-07-13-fix-formatador-final"


def test_aplicar_formatador_final_corrige_producao():
    sujo = (
        "Claro, Tironi. Posso te mostrar algumasopções do nosso catálogo. "
        "Temos produtos como: Hub USB 4 Portas (R$ 69,90)(temos 29 unidades). "
        "Você procura algo parauso pessoal, trabalho ou gamer?"
    )
    assert tem_espaco_colado(sujo) is True
    limpo, dbg = aplicar_formatador_final(sujo)
    assert dbg["formatador_final_aplicado"] is True
    assert dbg["tinha_espaco_colado_antes"] is True
    assert dbg["tem_espaco_colado_depois"] is False
    _assert_sem_colagem(limpo)
    assert "(R$ 69,90) (temos 29 unidades)" in limpo
    assert "para uso pessoal" in limpo


def test_chat_mande_catalogo_sem_colagem(monkeypatch):
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
    assert data.get("code_version") == "2026-07-13-fix-formatador-final"
    texto = data.get("resposta") or ""
    _assert_sem_colagem(texto)
    fmt = data.get("formatacao_debug") or {}
    assert fmt.get("formatador_final_aplicado") is True
    assert fmt.get("tem_espaco_colado_depois") is False


def test_chat_reaplica_filtro_mesmo_com_resposta_suja(monkeypatch):
    """Se o núcleo devolver texto colado, /chat ainda limpa na última camada."""
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")

    sujo = (
        "Claro, Tironi. Posso te mostrar algumasopções do nosso catálogo. "
        "Hub (R$ 69,90)(temos 29 unidades). Você procura algo parauso pessoal?"
    )

    def _fake_processar(*_a, **_k):
        return {
            "resposta": sujo,
            "persistencia_ok": True,
            "formatacao_debug": {
                "formatador_final_aplicado": True,
                "tinha_espaco_colado_antes": True,
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
    texto = data.get("resposta") or ""
    _assert_sem_colagem(texto)
    assert data["formatacao_debug"]["formatador_final_aplicado"] is True
    assert data["formatacao_debug"]["tem_espaco_colado_depois"] is False


def test_enviar_mensagem_whatsapp_passa_pelo_filtro(monkeypatch):
    capturado = {}

    def _fake_ultra(numero, mensagem):
        capturado["mensagem"] = mensagem
        return {"ok": True, "provider": "ultramsg"}

    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")
    monkeypatch.setattr(
        "services.ultramsg_service.ultramsg_configurado", lambda: True
    )
    monkeypatch.setattr(
        "services.ultramsg_service.enviar_mensagem", _fake_ultra
    )

    sujo = "algumasopções (R$ 10,00)(temos 2 unidades) parauso pessoal"
    enviar_mensagem("5543999999999", sujo)
    texto = capturado.get("mensagem") or ""
    _assert_sem_colagem(texto)
    assert ")(" not in texto
