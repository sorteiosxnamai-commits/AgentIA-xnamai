"""Histórico útil, anti-repetição e montagem de contexto para a OpenAI."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.lower()).strip()


_LIXO_LINHA = (
    r"^webhook\b",
    r"^teste\b.*(z-?api|ultramsg|plataforma)",
    r"^\[system\]",
    r"^event_type=",
    r"^null$",
    r"^undefined$",
)


def limpar_linhas_historico(historico_texto: str) -> list[str]:
    """Remove lixo técnico, vazios e duplicatas consecutivas."""
    linhas_out: list[str] = []
    ultima_norm = ""
    for linha in (historico_texto or "").split("\n"):
        raw = linha.strip()
        if not raw:
            continue
        if not (raw.startswith("Cliente:") or raw.startswith("IA:")):
            continue
        corpo = raw.split(":", 1)[-1].strip()
        if not corpo:
            continue
        if any(re.search(p, _normalizar(corpo)) for p in _LIXO_LINHA):
            continue
        norm = _normalizar(raw)
        if norm == ultima_norm:
            continue
        linhas_out.append(raw)
        ultima_norm = norm
    return linhas_out


def montar_historico_util(
    historico_texto: str,
    *,
    max_linhas: int = 16,
    contexto: dict[str, Any] | None = None,
) -> str:
    """
    Não corta às cegas: limpa lixo, deduplica e prioriza linhas recentes
    mantendo âncoras (produto, orçamento, preferências) se existirem no contexto.
    """
    linhas = limpar_linhas_historico(historico_texto)
    if not linhas:
        return "(primeira mensagem)"

    recentes = linhas[-max_linhas:]
    ancora: list[str] = []
    ctx = contexto or {}

    # Garante que fatos essenciais não sumam se ficaram fora da janela
    essenciais = []
    if ctx.get("produto_mencionado") or ctx.get("produto_ativo"):
        essenciais.append(
            str(ctx.get("produto_mencionado") or ctx.get("produto_ativo"))
        )
    if ctx.get("categoria_interesse"):
        essenciais.append(str(ctx["categoria_interesse"]))
    if ctx.get("faixa_preco") or ctx.get("orcamento"):
        essenciais.append(str(ctx.get("faixa_preco") or ctx.get("orcamento")))

    if essenciais:
        recentes_norm = {_normalizar(l) for l in recentes}
        for linha in linhas:
            if linha in recentes:
                continue
            corpo = _normalizar(linha)
            if any(_normalizar(e) in corpo for e in essenciais if e):
                if _normalizar(linha) not in recentes_norm:
                    ancora.append(linha)
                    recentes_norm.add(_normalizar(linha))
        ancora = ancora[-4:]

    if ancora:
        return "\n".join(ancora + ["---"] + recentes)
    return "\n".join(recentes)


def extrair_ultima_pergunta_ia(historico_texto: str) -> str:
    for linha in reversed((historico_texto or "").split("\n")):
        if not linha.startswith("IA:"):
            continue
        texto = linha.replace("IA:", "", 1).strip()
        if "?" in texto:
            # pega a última sentença interrogativa
            partes = re.split(r"(?<=[?.!])\s+", texto)
            for p in reversed(partes):
                if "?" in p:
                    return p.strip()
            return texto
    return ""


def perguntas_ja_feitas(historico_texto: str) -> list[str]:
    feitas: list[str] = []
    for linha in (historico_texto or "").split("\n"):
        if not linha.startswith("IA:"):
            continue
        texto = linha.replace("IA:", "", 1).strip()
        if "?" not in texto:
            continue
        for p in re.split(r"(?<=[?.!])\s+", texto):
            if "?" in p:
                feitas.append(p.strip())
    return feitas[-10:]


def pergunta_ja_feita(pergunta: str, historico_texto: str) -> bool:
    alvo = _normalizar(pergunta)
    if not alvo:
        return False
    for feita in perguntas_ja_feitas(historico_texto):
        f = _normalizar(feita)
        if not f:
            continue
        if alvo == f or alvo in f or f in alvo:
            return True
        # overlap alto de tokens
        ta, tb = set(alvo.split()), set(f.split())
        if ta and tb and len(ta & tb) / len(ta | tb) >= 0.7:
            return True
    return False


def cliente_recusou_responder(mensagem: str) -> bool:
    t = _normalizar(mensagem)
    return bool(
        re.search(
            r"\b(nao|não)\s+(quero|vou|preciso)\s+(responder|falar|dizer)\b"
            r"|\b(nao|não)\s+quero\s+responder\b"
            r"|\bprefiro\s+nao\b|\bdeixa\s+pra\s+la\b|\bdeixa\s+para\s+la\b"
            r"|\bnao\s+interessa\b|\bpula\s+(essa|isso)\b",
            t,
        )
    )


def deve_evitar_pergunta(
    pergunta_candidata: str,
    historico_texto: str,
    contexto: dict[str, Any] | None = None,
    mensagem_atual: str = "",
) -> tuple[bool, str]:
    """Retorna (evitar?, motivo)."""
    ctx = contexto or {}
    if not (pergunta_candidata or "").strip():
        return False, ""

    if cliente_recusou_responder(mensagem_atual):
        return True, "cliente_recusou_responder"

    if pergunta_ja_feita(pergunta_candidata, historico_texto):
        return True, "pergunta_ja_feita"

    p = _normalizar(pergunta_candidata)

    # Já tem categoria → não perguntar tipo de produto
    if ctx.get("categoria_interesse") and re.search(
        r"tipo de produto|o que (voce|voces)?\s*procura|qual produto",
        p,
    ):
        return True, "categoria_ja_informada"

    # Já tem orçamento → não perguntar preço/orçamento
    if (ctx.get("faixa_preco") or ctx.get("orcamento")) and re.search(
        r"orcamento|orçamento|faixa de preco|preferencia de preco|preço|preco",
        p,
    ):
        return True, "orcamento_ja_informado"

    # Já tem nome → não perguntar nome
    if ctx.get("nome_cliente") and re.search(r"\b(seu )?nome\b|como (voce|se) chama", p):
        return True, "nome_ja_informado"

    return False, ""


def montar_bloco_contexto_openai(
    *,
    historico_texto: str,
    mensagem_atual: str,
    contexto: dict[str, Any] | None,
    info_cliente: dict[str, Any] | None = None,
    max_linhas: int = 16,
) -> str:
    """
    Contexto enviado à OpenAI: resumo estruturado + histórico útil + mensagem atual.
    Não corta às cegas as últimas N linhas.
    """
    ctx = dict(contexto or {})
    cliente = info_cliente or {}
    if cliente.get("nome") and not ctx.get("nome_cliente"):
        ctx["nome_cliente"] = str(cliente["nome"]).split()[0]

    resumo = {
        "nome_cliente": ctx.get("nome_cliente") or "",
        "categoria_interesse": ctx.get("categoria_interesse") or "",
        "produto_mencionado": ctx.get("produto_mencionado")
        or ctx.get("produto_ativo")
        or "",
        "faixa_preco": ctx.get("faixa_preco") or "",
        "orcamento": ctx.get("orcamento"),
        "marca_preferida": ctx.get("marca_preferida") or "",
        "caracteristicas": ctx.get("caracteristicas") or [],
        "ultima_pergunta_agente": ctx.get("ultima_pergunta_agente") or "",
        "perguntas_respondidas": ctx.get("perguntas_respondidas") or [],
        "estagio_conversa": ctx.get("estagio_conversa") or "",
        "ultima_recomendacao": ctx.get("ultima_recomendacao") or "",
        "resumo_curto": ctx.get("resumo_curto") or "",
    }
    resumo_limpo = {k: v for k, v in resumo.items() if v not in ("", None, [], {})}

    hist_util = montar_historico_util(
        historico_texto, max_linhas=max_linhas, contexto=ctx
    )

    partes = [
        "RESUMO ESTRUTURADO DA CONVERSA:",
        str(resumo_limpo) if resumo_limpo else "(sem fatos confirmados ainda)",
        "",
        "HISTÓRICO ÚTIL:",
        hist_util,
        "",
        f"MENSAGEM ATUAL DO CLIENTE: {(mensagem_atual or '').strip()}",
    ]
    return "\n".join(partes)


def extrair_perguntas_da_resposta(texto: str) -> list[str]:
    perguntas: list[str] = []
    for sent in re.split(r"(?<=[?.!])\s+", (texto or "").strip()):
        if "?" in sent:
            perguntas.append(sent.strip())
    return perguntas


def sanitizar_resposta_anti_repeticao(
    resposta: str,
    historico_texto: str,
    contexto: dict[str, Any] | None = None,
    mensagem_atual: str = "",
) -> tuple[str, list[str]]:
    """Remove perguntas desnecessárias da resposta. Retorna (texto, motivos)."""
    if not (resposta or "").strip():
        return resposta or "", []

    motivos: list[str] = []
    sentencas = re.split(r"(?<=[?.!])\s+", resposta.strip())
    mantidas: list[str] = []
    for sent in sentencas:
        if "?" not in sent:
            mantidas.append(sent)
            continue
        evitar, motivo = deve_evitar_pergunta(
            sent, historico_texto, contexto, mensagem_atual
        )
        if evitar:
            motivos.append(motivo or "pergunta_evitada")
            continue
        mantidas.append(sent)

    if not mantidas:
        if motivos:
            return (
                "Beleza — me conta como posso te ajudar no próximo passo.",
                motivos,
            )
        return resposta, motivos

    texto = " ".join(m.strip() for m in mantidas if m.strip())
    return texto, motivos


def registrar_perguntas_respondidas(
    contexto: dict[str, Any],
    mensagem_cliente: str,
) -> dict[str, Any]:
    """Marca a última pergunta do agente como respondida se o cliente falou algo útil."""
    out = dict(contexto or {})
    msg = (mensagem_cliente or "").strip()
    if not msg:
        return out
    if cliente_recusou_responder(msg):
        respondidas = list(out.get("perguntas_respondidas") or [])
        ultima = out.get("ultima_pergunta_agente") or ""
        if ultima:
            chave = f"recusou:{_normalizar(ultima)[:60]}"
            if chave not in respondidas:
                respondidas.append(chave)
        out["perguntas_respondidas"] = respondidas[-12:]
        return out

    ultima = (out.get("ultima_pergunta_agente") or "").strip()
    if not ultima:
        return out
    respondidas = list(out.get("perguntas_respondidas") or [])
    chave = _normalizar(ultima)[:80]
    if chave and chave not in respondidas:
        respondidas.append(chave)
    out["perguntas_respondidas"] = respondidas[-12:]
    return out
