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
    historico_desde_ultimo_fechamento,
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


def _upsert_seguro(tabela: str, dados: dict, *, conflito: str, rotulo: str) -> None:
    """Upsert removendo colunas opcionais ausentes no schema Supabase."""
    payload = dict(dados)
    opcionais = (
        "ultima_alteracao",
        "created_at",
        "data_pedido",
        "quantidade_itens",
        "produto_nome",
        "produto_codigo",
        "endereco",
        "razao_social",
    )

    while True:
        try:
            _executar(
                lambda p=payload: supabase.table(tabela).upsert(p, on_conflict=conflito).execute(),
                rotulo,
            )
            return
        except Exception as exc:
            msg = str(exc).lower()
            if "pgrst204" not in msg:
                raise
            removido = False
            for campo in opcionais:
                if campo in payload and campo in msg:
                    payload.pop(campo, None)
                    removido = True
                    break
            if not removido:
                raise


def _update_seguro(tabela: str, dados: dict, *, filtro: str, valor) -> None:
    payload = dict(dados)
    opcionais = ("ultima_alteracao", "endereco", "razao_social")

    while True:
        try:
            supabase.table(tabela).update(payload).eq(filtro, valor).execute()
            return
        except Exception as exc:
            msg = str(exc).lower()
            if "pgrst204" not in msg:
                raise
            removido = False
            for campo in opcionais:
                if campo in payload and campo in msg:
                    payload.pop(campo, None)
                    removido = True
                    break
            if not removido:
                raise


def _buscar_cliente_pulsedesk_por_telefone(telefone: str) -> dict | None:
    tel = (telefone or "").strip()
    if not tel:
        return None
    for campo in ("telefone", "celular"):
        resposta = supabase.table("clientes").select("*").eq(campo, tel).limit(1).execute()
        if resposta.data:
            return resposta.data[0]
    return None


def _pedido_whatsapp_ja_no_pulsedesk(telefone: str) -> bool:
    cliente = _buscar_cliente_pulsedesk_por_telefone(telefone)
    if not cliente or cliente.get("mercos_id") is None:
        return False
    resposta = (
        supabase.table("pedidos")
        .select("mercos_id,numero")
        .eq("cliente_mercos_id", int(cliente["mercos_id"]))
        .execute()
    )
    for row in resposta.data or []:
        numero = str(row.get("numero") or "")
        mercos_id = row.get("mercos_id")
        if numero.startswith("WA-") or (mercos_id is not None and int(mercos_id) < 0):
            return True
    return False


def diagnosticar_pulsedesk_pedidos(telefone: str) -> dict:
    tel = (telefone or "").strip()
    cliente = _buscar_cliente_pulsedesk_por_telefone(tel)
    pedidos = []
    if cliente and cliente.get("mercos_id") is not None:
        resposta = (
            supabase.table("pedidos")
            .select("*")
            .eq("cliente_mercos_id", int(cliente["mercos_id"]))
            .execute()
        )
        pedidos = resposta.data or []
    return {
        "telefone": tel,
        "cliente_pulsedesk": cliente,
        "pedidos": pedidos,
        "whatsapp_registrado": _pedido_whatsapp_ja_no_pulsedesk(tel),
    }


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
        }
        if endereco:
            campos["endereco"] = endereco[:500]
        _update_seguro("clientes", campos, filtro="mercos_id", valor=mercos_id)
        return mercos_id

    mercos_id = int(pulsedesk_id) if pulsedesk_id else _id_sintetico(91, telefone)
    rotulo = nome or f"WhatsApp {telefone[-4:]}"
    dados = {
        "mercos_id": mercos_id,
        "nome": rotulo,
        "razao_social": rotulo,
        "telefone": telefone,
        "celular": telefone,
    }
    if endereco:
        dados["endereco"] = endereco[:500]

    _upsert_seguro("clientes", dados, conflito="mercos_id", rotulo="upsert_cliente_pulsedesk")
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
        "produto_nome": (produto_nome or "Produto WhatsApp")[:255],
        "data_pedido": agora,
        "ultima_alteracao": agora,
        "created_at": agora,
    }

    _upsert_seguro("pedidos", dados, conflito="mercos_id", rotulo="criar_pedido_pulsedesk")
    return {"pedido_id": pedido_id, "numero": numero, "cliente_id": cliente_mercos_id}


