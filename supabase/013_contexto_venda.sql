-- Memória estruturada da sessão de venda (agente WhatsApp)
-- Execute no SQL Editor do Supabase se a coluna ainda não existir.

ALTER TABLE public.agent_clientes
  ADD COLUMN IF NOT EXISTS contexto_venda jsonb DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.agent_clientes.contexto_venda IS
  'Sessão estruturada: produto_ativo, preco_cotado, nf, envio, tom, resumo_curto';
