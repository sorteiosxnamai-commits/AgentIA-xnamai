"""Revisão Etapa 1 — variações naturais e falsos positivos de 'mais opções'."""

from services.vendas.catalogo import montar_contexto_catalogo
from services.vendas.respostas import (
    cliente_pediu_mais_opcoes,
    cliente_quer_ver_catalogo,
    resposta_fora_catalogo,
    resposta_mais_opcoes,
)
from services.xnamai_script import mensagem_nao_e_busca_produto

# Frases que DEVEM acionar o fluxo de mais opções
VARIACOES_POSITIVAS = [
    "tem outras opções?",
    "vocês têm mais modelos?",
    "tem mais alguma coisa?",
    "quais outras opções vocês têm?",
    "me mostra outros",
    "tem outro mais barato?",
    "tem algum melhor?",
    "quero ver mais opções",
    "tem de outra marca?",
    "você tem outras alternativas?",
    "tem mais opções de produtos?",
]

# Frases que NÃO devem acionar (falso positivo)
VARIACOES_NEGATIVAS = [
    "qual é a melhor opção?",
    "esse produto tem opções de cor?",
    "produto com várias opções",
    "não quero mais opções",
    "não precisa mostrar outros",
    "quero comprar esse mesmo",
]


def _caminho_esperado(mensagem: str) -> str:
    if cliente_pediu_mais_opcoes(mensagem):
        return "mais_opcoes"
    if cliente_quer_ver_catalogo(mensagem):
        return "catalogo"
    return "outro"


def test_variacoes_positivas_detectam_mais_opcoes():
    falhas = []
    for msg in VARIACOES_POSITIVAS:
        if not cliente_pediu_mais_opcoes(msg):
            falhas.append(msg)
    assert not falhas, f"Não detectou mais_opcoes em: {falhas}"


def test_variacoes_negativas_nao_detectam_mais_opcoes():
    falhas = []
    for msg in VARIACOES_NEGATIVAS:
        if cliente_pediu_mais_opcoes(msg):
            falhas.append(msg)
    assert not falhas, f"Falso positivo em: {falhas}"


def test_positivas_nao_caem_em_fora_catalogo_sem_match():
    """Intenção genérica não deve virar 'não trabalhamos com opções produtos'."""
    for msg in VARIACOES_POSITIVAS:
        ctx = montar_contexto_catalogo(msg, "")
        # Ou é consulta ampla (sem_match False) ou termos genéricos filtrados
        assert ctx.get("sem_match") is False or mensagem_nao_e_busca_produto(msg), msg


def test_resposta_mais_opcoes_comportamento_sem_categoria():
    texto = resposta_mais_opcoes("Arthur", "", [])
    assert "Temos sim" in texto
    assert "não trabalhamos" not in texto.lower()
    # Sem categoria: pergunta o tipo — não força econômico/desempenho
    assert "tipo de produto" in texto.lower() or "procurando" in texto.lower()
    assert "econômico ou com melhor desempenho" not in texto.lower()


def test_resposta_mais_opcoes_comportamento_com_categoria():
    hist = "Cliente: quero headset\nIA: Headset Gamer — R$ 89,90\n"
    texto = resposta_mais_opcoes("Arthur", hist, [])
    assert "Temos sim" in texto
    assert "não trabalhamos" not in texto.lower()
    assert "econômico ou com melhor desempenho" not in texto.lower()
    assert any(
        trecho in texto.lower()
        for trecho in ("categoria", "linha", "opções", "preferência", "preço", "marca")
    )


def test_fora_catalogo_nao_usa_termos_genericos():
    texto = resposta_fora_catalogo("Arthur", ["opcoes", "produtos", "mais"], [])
    assert "não trabalhamos com opções" not in texto.lower()
    assert "não trabalhamos com produtos" not in texto.lower()


def test_caminho_fluxo_positivas():
    for msg in VARIACOES_POSITIVAS:
        assert _caminho_esperado(msg) == "mais_opcoes", msg


def test_caminho_fluxo_negativas_nao_e_mais_opcoes():
    for msg in VARIACOES_NEGATIVAS:
        assert _caminho_esperado(msg) != "mais_opcoes", msg


def test_nao_e_hardcode_so_uma_frase():
    """Garante que a detecção cobre família de frases, não só uma string."""
    assert cliente_pediu_mais_opcoes("tem mais opções de produtos?")
    assert cliente_pediu_mais_opcoes("quero ver mais opções")
    assert cliente_pediu_mais_opcoes("tem outras opções?")
    assert cliente_pediu_mais_opcoes("vocês têm mais modelos?")
    # Frase diferente da original do bug
    assert "tem mais opções de produtos?" != "quero ver mais opções"
