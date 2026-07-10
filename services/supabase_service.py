import os
import time

from dotenv import load_dotenv
from httpx import ConnectError, ReadError, TimeoutException

from postgrest.exceptions import APIError

from database.supabase import supabase
from services.config_tabelas import CLIENTES_TABLE, CONVERSAS_TABLE, normalizar_telefone
from services.env_loader import carregar_env

carregar_env()


def _leads_indisponivel(erro: Exception) -> bool:
    if isinstance(erro, APIError):
        payload = erro.args[0] if erro.args else {}
        if isinstance(payload, dict):
            if payload.get("code") == "PGRST205":
                return True
            if "leads" in str(payload.get("message", "")).lower():
                return True
    return "leads" in str(erro).lower()

# Tabelas explícitas (CLIENTES_TABLE / CONVERSAS_TABLE) — sem fallback silencioso
TABELA_CLIENTES = CLIENTES_TABLE
TABELA_HISTORICO = CONVERSAS_TABLE
# Alias legado (não usar em código novo)
TABELA_CONVERSAS = CONVERSAS_TABLE

_RETRIES = 3
_RETRY_ERRORS = (ReadError, ConnectError, TimeoutException, OSError)

# Cache de schema (None = ainda não detectado)
_SCHEMA_FLAGS: dict[str, bool | None] = {
    "message_id": None,
    "contexto_venda": None,
}

# Sentinel no JSON historico quando a coluna contexto_venda ainda não existe
_HIST_CTX_ROLE = "_contexto_venda"


def _executar(comando, rotulo: str = "supabase"):
    for tentativa in range(1, _RETRIES + 1):
        try:
            return comando()
        except _RETRY_ERRORS as erro:
            if tentativa >= _RETRIES:
                print(f"ERRO {rotulo} após {_RETRIES} tentativas:", erro)
                raise
            espera = 0.4 * tentativa
            print(f"RETRY {rotulo} ({tentativa}/{_RETRIES}) em {espera:.1f}s:", erro)
            time.sleep(espera)


def _texto_erro(exc: Exception) -> str:
    partes = [str(exc)]
    if getattr(exc, "args", None):
        for a in exc.args:
            partes.append(str(a))
    return " ".join(partes).lower()


def erro_coluna_ausente(exc: Exception, coluna: str | None = None) -> bool:
    """Detecta PGRST204 / column not in schema cache."""
    text = _texto_erro(exc)
    code = ""
    if isinstance(exc, APIError) and exc.args:
        arg0 = exc.args[0]
        if isinstance(arg0, dict):
            code = str(arg0.get("code") or "").lower()
            text = f"{text} {arg0.get('message') or ''}".lower()
    if code == "pgrst204" or "pgrst204" in text:
        if not coluna:
            return True
        return coluna.lower() in text
    if coluna and coluna.lower() in text and (
        "column" in text or "schema cache" in text or "could not find" in text
    ):
        return True
    return False


def schema_tem_message_id() -> bool | None:
    return _SCHEMA_FLAGS.get("message_id")


def schema_tem_contexto_venda() -> bool | None:
    return _SCHEMA_FLAGS.get("contexto_venda")


def diagnosticar_schema_persistencia() -> dict:
    """Lê uma linha de cada tabela e reporta colunas críticas."""
    out = {
        "clientes_tem_contexto_venda": False,
        "conversas_tem_message_id": False,
        "clientes_cols": [],
        "conversas_cols": [],
    }
    try:
        r = supabase.table(TABELA_CLIENTES).select("*").limit(1).execute()
        cols = sorted((r.data[0] if r.data else {}).keys())
        out["clientes_cols"] = cols
        out["clientes_tem_contexto_venda"] = "contexto_venda" in cols
        _SCHEMA_FLAGS["contexto_venda"] = out["clientes_tem_contexto_venda"]
    except Exception as exc:
        out["clientes_erro"] = type(exc).__name__
    try:
        r = supabase.table(TABELA_HISTORICO).select("*").limit(1).execute()
        cols = sorted((r.data[0] if r.data else {}).keys())
        out["conversas_cols"] = cols
        out["conversas_tem_message_id"] = "message_id" in cols
        _SCHEMA_FLAGS["message_id"] = out["conversas_tem_message_id"]
    except Exception as exc:
        out["conversas_erro"] = type(exc).__name__
    return out


