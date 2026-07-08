"""Registra vendas WhatsApp direto no Supabase — visível em Pedidos/Contatos/Relatórios."""

from __future__ import annotations

import hashlib
import os

from dotenv import load_dotenv

from database.supabase import supabase
from services.conversa_service import (
    _buscar_produto_do_historico,
    _extrair_preco_historico,
    extrair_endereco,
    extrair_nome_do_historico,
    extrair_pagamento,
    pedido_ja_encerrado,
)
from services.supabase_service import _executar, atualizar_cliente

load_dotenv(override=True)


def pulsedesk_pedidos_habilitado() -> bool:
    return os.getenv("PULSEDESK_PEDIDOS_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "sim",
        "yes",
    )


def _agora_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _id_sintetico(prefix: int, seed: str) -> int:
    digest = hashlib.sha256(f"{prefix}:{seed}".encode()).hexdigest()
    slot = int(digest[:10], 16) % 900_000_000
    return -(prefix * 1_000_000_000 + slot)


def _buscar_cliente_pulsedesk_por_telefone(telefone: str) -> dict | None:
    tel = (telefone or "").strip()
    if not tel:
        return None
    for campo in ("telefone", "celular"):
        resposta = supabase.table("clientes").select("*").eq(campo, tel).limit(1).execute()
        if resposta.data:
            return resposta.data[0]
    return None


def upsert_cliente_pulsedesk(
    telefone: str,
    nome: str = "",
    endereco: str = "",
    pulsedesk_id: int | None = None,
) -> int:
    existente = _buscar_cliente_pulsedesk_por_telefone(telefone)
    if existente and existente.get("mercos_id") is not None:
        mercos_id = int(existente["mercos_id"])
        campos = {
            "nome": nome or existente.get("nome") or f"WhatsApp {telefone[-4:]}",
            "razao_social": nome or existente.get("razao_social") or existente.get("nome"),
            "telefone": telefone,
            "celular": telefone,
            "ultima_alteracao": _agora_iso(),
        }
        if endereco:
            campos["endereco"] = endereco[:500]
        supabase.table("clientes").update(campos).eq("mercos_id", mercos_id).execute()
        return mercos_id

    mercos_id = int(pulsedesk_id) if pulsedesk_id else _id_sintetico(91, telefone)
    rotulo = nome or f"WhatsApp {telefone[-4:]}"
    dados = {
        "mercos_id": mercos_id,
        "nome": rotulo,
        "razao_social": rotulo,
        "telefone": telefone,
        "celular": telefone,
        "ultima_alteracao": _agora_iso(),
    }
    if endereco:
        dados["endereco"] = endereco[:500]

    _executar(
        lambda: supabase.table("clientes").upsert(dados, on_conflict="mercos_id").execute(),
        "upsert_cliente_pulsedesk",
    )
    return mercos_id


def criar_pedido_pulsedesk(
    cliente_mercos_id: int,
    produto_nome: str,
    valor_total: float,
    *,
    telefone: str = "",
) -> dict:
    agora = _agora_iso()
    seed = f"{telefone}:{cliente_mercos_id}:{produto_nome}:{valor_total}:{agora}"
    pedido_id = _id_sintetico(82, seed)
    numero = f"WA-{abs(pedido_id) % 1_000_000:06d}"

    dados = {
        "mercos_id": pedido_id,
        "numero": numero,
        "cliente_mercos_id": cliente_mercos_id,
        "valor_total": round(float(valor_total), 2),
        "situacao": "2",
        "quantidade_itens": 1,
        "data_pedido": agora,
        "ultima_alteracao": agora,
        "created_at": agora,
    }

    _executar(
        lambda: supabase.table("pedidos").upsert(dados, on_conflict="mercos_id").execute(),
        "criar_pedido_pulsedesk",
    )
    return {"pedido_id": pedido_id, "numero": numero, "cliente_id": cliente_mercos_id}


def registrar_venda_pulsedesk(
    historico_texto: str,
    cliente_supabase: dict,
    telefone: str,
    pushname: str = "",
    mensagem_atual: str = "",
    ultima_resposta_ia: str = "",
    frete_estimado: float = 0,
) -> dict | None:
    """Grava cliente + pedido no Supabase para o PulseDesk exibir sem sync Mercos."""
    if not pulsedesk_pedidos_habilitado():
        print("PULSEDESK: registro de pedidos desabilitado")
        return None

    if pedido_ja_encerrado(ultima_resposta_ia, historico_texto):
        print("PULSEDESK: pedido já registrado na conversa, ignorando duplicata")
        return None

    nome = extrair_nome_do_historico(historico_texto, pushname)
    endereco = extrair_endereco(historico_texto)
    extrair_pagamento(historico_texto, mensagem_atual, ultima_resposta_ia)
    produto = _buscar_produto_do_historico(historico_texto) or {}
    produto_nome = produto.get("nome") or "Produto WhatsApp"

    preco = _extrair_preco_historico(historico_texto)
    if preco is None:
        preco = produto.get("preco") or 0

    try:
        valor = float(str(preco).replace(",", "."))
    except (TypeError, ValueError):
        valor = 0.0

    valor += float(frete_estimado or 0)

    if valor <= 0:
        print("PULSEDESK: valor inválido, pedido não criado")
        return {"erro": "valor_invalido"}

    try:
        cliente_ref = cliente_supabase.get("mercos_cliente_id")
        cliente_mercos_id = upsert_cliente_pulsedesk(
            telefone=telefone,
            nome=nome,
            endereco=endereco,
            pulsedesk_id=int(cliente_ref) if cliente_ref else None,
        )

        pedido = criar_pedido_pulsedesk(
            cliente_mercos_id=cliente_mercos_id,
            produto_nome=produto_nome,
            valor_total=valor,
            telefone=telefone,
        )

        try:
            atualizar_cliente(cliente_supabase["id"], mercos_cliente_id=cliente_mercos_id)
        except Exception as exc:
            print("AVISO: mercos_cliente_id agente:", exc)

        print("PULSEDESK PEDIDO CRIADO:", pedido)
        return pedido
    except Exception as exc:
        print("PULSEDESK PEDIDO FALHOU:", exc)
        return {"erro": str(exc)}
