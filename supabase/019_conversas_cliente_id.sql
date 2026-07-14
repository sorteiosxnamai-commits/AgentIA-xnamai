-- ============================================================
-- 019_conversas_cliente_id.sql
-- Mesma migration de backend-xnamai/supabase/015_conversas_cliente_id.sql
-- (banco Supabase compartilhado Xnamai / PulseDesk)
--
-- Relacionamento seguro conversas → clientes via UUID
-- NÃO aplicar automaticamente — revisar e rodar no SQL Editor.
-- ============================================================

-- ---------- UP ----------

ALTER TABLE public.conversas
  ADD COLUMN IF NOT EXISTS cliente_id uuid;

COMMENT ON COLUMN public.conversas.cliente_id IS
  'FK opcional para public.clientes.id. Compatível com cliente_mercos_id (legado Mercos).';

UPDATE public.conversas AS c
SET cliente_id = cl.id
FROM public.clientes AS cl
WHERE c.cliente_id IS NULL
  AND c.cliente_mercos_id IS NOT NULL
  AND btrim(c.cliente_mercos_id) <> ''
  AND c.cliente_mercos_id ~ '^[0-9]+$'
  AND cl.mercos_id IS NOT NULL
  AND cl.mercos_id = (btrim(c.cliente_mercos_id))::bigint;

CREATE INDEX IF NOT EXISTS idx_conversas_cliente_id
  ON public.conversas (cliente_id)
  WHERE cliente_id IS NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'conversas_cliente_id_fkey'
      AND conrelid = 'public.conversas'::regclass
  ) THEN
    ALTER TABLE public.conversas
      ADD CONSTRAINT conversas_cliente_id_fkey
      FOREIGN KEY (cliente_id)
      REFERENCES public.clientes (id)
      ON DELETE SET NULL;
  END IF;
END $$;

-- ---------- DOWN (comentável) ----------
-- ALTER TABLE public.conversas DROP CONSTRAINT IF EXISTS conversas_cliente_id_fkey;
-- DROP INDEX IF EXISTS public.idx_conversas_cliente_id;
-- ALTER TABLE public.conversas DROP COLUMN IF EXISTS cliente_id;