def extrair_contexto_do_historico_json(historico_raw) -> dict:
    """Lê contexto embutido no JSON historico (fallback sem coluna)."""
    if isinstance(historico_raw, dict):
        ctx = historico_raw.get("contexto_venda") or historico_raw.get(_HIST_CTX_ROLE)
        return ctx if isinstance(ctx, dict) else {}
    if isinstance(historico_raw, list):
        for item in reversed(historico_raw):
            if isinstance(item, dict) and item.get("role") == _HIST_CTX_ROLE:
                content = item.get("content")
                return content if isinstance(content, dict) else {}
    return {}


def anexar_contexto_no_historico_json(mensagens: list, contexto: dict) -> list:
    """Mantém lista compatível + sentinel de contexto no final."""
    base = [
        m
        for m in (mensagens or [])
        if not (isinstance(m, dict) and m.get("role") == _HIST_CTX_ROLE)
    ]
    if contexto:
        base.append(
            {
                "role": _HIST_CTX_ROLE,
                "content": contexto,
                "timestamp": "",
            }
        )
    return base


def _normalizar_produto(row: dict) -> dict:
    """Compatível com produtos do ETL PulseDesk (preco_tabela, saldo_estoque)."""
    preco = row.get("preco")
    if preco in (None, ""):
        preco = row.get("preco_tabela") or 0
    estoque = row.get("estoque")
    if estoque is None:
        estoque = row.get("saldo_estoque")
    if estoque is None:
        estoque = 0
    return {
        **row,
        "preco": preco,
        "estoque": estoque,
        "descricao": row.get("descricao") or row.get("observacoes") or "",
    }


# =========================
# CLIENTES (agente WhatsApp)
# =========================

def buscar_cliente(telefone):
    tel = normalizar_telefone(telefone)
    if not tel:
        return None

    resultado = _executar(
        lambda: (
            supabase.table(TABELA_CLIENTES)
            .select("*")
            .eq("telefone", tel)
            .execute()
        ),
        "buscar_cliente",
    )

    if resultado.data:
        return resultado.data[0]

    return None


def criar_cliente(telefone, nome=""):
    tel = normalizar_telefone(telefone)
    dados = {"telefone": tel}
    if nome:
        dados["nome"] = nome

    try:
        resultado = _executar(
            lambda: supabase.table(TABELA_CLIENTES).insert(dados).execute(),
            "criar_cliente",
        )
        return resultado.data[0]
    except Exception as exc:
        text = _texto_erro(exc)
        # Telefone já existe — rebusca em vez de falhar
        if "duplicate" in text or "unique" in text or "23505" in text:
            existente = buscar_cliente(tel)
            if existente:
                return existente
        raise


def atualizar_cliente(cliente_id, **campos):
    if not campos:
        return None

    resultado = (
        supabase.table(TABELA_CLIENTES)
        .update(campos)
        .eq("id", cliente_id)
        .execute()
    )

    return resultado


def salvar_openai_thread_id(cliente_id, thread_id):
    resultado = (
        supabase.table(TABELA_CLIENTES)
        .update({
            "openai_thread_id": thread_id
        })
        .eq("id", cliente_id)
        .execute()
    )

    return resultado


# =========================
# HISTÓRICO (agente)
# =========================

