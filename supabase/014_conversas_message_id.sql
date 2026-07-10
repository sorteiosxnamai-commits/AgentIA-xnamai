-- Idempotência persistente de mensagens do webhook (Z-API messageId).
-- Execute no SQL Editor do Supabase antes do deploy que grava message_id.

ALTER TABLE public.conversas
  ADD COLUMN IF NOT EXISTS message_id text;

CREATE UNIQUE INDEX IF NOT EXISTS conversas_message_id_uidx
  ON public.conversas (message_id)
  WHERE message_id IS NOT NULL;

COMMENT ON COLUMN public.conversas.message_id IS
  'ID da mensagem Z-API/UltraMsg para deduplicação entre reinícios.';
