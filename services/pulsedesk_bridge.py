"""
Espelha atividade do agente de vendas no schema PulseDesk (conversas + mensagens).
O painel Atendimento passa a mostrar o que o agente faz no WhatsApp.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from database.supabase import supabase

CANAL_AGENT_ID = os.getenv("PULSEDESK_AGENT_CANAL_ID", "agent-vendas-zapi")
BRIDGE_ENABLED = os.getenv("PULSEDESK_BRIDGE_ENABLED", "true").lower() == "true"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _buscar_conversa_pulsedesk(telefone: str) -> dict | None:
    resposta = (
        supabase.table("conversas")
        .select("*")
        .eq("canal_id", CANAL_AGENT_ID)
        .eq("external_thread_id", telefone)
        .limit(1)
        .execute()
    )
    rows = resposta.data or []
    return rows[0] if rows else None


def _criar_conversa_pulsedesk(telefone: str, nome: str, ultima_mensagem: str) -> dict:
    protocolo = f"AG-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{telefone[-4:]}"
    dados = {
        "canal_id": CANAL_AGENT_ID,
        "external_thread_id": telefone,
        "contact_phone": telefone,
        "customer_name": nome or f"WhatsApp {telefone[-4:]}",
        "channel": "whatsapp",
        "department": "Vendas IA",
        "status": "active",
        "unread_count": 0,
        "last_message": ultima_mensagem[:500],
        "last_message_at": _agora_iso(),
        "protocol": protocolo,
    }
    resposta = supabase.table("conversas").insert(dados).execute()
    rows = resposta.data or []
    return rows[0] if rows else dados


def _atualizar_conversa(conversa_id: str, ultima_mensagem: str, incrementar_nao_lidas: bool) -> None:
    conversa = (
        supabase.table("conversas")
        .select("unread_count")
        .eq("id", conversa_id)
        .limit(1)
        .execute()
    )
    unread = 0
    if conversa.data:
        unread = int(conversa.data[0].get("unread_count") or 0)
    if incrementar_nao_lidas:
        unread += 1

    supabase.table("conversas").update({
        "last_message": ultima_mensagem[:500],
        "last_message_at": _agora_iso(),
        "unread_count": unread,
        "status": "active",
        "updated_at": _agora_iso(),
    }).eq("id", conversa_id).execute()


def _inserir_mensagem_pulsedesk(
    conversa_id: str,
    conteudo: str,
    sender: str,
    *,
    direction: str,
) -> None:
    external_id = f"agent-{uuid.uuid4()}"
    supabase.table("mensagens").insert({
        "conversa_id": conversa_id,
        "content": conteudo,
        "sender": sender,
        "status": "delivered",
        "direction": direction,
        "external_id": external_id,
        "provider_status": "sent",
    }).execute()


def espelhar_mensagem_cliente(telefone: str, nome: str, mensagem: str) -> None:
    if not BRIDGE_ENABLED or not telefone or not mensagem:
        return
    try:
        conversa = _buscar_conversa_pulsedesk(telefone)
        if not conversa:
            conversa = _criar_conversa_pulsedesk(telefone, nome, mensagem)
        else:
            _atualizar_conversa(str(conversa["id"]), mensagem, incrementar_nao_lidas=True)

        _inserir_mensagem_pulsedesk(
            str(conversa["id"]),
            mensagem,
            "customer",
            direction="inbound",
        )
    except Exception as exc:
        print("PULSEDESK BRIDGE (cliente) falhou:", exc)


def espelhar_mensagem_agente(telefone: str, nome: str, mensagem: str) -> None:
    if not BRIDGE_ENABLED or not telefone or not mensagem:
        return
    try:
        conversa = _buscar_conversa_pulsedesk(telefone)
        if not conversa:
            conversa = _criar_conversa_pulsedesk(telefone, nome, mensagem)
        else:
            _atualizar_conversa(str(conversa["id"]), mensagem, incrementar_nao_lidas=False)

        _inserir_mensagem_pulsedesk(
            str(conversa["id"]),
            mensagem,
            "ai",
            direction="outbound",
        )
    except Exception as exc:
        print("PULSEDESK BRIDGE (ia) falhou:", exc)
