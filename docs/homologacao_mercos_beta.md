# Homologação beta Mercos — plano atualizado (ata + rotas locais)

Documento alinhado às rotas **implementadas no backend** em `/mercos/*`  
(`routes/mercos_homolog.py` → `services/mercos_homolog_service.py` → API sandbox).

**Não anexar tokens / `.env`.**  
**Agente IA:** manter `CHECKOUT_CREATE_ORDER=false` (pedido automático desligado).

Company Token: variável **`MERCOS_COMPANY_TOKEN`** (header `CompanyToken`).  
Application Token: **`MERCOS_APPLICATION_TOKEN`**.  
Base: **`MERCOS_BASE_URL=https://sandbox.mercos.com/api`**.

Proteção das rotas locais: `SYNC_TOKEN` (query `token=`) ou `DIAGNOSTICOS_ABERTOS=true`.

---

## 1. O que já existia (antes desta entrega)

| Método | Endpoint Mercos | Uso no projeto |
|--------|-----------------|----------------|
| GET | `/v1/produtos` | Catálogo / sync |
| POST | `/v1/clientes` | Checkout (gated) |
| POST | `/v2/pedidos` | Checkout (gated) |

## 2. Rotas locais criadas agora (`/mercos/...`)

| Ata (obrigatório) | Método | Rota local | Endpoint Mercos | Status sandbox Xnamai |
|-------------------|--------|------------|-----------------|------------------------|
| Categorias de Produtos | GET | `GET /mercos/categorias` | `/v1/categorias` | **OK (200)** |
| Clientes | GET | `GET /mercos/clientes` | `/v1/clientes` | **OK (200)** |
| Clientes | POST | `POST /mercos/clientes` | `/v1/clientes` | **OK** (já existia service) |
| Clientes | PUT | `PUT /mercos/clientes/{id}` | `/v1/clientes/{id}` | **Rota pronta** |
| Condições de Pagamento | GET | `GET /mercos/condicoes-pagamento` | `/v1/condicoes_pagamento` | **OK (200)** |
| Produtos | GET | `GET /mercos/produtos` | `/v1/produtos` | **OK (200)** |
| Segmentos de Clientes | GET | `GET /mercos/segmentos` | `/v1/segmentos` | **OK (200)** |
| Tabelas de Preço | GET | `GET /mercos/tabelas-preco` | `/v1/tabelas_preco` | **OK (200)** |
| Tabelas de Preço por Produto | GET | `GET /mercos/tabelas-preco/{id}/produtos` | `/v1/tabelas_preco/{id}/produtos` | **Rota pronta — confirmar path se 404** |
| Tabelas de Preço por Produto | GET | `GET /mercos/tabelas-preco-produtos` | `MERCOS_PATH_TABELAS_PRECO_PRODUTO` | Path global **não encontrado** no probe |
| Tipo de Pedido | GET | `GET /mercos/tipos-pedido` | `MERCOS_PATH_TIPOS_PEDIDO` (default `/v1/tipos_pedido`) | **404 no sandbox** — confirmar com Mercos |
| Usuários | GET | `GET /mercos/usuarios` | `/v1/usuarios` | **OK (200)** |
| Pedidos | POST | `POST /mercos/pedidos` | `/v2/pedidos` | **Rota pronta** |
| Pedidos | PUT | `PUT /mercos/pedidos/{id}` | `/v1/pedidos/{id}` | **Rota pronta** |
| Títulos | POST | `POST /mercos/titulos` | `/v1/titulos` | **Rota pronta** (GET list OK) |
| Títulos | PUT | `PUT /mercos/titulos/{id}` | `/v1/titulos/{id}` | **Rota pronta** |
| Inventário | GET | `GET /mercos/homologacao` | — | Flags + mapa |

DELETE: **não implementado** (não requerido na ata).

---

## 3. Ainda falta / a confirmar com a Mercos

1. **Path oficial de “Tabelas de Preço por Produto”** (listagem global) — vários paths testados retornaram 404.  
2. **Path oficial de “Tipo de Pedido”** — `/v1/tipos_pedido` retornou 404 no sandbox.  
   → Após a Mercos informar o path, setar no Render:  
   - `MERCOS_PATH_TABELAS_PRECO_PRODUTO`  
   - `MERCOS_PATH_TIPOS_PEDIDO`

