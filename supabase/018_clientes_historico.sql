-- Coluna opcional clientes.historico (JSON das mensagens do agente).
--
-- Em schemas PulseDesk sem esta coluna:
--   - contexto_venda continua sendo a memória essencial do checkout
--   - histórico de turnos fica opcional (não derruba persistencia_ok)
--
-- Execute no SQL Editor se quiser gravar o log de mensagens em clientes.

ALTER TABLE public.clientes
  ADD COLUMN IF NOT EXISTS historico jsonb DEFAULT '[]'::jsonb;

COMMENT ON COLUMN public.clientes.historico IS
  'Log JSON de mensagens do agente (user/assistant). Opcional se contexto_venda existir.';
