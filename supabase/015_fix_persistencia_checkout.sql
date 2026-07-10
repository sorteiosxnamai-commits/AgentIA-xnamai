-- Fix persistência checkout (Etapa 5+)
-- Causa de persistencia_ok=false em produção: colunas ausentes (PGRST204).
--
-- Execute no SQL Editor do Supabase (projeto do agente):
--   1) clientes.contexto_venda
--   2) conversas.message_id
--
-- Sem estas colunas:
--   - checkout não persiste entre requests (só cache em memória)
--   - message_id de idempotência fica indisponível

ALTER TABLE public.clientes
  ADD COLUMN IF NOT EXISTS contexto_venda jsonb DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.clientes.contexto_venda IS
  'Memória estruturada da sessão de venda + checkout (JSON).';

ALTER TABLE public.conversas
  ADD COLUMN IF NOT EXISTS message_id text;

CREATE UNIQUE INDEX IF NOT EXISTS conversas_message_id_uidx
  ON public.conversas (message_id)
  WHERE message_id IS NOT NULL;

COMMENT ON COLUMN public.conversas.message_id IS
  'ID da mensagem Z-API/chat para deduplicação.';