def registrar_venda_pulsedesk(
    historico_texto: str,
    cliente_supabase: dict,
    telefone: str,
    pushname: str = "",
    mensagem_atual: str = "",
    ultima_resposta_ia: str = "",
    frete_estimado: float = 0,
    nova_venda: bool = False,
) -> dict | None:
    """Grava cliente + pedido no Supabase para o PulseDesk exibir sem sync Mercos."""
    if not pulsedesk_pedidos_habilitado():
        print("PULSEDESK: registro de pedidos desabilitado")
        return None

    historico_efetivo = (
        historico_desde_ultimo_fechamento(historico_texto)
        if nova_venda
        else historico_texto
    )

    if pedido_ja_encerrado(ultima_resposta_ia, historico_texto) and not nova_venda:
        if _pedido_whatsapp_ja_no_pulsedesk(telefone):
            print("PULSEDESK: pedido já existe no PulseDesk, ignorando duplicata")
            return None
        print("PULSEDESK: conversa fechada mas pedido ausente — registrando retroativo")
        historico_efetivo = historico_texto

    nome = extrair_nome_do_historico(historico_efetivo, pushname)
    endereco = extrair_endereco(historico_efetivo) or extrair_endereco(historico_texto)
    extrair_pagamento(historico_efetivo, mensagem_atual, ultima_resposta_ia)
    produto = _buscar_produto_do_historico(historico_efetivo) or {}
    produto_nome = produto.get("nome") or "Produto WhatsApp"

    preco = _extrair_preco_historico(historico_efetivo)
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
        import traceback

        print("PULSEDESK PEDIDO FALHOU:", exc)
        traceback.print_exc()
        return {"erro": str(exc)}


def registrar_venda_retroativa_por_telefone(telefone: str) -> dict:
    """Reconstrói pedido a partir do histórico do agent (backfill manual)."""
    from services.supabase_service import buscar_cliente, buscar_historico

    tel = (telefone or "").strip().replace("+", "")
    if not tel:
        return {"erro": "telefone_obrigatorio"}

    if _pedido_whatsapp_ja_no_pulsedesk(tel):
        return {
            "status": "ok",
            "mensagem": "Pedido WhatsApp já registrado no PulseDesk",
            **diagnosticar_pulsedesk_pedidos(tel),
        }

    cliente = buscar_cliente(tel)
    if not cliente:
        return {"erro": "cliente_agent_nao_encontrado", "telefone": tel}

    historico = buscar_historico(cliente["id"])
    historico_texto = ""
    ultima_resposta_ia = ""
    for msg in historico:
        if msg["tipo"] == "cliente":
            historico_texto += f"Cliente: {msg['mensagem']}\n"
        else:
            historico_texto += f"IA: {msg['mensagem']}\n"
            ultima_resposta_ia = msg["mensagem"]

    if "pedido registrado" not in historico_texto.lower():
        return {"erro": "conversa_sem_fechamento", "telefone": tel}

    resultado = registrar_venda_pulsedesk(
        historico_texto=historico_texto,
        cliente_supabase=cliente,
        telefone=tel,
        pushname=cliente.get("nome") or "",
        ultima_resposta_ia=ultima_resposta_ia,
    )
    if resultado and resultado.get("erro"):
        return {"status": "erro", **resultado}

    return {
        "status": "ok",
        "resultado": resultado,
        **diagnosticar_pulsedesk_pedidos(tel),
    }
