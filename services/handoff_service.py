"""Etapa 6 — handoff para atendimento humano + resumo para o vendedor.

Não cria pedido, Pix nem reserva. Só marca contexto_venda e monta resumo.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.intent_service import resposta_atendimento_humano

MOTIVO_CLIENTE_PEDIU = "cliente pediu atendimento humano"

CAMPOS_RESUMO = (
    "nome_cliente",
    "telefone",
    "produto_interesse",
    "preco_cotado",
    "quantidade",
    "forma_entrega",
    "cidade",
    "endereco",
    "forma_pagamento",
    "status_conversa",
    "proximo_passo_recomendado",
    "resumo_curto",
)


def _vazio(valor: Any) -> bool:
    return valor is None or valor == "" or valor == [] or valor == {}


def _str_ou_vazio(valor: Any) -> str:
    if valor is None:
        return ""
    s = str(valor).strip()
    return s


def _produto_interesse(sessao: dict[str, Any]) -> str:
    for chave in ("produto_checkout", "produto_ativo", "produto_mencionado", "ultima_recomendacao"):
        v = _str_ou_vazio(sessao.get(chave))
        if v:
            return v
    return ""


def _proximo_passo(sessao: dict[str, Any], produto: str) -> str:
    if not produto:
        return "Contatar o cliente, entender a necessidade e retomar o atendimento."
    if not _str_ou_vazio(sessao.get("forma_entrega")):
        return "Confirmar forma de entrega e dados necessários com o cliente."
    if not _str_ou_vazio(sessao.get("forma_pagamento")):
        return "Confirmar forma de pagamento e fechar a venda com o cliente."
    return "Retomar o atendimento e concluir a compra com o cliente."


def _resumo_curto(
    *,
    nome: str,
    produto: str,
    preco: Any,
    quantidade: Any,
    entrega: str,
    cidade: str,
) -> str:
    partes: list[str] = []
    if nome:
        partes.append(nome)
    else:
        partes.append("Cliente")
    partes.append("pediu atendimento humano")
    if produto:
        trecho = f"interesse em {produto}"
        if preco not in (None, ""):
            try:
                trecho += f" (R$ {float(preco):.2f})".replace(".", ",")
            except (TypeError, ValueError):
                trecho += f" ({preco})"
        partes.append(trecho)
    if quantidade not in (None, ""):
        partes.append(f"qtd {quantidade}")
    if entrega:
        partes.append(entrega)
    if cidade:
        partes.append(cidade)
    return ". ".join(partes[:1] + [", ".join(partes[1:])]) if len(partes) > 1 else partes[0]


def montar_resumo_vendedor(
    sessao: dict[str, Any] | None,
    *,
    nome_cliente: str = "",
    telefone: str = "",
) -> dict[str, Any]:
    """Monta resumo para o vendedor — não inventa dados ausentes."""
    s = sessao or {}
    nome = _str_ou_vazio(nome_cliente) or _str_ou_vazio(s.get("nome_cliente"))
    produto = _produto_interesse(s)
    preco = s.get("preco_cotado")
    if preco in ("",):
        preco = None
    quantidade = s.get("quantidade")
    if quantidade in ("",):
        quantidade = None
    entrega = _str_ou_vazio(s.get("forma_entrega"))
    cidade = _str_ou_vazio(s.get("cidade"))
    endereco = _str_ou_vazio(s.get("endereco"))
    pagamento = _str_ou_vazio(s.get("forma_pagamento"))
    status = _str_ou_vazio(s.get("estagio_conversa")) or _str_ou_vazio(
        s.get("checkout_status")
    ) or "handoff"
    proximo = _proximo_passo(s, produto)
    curto = _resumo_curto(
        nome=nome,
        produto=produto,
        preco=preco,
        quantidade=quantidade,
        entrega=entrega,
        cidade=cidade,
    )
    return {
        "nome_cliente": nome or None,
        "telefone": _str_ou_vazio(telefone) or None,
        "produto_interesse": produto or None,
        "preco_cotado": preco,
        "quantidade": quantidade,
        "forma_entrega": entrega or None,
        "cidade": cidade or None,
        "endereco": endereco or None,
        "forma_pagamento": pagamento or None,
        "status_conversa": status or None,
        "proximo_passo_recomendado": proximo,
        "resumo_curto": curto,
    }


def aplicar_handoff_sessao(
    sessao: dict[str, Any] | None,
    *,
    motivo: str = MOTIVO_CLIENTE_PEDIU,
    nome_cliente: str = "",
    telefone: str = "",
) -> dict[str, Any]:
    """Marca precisa_humano e grava resumo_vendedor na sessão."""
    out = deepcopy(sessao) if sessao else {}
    motivo_final = (motivo or MOTIVO_CLIENTE_PEDIU).strip() or MOTIVO_CLIENTE_PEDIU
    resumo = montar_resumo_vendedor(
        out,
        nome_cliente=nome_cliente,
        telefone=telefone,
    )
    out["precisa_humano"] = True
    out["motivo_handoff"] = motivo_final
    out["handoff_status"] = "pendente"
    out["resumo_vendedor"] = resumo
    out["estagio_conversa"] = "handoff"
    return out


def processar_handoff(
    sessao: dict[str, Any] | None,
    *,
    nome_cliente: str = "",
    telefone: str = "",
    motivo: str = MOTIVO_CLIENTE_PEDIU,
) -> dict[str, Any]:
    """Aplica handoff e devolve reply + debug (sem criar pedido)."""
    sessao_nova = aplicar_handoff_sessao(
        sessao,
        motivo=motivo,
        nome_cliente=nome_cliente,
        telefone=telefone,
    )
    resumo = sessao_nova.get("resumo_vendedor") or {}
    reply = resposta_atendimento_humano(nome_cliente or sessao_nova.get("nome_cliente") or "")
    debug = {
        "handoff_detectado": True,
        "precisa_humano": True,
        "motivo_handoff": sessao_nova.get("motivo_handoff") or "",
        "resumo_vendedor_gerado": bool(resumo) and not _vazio(resumo.get("resumo_curto")),
    }
    return {
        "ok": True,
        "sessao": sessao_nova,
        "reply": reply,
        "debug": debug,
        "pedido_criado": False,
    }


def handoff_debug_vazio() -> dict[str, Any]:
    return {
        "handoff_detectado": False,
        "precisa_humano": False,
        "motivo_handoff": "",
        "resumo_vendedor_gerado": False,
    }


def handoff_debug_da_sessao(sessao: dict[str, Any] | None) -> dict[str, Any]:
    s = sessao or {}
    precisa = bool(s.get("precisa_humano"))
    resumo = s.get("resumo_vendedor") if isinstance(s.get("resumo_vendedor"), dict) else {}
    return {
        "handoff_detectado": precisa,
        "precisa_humano": precisa,
        "motivo_handoff": _str_ou_vazio(s.get("motivo_handoff")),
        "resumo_vendedor_gerado": bool(resumo.get("resumo_curto")),
    }
