-- Coluna contexto_venda na tabela de clientes do agente.
-- Etapa 2: tabela canônica = clientes (CLIENTES_TABLE=clientes).
-- Não use agent_clientes a menos que essa seja a tabela real no seu projeto.

ALTER TABLE public.clientes
  ADD COLUMN IF NOT EXISTS contexto_venda jsonb DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.clientes.contexto_venda IS
  'Memória estruturada da sessão de venda (JSON). Etapa 2.';

-- Opcional: idempotência persistente de mensagens do webhook (Z-API messageId)
-- Só rode se a tabela conversas existir e você quiser dedup entre reinícios.
-- ALTER TABLE public.conversas
--   ADD COLUMN IF NOT EXISTS message_id text;
-- CREATE UNIQUE INDEX IF NOT EXISTS conversas_message_id_uidx
--   ON public.conversas (message_id)
--   WHERE message_id IS NOT NULL;