---

## 4. Ordem recomendada de homologação

1. `GET /mercos/homologacao` + `GET /status` (sandbox + `checkout_create_order: false`)  
2. GETs: categorias → produtos → clientes → condições → segmentos → tabelas-preço → usuários  
3. POST cliente (sandbox) → PUT cliente  
4. POST pedido (sandbox, payload mínimo) → PUT pedido  
5. POST título → PUT título  
6. Tabelas preço por produto / tipo pedido (após confirmação de path)  

Espaçamento entre chamadas por causa de **429**.

---

## 5. Comandos PowerShell / curl

```powershell
$BASE = "https://agent-ia-xnamai.onrender.com"
$T = $env:SYNC_TOKEN   # se DIAGNOSTICOS_ABERTOS=false

# Inventário
Invoke-RestMethod "$BASE/mercos/homologacao?token=$T" | ConvertTo-Json -Depth 6

# GETs (um por vez; espere se 429)
Invoke-RestMethod "$BASE/mercos/categorias?token=$T&max_paginas=2" | ConvertTo-Json -Depth 4
Invoke-RestMethod "$BASE/mercos/produtos?token=$T&max_paginas=2" | ConvertTo-Json -Depth 4
Invoke-RestMethod "$BASE/mercos/clientes?token=$T&max_paginas=2" | ConvertTo-Json -Depth 4
Invoke-RestMethod "$BASE/mercos/condicoes-pagamento?token=$T" | ConvertTo-Json -Depth 4
Invoke-RestMethod "$BASE/mercos/segmentos?token=$T" | ConvertTo-Json -Depth 4
Invoke-RestMethod "$BASE/mercos/tabelas-preco?token=$T" | ConvertTo-Json -Depth 4
Invoke-RestMethod "$BASE/mercos/usuarios?token=$T" | ConvertTo-Json -Depth 4

# POST cliente (sandbox) — ajuste o JSON ao layout Mercos
$body = @{ razao_social = "Homolog Teste"; nome_fantasia = "Homolog"; tipo = "F" } | ConvertTo-Json
Invoke-RestMethod -Method Post "$BASE/mercos/clientes?token=$T" -ContentType "application/json" -Body $body
```

```bash
curl -s "$BASE/mercos/homologacao?token=$T"
curl -s "$BASE/mercos/produtos?token=$T&max_paginas=1"
```

Script de apoio: `scripts/homologacao_mercos/smoke_gets.ps1`

---

## 6. Prints / evidências para a Mercos

| # | Evidência | Como |
|---|-----------|------|
| 1 | Sandbox ativo | `/status` → `mercos_sandbox: true` |
| 2 | Pedido automático off | `/status` → `checkout_create_order: false` |
| 3 | Cada GET 200 | Resposta `/mercos/...` com `total` / amostra (sem token) |
| 4 | POST/PUT | ID retornado + painel sandbox |
| 5 | 429 tratado | (opcional) log/mensagem “throttling” sem token |
| 6 | Paginação | `paginas_lidas` > 1 quando houver volume |

---

## 7. Cuidados

- **Sandbox only** para POST/PUT de teste.  
- **Throttling:** retry limitado (3x) com sleep; não martelar a API.  
- **Paginação:** `pagina` + `max_paginas` (teto); para se lote vazio ou curto.  
- **Não** versionar `.env` nem colar Company Token.  
- **Não** ligar `CHECKOUT_CREATE_ORDER` no agente por causa da homologação.

---

## 8. Variáveis Render

| Variável | Obrigatória | Notas |
|----------|-------------|-------|
| `MERCOS_BASE_URL` | sim | `https://sandbox.mercos.com/api` |
| `MERCOS_COMPANY_TOKEN` | sim | Company Token |
| `MERCOS_APPLICATION_TOKEN` | sim | Application Token |
| `SYNC_TOKEN` | recomendado | Protege `/mercos/*` |
| `CHECKOUT_CREATE_ORDER` | manter `false` | Agente |
| `MERCOS_PATH_TIPOS_PEDIDO` | opcional | Se Mercos informar path |
| `MERCOS_PATH_TABELAS_PRECO_PRODUTO` | opcional | Se Mercos informar path |

---

*Atualizado com implementação das rotas locais de homologação.*
