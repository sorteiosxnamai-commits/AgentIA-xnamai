"""Conhecimento institucional da xNamai (estático — sem preço/estoque)."""

from __future__ import annotations

import os

NOME_EMPRESA = "xNamai"
NOME_AGENTE = "Agente de Vendas da xNamai"
SITE_URL = (os.getenv("XNAMAI_SITE_URL") or os.getenv("SITE_URL") or "").strip()
VENDEDOR_WHATSAPP = (os.getenv("VENDEDOR_WHATSAPP") or "").strip()

APRESENTACAO = (
    "Olá! Sou o assistente de vendas da xNamai. "
    "Posso ajudar você a encontrar um produto, consultar preços, estoque ou acompanhar uma compra."
)

HUMAN_SUPPORT_MESSAGE = (
    "Vou encaminhar você para um atendente humano da xNamai. "
    + (
        f"Se preferir, fale direto pelo WhatsApp {VENDEDOR_WHATSAPP}."
        if VENDEDOR_WHATSAPP
        else "Em breve alguém da equipe continua o atendimento por aqui."
    )
)


def build_sales_knowledge_text() -> str:
    site = SITE_URL or "(site não configurado)"
    return f"""
Empresa: {NOME_EMPRESA}
Agente: {NOME_AGENTE}
Site: {site}

A xNamai atende clientes pelo WhatsApp com foco em produtos, preços, estoque,
pedidos e suporte comercial. Dados dinâmicos (preço, estoque, catálogo) vêm
sempre da Mercos via ferramentas. Dados de cliente/histórico vêm do Supabase.

Não invente promoções, saldo, cupom, números de sorteio ou pedidos.
Não se apresente como NewStore, New Store Sorteios ou agente de sorteios.
""".strip()
