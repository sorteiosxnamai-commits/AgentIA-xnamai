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
        input=mensagem
    )

    return resposta.output_text