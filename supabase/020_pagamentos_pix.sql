-- Pagamentos Pix (Mercado Pago) — xNamai
-- Execute manualmente no SQL Editor do Supabase após revisão.
-- NÃO roda automaticamente no deploy.
--
-- Acesso: somente service_role (backend). anon/authenticated/PUBLIC sem permissão.

CREATE TABLE IF NOT EXISTS public.pagamentos_pix (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  pedido_id text NOT NULL,
  cliente_id uuid NULL,
  provider text NOT NULL DEFAULT 'mercadopago',
  provider_payment_id text NULL,
  external_reference text NOT NULL,
  idempotency_key text NOT NULL,
  valor numeric(12, 2) NOT NULL CHECK (valor > 0),
  status text NOT NULL DEFAULT 'aguardando_pagamento'
    CHECK (status IN (
      'aguardando_pagamento',
      'pago',
      'recusado_ou_cancelado',
      'reembolsado_ou_contestado'
    )),
  provider_status text NULL,
  pix_copia_cola text NULL,
  qr_code_base64 text NULL,
  ticket_url text NULL,
  expira_em timestamptz NULL,
  produto_nome text NULL,
  quantidade integer NOT NULL DEFAULT 1 CHECK (quantidade > 0),
  telefone_mascarado text NULL,
  email_mascarado text NULL,
  cpf_mascarado text NULL,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  pago_em timestamptz NULL
);

-- FK opcional → public.clientes(id) uuid (padrão 019_conversas_cliente_id.sql)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'pagamentos_pix_cliente_id_fkey'
      AND conrelid = 'public.pagamentos_pix'::regclass
  ) THEN
    ALTER TABLE public.pagamentos_pix
      ADD CONSTRAINT pagamentos_pix_cliente_id_fkey
      FOREIGN KEY (cliente_id)
      REFERENCES public.clientes (id)
      ON DELETE SET NULL;
  END IF;
END $$;

ALTER TABLE public.pagamentos_pix ENABLE ROW LEVEL SECURITY;

-- Sem policy para anon/authenticated: frontend nunca acessa esta tabela.
REVOKE ALL ON TABLE public.pagamentos_pix FROM PUBLIC;
REVOKE ALL ON TABLE public.pagamentos_pix FROM anon;
REVOKE ALL ON TABLE public.pagamentos_pix FROM authenticated;

REVOKE ALL ON TABLE public.pagamentos_pix FROM service_role;
GRANT SELECT, INSERT, UPDATE
ON TABLE public.pagamentos_pix
TO service_role;

CREATE UNIQUE INDEX IF NOT EXISTS pagamentos_pix_provider_payment_id_uidx
  ON public.pagamentos_pix (provider_payment_id)
  WHERE provider_payment_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS pagamentos_pix_external_reference_uidx
  ON public.pagamentos_pix (external_reference);

CREATE UNIQUE INDEX IF NOT EXISTS pagamentos_pix_idempotency_key_uidx
  ON public.pagamentos_pix (idempotency_key);

CREATE INDEX IF NOT EXISTS pagamentos_pix_status_idx
  ON public.pagamentos_pix (status);

-- Garante atualizado_em em todo UPDATE (defesa além do backend Python).
CREATE OR REPLACE FUNCTION public.pagamentos_pix_set_atualizado_em()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.atualizado_em = now();
  RETURN NEW;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    WHERE t.tgname = 'pagamentos_pix_atualizado_em_trg'
      AND c.relname = 'pagamentos_pix'
      AND c.relnamespace = 'public'::regnamespace
  ) THEN
    CREATE TRIGGER pagamentos_pix_atualizado_em_trg
      BEFORE UPDATE ON public.pagamentos_pix
      FOR EACH ROW
      EXECUTE FUNCTION public.pagamentos_pix_set_atualizado_em();
  END IF;
END $$;

COMMENT ON TABLE public.pagamentos_pix IS
  'Cobranças Pix Mercado Pago — status pago só após confirmação oficial da API. Acesso exclusivo service_role.';

COMMENT ON COLUMN public.pagamentos_pix.pix_copia_cola IS
  'EMV Pix; dado sensível — tabela inacessível a anon/authenticated.';

COMMENT ON COLUMN public.pagamentos_pix.qr_code_base64 IS
  'Cache opcional do QR; derivável do pix_copia_cola. Protegido por RLS + REVOKE.';

COMMENT ON COLUMN public.pagamentos_pix.cpf_mascarado IS
  'Apenas máscara (***XXXX); nunca CPF completo.';

COMMENT ON COLUMN public.pagamentos_pix.email_mascarado IS
  'Apenas máscara parcial; nunca e-mail completo.';

COMMENT ON COLUMN public.pagamentos_pix.telefone_mascarado IS
  'Apenas últimos dígitos; nunca telefone completo.';