def salvar_mensagem(cliente_id, tipo, mensagem, message_id: str | None = None):
    from services.webhook_guard import log_seguro

    payload = {
        "cliente_id": cliente_id,
        "tipo": tipo,
        "mensagem": mensagem,
    }
    mid = (message_id or "").strip()
    # Só envia message_id se a coluna existir (evita PGRST204)
    if mid and _SCHEMA_FLAGS.get("message_id") is not False:
        payload["message_id"] = mid

    log_seguro(
        "salvar_mensagem_inicio",
        tipo=tipo,
        message_id=mid if "message_id" in payload else "-",
        chars=len(mensagem or ""),
    )
    try:
        return (
            supabase.table(TABELA_HISTORICO)
            .insert(payload)
            .execute()
        )
    except Exception as exc:
        log_seguro(
            "salvar_mensagem_erro",
            tipo=tipo,
            message_id=mid or "-",
            erro=type(exc).__name__,
            detalhe=str(exc)[:120],
        )
        text = _texto_erro(exc)
        # Índice único em message_id — trata como duplicata (idempotente)
        if mid and ("duplicate" in text or "unique" in text or "23505" in text):
            print("AVISO: message_id já existe — insert ignorado")
            return None
        # Coluna message_id ainda não migrada — grava sem o campo
        if "message_id" in payload and erro_coluna_ausente(exc, "message_id"):
            _SCHEMA_FLAGS["message_id"] = False
            payload.pop("message_id", None)
            try:
                return (
                    supabase.table(TABELA_HISTORICO)
                    .insert(payload)
                    .execute()
                )
            except Exception as exc2:
                log_seguro(
                    "salvar_mensagem_erro",
                    tipo=tipo,
                    message_id="-",
                    erro=type(exc2).__name__,
                    detalhe=str(exc2)[:120],
                )
                raise
        raise


def mensagem_ja_existe(message_id: str) -> bool:
    """Fonte final de idempotência: message_id já gravado em conversas."""
    mid = (message_id or "").strip()
    if not mid:
        return False
    if _SCHEMA_FLAGS.get("message_id") is False:
        return False
    try:
        resultado = _executar(
            lambda: (
                supabase.table(TABELA_HISTORICO)
                .select("id")
                .eq("message_id", mid)
                .limit(1)
                .execute()
            ),
            "mensagem_ja_existe",
        )
        _SCHEMA_FLAGS["message_id"] = True
        return bool(resultado.data)
    except Exception as exc:
        # Coluna pode não existir ainda — não bloqueia o fluxo
        if erro_coluna_ausente(exc, "message_id") or "pgrst" in _texto_erro(exc):
            _SCHEMA_FLAGS["message_id"] = False
            print("AVISO: checagem message_id indisponível:", type(exc).__name__)
            return False
        raise


def buscar_historico(cliente_id, limit: int | None = None):
    query = (
        supabase.table(TABELA_HISTORICO)
        .select("*")
        .eq("cliente_id", cliente_id)
        .order("criado_em")
    )
    resultado = query.execute()
    dados = resultado.data or []
    if limit is not None and limit > 0 and len(dados) > limit:
        return dados[-limit:]
    return dados


def atualizar_historico_json(cliente_id, contexto_extra: dict | None = None):
    """Atualiza clientes.historico; preserva contexto embutido se coluna ausente."""
    historico = buscar_historico(cliente_id)

    historico_json = []
    for msg in historico:
        historico_json.append({
            "role": "user" if msg["tipo"] == "cliente" else "assistant",
            "content": msg["mensagem"],
            "timestamp": str(msg.get("criado_em") or ""),
        })

    # Preserva/atualiza contexto no JSON quando não há coluna contexto_venda
    ctx = contexto_extra
    if ctx is None and _SCHEMA_FLAGS.get("contexto_venda") is False:
        try:
            atual = (
                supabase.table(TABELA_CLIENTES)
                .select("historico")
                .eq("id", cliente_id)
                .limit(1)
                .execute()
            )
            if atual.data:
                ctx = extrair_contexto_do_historico_json(atual.data[0].get("historico"))
        except Exception:
            ctx = {}

    payload_hist = historico_json
    if ctx and _SCHEMA_FLAGS.get("contexto_venda") is not True:
        payload_hist = anexar_contexto_no_historico_json(historico_json, ctx)

    resultado = (
        supabase.table(TABELA_CLIENTES)
        .update({"historico": payload_hist})
        .eq("id", cliente_id)
        .execute()
    )
    return resultado


