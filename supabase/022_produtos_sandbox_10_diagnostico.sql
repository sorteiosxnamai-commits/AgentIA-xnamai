-- =============================================================================
-- Diagnóstico: 10 produtos sandbox em public.produtos
-- =============================================================================
-- SOMENTE SELECT. Não altera dados nem schema.
-- Não contém INSERT / UPDATE / DELETE / TRUNCATE / DROP / ALTER.
--
-- Contexto (dry-run produção): indice_local_total=10; nenhum match Mercos produção.
-- Execute no SQL Editor do Supabase (service_role / role com leitura).
-- Depois, use id + mercos_id desta saída no arquivo 023_produtos_sandbox_10_limpeza.sql.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 0) Contagem global (deve ser 10 antes da sync real)
-- ---------------------------------------------------------------------------
SELECT COUNT(*) AS total_produtos
FROM public.produtos;

-- ---------------------------------------------------------------------------
-- 1) Listar os produtos atuais (id, mercos_id, codigo, nome, created_at)
--     created_at: usa created_at ou criado_em se existirem na linha (jsonb).
-- ---------------------------------------------------------------------------
SELECT
  p.id,
  p.mercos_id,
  p.codigo,
  p.nome,
  COALESCE(
    NULLIF(to_jsonb(p)->>'created_at', ''),
    NULLIF(to_jsonb(p)->>'criado_em', '')
  ) AS created_at
FROM public.produtos AS p
ORDER BY p.mercos_id NULLS LAST, p.codigo NULLS LAST, p.id;

-- ---------------------------------------------------------------------------
-- 2) Foreign keys formais que referenciam public.produtos
--     (migrations do repo não declaram nenhuma; confirma no schema real)
-- ---------------------------------------------------------------------------
SELECT
  n_src.nspname AS schema_origem,
  c_src.relname AS tabela_origem,
  a_src.attname AS coluna_origem,
  n_tgt.nspname AS schema_destino,
  c_tgt.relname AS tabela_destino,
  a_tgt.attname AS coluna_destino,
  con.conname AS constraint_name,
  pg_get_constraintdef(con.oid) AS definicao
FROM pg_constraint AS con
JOIN pg_class AS c_src ON c_src.oid = con.conrelid
JOIN pg_namespace AS n_src ON n_src.oid = c_src.relnamespace
JOIN pg_class AS c_tgt ON c_tgt.oid = con.confrelid
JOIN pg_namespace AS n_tgt ON n_tgt.oid = c_tgt.relnamespace
JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS ck(attnum, ord) ON TRUE
JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS fk(attnum, ord)
  ON fk.ord = ck.ord
JOIN pg_attribute AS a_src
  ON a_src.attrelid = con.conrelid AND a_src.attnum = ck.attnum
JOIN pg_attribute AS a_tgt
  ON a_tgt.attrelid = con.confrelid AND a_tgt.attnum = fk.attnum
WHERE con.contype = 'f'
  AND n_tgt.nspname = 'public'
  AND c_tgt.relname = 'produtos'
ORDER BY schema_origem, tabela_origem, coluna_origem;

-- ---------------------------------------------------------------------------
-- 3) Colunas públicas cujo nome sugere referência a produto
-- ---------------------------------------------------------------------------
SELECT
  c.table_name,
  c.column_name,
  c.data_type,
  c.udt_name
FROM information_schema.columns AS c
WHERE c.table_schema = 'public'
  AND (
    c.column_name ILIKE '%produto%'
    OR c.column_name = 'produto_id'
  )
ORDER BY c.table_name, c.column_name;

-- ---------------------------------------------------------------------------
-- 4) Referências soft em clientes.contexto_venda (JSON) aos id / mercos_id
-- ---------------------------------------------------------------------------
WITH alvos AS (
  SELECT
    p.id::text AS id_txt,
    p.mercos_id::text AS mercos_id_txt,
    p.codigo,
    p.nome
  FROM public.produtos AS p
)
SELECT
  cl.id AS cliente_id,
  a.id_txt AS produto_id_ref,
  a.mercos_id_txt AS mercos_id_ref,
  a.codigo AS produto_codigo,
  a.nome AS produto_nome,
  cl.contexto_venda
FROM public.clientes AS cl
CROSS JOIN alvos AS a
WHERE cl.contexto_venda IS NOT NULL
  AND (
    cl.contexto_venda::text LIKE '%' || a.id_txt || '%'
    OR (
      a.mercos_id_txt IS NOT NULL
      AND a.mercos_id_txt <> ''
      AND cl.contexto_venda::text LIKE '%' || a.mercos_id_txt || '%'
    )
  )
