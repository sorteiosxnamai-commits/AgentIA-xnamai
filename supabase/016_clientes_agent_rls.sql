-- Agente WhatsApp: escrita em public.clientes
-- Execute no SQL Editor do Supabase se busca/criação cair em ephemeral (RLS).
--
-- No Render, prefira SUPABASE_SERVICE_ROLE_KEY (bypassa RLS).
-- Se usar apenas anon/publishable key, estas policies são necessárias.

-- Coluna opcional de memória (fallback usa clientes.historico se ausente)
ALTER TABLE public.clientes
  ADD COLUMN IF NOT EXISTS contexto_venda jsonb DEFAULT '{}'::jsonb;

ALTER TABLE public.clientes ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'clientes'
      AND policyname = 'agent_write_clientes'
  ) THEN
    CREATE POLICY agent_write_clientes ON public.clientes
      FOR ALL
      USING (true)
      WITH CHECK (true);
  END IF;
EXCEPTION
  WHEN undefined_table THEN
    RAISE NOTICE 'Tabela public.clientes não existe';
END $$;

COMMENT ON POLICY agent_write_clientes ON public.clientes IS
  'Permite select/insert/update do agente. Preferível usar service_role key no backend.';
