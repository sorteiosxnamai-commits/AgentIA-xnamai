-- Torna mercos_id nullable em clientes.
--
-- Causa em produção (23502):
--   null value in column "mercos_id" of relation "clientes"
--   violates not-null constraint
--
-- Clientes criados pelo WhatsApp ainda não existem na Mercos;
-- mercos_id só deve ser preenchido depois da sincronização real.
-- NÃO use 0, string fake ou id sintético no insert do agente.
--
-- Execute no SQL Editor do Supabase (projeto do agente / PulseDesk).

ALTER TABLE public.clientes
  ALTER COLUMN mercos_id DROP NOT NULL;

COMMENT ON COLUMN public.clientes.mercos_id IS
  'ID do cliente na Mercos (opcional). Null até sincronizar; nunca inventar valor fake.';
