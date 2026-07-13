"""Integração: JSON /chat.resposta realmente formatado (não só debug)."""

from __future__ import annotations

import routes.api as api_mod
from fastapi.testclient import TestClient
from services.texto_seguro import (
    aplicar_formatador_final,
    tem_espaco_colado,
    tem_numero_unidade_colado,
)
from services.whatsapp_service import enviar_mensagem


PRODUTOS_FAKE = [
    {"nome": "HD Externo 1 TB", "preco": 429.9, "saldo_estoque": 33},
    {"nome": "Headset Gamer", "preco": 249.9, "saldo_estoque": 50},
    {"nome": "Hub USB 4 Portas", "preco": 69.9, "saldo_estoque": 29},
]

PRODUTOS_ESTOQUE_CRITICO = [
    {
        "nome": "Notebook Intel i5",
        "preco": 3499.9,
        "saldo_estoque": 89,
        "stock_confirmed": True,
        "stock_quantity": 89,
    },
    {
        "nome": "Mouse Óptico",
        "preco": 39.9,
        "saldo_estoque": 1,
        "stock_confirmed": True,
        "stock_quantity": 1,
    },
    {
        "nome": "Cabo HDMI",
        "preco": 49.9,
        "saldo_estoque": 10,
        "stock_confirmed": True,
        "stock_quantity": 10,
    },
    {
        "nome": "Hub USB",
        "preco": 69.9,
        "saldo_estoque": 5,
        "stock_confirmed": True,
        "stock_quantity": 5,
    },
]

_RUINS = (
    "algumasopções",
    "algumasopcoes",
    "algumasop",
    "algumasopÃ",
    "parauso",
    ")(",
    ")(temos",
    "89unidades",
    "1unidade",
    "10peças",
    "10pecas",
    "5itens",
    "temos 89unidades",
)


def _assert_json_resposta_limpa(texto: str) -> None:
    assert texto
    for ruim in _RUINS:
        assert ruim not in texto, f"JSON resposta ainda tem {ruim!r}: {texto!r}"
    assert tem_espaco_colado(texto) is False


def test_code_version_retorno_formatado():
    assert api_mod.CODE_VERSION == "2026-07-13-fix-invisivel-unidades"


def test_detector_e_fix_numero_unidade_colada():
    assert tem_espaco_colado("89unidades") is True
    assert tem_espaco_colado("1unidade") is True
    assert tem_espaco_colado("10peças") is True
    assert tem_espaco_colado("5itens") is True
    assert tem_espaco_colado("89 unidades") is False

    limpo, dbg = aplicar_formatador_final(
        "Notebook Intel i5 (R$ 3499,90) (temos 89unidades) "
        "Mouse (R$ 39,90) (temos 1unidade) "
        "Cabo (R$ 19,90) (temos 10peças) "
        "Hub (R$ 69,90) (temos 5itens)"
    )
    assert "89 unidades" in limpo
    assert "1 unidade" in limpo
    assert "10 peças" in limpo
    assert "5 itens" in limpo
    assert "89unidades" not in limpo
    assert "1unidade" not in limpo
    assert "10peças" not in limpo
    assert "5itens" not in limpo
    assert dbg["tem_espaco_colado_depois"] is False
    assert dbg["resposta_final_tem_89unidades"] is False
    assert dbg["tinha_espaco_colado_antes"] is True
    _assert_json_resposta_limpa(limpo)


def test_detector_numero_unidade_com_invisivel():
    assert tem_espaco_colado("89\u00adunidades") is True
    assert tem_espaco_colado("89\u200bunidades") is True
    assert tem_espaco_colado("89\u00a0unidades") is True
    assert tem_numero_unidade_colado("89\u200bunidades") is True
    assert tem_numero_unidade_colado("89 unidades") is False

    limpo, dbg = aplicar_formatador_final("(temos 89\u00adunidades)")
    assert "89 unidades" in limpo
    assert "89unidades" not in limpo
    assert "\u00ad" not in limpo
    assert dbg["resposta_final_tem_89unidades"] is False
    assert dbg["tem_espaco_colado_depois"] is False
    assert dbg["tem_numero_unidade_colado"] is False


def test_normaliza_zwsp_soft_hyphen_nbsp_entre_numero_unidade():
    """ZWSP, soft-hyphen e NBSP entre número e unidade → espaço ASCII."""
    sujo = (
        "Notebook Intel i5 (R$ 3499,90) (temos 89\u200bunidades) "
        "Mouse (R$ 39,90) (temos 1\u00adunidade) "
        "Cabo (R$ 19,90) (temos 10\u00a0peças) "
        "Hub (R$ 69,90) (temos 5\u200citens)"
    )
    assert tem_espaco_colado(sujo) is True
    limpo, dbg = aplicar_formatador_final(sujo)
    assert "89 unidades" in limpo
    assert "1 unidade" in limpo
    assert "10 peças" in limpo
    assert "5 itens" in limpo
    assert "89\u200bunidades" not in limpo
    assert "89unidades" not in limpo
    assert "\u200b" not in limpo
    assert "\u00ad" not in limpo
    assert "\u00a0" not in limpo
    assert dbg["tem_espaco_colado_depois"] is False
    assert dbg["tem_numero_unidade_colado"] is False
    assert dbg["resposta_final_tem_89unidades"] is False
    assert "Notebook" in dbg["trecho_notebook"]
    assert any(x.endswith(":0020") for x in dbg["trecho_notebook_codepoints"])
    # Entre 89 e unidades no trecho final deve ser espaço ASCII
    idx = limpo.find("89")
    assert limpo[idx : idx + 11] == "89 unidades"
    assert limpo[idx + 2] == " "
    assert ord(limpo[idx + 2]) == 0x20
    _assert_json_resposta_limpa(limpo)


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
    assert data["code_version"] == "2026-07-13-fix-invisivel-unidades"
    # Valida o campo JSON, não variável interna
    _assert_json_resposta_limpa(data["resposta"])
    assert data["formatacao_debug"]["formatador_final_aplicado"] is True
    assert data["formatacao_debug"]["tem_espaco_colado_depois"] is False
    # Debug deve refletir a MESMA string do JSON
    assert data["formatacao_debug"]["amostra_resposta_final"] in data["resposta"] or data[
        "resposta"
    ].startswith(data["formatacao_debug"]["amostra_resposta_final"][:20])


