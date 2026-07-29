-- Diagnóstico produtos (somente SELECT) — schema real confirmado:
--   mercos_id BIGINT NOT NULL + UNIQUE (produtos_mercos_id_key)
--   codigo TEXT NULL
--   sem mercos_produto_id / ean / empresa_id
--
-- NÃO altera schema. NÃO cria índices. Rode no SQL Editor antes da sync real.

-- 1) Códigos/SKUs duplicados (candidatos a ambiguidade na sync)
SELECT codigo, COUNT(*) AS qtd
FROM public.produtos
WHERE codigo IS NOT NULL AND btrim(codigo) <> ''
GROUP BY codigo
HAVING COUNT(*) > 1
ORDER BY qtd DESC;

-- 2) mercos_id duplicados (não deve retornar linhas — UNIQUE produtos_mercos_id_key)
SELECT mercos_id, COUNT(*) AS qtd
FROM public.produtos
GROUP BY mercos_id
HAVING COUNT(*) > 1;

-- 3) Amostra de produtos (revisão sandbox ↔ produção via codigo)
SELECT id, mercos_id, codigo, nome, ativo
FROM public.produtos
ORDER BY codigo NULLS LAST, nome
LIMIT 200;
