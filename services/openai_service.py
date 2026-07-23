import os
import re
import unicodedata

from dotenv import load_dotenv
from openai import OpenAI

from services.vendas.contexto import ContextoVenda
from services.vendas.prompt import montar_entrada_ia, montar_instrucoes

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.3"))
TEMPERATURE_CONVERSA = float(os.getenv("OPENAI_TEMPERATURE_CONVERSA", "0.5"))


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.lower()).strip()


def _muito_parecida(a: str, b: str) -> bool:
    """Similaridade simples: overlap de tokens altos = repetição."""
    ta = set(_normalizar(a).split())
    tb = set(_normalizar(b).split())
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    union = len(ta | tb)
    return (inter / union) >= 0.72 and len(ta) >= 4


def resposta_saudacao(nome_cliente: str = "") -> str:
    from services.xnamai_script import resposta_saudacao_xnamai

    return resposta_saudacao_xnamai(nome_cliente)


def resposta_sem_foto(produto: dict) -> str:
    nome = produto.get("nome", "produto")
    preco = produto.get("preco", "")
    if preco not in (None, ""):
        return (
            f"Para o que você precisa, indico o {nome} por R$ {preco}. "
            f"É uma boa opção custo-benefício. Quer que eu te passe mais detalhes "
            f"ou prefere ver outra faixa de preço?"
        )
    return (
        f"Indico o {nome} para o que você comentou. "
        f"Quer que eu te passe os detalhes principais?"
    )


def resposta_com_foto(produto: dict) -> str:
    nome = produto.get("nome", "produto")
    preco = produto.get("preco", "")
    if preco not in (None, ""):
        return f"Segue a foto do {nome} — R$ {preco}"
    return f"Segue a foto do {nome}"


def resposta_ja_informado(produto: dict) -> str:
    nome = produto.get("nome", "produto")
    preco = produto.get("preco", "")
    return f"O {nome} está R$ {preco}. Fechamos?"


def _chamar_openai(instrucoes: str, entrada: str, temperature: float) -> str:
    """LEGADO — mantido apenas como backup. Não é mais chamado pelo fluxo ativo."""
    kwargs = {
        "model": MODEL,
        "instructions": instrucoes,
        "input": entrada,
    }
    try:
        resposta = client.responses.create(**kwargs, temperature=temperature)
    except TypeError:
        resposta = client.responses.create(**kwargs)
    except Exception:
        resposta = client.responses.create(**kwargs)
    return (resposta.output_text or "").strip()


def _perguntar_ia_legado(
    mensagem: str,
    catalogo: str,
    historico_texto: str = "",
    nome_cliente: str = "",
    ultima_resposta_ia: str = "",
    foto_automatica: bool = False,
    contexto_venda: ContextoVenda | None = None,
    memoria_sessao: dict | None = None,
    temperature: float | None = None,
    mcp_enrichment: str = "",
) -> str:
    """Implementação anterior (xNaMai / Responses API). Preservada, NÃO chamada."""
    ctx = contexto_venda or ContextoVenda(catalogo=catalogo)
    if catalogo and not ctx.catalogo:
        ctx.catalogo = catalogo

    mem = memoria_sessao or getattr(ctx, "memoria", None) or {}
    temp = TEMPERATURE if temperature is None else temperature

    instrucoes = montar_instrucoes(ctx.briefing)
    entrada = montar_entrada_ia(
        nome_cliente=nome_cliente,
        mensagem=mensagem,
        historico_texto=historico_texto,
        ultima_resposta_ia=ultima_resposta_ia,
        catalogo=ctx.catalogo or catalogo,
        contexto_venda=ctx,
        foto_automatica=foto_automatica,
        memoria_sessao=mem,
        mcp_enrichment=mcp_enrichment or "",
    )

    texto = _chamar_openai(instrucoes, entrada, temp)

    if ultima_resposta_ia and _muito_parecida(texto, ultima_resposta_ia):
        instrucoes2 = (
            instrucoes
            + "\n\n=== ANTI-REPETIÇÃO ===\n"
            "Sua última resposta foi quase idêntica. Reformule com outras palavras, "
            "mantenha o mesmo conteúdo útil, sem 'Claro!'/'Com certeza!'."
        )
        texto2 = _chamar_openai(instrucoes2, entrada, max(temp, TEMPERATURE_CONVERSA))
        if texto2:
            texto = texto2

    from services.intent_service import sanitizar_frases_comerciais

    stock_ok = False
    prods = getattr(ctx, "produtos", None) or []
    if prods:
        p0 = prods[0] or {}
        qty = p0.get("stock_quantity", p0.get("estoque"))
        try:
            stock_ok = bool(
                p0.get("stock_confirmed")
                and qty is not None
                and float(qty) > 0
            )
        except (TypeError, ValueError):
            stock_ok = False

    return sanitizar_frases_comerciais(texto, stock_confirmed=stock_ok)


