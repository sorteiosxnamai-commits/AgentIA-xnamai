"""Memória estruturada da sessão de venda (curta + fatos + resumo)."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

SESSAO_PADRAO: dict[str, Any] = {
    "produto_ativo": "",
    "preco_cotado": None,
    "intencao": "neutro",
    "nf": None,
    "envio": None,
    "pagamento": None,
    "tom": "neutro",
    "fatos": [],
    "resumo_curto": "",
    # Etapa 2 — contexto estruturado
    "nome_cliente": "",
    "categoria_interesse": "",
    "produto_mencionado": "",
    "faixa_preco": "",
    "orcamento": None,
    "marca_preferida": "",
    "caracteristicas": [],
    "ultima_pergunta_agente": "",
    "perguntas_respondidas": [],
    "estagio_conversa": "abertura",
    "ultima_recomendacao": "",
    "ultima_intencao": "",
}

# Cache em processo (fallback se coluna contexto_venda não existir no Supabase)
_cache_sessao: dict[str, dict[str, Any]] = {}


def sessao_vazia() -> dict[str, Any]:
    return deepcopy(SESSAO_PADRAO)


def carregar_sessao(cliente: dict | None, cliente_id: str | None = None) -> dict[str, Any]:
    cid = str(cliente_id or (cliente or {}).get("id") or "")
    if cliente and isinstance(cliente.get("contexto_venda"), dict):
        base = sessao_vazia()
        base.update({k: v for k, v in cliente["contexto_venda"].items() if k in base})
        if cid:
            _cache_sessao[cid] = base
        return deepcopy(base)
    if cid and cid in _cache_sessao:
        return deepcopy(_cache_sessao[cid])
    return sessao_vazia()


def persistir_sessao(cliente_id: str, sessao: dict[str, Any]) -> None:
    if not cliente_id:
        return
    limpa = {k: sessao.get(k, SESSAO_PADRAO[k]) for k in SESSAO_PADRAO}
    _cache_sessao[str(cliente_id)] = deepcopy(limpa)
    try:
        from services.supabase_service import atualizar_cliente

        atualizar_cliente(cliente_id=cliente_id, contexto_venda=limpa)
    except Exception as exc:
        # Coluna pode não existir ainda — cache em memória basta
        print("AVISO contexto_venda não persistido:", type(exc).__name__, str(exc)[:120])


def limpar_sessao(cliente_id: str) -> None:
    _cache_sessao.pop(str(cliente_id), None)
    try:
        from services.supabase_service import atualizar_cliente

        atualizar_cliente(cliente_id=cliente_id, contexto_venda=sessao_vazia())
    except Exception:
        pass


def _adicionar_fato(sessao: dict[str, Any], fato: str) -> None:
    fato = (fato or "").strip()
    if not fato:
        return
    fatos = list(sessao.get("fatos") or [])
    if fato not in fatos:
        fatos.append(fato)
    sessao["fatos"] = fatos[-8:]


def atualizar_sessao_turno(
    sessao: dict[str, Any],
    *,
    historico_texto: str,
    mensagem: str = "",
    produtos: list | None = None,
    tom: str | None = None,
    intencao: str | None = None,
    nova_venda: bool = False,
    nome_cliente: str = "",
) -> dict[str, Any]:
    """Atualiza memória com extractors existentes + catálogo do turno."""
    from services.conversa_service import (
        _extrair_oferta_ia,
        _extrair_preco_historico,
        extrair_pagamento,
    )
    from services.historico_service import extrair_ultima_pergunta_ia
    from services.xnamai_script import extrair_forma_envio, extrair_preferencia_nf

    out = deepcopy(sessao) if sessao else sessao_vazia()
    if nova_venda:
        out = sessao_vazia()

    if nome_cliente:
        out["nome_cliente"] = nome_cliente.split()[0]

    nome_oferta, preco_oferta = _extrair_oferta_ia(historico_texto or "")
    if produtos:
        p0 = produtos[0] or {}
        if p0.get("nome"):
            out["produto_ativo"] = str(p0["nome"])
            out["produto_mencionado"] = str(p0["nome"])
            if p0.get("categoria"):
                out["categoria_interesse"] = str(p0["categoria"])
            bruto = p0.get("preco") if p0.get("preco") not in (None, "") else p0.get("preco_tabela")
            try:
                out["preco_cotado"] = float(bruto) if bruto not in (None, "") else out.get("preco_cotado")
            except (TypeError, ValueError):
                pass
            _adicionar_fato(out, f"Produto em discussão: {p0['nome']}")
    elif nome_oferta:
        out["produto_ativo"] = nome_oferta
        out["produto_mencionado"] = nome_oferta
        if preco_oferta is not None:
            out["preco_cotado"] = preco_oferta
        _adicionar_fato(out, f"Oferta ativa: {nome_oferta}")

    if out.get("preco_cotado") is None:
        preco_h = _extrair_preco_historico(historico_texto or "")
        if preco_h is not None:
            out["preco_cotado"] = preco_h

    # Orçamento / faixa de preço na mensagem do cliente
    msg_n = (mensagem or "").lower()
    m_orc = re.search(
        r"(?:orcamento|orçamento|ate|até|faixa|maximo|máximo).{0,24}?r?\$?\s*([\d.,]{2,})",
        msg_n,
    )
    if not m_orc:
        m_orc = re.search(r"r\$\s*([\d.,]{2,})", msg_n)
    if m_orc:
        try:
            valor = float(m_orc.group(1).replace(".", "").replace(",", "."))
            if valor > 20:
                out["orcamento"] = valor
                out["faixa_preco"] = f"até R$ {valor:.2f}".replace(".", ",")
                _adicionar_fato(out, f"Orçamento: {out['faixa_preco']}")
        except ValueError:
            pass

    # Marca preferida (só se citada)
    for marca in ("hmaston", "lenovo", "jbl", "logitech", "samsung", "apple", "kimaster", "knup"):
        if marca in msg_n:
            out["marca_preferida"] = marca
            _adicionar_fato(out, f"Marca: {marca}")
            break

    # Categoria por palavras-chave na mensagem
    cats = {
        "headset": "headset",
        "fone": "fone",
        "ssd": "armazenamento",
        "hd": "armazenamento",
        "cabo": "cabo",
        "hdmi": "cabo",
        "mouse": "mouse",
        "monitor": "monitor",
        "carregador": "carregador",
        "celular": "celular",
    }
    for chave, cat in cats.items():
        if re.search(rf"\b{chave}\b", msg_n):
            out["categoria_interesse"] = cat
            break

    nf = extrair_preferencia_nf(historico_texto or "", mensagem)
    if nf:
        out["nf"] = nf
        _adicionar_fato(out, f"NF: {nf}")

    envio = extrair_forma_envio(historico_texto or "", mensagem)
    if envio:
        out["envio"] = envio if envio in ("retirada", "envio") else "envio"
        _adicionar_fato(out, f"Envio: {out['envio']}")

    pag = extrair_pagamento(historico_texto or "", mensagem_atual=mensagem)
    if pag and pag != "a combinar":
        out["pagamento"] = pag
        _adicionar_fato(out, f"Pagamento: {pag}")

    if tom:
        out["tom"] = tom
    if intencao:
        out["intencao"] = intencao

    ultima_perg = extrair_ultima_pergunta_ia(historico_texto or "")
    if ultima_perg:
        out["ultima_pergunta_agente"] = ultima_perg

    # Estágio simples
    if out.get("pagamento") and out.get("envio"):
        out["estagio_conversa"] = "fechamento"
    elif out.get("produto_ativo") or out.get("produto_mencionado"):
        out["estagio_conversa"] = "negociacao"
    elif out.get("categoria_interesse"):
        out["estagio_conversa"] = "descoberta"
    else:
        out["estagio_conversa"] = "abertura"

    if out.get("produto_ativo"):
        out["ultima_recomendacao"] = str(out["produto_ativo"])

    # Resumo curto (1 linha) para o prompt
    partes = []
    if out.get("nome_cliente"):
        partes.append(f"nome={out['nome_cliente']}")
    if out.get("categoria_interesse"):
        partes.append(f"cat={out['categoria_interesse']}")
    if out.get("produto_ativo"):
        preco = out.get("preco_cotado")
        if preco is not None:
            partes.append(f"{out['produto_ativo']} (R$ {preco})")
        else:
            partes.append(str(out["produto_ativo"]))
    if out.get("faixa_preco"):
        partes.append(f"orc={out['faixa_preco']}")
    if out.get("marca_preferida"):
        partes.append(f"marca={out['marca_preferida']}")
    if out.get("nf"):
        partes.append(f"NF={out['nf']}")
    if out.get("envio"):
        partes.append(f"envio={out['envio']}")
    if out.get("tom") and out["tom"] != "neutro":
        partes.append(f"tom={out['tom']}")
    out["resumo_curto"] = "; ".join(partes) if partes else "Sessão aberta, sem produto definido."
    return out


def formatar_sessao_para_prompt(sessao: dict[str, Any] | None) -> str:
    s = sessao or sessao_vazia()
    return json.dumps(s, ensure_ascii=False, indent=2)


def mensagem_referencia_implicita(mensagem: str) -> bool:
    """Perguntas curtas que se referem ao produto já em discussão."""
    t = (mensagem or "").strip().lower()
    t = re.sub(r"[!?.,]+$", "", t)
    padroes = (
        r"^(tem|temos)\s+(preto|branco|azul|vermelho|rosa|verde|outro|outra|maior|menor)\??$",
        r"^(e\s+)?(de\s+)?(outra\s+)?cor\??$",
        r"^(tem\s+)?(em\s+)?estoque\??$",
        r"^e\s+o\s+(frete|envio|prazo)\??$",
        r"^(serve|funciona)\s+com\b",
        r"^(qual|quanto)\s+(e|é|eh)?\s*(o\s+)?(valor|preco|preço)",
        r"^quanto\s+(custa|fica|sai)",
        r"^(esse|essa|desse|dessa|dele|dela)\b",
        r"^tem\s+garantia\??$",
        r"^aceita\s+(pix|cartao|cartão)\??$",
    )
    return any(re.search(p, t) for p in padroes)


def mensagem_ambigua_para_llm(mensagem: str, sessao: dict[str, Any] | None) -> bool:
    """Quando há produto ativo e a pergunta é ambígua/cor/objeção — preferir LLM."""
    s = sessao or {}
    if not s.get("produto_ativo"):
        return False
    if mensagem_referencia_implicita(mensagem):
        return True
    t = (mensagem or "").lower()
    return bool(
        re.search(
            r"\b(caro|barato|desconto|duvida|dúvida|sera que|será que|melhor|"
            r"diferenca|diferença|vale a pena|outro modelo)\b",
            t,
        )
    )
