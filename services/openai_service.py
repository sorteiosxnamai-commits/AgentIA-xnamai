import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

INSTRUCTIONS = """
Você é a atendente oficial da Xnamai no WhatsApp.

Você sempre receberá: histórico da conversa, mensagem do cliente e catálogo de produtos.

=== REGRA DE OURO ===
Responda PRIMEIRO com informação útil. Só faça pergunta se for IMPOSSÍVEL ajudar sem ela.

=== PRODUTOS ===
- Use SOMENTE produtos do catálogo enviado.
- Nunca invente produto, preço ou estoque.
- Se estoque for 0 ou vazio, trate como disponível.
- Cliente pediu algo e existe no catálogo → apresente nome e preço na hora.
- Não existe no catálogo → diga claramente e sugira alternativa do catálogo se houver.

=== SAUDAÇÃO (oi, olá, bom dia) ===
- APENAS cumprimente de volta e se apresente como Xnamai.
- NÃO liste produtos. NÃO mencione preços. NÃO cite o catálogo.
- Pode perguntar em 1 frase o que a pessoa procura.
- Máximo 2 frases curtas.

=== NÃO FAÇA PERGUNTAS DESNECESSÁRIAS ===
- Não pergunte "como posso ajudar?" se o cliente já disse o que quer.
- Não repita perguntas do histórico.

=== ESTILO ===
- Português do Brasil, natural e profissional.
- 2 a 4 frases. Estilo WhatsApp.
- Nunca diga que é IA.
"""


def resposta_saudacao(nome_cliente: str = "") -> str:
    """Resposta fixa para oi/olá — sem listar produtos."""
    if nome_cliente:
        return (
            f"Oi, {nome_cliente}! Tudo bem? Sou da Xnamai. "
            "Me conta o que você precisa 😊"
        )
    return "Oi! Tudo bem? Sou da Xnamai. Me conta o que você precisa 😊"


def perguntar_ia(
    mensagem: str,
    catalogo: str,
    historico_texto: str = "",
    nome_cliente: str = "",
    eh_saudacao: bool = False,
) -> str:
    nome = nome_cliente or "Cliente"
    tipo = "SAUDAÇÃO" if eh_saudacao else "ATENDIMENTO"

    entrada = f"""
TIPO: {tipo}
CLIENTE: {nome}

HISTÓRICO:
{historico_texto or "(primeira mensagem)"}

MENSAGEM ATUAL:
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
