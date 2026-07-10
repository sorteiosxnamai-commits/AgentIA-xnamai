from services.vendas.respostas import cliente_perguntou_preco, resposta_preco_em_discussao
from services.xnamai_script import (
    PEDIDO_MINIMO,
    alinhamento_completo,
    cliente_perguntou_como_trabalham,
    extrair_forma_envio,
    extrair_preferencia_nf,
    ia_pediu_alinhamento,
    mensagem_nao_e_busca_produto,
    precisa_avisar_pedido_minimo,
    resposta_abrir_espaco_pedido,
    resposta_alinhamento_pedido,
    resposta_como_trabalham,
    resposta_saudacao_xnamai,
)


def test_saudacao_tom_consultora():
    texto = resposta_saudacao_xnamai("Tironi")
    assert "Tironi" in texto
    assert "xNaMai" in texto or "Xnamai" in texto.lower()
    assert "vendas" in texto.lower()
    assert "R$" not in texto
    assert "Webcam" not in texto


def test_quero_pedido_nao_oferece_produto():
    texto = resposta_abrir_espaco_pedido("Tironi")
    assert "procurando" in texto.lower() or "mente" in texto.lower() or "busca" in texto.lower()
    assert "R$" not in texto
    assert "Webcam" not in texto
    assert "HDMI" not in texto


def test_como_trabalham_nao_e_produto():
    msg = "queria saber como vocês trabalham ?"
    assert cliente_perguntou_como_trabalham(msg) is True
    assert mensagem_nao_e_busca_produto(msg) is True
    texto = resposta_como_trabalham("Tironi")
    assert "não trabalhamos com" not in texto.lower()
    assert "pagamento antecipado" in texto.lower()
    assert "Webcam" not in texto


def test_headset_ainda_e_busca_produto():
    assert mensagem_nao_e_busca_produto("quero um headset gamer") is False
    assert cliente_perguntou_como_trabalham("quero um headset gamer") is False


def test_retirar_e_forma_envio_nao_produto():
    assert extrair_forma_envio("", "retirar") == "retirada"
    assert extrair_forma_envio("", "quero retirar") == "retirada"
    assert mensagem_nao_e_busca_produto("retirar") is True
    assert mensagem_nao_e_busca_produto("sem nf, retirar") is True
    assert mensagem_nao_e_busca_produto("qual o valor") is True
    assert mensagem_nao_e_busca_produto("eu sei que não") is True


def test_qual_o_valor_responde_produto_do_historico():
    assert cliente_perguntou_preco("qual o valor") is True
    hist = (
        "Cliente: quero headset\n"
        "IA: Headset Gamer por R$ 249.9 — temos disponível.\n"
    )
    texto = resposta_preco_em_discussao(hist, "Tironi")
    assert texto is not None
    assert "249" in texto
    assert "Headset" in texto or "headset" in texto.lower()


def test_pergunta_monitor_nao_e_endereco():
    from services.conversa_service import extrair_endereco, _parece_endereco_real

    lixo = "o munitor led 24 qual e o valor ?"
    assert _parece_endereco_real(lixo) is False
    hist = f"Cliente: {lixo}\nIA: Monitor LED 24 por R$ 899.9\n"
    assert extrair_endereco(hist) == ""


def test_alinhamento_nf_e_envio():
    hist = "Cliente: quero headset\nIA: Fechamos?\n"
    assert extrair_preferencia_nf(hist, "sem nf") == "sem_nf"
    assert extrair_forma_envio(hist, "envio") == "envio"
    assert alinhamento_completo(hist, "sem nf, envio") is True
    assert alinhamento_completo(hist, "sem nf, retirar") is True


def test_alinhamento_incompleto():
    hist = "Cliente: quero headset\n"
    assert alinhamento_completo(hist, "fechamos sim") is False


def test_ia_pediu_alinhamento():
    msg = resposta_alinhamento_pedido("Tironi")
    assert ia_pediu_alinhamento(msg) is True


def test_pedido_minimo_padrao():
    assert PEDIDO_MINIMO == 800.0
    hist = (
        "Cliente: quero cabo\n"
        "IA: Cabo HDMI 2m por R$ 29.9. Fechamos 1 unidade?\n"
    )
    # Por padrão desligado no sandbox
    assert precisa_avisar_pedido_minimo(hist) is False