def persistir_contexto_venda(cliente_id: str, contexto: dict) -> bool:
    """Persiste contexto_venda na coluna ou fallback no JSON historico.

    Retorna True se gravou no Supabase; False se falhou.
    """
    from services.webhook_guard import log_seguro

    if not cliente_id or str(cliente_id).startswith("ephemeral-"):
        return False

    log_seguro("atualizar_contexto_inicio", cliente_id=str(cliente_id)[:8])

    # Caminho preferencial: coluna dedicada
    if _SCHEMA_FLAGS.get("contexto_venda") is not False:
        try:
            atualizar_cliente(cliente_id=cliente_id, contexto_venda=contexto)
            _SCHEMA_FLAGS["contexto_venda"] = True
            return True
        except Exception as exc:
            if erro_coluna_ausente(exc, "contexto_venda"):
                _SCHEMA_FLAGS["contexto_venda"] = False
                log_seguro(
                    "atualizar_contexto_erro",
                    cliente_id=str(cliente_id)[:8],
                    erro="PGRST204",
                    detalhe="coluna contexto_venda ausente — usando fallback historico",
                )
            else:
                log_seguro(
                    "atualizar_contexto_erro",
                    cliente_id=str(cliente_id)[:8],
                    erro=type(exc).__name__,
                    detalhe=str(exc)[:120],
                )
                return False

    # Fallback: embute no JSON historico (sem migração)
    try:
        atual = (
            supabase.table(TABELA_CLIENTES)
            .select("historico")
            .eq("id", cliente_id)
            .limit(1)
            .execute()
        )
        hist_raw = (atual.data[0].get("historico") if atual.data else None) or []
        if isinstance(hist_raw, list):
            mensagens = [
                m
                for m in hist_raw
                if not (isinstance(m, dict) and m.get("role") == _HIST_CTX_ROLE)
            ]
        elif isinstance(hist_raw, dict):
            mensagens = hist_raw.get("mensagens") or hist_raw.get("messages") or []
            if not isinstance(mensagens, list):
                mensagens = []
        else:
            mensagens = []

        novo = anexar_contexto_no_historico_json(mensagens, contexto)
        atualizar_cliente(cliente_id=cliente_id, historico=novo)
        log_seguro(
            "atualizar_contexto_inicio",
            cliente_id=str(cliente_id)[:8],
            modo="fallback_historico",
        )
        return True
    except Exception as exc:
        log_seguro(
            "atualizar_contexto_erro",
            cliente_id=str(cliente_id)[:8],
            erro=type(exc).__name__,
            detalhe=str(exc)[:120],
            modo="fallback_historico",
        )
        return False


# =========================
# PRODUTOS (ETL PulseDesk → Supabase)
# =========================

_cache_produtos: dict = {"dados": None, "expira_em": 0.0}
_CACHE_PRODUTOS_SEG = float(os.getenv("PRODUTOS_CACHE_SEGUNDOS", "120") or "120")


def invalidar_cache_produtos() -> None:
    _cache_produtos["dados"] = None
    _cache_produtos["expira_em"] = 0.0


def buscar_produtos():
    agora = time.time()
    if _cache_produtos["dados"] is not None and agora < float(_cache_produtos["expira_em"]):
        return list(_cache_produtos["dados"])

    resultado = (
        supabase.table("produtos")
        .select("*")
        .execute()
    )
    produtos = [_normalizar_produto(row) for row in (resultado.data or [])]
    _cache_produtos["dados"] = produtos
    _cache_produtos["expira_em"] = agora + max(30.0, _CACHE_PRODUTOS_SEG)
    return list(produtos)


