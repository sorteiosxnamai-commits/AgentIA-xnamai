"""Router de intenção → tools MCP necessárias (regras, não LLM)."""

from __future__ import annotations

import re
import unicodedata


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().strip()


def decide_tools(mensagem: str, sessao: dict | None = None) -> list[dict]:
    """Retorna lista [{name, args}, ...] mínima para enriquecer o turno."""
    t = _norm(mensagem)
    sessao = sessao or {}
    calls: list[dict] = []

    # Sempre carrega contexto se houver produto/sessão
    calls.append({"name": "contexto.carregar", "args": {}})

    # Busca de produto
    if re.search(
        r"\b(quero|tem|preciso|procuro|headset|cabo|hdmi|mouse|monitor|notebook|"
        r"webcam|ssd|hub|fone|teclado|hd)\b",
        t,
    ) and not re.search(r"\b(retirar|retirada|envio|sem nf|com nf)\b", t):
        calls.append({"name": "produtos.buscar", "args": {"consulta": mensagem}})

    if re.search(r"\b(valor|preco|preço|quanto custa|quanto fica)\b", t):
        calls.append({"name": "produtos.preco", "args": {}})

    if re.search(r"\b(estoque|disponivel|disponível|tem todos|vai ter)\b", t):
        calls.append({"name": "produtos.estoque", "args": {}})

    if re.search(r"\b(pedido|meus pedidos|status do pedido|acompanhar)\b", t):
        calls.append({"name": "pedidos.consultar", "args": {}})

    if re.search(r"\b(carrinho|adicionar|coloca no|tira do|quantidade)\b", t):
        calls.append({"name": "carrinho.consultar", "args": {}})
        if re.search(r"\b(adicion|coloca|quero\s+\d+)\b", t) and sessao.get("produto_ativo"):
            calls.append(
                {
                    "name": "carrinho.adicionar",
                    "args": {"nome": sessao.get("produto_ativo")},
                }
            )

    if re.search(r"\b(nf|nota fiscal)\b", t):
        calls.append({"name": "nf.consultar", "args": {}})

    if re.search(r"\b(frete|envio|retirada|retirar|correios)\b", t):
        calls.append({"name": "envio.consultar", "args": {}})
        if re.search(r"\bfrete\b", t):
            calls.append({"name": "frete.cotar", "args": {}})

    if re.search(r"\b(pix|pagamento|cartao|cartão|boleto)\b", t):
        calls.append({"name": "pagamento.consultar", "args": {}})

    if re.search(r"\b(orcamento|orçamento|cotacao|cotação)\b", t):
        calls.append({"name": "orcamento.gerar", "args": {}})

    if re.search(r"\b(humano|atendente|pessoa|falar com alguem|falar com alguém)\b", t):
        calls.append({"name": "atendimento.transferir_humano", "args": {}})

    if re.search(r"\b(credito|crédito)\b", t):
        calls.append({"name": "credito.registrar", "args": {}})
    if re.search(r"\b(estorno|reembolso)\b", t):
        calls.append({"name": "estorno.registrar", "args": {}})

    # Referência implícita com produto ativo → preço + estoque leves
    if sessao.get("produto_ativo") and re.search(
        r"^(tem|qual|quanto|e o|esse|dessa|dele)\b", t
    ):
        if not any(c["name"] == "produtos.preco" for c in calls):
            calls.append({"name": "produtos.preco", "args": {}})

    # Dedup por nome mantendo ordem
    vistos = set()
    unicos = []
    for c in calls:
        if c["name"] in vistos:
            continue
        vistos.add(c["name"])
        unicos.append(c)
    return unicos


def enrich_turno(
    *,
    mensagem: str,
    sessao: dict,
    cliente_id: str = "",
    telefone: str = "",
    nome_cliente: str = "",
    historico_texto: str = "",
) -> tuple[dict, str, dict]:
    """
    Executa tools MCP do turno.
    Retorna (sessao_atualizada, bloco_prompt, resultados_dict).
    """
    from services.mcp.client import get_client
    from services.mcp.context import build_session_context, sync_carrinho_to_store
    from services.mcp.flags import mcp_enabled
    from services.mcp.formatter import para_prompt

    if not mcp_enabled():
        return sessao, "", {}

    ctx = build_session_context(
        cliente_id=cliente_id,
        telefone=telefone,
        nome_cliente=nome_cliente,
        historico_texto=historico_texto,
        mensagem=mensagem,
        sessao=sessao,
        caller="rules",
    )
    calls = decide_tools(mensagem, sessao)
    client = get_client()
    results = client.invoke_many(calls, ctx)
    sync_carrinho_to_store(ctx)

    # Propaga preferências de volta à sessão
    nova = dict(sessao or {})
    nova.update(ctx.sessao or {})
    if ctx.preferencias.get("nf"):
        nova["nf"] = ctx.preferencias["nf"]
    if ctx.preferencias.get("envio"):
        nova["envio"] = ctx.preferencias["envio"]
    if ctx.preferencias.get("pagamento"):
        nova["pagamento"] = ctx.preferencias["pagamento"]
    if ctx.produtos_consultados and not nova.get("produto_ativo"):
        p0 = ctx.produtos_consultados[0]
        nova["produto_ativo"] = p0.get("nome") or ""
        nova["preco_cotado"] = p0.get("preco")

    bloco = para_prompt(results)
    serializado = {k: v.to_dict() for k, v in results.items()}
    return nova, bloco, serializado
