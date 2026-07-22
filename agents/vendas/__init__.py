"""Agente de Vendas da xNamai.

Arquitetura modular (inspirada no NSAgent) adaptada para vendas comerciais:
WhatsApp + Mercos + Supabase. Sem identidade de sorteios.
"""

from .agent import processar_mensagem, processar_mensagem_sync

__all__ = ["processar_mensagem", "processar_mensagem_sync"]
