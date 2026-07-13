# Homologação beta Mercos — checklist do projeto AgentIA

Documento baseado **somente** no que o código em `agente-vendas-python` realmente implementa (`services/mercos_service.py`, `pedido_mercos_service.py`, `sync_mercos_service.py`, `routes/api.py`).

**Ambiente alvo:** sandbox  
**Não anexar tokens, `.env` ou Company Token em prints/tickets.**

---

## 1. Inventário de rotas Mercos (código real)

Todas as chamadas HTTP passam por `_executar_requisicao_mercos` em `services/mercos_service.py`.

| Entidade | GET list | GET by id | POST | PUT | DELETE | Status no projeto |
|----------|----------|-----------|------|-----|--------|-------------------|
| **Clientes** | — | — | `/v1/clientes` | — | — | **POST pronto** |
| **Produtos** | `/v1/produtos?pagina=N` | — | — | — | — | **GET list pronto** |
| **Pedidos** | — | — | `/v2/pedidos` | — | — | **POST pronto** (gated) |
| **Títulos** | — | — | — | — | — | Não implementado |
| **Tabelas de preço** | — | — | — | — | — | Não implementado (só lê `preco_tabela` no JSON do produto) |
| **Condições de pagamento** | — | — | — | — | — | Não implementado (envia texto livre no pedido, ex.: PIX) |
| **Transportadoras** | — | — | — | — | — | Não implementado |
| **Políticas comerciais** | — | — | — | — | — | Não implementado |
| **Categorias** | — | — | — | — | — | Não implementado (campo local do produto) |
| **Ajuste de estoque** | — | — | — | — | — | Não implementado (só lê `saldo_estoque` na listagem) |
| **Oportunidades / Funis** | — | — | — | — | — | Não implementado |

### Rotas prontas para homologar (3)

1. `GET /v1/produtos` — listagem paginada  
2. `POST /v1/clientes` — criação de cliente  
3. `POST /v2/pedidos` — criação de pedido  

### Rotas que ainda faltam (não homologar neste ciclo)

- Clientes: GET/PUT/DELETE  
- Produtos: GET by id / POST / PUT / DELETE  
- Pedidos: GET / PUT / DELETE  
- Títulos (qualquer método)  
- Tabelas de preço, condições de pagamento, transportadoras, políticas, categorias, ajuste de estoque, oportunidades/funis  

---

## 2. Configuração e gates

| Item | Valor / comportamento |
|------|------------------------|
| Base URL | `MERCOS_BASE_URL` — default `https://sandbox.mercos.com/api` |
| Sandbox? | `mercos_ambiente_sandbox()` → `true` se `"sandbox"` estiver na URL |
| Company Token | **`MERCOS_COMPANY_TOKEN`** (header `CompanyToken`) |
| Application Token | `MERCOS_APPLICATION_TOKEN` (header `ApplicationToken`) |
| Fallback app token | `MERCOS_APPLICATION_TOKEN_FALLBACK` (opcional) |
| Criar pedido no checkout do agente | **`CHECKOUT_CREATE_ORDER=false`** (padrão — **manter assim**) |
| Flag Mercos pedido | `MERCOS_CRIAR_PEDIDO` (também precisa estar coerente; agente não deve criar pedido automático) |

### Throttling (429)

Implementado em `_executar_requisicao_mercos`:

- Até **3 tentativas** por application token  
- Em **429**: `sleep(10 * (tentativa + 1))` e retry  
- Após esgotar: erro pedindo aguardar ~1 minuto  
- Entre páginas de produtos: `sleep(0.3)`  

Não há parsing de header `Retry-After`.

### Paginação

Só em produtos (`buscar_produtos_mercos`):

- Query `?pagina=1,2,…`  
- Para quando o lote vem vazio **ou** `len(lote) < 50` (assume página de 50)  
- Aceita lista JSON ou chaves `produtos` / `data` / `results`  

### Sync Mercos → Supabase

| O quê | Como |
|-------|------|
| **Produtos** | `sincronizar_produtos_mercos` → upsert em `produtos` |
| CLI | `python sync_produtos.py` |
| HTTP | `GET|POST /sync-produtos?token=…` |
| Clientes / pedidos | **Não** há sync de listagem; só grava `mercos_cliente_id` após POST cliente |