def test_chat_catalogo_real_resp_json_sem_estoque_colado(monkeypatch):
    """Integração real /chat 'mande o catalogo' — valida resp_json['resposta']."""
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")
    monkeypatch.setenv("WHATSAPP_PROVIDER", "ultramsg")

    def _produtos_ps(limit=8):
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
                    "estoque": p["saldo_estoque"],
                }
                for p in PRODUTOS_ESTOQUE_CRITICO[:limit]
            ],
            "produtos": PRODUTOS_ESTOQUE_CRITICO[:limit],
            "message": "ok",
            "fonte": "supabase",
            "catalogo": "fake",
        }

    monkeypatch.setattr(
        "services.vendas.catalogo.montar_catalogo_geral",
        lambda limite=20: {
            "produtos": PRODUTOS_ESTOQUE_CRITICO[:limite],
            "catalogo": "fake",
            "fonte": "supabase",
        },
    )
    monkeypatch.setattr(
        "services.product_service.listar_produtos_catalogo",
        _produtos_ps,
    )
    monkeypatch.setattr(
        "services.product_service.buscar_por_intencao",
        lambda **_k: _produtos_ps(),
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
    resp_json = resp.json()
    assert resp_json["code_version"] == "2026-07-13-fix-invisivel-unidades"

    resposta = resp_json["resposta"]
    # Falha explícita se ainda colar número+unidade
    for ruim in (
        "89unidades",
        "1unidade",
        "10peças",
        "10pecas",
        "5itens",
        "temos 89unidades",
    ):
        assert ruim not in resposta, f"resp_json['resposta'] ainda tem {ruim!r}: {resposta!r}"

    assert "89 unidades" in resposta
    assert "1 unidade" in resposta
    assert "(temos 89 unidades)" in resposta
    assert "(temos 1 unidade)" in resposta
    # Espaço ASCII literal entre 89 e unidades
    i = resposta.find("89")
    assert i >= 0
    assert resposta[i : i + 11] == "89 unidades"
    assert ord(resposta[i + 2]) == 0x20
    assert resp_json["formatacao_debug"]["tem_espaco_colado_depois"] is False
    assert resp_json["formatacao_debug"]["resposta_final_tem_89unidades"] is False
    assert resp_json["formatacao_debug"]["tem_numero_unidade_colado"] is False
    assert "Notebook" in resp_json["formatacao_debug"]["trecho_notebook"]
    assert isinstance(resp_json["formatacao_debug"]["trecho_notebook_codepoints"], list)
    assert len(resp_json["formatacao_debug"]["trecho_notebook_codepoints"]) > 0
    _assert_json_resposta_limpa(resposta)


def test_chat_json_resposta_separa_numero_unidade(monkeypatch):
    """Valida resp_json['resposta'] com número colado em unidade de estoque."""
    monkeypatch.setenv("CHECKOUT_CREATE_ORDER", "false")

    sujo = (
        "Claro, Tironi. Posso te mostrar algumas opções do nosso catálogo. "
        "Notebook Intel i5 (R$ 3499,90) (temos 89unidades). "
        "Mouse Óptico (R$ 39,90) (temos 1unidade). "
        "Cabo HDMI (R$ 49,90) (temos 10peças). "
        "Hub USB (R$ 69,90) (temos 5itens). "
        "Você procura algo para uso pessoal, trabalho ou gamer?"
    )

    def _fake_processar(*_a, **_k):
        return {
            "resposta": sujo,
            "persistencia_ok": True,
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
    assert resp.status_code == 200
    resp_json = resp.json()
    assert resp_json["code_version"] == "2026-07-13-fix-invisivel-unidades"
    # Campo JSON final — não variável interna
    resposta = resp_json["resposta"]
    assert "89 unidades" in resposta
    assert "1 unidade" in resposta
    assert "10 peças" in resposta
    assert "5 itens" in resposta
    assert "89unidades" not in resposta
    assert "1unidade" not in resposta
    assert "10peças" not in resposta
    assert "5itens" not in resposta
    assert "(R$ 3499,90) (temos 89 unidades)" in resposta
    assert resp_json["formatacao_debug"]["tem_espaco_colado_depois"] is False
    assert resp_json["formatacao_debug"]["resposta_final_tem_89unidades"] is False
    assert resp_json["formatacao_debug"]["tinha_espaco_colado_antes"] is True
    _assert_json_resposta_limpa(resposta)


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
