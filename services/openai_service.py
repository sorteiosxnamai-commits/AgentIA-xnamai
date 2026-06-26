import os
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID", "").strip()

FALLBACK_INSTRUCTIONS = """
Você é a atendente oficial da Xnamai no WhatsApp.

Responda PRIMEIRO com informação útil. Use SOMENTE produtos do catálogo enviado.
Nunca invente produto, preço ou estoque. Mensagens curtas (2 a 4 frases).
Não faça perguntas desnecessárias quando o cliente já disse o que quer.
"""


def _extrair_texto_resposta(messages) -> str:
    for message in messages.data:
        if message.role != "assistant":
            continue

        partes = []
        for block in message.content:
            if block.type == "text":
                partes.append(block.text.value)

        if partes:
            return "\n".join(partes).strip()

    raise ValueError("Assistant não retornou texto na resposta.")


def _perguntar_assistant(contexto: str, thread_id: str | None = None) -> tuple[str, str]:
    if not thread_id:
        thread_id = client.beta.threads.create().id

    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=contexto,
    )

    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
    )

    while run.status in ("queued", "in_progress"):
        time.sleep(0.5)
        run = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id,
        )

    if run.status != "completed":
        raise ValueError(f"OpenAI Assistant falhou com status: {run.status}")

    messages = client.beta.threads.messages.list(
        thread_id=thread_id,
        order="desc",
        limit=5,
    )

    return _extrair_texto_resposta(messages), thread_id


def _perguntar_responses(contexto: str) -> tuple[str, None]:
    resposta = client.responses.create(
        model="gpt-5",
        instructions=FALLBACK_INSTRUCTIONS,
        input=contexto,
    )
    return resposta.output_text, None


def perguntar_ia(contexto: str, thread_id: str | None = None) -> tuple[str, str | None]:
    """
    Usa o Assistant da OpenAI (OPENAI_ASSISTANT_ID) se configurado.
    Caso contrário, usa a API Responses com prompt local.
    Retorna (texto_resposta, thread_id).
    """
    if ASSISTANT_ID:
        return _perguntar_assistant(contexto, thread_id)

    return _perguntar_responses(contexto)