def buscar_produto_por_nome(nome):
    resultado = (
        supabase.table("produtos")
        .select("*")
        .ilike("nome", f"%{nome}%")
        .execute()
    )

    return [_normalizar_produto(row) for row in (resultado.data or [])]


def buscar_produto_por_id(produto_id):
    resultado = (
        supabase.table("produtos")
        .select("*")
        .eq("id", produto_id)
        .execute()
    )

    if resultado.data:
        return _normalizar_produto(resultado.data[0])

    return None


def buscar_produto_por_mercos_id(mercos_id):
    resultado = (
        supabase.table("produtos")
        .select("*")
        .eq("mercos_id", mercos_id)
        .execute()
    )

    if resultado.data:
        return _normalizar_produto(resultado.data[0])

    return None


def sincronizar_produto_mercos(dados: dict) -> str:
    """Legado — preferir ETL do backend PulseDesk."""
    mercos_id = dados.get("mercos_id")
    existente = None

    if mercos_id is not None:
        existente = buscar_produto_por_mercos_id(mercos_id)

    if not existente and dados.get("nome"):
        resultado = (
            supabase.table("produtos")
            .select("*")
            .eq("nome", dados["nome"])
            .limit(1)
            .execute()
        )
        if resultado.data:
            existente = resultado.data[0]

    # Schema PulseDesk (ETL): preco_tabela / saldo_estoque — sem coluna categoria/preco/estoque
    campos = {
        "mercos_id": mercos_id,
        "nome": dados.get("nome"),
        "codigo": dados.get("codigo") or "",
        "descricao": dados.get("descricao") or "",
        "preco_tabela": dados.get("preco_tabela", dados.get("preco") or 0),
        "preco_minimo": dados.get("preco_minimo") or 0,
        "saldo_estoque": dados.get("saldo_estoque", dados.get("estoque") or 0),
        "ativo": dados.get("ativo", True),
    }
    if dados.get("unidade") is not None:
        campos["unidade"] = dados.get("unidade")
    if dados.get("ultima_alteracao"):
        campos["ultima_alteracao"] = dados["ultima_alteracao"]

    if dados.get("imagem_url"):
        # Só grava se a coluna existir no projeto; ignora se falhar no insert/update
        campos["imagem_url"] = dados["imagem_url"]

    def _sem_imagem(payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k != "imagem_url"}

    if existente:
        if mercos_id is not None and not existente.get("mercos_id"):
            campos["mercos_id"] = mercos_id
        try:
            supabase.table("produtos").update(campos).eq("id", existente["id"]).execute()
        except Exception:
            supabase.table("produtos").update(_sem_imagem(campos)).eq(
                "id", existente["id"]
            ).execute()
        return "atualizado"

    try:
        supabase.table("produtos").insert(campos).execute()
    except Exception:
        supabase.table("produtos").insert(_sem_imagem(campos)).execute()
    return "criado"


# =========================
# LEADS
# =========================

def criar_lead(cliente_id, interesse):
    try:
        return _executar(
            lambda: supabase.table("leads")
            .insert({
                "cliente_id": cliente_id,
                "interesse": interesse,
                "status": "novo",
            })
            .execute(),
            "criar_lead",
        )
    except Exception as erro:
        if _leads_indisponivel(erro):
            print("AVISO: tabela leads indisponível — lead não salvo")
            return None
        raise


def buscar_lead(cliente_id, interesse):
    try:
        resultado = _executar(
            lambda: (
                supabase.table("leads")
                .select("*")
                .eq("cliente_id", cliente_id)
                .eq("interesse", interesse)
                .execute()
            ),
            "buscar_lead",
        )
    except Exception as erro:
        if _leads_indisponivel(erro):
            print("AVISO: tabela leads indisponível — lead ignorado")
            return None
        raise

    if resultado.data:
        return resultado.data[0]

    return None
