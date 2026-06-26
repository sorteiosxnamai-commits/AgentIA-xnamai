import os
import time

from dotenv import load_dotenv
from openai import OpenAI, NotFoundError

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID", "").strip()
USE_ASSISTANT = os.getenv("OPENAI_USE_ASSISTANT", "false").strip().lower() in (
    "1",
    "true",
    "sim",
    "yes",
)

INSTRUCTIONS = """
Você é a atendente da Xnamai no WhatsApp. Tom humano, simpático e profissional.

REGRAS OBRIGATÓRIAS:
1. Sempre responda em português do Brasil.
2. Mensagens CURTAS: 2 a 4 frases. Estilo WhatsApp.
3. Nunca diga que é IA, robô ou assistente virtual.
4. Use SOMENTE produtos do catálogo enviado na mensagem.
5. Nunca invente produto, preço ou estoque.
6. Se estoque aparecer 0 ou vazio, trate como DISPONÍVEL (catálogo sandbox).
7. Nunca diga que "nada está disponível" se houver produtos no catálogo.

SAUDAÇÃO (oi, olá, bom dia):
- Cumprimente de volta com carinho.
- Apresente-se brevemente como Xnamai.
- Pergunte o que a pessoa procura.
- Pode citar 1 ou 2 produtos do catálogo como exemplo, sem textão.

PRODUTO ESPECÍFICO:
- Diga nome, preço e confirme disponibilidade.
- Responda direto. Não faça perguntas óbvias.

NÃO PERGUNTE:
- "Como posso ajudar?" se o cliente já disse o que quer.
- "Qual produto?" se ele já mencionou.
- Dados pessoais (CPF, endereço).

EXEMPLO SAUDAÇÃO:
Cliente: Olá
Resposta: Oi! Tudo bem? 😊 Sou da Xnamai. Posso te ajudar a encontrar fones, carregadores e muito mais. O que você está procurando hoje?
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


def _montar_entrada_responses(
    mensagem: str,
    catalogo: str,
    historico_texto: str,
    nome_cliente: str,
    eh_saudacao: bool,
) -> str:
    nome = nome_cliente or "Cliente"
    tipo = "SAUDAÇÃO — cumprimente e pergunte o que procura" if eh_saudacao else "ATENDIMENTO"

    return f"""
TIPO DESTA MENSAGEM: {tipo}
NOME DO CLIENTE: {nome}

HISTÓRICO RECENTE:
{historico_texto or "(primeira mensagem)"}

MENSAGEM ATUAL DO CLIENTE:
{mensagem}

CATÁLOGO PARA USAR NA RESPOSTA:
{catalogo}
"""


def _montar_entrada_assistant(
    mensagem: str,
    catalogo: str,
    nome_cliente: str,
    eh_saudacao: bool,
) -> str:
    nome = nome_cliente or "Cliente"
    tipo = "saudação" if eh_saudacao else "atendimento"

    return f"""
Cliente ({nome}) disse: {mensagem}
Tipo: {tipo}

Catálogo:
{catalogo}
"""


def _perguntar_assistant(entrada: str, thread_id: str | None = None) -> tuple[str, str]:
    if not thread_id:
        thread_id = client.beta.threads.create().id

    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=entrada,
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


def _perguntar_responses(entrada: str) -> tuple[str, None]:
    resposta = client.responses.create(
        model="gpt-4o-mini",
        instructions=INSTRUCTIONS,
        input=entrada,
    )
    return resposta.output_text, None


def perguntar_ia(
    mensagem: str,
    catalogo: str,
    historico_texto: str = "",
    nome_cliente: str = "",
    eh_saudacao: bool = False,
    thread_id: str | None = None,
) -> tuple[str, str | None]:
    usar_assistant = USE_ASSISTANT and bool(ASSISTANT_ID)

    if usar_assistant:
        entrada = _montar_entrada_assistant(
            mensagem, catalogo, nome_cliente, eh_saudacao
        )
        try:
            return _perguntar_assistant(entrada, thread_id)
        except NotFoundError:
            print("AVISO: Assistant não encontrado. Usando Responses API.")
        except Exception as e:
            if "No assistant found" not in str(e):
                raise
            print("AVISO: Assistant inválido. Usando Responses API.")

    entrada = _montar_entrada_responses(
        mensagem, catalogo, historico_texto, nome_cliente, eh_saudacao
    )
    return _perguntar_responses(entrada)
