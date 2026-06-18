from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

def perguntar_ia(mensagem):

    resposta = client.responses.create(
        model="gpt-5-mini",
        instructions="""
        Você é um atendente virtual da Xnamai.

        Sua função é ajudar clientes a encontrar qualquer produto ou serviço que estejam procurando.

        Regras:
        - Nunca assuma que o cliente quer celular.
        - Primeiro entenda o que o cliente procura.
        - Faça perguntas quando necessário.
        - Seja simpático e objetivo.
        - Responda sempre em português.
        - Sugira produtos apenas depois de entender a necessidade do cliente.
        - Se o cliente não especificar o produto, pergunte o que ele deseja comprar.
        """,
        input=mensagem
    )

    return resposta.output_text