### Scripts / rotas de teste (sem expor token)

| Rota / script | O que faz | Cria registro na Mercos? |
|---------------|-----------|--------------------------|
| `GET /status` | Flags sandbox, base URL, checkout | Não |
| `GET /teste-mercos?q=…` | Busca catálogo (Mercos/Supabase) | Não |
| `GET|POST /sync-produtos` | Sync produtos | Não |
| Checkout WhatsApp / `/chat` | Fluxo comercial | **Não** com `CHECKOUT_CREATE_ORDER=false` |
| MCP `pedidos.criar_mercos` | Escrita gated | Só se `MCP_WRITE_ORDERS` ligado |

Não existe rota dedicada “criar cliente/pedido de teste na sandbox” isolada do checkout. Para evidência de POST na homologação, usar **sandbox** com script/controle manual ou flag temporária — **nunca** ligar pedido automático em produção/WhatsApp sem alinhamento.

### Logs e tokens

- Headers `CompanyToken` / `ApplicationToken` **não** são impressos de propósito.  
- `log_seguro` omite chaves `token` / `key` / `authorization`.  
- **Não** colar `.env`, tokens ou Company Token em prints para a Mercos.  
- Respostas de erro podem incluir trecho do body da API (não o token de saída).

### Respostas úteis para print

| Endpoint local | Evidência típica |
|----------------|------------------|
| `/status` | `mercos_configurado`, `mercos_sandbox`, `mercos_base_url`, `checkout_create_order: false` |
| `/teste-mercos` | `fonte`, `total`, lista `produtos` (nome, preço, estoque) |
| `/sync-produtos` | contagens de sync (inseridos/atualizados) |

---

## 3. Ordem recomendada de homologação

1. **Status / ambiente** — provar sandbox + tokens configurados (sem mostrar o valor do token).  
2. **GET produtos** — listagem + paginação + (opcional) sync Supabase.  
3. **POST clientes** — criar 1 cliente de teste na sandbox (evidência: ID / header MeusPedidosID).  
4. **POST pedidos** — 1 pedido mínimo na sandbox ligado a esse cliente (**somente sandbox**, flags explícitas, sem WhatsApp em massa).  
5. **Encerrar** — documentar o que **não** foi homologado por não existir no código.

---

## 4. Comandos PowerShell / curl

Substitua `$BASE` pela URL do Render (ex.: `https://agent-ia-xnamai.onrender.com`) e `$SYNC` pelo `SYNC_TOKEN` se `DIAGNOSTICOS_ABERTOS=false`.  
**Não** imprima tokens no terminal compartilhado / ticket.

### 4.1 Status (sandbox + checkout off)

```powershell
$BASE = "https://agent-ia-xnamai.onrender.com"
Invoke-RestMethod "$BASE/status" | ConvertTo-Json -Depth 6
```

```bash
curl -s "$BASE/status"
```

**Print sugerido:** trecho com  
`mercos_sandbox: true`,  
`mercos_base_url` contendo `sandbox.mercos.com`,  
`checkout_create_order: false`.

### 4.2 GET produtos (via diagnóstico do agente)

```powershell
$BASE = "https://agent-ia-xnamai.onrender.com"
$SYNC = $env:SYNC_TOKEN   # se necessário
Invoke-RestMethod "$BASE/teste-mercos?q=headset&token=$SYNC" | ConvertTo-Json -Depth 8
```

```bash
curl -s "$BASE/teste-mercos?q=headset&token=$SYNC"
```

**Print sugerido:** `status: ok`, `fonte` (mercos/supabase), `total` > 0, amostra de 1–2 produtos **sem** dados sensíveis de cliente.

### 4.3 Sync Mercos → Supabase (produtos)

```powershell
Invoke-RestMethod -Method Post "$BASE/sync-produtos?token=$SYNC" | ConvertTo-Json -Depth 6
```

```bash
curl -s -X POST "$BASE/sync-produtos?token=$SYNC"
```

Local:

```powershell
cd agente-vendas-python
python sync_produtos.py
```

**Print sugerido:** resultado do sync (totais), sem tokens.

