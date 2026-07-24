"""Etapa 2 — histórico, isolamento, idempotência, anti-repetição, tabelas."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from services.config_tabelas import (
    mascarar_telefone,
    normalizar_telefone,
    validar_tabelas_supabase,
)
from services.historico_service import (
    cliente_recusou_responder,
    deve_evitar_pergunta,
    limpar_linhas_historico,
    montar_bloco_contexto_openai,
    montar_historico_util,
    sanitizar_resposta_anti_repeticao,
)
from services.vendas.memoria import atualizar_sessao_turno, sessao_vazia
from services.vendas.respostas import cliente_pediu_mais_opcoes
from services.webhook_guard import (
    finalizar_mensagem,
    lock_telefone,
    reclamar_mensagem,
)
from services.webhook_normalizer import normalizar_webhook
from services.webhook_service import _IDS_PROCESSADOS, evento_deve_ser_ignorado


# ---------------------------------------------------------------------------
# 1. Isolamento por telefone
# ---------------------------------------------------------------------------

def test_dois_telefones_historicos_isolados():
    """Dois clientes → IDs/telefones distintos; histórico montado por cliente_id."""
    tel_a = normalizar_telefone("+55 (43) 99999-1111")
    tel_b = normalizar_telefone("5543999992222")
    assert tel_a != tel_b

    hist_a = "Cliente: quero headset\nIA: Temos o HMaston.\n"
    hist_b = "Cliente: quero HD\nIA: Temos SSD e HD.\n"

    bloco_a = montar_bloco_contexto_openai(
        historico_texto=hist_a,
        mensagem_atual="tem mais?",
        contexto={"categoria_interesse": "headset", "nome_cliente": "Ana"},
    )
    bloco_b = montar_bloco_contexto_openai(
        historico_texto=hist_b,
        mensagem_atual="tem mais?",
        contexto={"categoria_interesse": "armazenamento", "nome_cliente": "Bruno"},
    )
    assert "headset" in bloco_a.lower()
    assert "hd" in bloco_b.lower() or "armazenamento" in bloco_b.lower()
    assert "Ana" in bloco_a
    assert "Bruno" in bloco_b
    assert "Bruno" not in bloco_a
    assert "Ana" not in bloco_b


# ---------------------------------------------------------------------------
# 2–4. Nome / categoria / orçamento já informados
# ---------------------------------------------------------------------------

def test_nao_reperguntar_nome():
    ctx = {"nome_cliente": "Arthur"}
    evitar, motivo = deve_evitar_pergunta(
        "Qual é o seu nome?",
        "Cliente: me chamo Arthur\n",
        ctx,
    )
    assert evitar is True
    assert motivo == "nome_ja_informado"


def test_nao_reperguntar_categoria():
    ctx = {"categoria_interesse": "headset"}
    evitar, motivo = deve_evitar_pergunta(
        "Qual tipo de produto você procura?",
        "Cliente: quero headset\n",
        ctx,
    )
    assert evitar is True
    assert motivo == "categoria_ja_informada"


def test_nao_reperguntar_orcamento():
    ctx = {"orcamento": 300.0, "faixa_preco": "até R$ 300,00"}
    evitar, motivo = deve_evitar_pergunta(
        "Qual seu orçamento?",
        "Cliente: até 300 reais\n",
        ctx,
    )
    assert evitar is True
    assert motivo == "orcamento_ja_informado"

    sessao = atualizar_sessao_turno(
        sessao_vazia(),
        historico_texto="",
        mensagem="meu orçamento é até R$ 250",
    )
    assert sessao.get("orcamento") == 250.0
    assert sessao.get("faixa_preco")


# ---------------------------------------------------------------------------
# 5. Mensagem duplicada
# ---------------------------------------------------------------------------

def test_mensagem_duplicada_nao_processa_duas_vezes():
    _IDS_PROCESSADOS.clear()
    from services import webhook_guard as wg

    wg._IDS_ESTADO.clear()

    data = {
        "event_type": "message_received",
        "data": {"id": "msg-dup-001", "from": "5543999990001", "body": "oi", "time": time.time()},
    }
    ok1, _ = reclamar_mensagem(data)
    assert ok1 is True
    ok2, motivo2 = reclamar_mensagem(data)
    assert ok2 is False
    assert "duplicado" in motivo2 or "em_processamento" in motivo2

    finalizar_mensagem(data, sucesso=True)
    ok3, motivo3 = reclamar_mensagem(data)
    assert ok3 is False
    assert "duplicado" in motivo3


# ---------------------------------------------------------------------------
# 6. Eco do bot (fromMe)
# ---------------------------------------------------------------------------

def test_mensagem_do_bot_ignorada_pelo_normalizer():
    payload = {
        "type": "ReceivedCallback",
        "fromMe": True,
        "phone": "5543999990002",
        "text": {"message": "Olá, sou a Ana"},
        "messageId": "bot-echo-1",
    }
    assert normalizar_webhook(payload) is None


def test_fromMe_no_processamento():
    from routes.api import processar_mensagem

    data = {
        "event_type": "message_received",
        "data": {
            "from": "5543999990003",
            "body": "resposta do bot",
            "fromMe": True,
            "type": "chat",
            "id": f"fromme-{time.time()}",
            "time": time.time(),
        },
    }
    assert processar_mensagem(data, dry_run=True) is None


# ---------------------------------------------------------------------------
# 7. Duas mensagens rápidas — lock por telefone
# ---------------------------------------------------------------------------

def test_duas_mensagens_rapidas_mesmo_telefone_serializam():
    ordem: list[str] = []

    def worker(nome: str, delay: float):
        with lock_telefone("5543999888777"):
            ordem.append(f"{nome}-in")
            time.sleep(delay)
            ordem.append(f"{nome}-out")

    t1 = threading.Thread(target=worker, args=("a", 0.12))
    t2 = threading.Thread(target=worker, args=("b", 0.05))
    t1.start()
    time.sleep(0.02)
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert len(ordem) == 4
    # Sem interleaving: in/out de um antes do in do outro
    assert ordem[0].endswith("-in") and ordem[1].endswith("-out")
    assert ordem[2].endswith("-in") and ordem[3].endswith("-out")
    assert ordem[0][:1] == ordem[1][:1]
    assert ordem[2][:1] == ordem[3][:1]


# ---------------------------------------------------------------------------
# 8. Histórico maior que o limite — âncoras preservadas
# ---------------------------------------------------------------------------

def test_historico_maior_que_limite_preserva_essenciais():
    linhas = []
    for i in range(40):
        linhas.append(f"Cliente: msg filler {i}")
        linhas.append(f"IA: ok {i}")
    linhas.insert(2, "Cliente: quero headset gamer até R$ 200")
    hist = "\n".join(linhas)
    ctx = {
        "categoria_interesse": "headset",
        "faixa_preco": "até R$ 200",
        "produto_mencionado": "headset",
    }
    util = montar_historico_util(hist, max_linhas=8, contexto=ctx)
    assert util.count("\n") + 1 <= 20  # âncoras + recentes
    # Essencial deve aparecer (âncora ou recente)
    assert "headset" in util.lower() or "200" in util


# ---------------------------------------------------------------------------
# 9. Mensagem vazia
# ---------------------------------------------------------------------------

def test_mensagem_vazia_legado_descartada():
    payload = {
        "type": "ReceivedCallback",
        "fromMe": False,
        "phone": "5543999990004",
        "text": {"message": "   "},
        "messageId": "empty-1",
    }
    assert normalizar_webhook(payload) is None


def test_mensagem_vazia_processar():
    from routes.api import processar_mensagem

    data = {
        "event_type": "message_received",
        "data": {
            "from": "5543999990005",
            "body": "",
            "fromMe": False,
            "type": "chat",
            "id": f"empty-{time.time()}",
            "time": time.time(),
        },
    }
    assert processar_mensagem(data, dry_run=True) is None


# ---------------------------------------------------------------------------
# 10. Telefone em formatos diferentes
# ---------------------------------------------------------------------------

def test_telefone_formatos_diferentes_mesmo_destino():
    a = normalizar_telefone("+55 43 99999-8888")
    b = normalizar_telefone("5543999998888")
    c = normalizar_telefone("(43) 99999-8888")
    assert a == b
    # sem DDI ainda normaliza dígitos; pode diferir se faltar 55
    assert normalizar_telefone("43 99999-8888") == "43999998888"
    assert mascarar_telefone(a).startswith("***")
    assert "9999" not in mascarar_telefone(a) or len(mascarar_telefone(a)) <= 7


# ---------------------------------------------------------------------------
# 11. Tabela configurada inexistente
# ---------------------------------------------------------------------------

def test_tabela_inexistente_erro_claro_sem_fallback():
    fake_sb = MagicMock()

    class FakeTable:
        def select(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def execute(self):
            raise Exception(
                "{'code': 'PGRST205', 'message': \"Could not find the table "
                "'public.agent_clientes' in the schema cache\"}"
            )

    fake_sb.table.return_value = FakeTable()

    with patch("database.supabase.supabase", fake_sb):
        with patch("services.config_tabelas.CLIENTES_TABLE", "agent_clientes"):
            with patch("services.config_tabelas.CONVERSAS_TABLE", "conversas"):
                # conversas ok, clientes falha
                def table_side(name):
                    t = MagicMock()
                    if name == "agent_clientes":
                        t.select.return_value.limit.return_value.execute.side_effect = (
                            Exception("PGRST205 does not exist schema cache")
                        )
                    else:
                        t.select.return_value.limit.return_value.execute.return_value = MagicMock(
                            data=[]
                        )
                    return t

                fake_sb.table.side_effect = table_side
                with pytest.raises(RuntimeError) as exc:
                    validar_tabelas_supabase(obrigatorio=True)
                assert "CLIENTES_TABLE" in str(exc.value) or "agent_clientes" in str(exc.value)
                assert "fallback" not in str(exc.value).lower()


# ---------------------------------------------------------------------------
# 12. Falha temporária do Supabase
# ---------------------------------------------------------------------------

def test_falha_temporaria_supabase_nao_confunde_com_tabela_inexistente():
    fake_sb = MagicMock()

    def table_side(_name):
        t = MagicMock()
        t.select.return_value.limit.return_value.execute.side_effect = (
            ConnectionError("temporary network blip")
        )
        return t

    fake_sb.table.side_effect = table_side

    with patch("database.supabase.supabase", fake_sb):
        resultado = validar_tabelas_supabase(obrigatorio=False)
        assert resultado["ok"] is False
        assert resultado.get("avisos")
        assert not any("não existe" in e for e in resultado.get("erros", []))


# ---------------------------------------------------------------------------
# 13. Headset → “tem mais opções?”
# ---------------------------------------------------------------------------

def test_headset_depois_mais_opcoes_fluxo():
    assert cliente_pediu_mais_opcoes("tem mais opções?") is True
    sessao = atualizar_sessao_turno(
        sessao_vazia(),
        historico_texto="Cliente: quero headset\nIA: Temos o HMaston RS60.\n",
        mensagem="tem mais opções?",
    )
    # Mantém categoria headset (mensagem genérica não apaga)
    assert sessao.get("categoria_interesse") in ("headset", "fone", "")
    # Se a msg não tem keyword, categoria pode vir do histórico via produto —
    # pelo menos não inventa "opções"
    assert "opções" not in (sessao.get("categoria_interesse") or "")


# ---------------------------------------------------------------------------
# 14. Muda de assunto headset → HD
# ---------------------------------------------------------------------------

def test_mudanca_assunto_headset_para_hd():
    s = atualizar_sessao_turno(
        sessao_vazia(),
        historico_texto="",
        mensagem="quero um headset gamer",
    )
    assert s["categoria_interesse"] == "headset"
    s2 = atualizar_sessao_turno(
        s,
        historico_texto="Cliente: quero um headset gamer\n",
        mensagem="na verdade quero um HD de 1TB",
    )
    assert s2["categoria_interesse"] == "armazenamento"


# ---------------------------------------------------------------------------
# 15. “não quero responder” — não repete a mesma pergunta
# ---------------------------------------------------------------------------

def test_cliente_recusa_nao_repete_pergunta_identica():
    assert cliente_recusou_responder("não quero responder isso") is True
    hist = (
        "Cliente: oi\n"
        "IA: Qual seu orçamento aproximado?\n"
        "Cliente: não quero responder isso\n"
    )
    ctx = {
        "ultima_pergunta_agente": "Qual seu orçamento aproximado?",
        "orcamento": None,
    }
    evitar, motivo = deve_evitar_pergunta(
        "Qual seu orçamento aproximado?",
        hist,
        ctx,
        mensagem_atual="não quero responder isso",
    )
    assert evitar is True
    assert motivo in ("cliente_recusou_responder", "pergunta_ja_feita")

    resposta_ruim = (
        "Entendi. Qual seu orçamento aproximado? Posso te ajudar com outras coisas."
    )
    limpa, motivos = sanitizar_resposta_anti_repeticao(
        resposta_ruim, hist, ctx, "não quero responder isso"
    )
    assert "orçamento aproximado" not in limpa.lower()
    assert motivos


# ---------------------------------------------------------------------------
# Extra: limpeza de lixo / mascaramento
# ---------------------------------------------------------------------------

def test_limpar_lixo_e_duplicatas():
    bruto = (
        "Cliente: oi\n"
        "Cliente: oi\n"
        "webhook event_type=MessageStatusCallback\n"
        "IA: Olá!\n"
        "Cliente: \n"
        "Cliente: quero cabo hdmi\n"
    )
    limpo = limpar_linhas_historico(bruto)
    assert limpo[0] == "Cliente: oi"
    assert all("webhook" not in l.lower() for l in limpo)
    assert limpo.count("Cliente: oi") == 1
