from services.xnamai_script import (
    PEDIDO_MINIMO,
    alinhamento_completo,
    extrair_forma_envio,
    extrair_preferencia_nf,
    ia_pediu_alinhamento,
    precisa_avisar_pedido_minimo,
    resposta_alinhamento_pedido,
    resposta_saudacao_xnamai,
)


def test_saudacao_tom_consultora():
    texto = resposta_saudacao_xnamai("Tironi")
    assert "Tironi" in texto
    assert "xNaMai" in texto or "Xnamai" in texto.lower()
    assert "vendas" in texto.lower()


def test_alinhamento_nf_e_envio():
    hist = "Cliente: quero headset\nIA: Fechamos?\n"
    assert extrair_preferencia_nf(hist, "sem nf") == "sem_nf"
    assert extrair_forma_envio(hist, "envio") == "envio"
    assert alinhamento_completo(hist, "sem nf, envio") is True


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