def perguntar_ia(
    mensagem: str,
    catalogo: str,
    historico_texto: str = "",
    nome_cliente: str = "",
    ultima_resposta_ia: str = "",
    foto_automatica: bool = False,
    contexto_venda: ContextoVenda | None = None,
    memoria_sessao: dict | None = None,
    temperature: float | None = None,
    mcp_enrichment: str = "",
) -> str:
    """Interface pública do cérebro. Roteia por AGENT_VERSION (novo|legado).

    novo → agents.vendas (Agente de Vendas da xNamai)
    legado → _perguntar_ia_legado
    Nunca executa os dois agentes na mesma mensagem.
    """
    from services.intent_service import sanitizar_frases_comerciais

    versao = (os.getenv("AGENT_VERSION") or "novo").strip().lower()
    if versao not in ("novo", "legado"):
        print("AVISO AGENT_VERSION invalido; usando novo | valor=", versao[:32])
        versao = "novo"

    telefone = ""
    message_id = ""
    input_modality = "text"
    if isinstance(memoria_sessao, dict):
        telefone = str(
            memoria_sessao.get("telefone") or memoria_sessao.get("phone") or ""
        ).strip()
        message_id = str(memoria_sessao.get("message_id") or "").strip()
        input_modality = str(memoria_sessao.get("input_modality") or "text").strip() or "text"

    if versao == "legado":
        print("EVT=resposta_origem | origem=legacy_agent")
        texto = _perguntar_ia_legado(
            mensagem=mensagem,
            catalogo=catalogo,
            historico_texto=historico_texto,
            nome_cliente=nome_cliente,
            ultima_resposta_ia=ultima_resposta_ia,
            foto_automatica=foto_automatica,
            contexto_venda=contexto_venda,
            memoria_sessao=memoria_sessao,
            temperature=temperature,
            mcp_enrichment=mcp_enrichment,
        )
    else:
        from agents.vendas import processar_mensagem_sync

        print("EVT=resposta_origem | origem=xnamai_sales_agent")
        _ = (foto_automatica, temperature, mcp_enrichment)
        ctx = contexto_venda
        produtos_ctx = list(getattr(ctx, "produtos", None) or []) if ctx is not None else []
        fonte_ctx = str(getattr(ctx, "fonte", "") or "") if ctx is not None else ""
        catalogo_final = catalogo or (getattr(ctx, "catalogo", "") if ctx is not None else "") or ""
        try:
            texto = processar_mensagem_sync(
                mensagem=mensagem or "",
                telefone=telefone,
                nome=nome_cliente or None,
                historico_texto=historico_texto or "",
                ultima_resposta_ia=ultima_resposta_ia or "",
                catalogo=catalogo_final,
                memoria_sessao=memoria_sessao if isinstance(memoria_sessao, dict) else None,
                input_modality=input_modality,
                message_id=message_id or None,
                produtos_contexto=produtos_ctx,
                fonte_produtos=fonte_ctx,
            )
        except Exception as exc:
            print("AVISO xnamai_sales_agent falhou:", type(exc).__name__, str(exc)[:120])
            if produtos_ctx:
                from agents.vendas.context_builder import reply_from_preloaded_products

                texto = reply_from_preloaded_products(
                    {"produtos_precarregados": produtos_ctx}
                ) or (
                    "Não consegui consultar o catálogo agora. "
                    "Tente novamente em instantes."
                )
            else:
                texto = (
                    "Não consegui concluir o atendimento agora. "
                    "Pode tentar novamente ou pedir atendimento humano?"
                )

    stock_ok = False
    ctx = contexto_venda
    prods = getattr(ctx, "produtos", None) or [] if ctx is not None else []
    if prods:
        p0 = prods[0] or {}
        qty = p0.get("stock_quantity", p0.get("estoque"))
        try:
            stock_ok = bool(
                p0.get("stock_confirmed")
                and qty is not None
                and float(qty) > 0
            )
        except (TypeError, ValueError):
            stock_ok = False

    return sanitizar_frases_comerciais(texto or "", stock_confirmed=stock_ok)
