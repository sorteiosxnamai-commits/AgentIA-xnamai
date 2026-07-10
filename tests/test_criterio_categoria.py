"""Critério de follow-up por categoria — sem pergunta genérica fixa."""

from services.vendas.respostas import (
    criterio_util_por_categoria,
    resposta_mais_opcoes,
)

NEUTRA = "Você tem alguma preferência de preço, marca ou característica?"


def test_headset_com_atributo_de_uso():
    produtos = [
        {"nome": "Headset Gamer RGB", "preco": 159.9, "descricao": "headset gamer com microfone"},
        {"nome": "Headset Office", "preco": 99.9, "descricao": "fone para trabalho e chamadas"},
    ]
    pergunta = criterio_util_por_categoria("headset", produtos)
    assert pergunta is not None
    assert "econômico ou" not in pergunta.lower()
    assert any(x in pergunta.lower() for x in ("jogos", "trabalho", "chamadas"))


def test_headset_sem_atributo_nao_inventa():
    produtos = [
        {"nome": "Headset X1", "preco": 80},
        {"nome": "Headset X2", "preco": 120},
    ]
    pergunta = criterio_util_por_categoria("headset", produtos)
    assert pergunta == NEUTRA


def test_armazenamento_usa_capacidade_velocidade():
    produtos = [
        {"nome": "SSD 480GB", "preco": 199, "descricao": "SSD SATA 480GB rápido"},
        {"nome": "HD Externo 1TB", "preco": 299, "descricao": "HD externo portátil 1TB"},
    ]
    pergunta = criterio_util_por_categoria("ssd", produtos)
    assert pergunta is not None
    assert "econômico ou" not in pergunta.lower()
    assert any(x in pergunta.lower() for x in ("capacidade", "velocidade", "portabilidade"))


def test_celular_usa_atributos_reais():
    produtos = [
        {
            "nome": "Smartphone A",
            "preco": 1200,
            "descricao": "câmera 48mp bateria 5000mah desempenho",
        },
        {
            "nome": "Smartphone B",
            "preco": 900,
            "descricao": "bateria longa e câmera boa",
        },
    ]
    pergunta = criterio_util_por_categoria("celular", produtos)
    assert pergunta is not None
    assert any(x in pergunta.lower() for x in ("câmera", "bateria", "desempenho", "orçamento"))


def test_moveis_usa_medidas_material():
    produtos = [
        {"nome": "Mesa 120cm", "preco": 499, "descricao": "mesa 120x60 cm madeira mdp"},
        {"nome": "Mesa Premium", "preco": 579, "descricao": "acabamento verniz madeira"},
    ]
    pergunta = criterio_util_por_categoria("mesa", produtos)
    assert pergunta is not None
    assert any(x in pergunta.lower() for x in ("medidas", "material", "acabamento", "preço"))


def test_produto_simples_sem_pergunta():
    produtos = [
        {"nome": "Cabo USB-C 1 Metro", "preco": 19.9},
        {"nome": "Cabo USB-C Premium 2m", "preco": 34.9},
    ]
    pergunta = criterio_util_por_categoria("cabo", produtos)
    assert pergunta is None


def test_resposta_simples_so_lista_opcoes():
    hist = "Cliente: quero cabo usb\nIA: Cabo USB-C 1 Metro — R$ 19,90\n"
    produtos = [
        {"nome": "Cabo USB-C 1 Metro", "preco": 19.9, "categoria": "Cabos"},
        {"nome": "Cabo USB-C Premium 2m", "preco": 34.9, "categoria": "Cabos"},
    ]
    texto = resposta_mais_opcoes("Arthur", hist, produtos)
    assert "Temos sim" in texto
    assert "Cabo" in texto
    assert "econômico ou" not in texto.lower()
    assert "jogos, trabalho" not in texto.lower()


def test_resposta_headset_nao_usa_economico_desempenho():
    hist = "Cliente: quero headset\nIA: Headset Gamer RGB — R$ 159,90\n"
    produtos = [
        {"nome": "Headset Gamer RGB", "preco": 159.9, "descricao": "gamer com microfone"},
        {"nome": "Headset Bluetooth", "preco": 89.9, "descricao": "fone bluetooth para chamadas"},
    ]
    texto = resposta_mais_opcoes("Arthur", hist, produtos)
    assert "Temos sim" in texto
    assert "econômico ou com melhor desempenho" not in texto.lower()


def test_sem_criterio_usa_pergunta_neutra():
    pergunta = criterio_util_por_categoria("produto misterioso", [{"nome": "Item X", "preco": 10}])
    assert pergunta == NEUTRA
