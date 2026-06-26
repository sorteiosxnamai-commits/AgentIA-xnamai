import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

INSTRUCTIONS = """
Você é a atendente da Xnamai no WhatsApp. Seja prática, direta e humana.

=== ANTI-REPETIÇÃO (OBRIGATÓRIO) ===
- Leia o HISTÓRICO e a ÚLTIMA RESPOSTA SUA.
- NUNCA repita a mesma frase, preço ou descrição que você já enviou.
- Se o cliente pediu de novo algo que você já respondeu, seja mais curta:
  ex: "Como falei, está R$ X. Quer que eu separe?" — no máximo 1 frase.
- Não repita pitch longo do produto duas vezes seguidas.

=== FOTOS ===
- Se FOTO_AUTOMÁTICA=sim → a foto já será enviada pelo sistema DEPOIS do seu texto.
  Responda SÓ: "Segue a foto do [nome] — R$ [preço]." (1 frase). Não diga "vou enviar".
- Se FOTO_AUTOMÁTICA=não e cliente pediu foto → diga honestamente:
  "Ainda não tenho foto desse produto aqui." + preço em 1 frase. Não prometa enviar.
- NUNCA diga "vou te enviar", "já te mando" se FOTO_AUTOMÁTICA=não.

=== PRODUTOS ===
- Use SOMENTE o catálogo enviado.
- Nunca invente preço ou produto.
- Resposta prática: nome + preço + 1 detalhe útil no máximo.

=== NÃO SEJA BURRA ===
- Cliente já disse o que quer → responda, não pergunte de novo.
- Não pergunte "como posso ajudar?" se ele já pediu produto/foto/preço.
- Não pergunte "posso separar?" em toda mensagem — só se cliente demonstrar interesse em comprar.
- Máximo 2 frases curtas. Sem textão.

=== ESTILO ===
- Português BR, WhatsApp, natural.
- Nunca diga que é IA.
"""


def resposta_saudacao(nome_cliente: str = "") -> str:
    if nome_cliente:
        return (
            f"Oi, {nome_cliente}! Tudo bem? Sou da Xnamai. "
            "Me conta o que você precisa 😊"
        )
    return "Oi! Tudo bem? Sou da Xnamai. Me conta o que você precisa 😊"


def resposta_sem_foto(produto: dict) -> str:
    nome = produto.get("nome", "produto")
    preco = produto.get("preco", "")
    if preco not in (None, ""):
        return f"Ainda não tenho foto do {nome} aqui. O preço é R$ {preco}."
    return f"Ainda não tenho foto do {nome} aqui."


def resposta_com_foto(produto: dict) -> str:
    nome = produto.get("nome", "produto")
    preco = produto.get("preco", "")
    if preco not in (None, ""):
        return f"Segue a foto do {nome} — R$ {preco} 👇"
    return f"Segue a foto do {nome} 👇"


def resposta_ja_informado(produto: dict) -> str:
    nome = produto.get("nome", "produto")
    preco = produto.get("preco", "")
    return f"Como te passei, o {nome} está R$ {preco}. Quer fechar?"


def perguntar_ia(
    mensagem: str,
    catalogo: str,
    historico_texto: str = "",
    nome_cliente: str = "",
    ultima_resposta_ia: str = "",
    foto_automatica: bool = False,
) -> str:
    nome = nome_cliente or "Cliente"

    entrada = f"""
CLIENTE: {nome}
FOTO_AUTOMÁTICA: {"sim" if foto_automatica else "não"}

ÚLTIMA RESPOSTA SUA (não repita):
{ultima_resposta_ia or "(nenhuma)"}

HISTÓRICO:
{historico_texto or "(primeira mensagem)"}

MENSAGEM ATUAL DO CLIENTE:
{mensagem}

CATÁLOGO:
{catalogo}
"""

    resposta = client.responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        input=entrada,
    )

    return resposta.output_text