### 4.4 POST cliente / POST pedido (sandbox controlado)

Não há endpoint HTTP público “só para homolog” que ignore o checkout. Opções alinhadas ao código:

1. **Sandbox + flags temporárias** em ambiente de teste (não produção WhatsApp):  
   - `MERCOS_BASE_URL=https://sandbox.mercos.com/api`  
   - Manter produção do agente com `CHECKOUT_CREATE_ORDER=false`  
   - Exercitar create apenas em sessão controlada / script interno / MCP com write guard  

2. Evidências mínimas na Mercos (painel sandbox):  
   - Cliente criado (ID)  
   - Pedido criado (ID / número)  

**Não** usar o WhatsApp real de clientes para “provar” POST em massa.  
**Não** anexar Company Token nos prints.

### 4.5 Confirmar que o agente NÃO cria pedido automático

```powershell
(Invoke-RestMethod "$BASE/status").checkout_create_order
# Esperado: False
```

```bash
curl -s "$BASE/status" | findstr /i checkout_create_order
```

---

## 5. Evidências / prints para anexar na Mercos

| # | Evidência | Como obter | Cuidado |
|---|-----------|------------|--------|
| 1 | Ambiente sandbox | `/status` → `mercos_sandbox` + `mercos_base_url` | Não mostrar token |
| 2 | Listagem de produtos | `/teste-mercos` ou painel sandbox | Omitir dados irrelevantes |
| 3 | Paginação | Log/print de sync com múltiplas páginas ou captura de `?pagina=` no código/teste | — |
| 4 | Tratamento 429 | (Opcional) print do código `_executar_requisicao_mercos` ou log de retry | Sem token |
| 5 | Cliente criado | Painel sandbox / ID retornado | Sem PII desnecessária |
| 6 | Pedido criado | Painel sandbox / ID | Só sandbox |
| 7 | Pedido automático off | `/status` → `checkout_create_order: false` | Obrigatório para o agente |

---

## 6. Cuidados

### Sandbox

- URL deve conter `sandbox.mercos.com`.  
- Não apontar Company Token de produção no sandbox e vice-versa.  
- Dados de teste podem ser baratos/exemplos; `MERCOS_OCULTAR_EXEMPLOS=true` filtra `[exemplo]` no catálogo do agente.

### Paginação

- Homologar listagem com mais de uma página se o sandbox tiver ≥ 50 produtos.  
- Critério de parada do código: lote vazio ou `< 50` itens.

### Throttling

- Evitar loops agressivos de sync/teste.  
- Em 429, aguardar conforme mensagem do serviço (~1 min após 3 falhas).  
- Espaçamento de 0,3 s entre páginas já existe.

### O que NÃO homologar (ainda não implementado)

- CRUD completo de clientes/produtos/pedidos além do descrito  
- Títulos financeiros  
- Tabelas de preço / condições / transportadoras / políticas / categorias / ajuste de estoque como APIs  
- Oportunidades e funis  
- Qualquer PUT/DELETE Mercos  

---

## 7. Mapa rápido código ↔ rota

| Função | Arquivo | Rota Mercos |
|--------|---------|-------------|
| `buscar_produtos_mercos` | `mercos_service.py` | `GET /v1/produtos` |
| `criar_cliente_mercos` | `mercos_service.py` | `POST /v1/clientes` |
| `criar_pedido_mercos` | `mercos_service.py` | `POST /v2/pedidos` |
| `sincronizar_produtos_mercos` | `sync_mercos_service.py` | usa GET produtos |
| `criar_pedido_fechamento_mercos` | `pedido_mercos_service.py` | orquestra POST cliente + pedido |

---

## 8. Resumo executivo

**Prontas (3):** GET produtos · POST clientes · POST pedidos (v2).  

**Faltantes:** restante do catálogo Mercos (títulos, tabelas, transportadoras, políticas, categorias, estoque API, oportunidades, CRUD completo).  

**Agente:** manter `CHECKOUT_CREATE_ORDER=false` — homologação Mercos ≠ ligar pedido automático no WhatsApp.

---

*Gerado para o plano de homologação beta. Atualizar este arquivo quando novas rotas Mercos forem implementadas.*