ORDER BY cl.id, a.id_txt;

-- ---------------------------------------------------------------------------
-- 5) Referências soft em clientes.historico (JSON), sem exigir a coluna
--     (usa to_jsonb da linha; se a coluna não existir, retorna 0 linhas)
-- ---------------------------------------------------------------------------
WITH alvos AS (
  SELECT
    p.id::text AS id_txt,
    p.mercos_id::text AS mercos_id_txt
  FROM public.produtos AS p
),
clientes_hist AS (
  SELECT
    cl.id AS cliente_id,
    to_jsonb(cl) -> 'historico' AS historico_json
  FROM public.clientes AS cl
  WHERE to_jsonb(cl) ? 'historico'
    AND to_jsonb(cl) -> 'historico' IS NOT NULL
    AND jsonb_typeof(to_jsonb(cl) -> 'historico') <> 'null'
)
SELECT
  ch.cliente_id,
  a.id_txt AS produto_id_ref,
  a.mercos_id_txt AS mercos_id_ref
FROM clientes_hist AS ch
CROSS JOIN alvos AS a
WHERE ch.historico_json::text LIKE '%' || a.id_txt || '%'
   OR (
     a.mercos_id_txt IS NOT NULL
     AND a.mercos_id_txt <> ''
     AND ch.historico_json::text LIKE '%' || a.mercos_id_txt || '%'
   )
ORDER BY ch.cliente_id, a.id_txt;

-- ---------------------------------------------------------------------------
-- 6) Soft match por nome em pagamentos_pix.produto_nome (sem FK)
-- ---------------------------------------------------------------------------
SELECT
  px.id AS pagamento_pix_id,
  px.produto_nome,
  p.id AS produto_id,
  p.mercos_id,
  p.codigo,
  px.status,
  px.criado_em
FROM public.pagamentos_pix AS px
JOIN public.produtos AS p
  ON lower(btrim(px.produto_nome)) = lower(btrim(p.nome))
WHERE px.produto_nome IS NOT NULL
  AND btrim(px.produto_nome) <> ''
ORDER BY px.criado_em DESC NULLS LAST;

-- ---------------------------------------------------------------------------
-- 7) Quantidade de referências por origem (resumo)
--     Conta FKs (se houver) dinamicamente + soft refs acima.
-- ---------------------------------------------------------------------------

-- 7a) Soft: contexto_venda
WITH alvos AS (
  SELECT p.id::text AS id_txt, p.mercos_id::text AS mercos_id_txt
  FROM public.produtos AS p
)
SELECT
  'clientes.contexto_venda'::text AS origem,
  COUNT(*)::bigint AS qtd_refs
FROM public.clientes AS cl
CROSS JOIN alvos AS a
WHERE cl.contexto_venda IS NOT NULL
  AND (
    cl.contexto_venda::text LIKE '%' || a.id_txt || '%'
    OR (
      a.mercos_id_txt IS NOT NULL
      AND a.mercos_id_txt <> ''
      AND cl.contexto_venda::text LIKE '%' || a.mercos_id_txt || '%'
    )
  );

-- 7b) Soft: pagamentos_pix.produto_nome
SELECT
  'pagamentos_pix.produto_nome'::text AS origem,
  COUNT(*)::bigint AS qtd_refs
FROM public.pagamentos_pix AS px
JOIN public.produtos AS p
  ON lower(btrim(px.produto_nome)) = lower(btrim(p.nome))
WHERE px.produto_nome IS NOT NULL
  AND btrim(px.produto_nome) <> '';

-- 7c) FKs formais: lista de (tabela, coluna) — contagem por tabela exige
--     SQL dinâmico; aqui apenas inventário (use query 2). Se vazia = 0 FKs.
SELECT
  'fk_formais_para_public.produtos'::text AS origem,
  COUNT(*)::bigint AS qtd_constraints
FROM pg_constraint AS con
JOIN pg_class AS c_tgt ON c_tgt.oid = con.confrelid
JOIN pg_namespace AS n_tgt ON n_tgt.oid = c_tgt.relnamespace
WHERE con.contype = 'f'
  AND n_tgt.nspname = 'public'
  AND c_tgt.relname = 'produtos';

-- ---------------------------------------------------------------------------
-- 8) Pares id + mercos_id para colar na limpeza (023)
-- ---------------------------------------------------------------------------
SELECT
  p.id,
  p.mercos_id,
  format('(%L, %s)', p.id::text, COALESCE(p.mercos_id::text, 'NULL')) AS valor_para_insert
FROM public.produtos AS p
ORDER BY p.mercos_id NULLS LAST, p.id;
