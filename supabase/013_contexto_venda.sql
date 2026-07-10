-- Coluna contexto_venda na tabela de clientes do agente.
-- Etapa 2: tabela canônica = clientes (CLIENTES_TABLE=clientes).
-- Não use agent_clientes a menos que essa seja a tabela real no seu projeto.

ALTER TABLE public.clientes
  ADD COLUMN IF NOT EXISTS contexto_venda jsonb DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.clientes.contexto_venda IS
  'Memória estruturada da sessão de venda (JSON). Etapa 2.';

-- message_id: ver supabase/014_conversas_message_id.sql
