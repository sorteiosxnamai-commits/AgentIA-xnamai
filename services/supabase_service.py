import os
import time

from dotenv import load_dotenv
from httpx import ConnectError, ReadError, TimeoutException

from postgrest.exceptions import APIError

from database.supabase import (
    supabase,
    supabase_client_ready,
    supabase_key_kind,
    supabase_key_source,
    supabase_url_configurada,
)
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
    # True = tabela CONVERSAS é thread/atendimento (PulseDesk)
    # False = tabela legada de mensagens (cliente_id/tipo/mensagem)
    "conversas_thread": None,
    "clientes_celular": None,
    "clientes_historico": None,
}

# Último erro seguro de busca/criação (para dry_run / debug)
_ULTIMO_ERRO_CLIENTE: dict | None = None

# Colunas conhecidas que o agente pode usar em clientes
_COLS_CLIENTES_CONHECIDAS = (
    "id",
    "telefone",
    "celular",
    "nome",
    "historico",
    "contexto_venda",
    "ativo",
    "criado_em",
    "mercos_cliente_id",
    "mercos_id",
    "email",
    "cnpj",
)

# Sentinel no JSON historico quando a coluna contexto_venda ainda não existe
_HIST_CTX_ROLE = "_contexto_venda"

# Colunas típicas de thread PulseDesk vs mensagens do agente
_COLS_THREAD = frozenset({
    "contact_phone", "last_message", "external_thread_id", "canal_id", "channel",
})
_COLS_MENSAGENS = frozenset({"cliente_id", "tipo", "mensagem"})


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


def _payload_api_error(exc: Exception) -> dict:
    if isinstance(exc, APIError) and exc.args:
        arg0 = exc.args[0]
        if isinstance(arg0, dict):
            return arg0
    return {}


def classificar_erro_supabase(exc: Exception) -> tuple[str, str, str]:
    """Retorna (codigo, tipo, resumo) sem dados sensíveis."""
    payload = _payload_api_error(exc)
    code = str(payload.get("code") or "").strip()
    message = str(payload.get("message") or exc)[:160]
    text = f"{code} {message}".lower()

    if (
        "row-level security" in text
        or "42501" in text
        or code == "42501"
        or "permission denied" in text
        or "not allowed" in text
    ):
        return (
            code or "42501",
            "RLS",
            "RLS/permissão bloqueou clientes — use SUPABASE_SERVICE_ROLE_KEY no Render",
        )
    if code.upper() == "PGRST204" or "pgrst204" in text or "schema cache" in text:
        return code or "PGRST204", "SCHEMA", message[:120]
    if code.upper() == "PGRST116" or "pgrst116" in text:
        return code or "PGRST116", "NOT_FOUND", message[:120]
    if "23505" in text or "duplicate" in text or "unique" in text:
        return code or "23505", "DUPLICATE", "telefone/celular já existe"
    if "23502" in text or ("null value" in text and "column" in text):
        return code or "23502", "NOT_NULL", message[:120]
    if isinstance(exc, _RETRY_ERRORS):
        return "", "NETWORK", type(exc).__name__
    return code or "", type(exc).__name__, message[:120]


def limpar_ultimo_erro_cliente() -> None:
    global _ULTIMO_ERRO_CLIENTE
    _ULTIMO_ERRO_CLIENTE = None


def obter_ultimo_erro_cliente() -> dict | None:
    return dict(_ULTIMO_ERRO_CLIENTE) if _ULTIMO_ERRO_CLIENTE else None


def registrar_erro_cliente(etapa: str, exc: Exception | None = None, *, codigo: str = "", tipo: str = "", resumo: str = "") -> dict:
    global _ULTIMO_ERRO_CLIENTE
    if exc is not None:
        codigo, tipo, resumo = classificar_erro_supabase(exc)
    if not tipo:
        tipo = type(exc).__name__ if exc is not None else "DESCONHECIDO"
    if not resumo:
        resumo = (str(exc)[:120] if exc is not None else "erro sem detalhe")
    _ULTIMO_ERRO_CLIENTE = {
        "etapa": etapa or "desconhecida",
        "erro_codigo": codigo or "",
        "erro_tipo": tipo,
        "erro_resumido": resumo[:160],
        "key_source": supabase_key_source(),
        "key_kind": supabase_key_kind(),
        "tabela": TABELA_CLIENTES,
    }
    try:
        from services.webhook_guard import log_seguro

        log_seguro(
            "cliente_criacao_erro" if "criar" in (etapa or "") or "rebusca" in (etapa or "") else "cliente_busca_nao_encontrado",
            etapa=etapa,
            erro=tipo,
            detalhe=resumo[:120],
            codigo=codigo or "-",
            key_source=supabase_key_source(),
            key_kind=supabase_key_kind(),
        )
    except Exception:
        pass
    return dict(_ULTIMO_ERRO_CLIENTE)


def erro_cliente_para_debug(fallback_etapa: str = "criar_cliente") -> dict:
    """Sempre retorna objeto estruturado (nunca string vazia)."""
    atual = obter_ultimo_erro_cliente()
    if atual and (atual.get("erro_tipo") or atual.get("erro_resumido") or atual.get("erro_codigo")):
        return {
            "etapa": str(atual.get("etapa") or fallback_etapa),
            "erro_codigo": str(atual.get("erro_codigo") or ""),
            "erro_tipo": str(atual.get("erro_tipo") or ""),
            "erro_resumido": str(atual.get("erro_resumido") or "")[:160],
        }
    return {
        "etapa": fallback_etapa,
        "erro_codigo": "EPHEMERAL",
        "erro_tipo": "FALLBACK",
        "erro_resumido": "busca/criação falhou sem detalhe — verifique SUPABASE_SERVICE_ROLE_KEY e RLS",
    }


def diagnosticar_supabase_status() -> dict:
    """Campos seguros para /status (sem segredos)."""
    out = {
        "supabase_url_configurada": supabase_url_configurada(),
        "supabase_client_ready": supabase_client_ready(),
        "supabase_key_source": supabase_key_source(),
        "supabase_key_kind": supabase_key_kind(),
        "clientes_table": TABELA_CLIENTES,
    }
    # Probe leve: select 1
    try:
        r = supabase.table(TABELA_CLIENTES).select("id").limit(1).execute()
        out["clientes_select_ok"] = True
        out["clientes_tem_linhas"] = bool(r.data)
    except Exception as exc:
        codigo, tipo, resumo = classificar_erro_supabase(exc)
        out["clientes_select_ok"] = False
        out["clientes_select_erro"] = {
            "erro_codigo": codigo,
            "erro_tipo": tipo,
            "erro_resumido": resumo[:120],
        }
    return out


def diagnosticar_persistencia_cliente(telefone: str = "") -> dict:
    """Probe seguro: select / insert mínimo / update historico|contexto.

    Usa telefone de teste se vazio. Remove o registro de probe ao final quando possível.
    """
    from services.config_tabelas import normalizar_telefone as _norm

    tel = _norm(telefone) or "5500000000000"
    # evita colidir com números reais de teste do usuário
    if tel.endswith("9993") or len(tel) < 10:
        tel = "5500000000099"

    out: dict = {
        "key_source": supabase_key_source(),
        "key_kind": supabase_key_kind(),
        "tabela": TABELA_CLIENTES,
        "select_ok": False,
        "insert_ok": False,
        "historico_ok": False,
        "contexto_ok": False,
        "erro": None,
    }
    cols = _detectar_colunas_clientes()
    out["colunas_detectadas"] = sorted(cols)[:20]

    try:
        r = (
            supabase.table(TABELA_CLIENTES)
            .select("id")
            .eq("telefone", tel)
            .limit(1)
            .execute()
        )
        out["select_ok"] = True
        existente_id = (r.data[0]["id"] if r.data else None)
    except Exception as exc:
        codigo, tipo, resumo = classificar_erro_supabase(exc)
        out["erro"] = {"etapa": "select", "erro_codigo": codigo, "erro_tipo": tipo, "erro_resumido": resumo[:120]}
        registrar_erro_cliente("probe_select", exc)
        return out

    cliente_id = existente_id
    criado_probe = False
    if not cliente_id:
        payload = {"telefone": tel, "nome": "Probe Agente"}
        if "celular" in cols:
            payload["celular"] = tel
        try:
            ins = supabase.table(TABELA_CLIENTES).insert(payload).execute()
            if ins.data:
                cliente_id = ins.data[0].get("id")
                criado_probe = True
                out["insert_ok"] = True
            else:
                # insert sem return — rebusca
                r2 = (
                    supabase.table(TABELA_CLIENTES)
                    .select("id")
                    .eq("telefone", tel)
                    .limit(1)
                    .execute()
                )
                if r2.data:
                    cliente_id = r2.data[0]["id"]
                    criado_probe = True
                    out["insert_ok"] = True
                else:
                    out["erro"] = {
                        "etapa": "insert",
                        "erro_codigo": "SEM_RETORNO",
                        "erro_tipo": "INSERT_EMPTY",
                        "erro_resumido": "insert sem data e sem rebusca — possível RLS no SELECT",
                    }
                    registrar_erro_cliente(
                        "probe_insert",
                        codigo="SEM_RETORNO",
                        tipo="INSERT_EMPTY",
                        resumo=out["erro"]["erro_resumido"],
                    )
                    return out
        except Exception as exc:
            codigo, tipo, resumo = classificar_erro_supabase(exc)
            out["erro"] = {"etapa": "insert", "erro_codigo": codigo, "erro_tipo": tipo, "erro_resumido": resumo[:120]}
            registrar_erro_cliente("probe_insert", exc)
            return out
    else:
        out["insert_ok"] = True  # já existia / select ok

    if cliente_id and "historico" in cols:
        try:
            supabase.table(TABELA_CLIENTES).update(
                {"historico": [{"role": "system", "content": "probe"}]}
            ).eq("id", cliente_id).execute()
            out["historico_ok"] = True
        except Exception as exc:
            codigo, tipo, resumo = classificar_erro_supabase(exc)
            out["erro"] = out["erro"] or {
                "etapa": "update_historico",
                "erro_codigo": codigo,
                "erro_tipo": tipo,
                "erro_resumido": resumo[:120],
            }
            registrar_erro_cliente("probe_historico", exc)

    if cliente_id and "contexto_venda" in cols:
        try:
            supabase.table(TABELA_CLIENTES).update(
                {"contexto_venda": {"probe": True}}
            ).eq("id", cliente_id).execute()
            out["contexto_ok"] = True
        except Exception as exc:
            codigo, tipo, resumo = classificar_erro_supabase(exc)
            out["erro"] = out["erro"] or {
                "etapa": "update_contexto",
                "erro_codigo": codigo,
                "erro_tipo": tipo,
                "erro_resumido": resumo[:120],
            }
            registrar_erro_cliente("probe_contexto", exc)
    elif cliente_id and "historico" in cols:
        out["contexto_ok"] = out["historico_ok"]  # fallback disponível

    # limpa probe criado por nós
    if criado_probe and cliente_id:
        try:
            supabase.table(TABELA_CLIENTES).delete().eq("id", cliente_id).execute()
            out["probe_removido"] = True
        except Exception:
            out["probe_removido"] = False

    return out


def erro_coluna_ausente(exc: Exception, coluna: str | None = None) -> bool:
    """Detecta PGRST204 / column not in schema cache."""
    text = _texto_erro(exc)
    code = ""
    payload = _payload_api_error(exc)
    if payload:
        code = str(payload.get("code") or "").lower()
        text = f"{text} {payload.get('message') or ''}".lower()
    if code == "pgrst204" or "pgrst204" in text:
        if not coluna:
            return True
        return coluna.lower() in text
    if coluna and coluna.lower() in text and (
        "column" in text or "schema cache" in text or "could not find" in text
    ):
        return True
    return False


def _null_violation_coluna(exc: Exception, coluna: str) -> bool:
    text = _texto_erro(exc)
    payload = _payload_api_error(exc)
    if str(payload.get("code") or "") == "23502" or "23502" in text:
        return coluna.lower() in text
    return "null value" in text and coluna.lower() in text and "column" in text


def conversas_e_thread() -> bool:
    """True se CONVERSAS_TABLE é schema de atendimento/thread (não mensagens)."""
    flag = _SCHEMA_FLAGS.get("conversas_thread")
    if flag is not None:
        return bool(flag)
    try:
        r = supabase.table(TABELA_HISTORICO).select("*").limit(1).execute()
        cols = set((r.data[0] if r.data else {}).keys())
        # Se não há linhas, tenta insert probe via heurística de nomes conhecidos
        if not cols:
            # Assume thread se a tabela se chama conversas (PulseDesk) — confirma com select de colunas via erro
            # Fallback: tenta filtrar por contact_phone (thread) vs cliente_id (mensagens)
            try:
                supabase.table(TABELA_HISTORICO).select("id").eq(
                    "contact_phone", "__probe__"
                ).limit(1).execute()
                _SCHEMA_FLAGS["conversas_thread"] = True
                return True
            except Exception as exc:
                if erro_coluna_ausente(exc, "contact_phone"):
                    _SCHEMA_FLAGS["conversas_thread"] = False
                    return False
                # Outro erro — tenta cliente_id
                try:
                    supabase.table(TABELA_HISTORICO).select("id").eq(
                        "cliente_id", "__probe__"
                    ).limit(1).execute()
                    _SCHEMA_FLAGS["conversas_thread"] = False
                    return False
                except Exception as exc2:
                    if erro_coluna_ausente(exc2, "cliente_id"):
                        _SCHEMA_FLAGS["conversas_thread"] = True
                        return True
                    _SCHEMA_FLAGS["conversas_thread"] = True  # seguro: não inserir campos errados
                    return True
        is_thread = bool(cols & _COLS_THREAD) and not bool(cols & _COLS_MENSAGENS)
        is_msgs = bool(cols & _COLS_MENSAGENS)
        if is_thread or (not is_msgs and ("last_message" in cols or "contact_phone" in cols)):
            _SCHEMA_FLAGS["conversas_thread"] = True
            _SCHEMA_FLAGS["message_id"] = "message_id" in cols
            return True
        _SCHEMA_FLAGS["conversas_thread"] = False
        _SCHEMA_FLAGS["message_id"] = "message_id" in cols
        return False
    except Exception:
        # Em dúvida, trata como thread para não inserir cliente_id/tipo/mensagem
        _SCHEMA_FLAGS["conversas_thread"] = True
        return True


def schema_tem_message_id() -> bool | None:
    return _SCHEMA_FLAGS.get("message_id")


def schema_tem_contexto_venda() -> bool | None:
    return _SCHEMA_FLAGS.get("contexto_venda")


def diagnosticar_schema_persistencia() -> dict:
    """Lê uma linha de cada tabela e reporta colunas críticas."""
    out = {
        "clientes_tem_contexto_venda": False,
        "conversas_tem_message_id": False,
        "conversas_modo": "desconhecido",
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
        cols_set = set(cols)
        if cols_set & _COLS_THREAD and not (cols_set & _COLS_MENSAGENS):
            out["conversas_modo"] = "thread"
            _SCHEMA_FLAGS["conversas_thread"] = True
        elif cols_set & _COLS_MENSAGENS:
            out["conversas_modo"] = "mensagens"
            _SCHEMA_FLAGS["conversas_thread"] = False
        else:
            # Heurística pelo nome / colunas parciais
            if "last_message" in cols_set or "contact_phone" in cols_set:
                out["conversas_modo"] = "thread"
                _SCHEMA_FLAGS["conversas_thread"] = True
            else:
                out["conversas_modo"] = "desconhecido"
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

def _detectar_colunas_clientes() -> set[str]:
    """Lê colunas da tabela clientes (funciona mesmo com tabela vazia)."""
    cols: set[str] = set()
    try:
        r = supabase.table(TABELA_CLIENTES).select("*").limit(1).execute()
        if r.data:
            cols = set(r.data[0].keys())
    except Exception as exc:
        registrar_erro_cliente("detectar_colunas", exc)
        # Continua com probe individual se possível

    if not cols:
        for col in _COLS_CLIENTES_CONHECIDAS:
            try:
                supabase.table(TABELA_CLIENTES).select(col).limit(1).execute()
                cols.add(col)
            except Exception as exc:
                if erro_coluna_ausente(exc, col):
                    continue
                # permissão / rede — aborta probe
                registrar_erro_cliente("detectar_colunas", exc)
                break

    if cols:
        _SCHEMA_FLAGS["clientes_celular"] = "celular" in cols
        _SCHEMA_FLAGS["clientes_historico"] = "historico" in cols
        _SCHEMA_FLAGS["contexto_venda"] = "contexto_venda" in cols
    return cols


def _nome_cliente_seguro(nome: str, tel: str) -> str:
    limpo = (nome or "").strip()
    if limpo:
        return limpo[:120]
    sufixo = (tel or "")[-4:] or "0000"
    return f"WhatsApp {sufixo}"


def _buscar_cliente_por_campo(campo: str, tel: str) -> dict | None:
    try:
        resultado = _executar(
            lambda: (
                supabase.table(TABELA_CLIENTES)
                .select("*")
                .eq(campo, tel)
                .limit(1)
                .execute()
            ),
            f"buscar_cliente_{campo}",
        )
        if resultado.data:
            return resultado.data[0]
    except Exception as exc:
        if erro_coluna_ausente(exc, campo):
            if campo == "celular":
                _SCHEMA_FLAGS["clientes_celular"] = False
            return None
        registrar_erro_cliente(f"buscar_cliente_{campo}", exc)
        raise
    return None


def buscar_cliente(telefone):
    """Busca por telefone e, se a coluna existir, por celular."""
    from services.webhook_guard import log_seguro

    tel = normalizar_telefone(telefone)
    if not tel:
        return None

    log_seguro("cliente_busca_inicio", tel_sufixo=tel[-4:])

    try:
        row = _buscar_cliente_por_campo("telefone", tel)
        if row:
            log_seguro("cliente_busca_ok", via="telefone", id_prefix=str(row.get("id") or "")[:8])
            return row

        # Só tenta celular se não sabemos que a coluna não existe
        if _SCHEMA_FLAGS.get("clientes_celular") is not False:
            row = _buscar_cliente_por_campo("celular", tel)
            if row:
                _SCHEMA_FLAGS["clientes_celular"] = True
                log_seguro("cliente_busca_ok", via="celular", id_prefix=str(row.get("id") or "")[:8])
                return row

        if _SCHEMA_FLAGS.get("clientes_celular") is not False:
            try:
                resultado = _executar(
                    lambda: (
                        supabase.table(TABELA_CLIENTES)
                        .select("*")
                        .or_(f"telefone.eq.{tel},celular.eq.{tel}")
                        .limit(1)
                        .execute()
                    ),
                    "buscar_cliente_or",
                )
                if resultado.data:
                    row = resultado.data[0]
                    log_seguro(
                        "cliente_busca_ok",
                        via="or",
                        id_prefix=str(row.get("id") or "")[:8],
                    )
                    return row
            except Exception as exc:
                if erro_coluna_ausente(exc, "celular"):
                    _SCHEMA_FLAGS["clientes_celular"] = False
                else:
                    registrar_erro_cliente("buscar_cliente_or", exc)
    except Exception as exc:
        registrar_erro_cliente("buscar_cliente", exc)
        raise

    log_seguro("cliente_busca_nao_encontrado", tel_sufixo=tel[-4:])
    return None


def criar_cliente(telefone, nome=""):
    """Cria cliente só com colunas existentes (sem email/CPF/CNPJ/endereço)."""
    from services.webhook_guard import log_seguro

    tel = normalizar_telefone(telefone)
    if not tel:
        raise ValueError("telefone_obrigatorio")

    nome_ok = _nome_cliente_seguro(nome, tel)
    log_seguro("cliente_criacao_inicio", tel_sufixo=tel[-4:])
    cols = _detectar_colunas_clientes()

    # Payload mínimo seguro — NUNCA inclui email/cpf/cnpj/endereço
    dados: dict = {"telefone": tel, "nome": nome_ok}
    if "celular" in cols:
        dados["celular"] = tel
        _SCHEMA_FLAGS["clientes_celular"] = True
    else:
        _SCHEMA_FLAGS["clientes_celular"] = False

    def _rebusca_ok(via: str):
        existente = buscar_cliente(tel)
        if existente:
            log_seguro(
                "cliente_criacao_ok",
                id_prefix=str(existente.get("id") or "")[:8],
                via=via,
            )
            return existente
        return None

    def _insert(payload: dict, rotulo: str):
        return _executar(
            lambda: supabase.table(TABELA_CLIENTES).insert(payload).execute(),
            rotulo,
        )

    tentativas = [dict(dados)]
    # Se celular conhecido, já está no payload. Se desconhecido (tabela vazia),
    # NÃO inventa celular — só adiciona se NOT NULL exigir explicitamente.

    ultimo_exc: Exception | None = None
    for payload in tentativas:
        try:
            resultado = _insert(payload, "criar_cliente")
            if resultado.data:
                row = resultado.data[0]
                log_seguro(
                    "cliente_criacao_ok",
                    id_prefix=str(row.get("id") or "")[:8],
                    via="insert",
                )
                return row
            encontrado = _rebusca_ok("rebusca_pos_insert")
            if encontrado:
                return encontrado
            registrar_erro_cliente(
                "criar_cliente",
                codigo="SEM_RETORNO",
                tipo="INSERT_EMPTY",
                resumo="insert sem data[0] e rebusca vazia",
            )
            raise RuntimeError("criar_cliente_sem_retorno")
        except Exception as exc:
            ultimo_exc = exc
            text = _texto_erro(exc)

            if "duplicate" in text or "unique" in text or "23505" in text:
                encontrado = _rebusca_ok("duplicado_rebusca")
                if encontrado:
                    return encontrado

            # Remove coluna inexistente e tenta de novo uma vez
            removida = False
            for col in list(payload.keys()):
                if erro_coluna_ausente(exc, col) and col not in ("telefone", "nome"):
                    payload.pop(col, None)
                    if col == "celular":
                        _SCHEMA_FLAGS["clientes_celular"] = False
                    removida = True
            if removida:
                try:
                    resultado = _insert(payload, "criar_cliente_sem_coluna")
                    if resultado.data:
                        row = resultado.data[0]
                        log_seguro(
                            "cliente_criacao_ok",
                            id_prefix=str(row.get("id") or "")[:8],
                            via="insert_sem_coluna",
                        )
                        return row
                    encontrado = _rebusca_ok("rebusca_sem_coluna")
                    if encontrado:
                        return encontrado
                except Exception as exc2:
                    ultimo_exc = exc2
                    if "duplicate" in _texto_erro(exc2) or "23505" in _texto_erro(exc2):
                        encontrado = _rebusca_ok("duplicado_rebusca")
                        if encontrado:
                            return encontrado

            # NOT NULL em celular: só então inclui celular (schema exige)
            if "celular" not in payload and _null_violation_coluna(exc, "celular"):
                payload["celular"] = tel
                _SCHEMA_FLAGS["clientes_celular"] = True
                try:
                    resultado = _insert(payload, "criar_cliente_com_celular")
                    if resultado.data:
                        row = resultado.data[0]
                        log_seguro(
                            "cliente_criacao_ok",
                            id_prefix=str(row.get("id") or "")[:8],
                            via="insert_com_celular",
                        )
                        return row
                    encontrado = _rebusca_ok("rebusca_com_celular")
                    if encontrado:
                        return encontrado
                except Exception as exc3:
                    ultimo_exc = exc3
                    if "duplicate" in _texto_erro(exc3) or "23505" in _texto_erro(exc3):
                        encontrado = _rebusca_ok("duplicado_rebusca")
                        if encontrado:
                            return encontrado

            # Não repetir heurística ampla com "null" genérico (causava PGRST204 em celular)
            break

    if ultimo_exc is not None:
        registrar_erro_cliente("criar_cliente", ultimo_exc)
        raise ultimo_exc
    registrar_erro_cliente(
        "criar_cliente",
        codigo="DESCONHECIDO",
        tipo="CRIAR_FALHOU",
        resumo="falha ao criar cliente",
    )
    raise RuntimeError("criar_cliente_falhou")


def atualizar_cliente(cliente_id, **campos):
    if not campos:
        return None

    try:
        resultado = (
            supabase.table(TABELA_CLIENTES)
            .update(campos)
            .eq("id", cliente_id)
            .execute()
        )
        return resultado
    except Exception as exc:
        from services.webhook_guard import log_seguro

        log_seguro(
            "cliente_update_erro",
            id_prefix=str(cliente_id)[:8],
            erro=type(exc).__name__,
            detalhe=str(exc)[:120],
            campos=",".join(sorted(campos.keys())),
        )
        raise


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

def _mensagens_do_historico_json(historico_raw) -> list[dict]:
    """Extrai lista de mensagens (sem sentinel de contexto) do JSON clientes.historico."""
    if isinstance(historico_raw, dict):
        msgs = historico_raw.get("mensagens") or historico_raw.get("messages") or []
        if not isinstance(msgs, list):
            msgs = []
        return [
            m
            for m in msgs
            if isinstance(m, dict) and m.get("role") != _HIST_CTX_ROLE
        ]
    if isinstance(historico_raw, list):
        return [
            m
            for m in historico_raw
            if isinstance(m, dict) and m.get("role") != _HIST_CTX_ROLE
        ]
    return []


def _salvar_mensagem_no_historico_cliente(
    cliente_id: str,
    tipo: str,
    mensagem: str,
    message_id: str | None = None,
) -> dict:
    """Grava mensagem no JSON clientes.historico (modo thread / sem tabela de msgs)."""
    from datetime import datetime, timezone

    atual = (
        supabase.table(TABELA_CLIENTES)
        .select("historico")
        .eq("id", cliente_id)
        .limit(1)
        .execute()
    )
    hist_raw = (atual.data[0].get("historico") if atual.data else None) or []
    msgs = _mensagens_do_historico_json(hist_raw)
    ctx = extrair_contexto_do_historico_json(hist_raw)

    mid = (message_id or "").strip()
    # Idempotência: message_id já no histórico
    if mid:
        for m in msgs:
            if str(m.get("message_id") or "") == mid:
                return {"ok": True, "duplicado": True, "modo": "historico_json"}

    entry = {
        "role": "user" if tipo == "cliente" else "assistant",
        "content": mensagem,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if mid:
        entry["message_id"] = mid
    msgs.append(entry)

    # Limita tamanho do JSON (últimas 80 mensagens)
    if len(msgs) > 80:
        msgs = msgs[-80:]

    payload = anexar_contexto_no_historico_json(msgs, ctx) if (
        ctx and _SCHEMA_FLAGS.get("contexto_venda") is not True
    ) else msgs

    # Se há coluna contexto_venda, não precisa do sentinel
    if _SCHEMA_FLAGS.get("contexto_venda") is True:
        payload = msgs

    supabase.table(TABELA_CLIENTES).update({"historico": payload}).eq(
        "id", cliente_id
    ).execute()
    return {"ok": True, "duplicado": False, "modo": "historico_json"}


def atualizar_thread_conversa(
    telefone: str,
    nome: str,
    mensagem: str,
    *,
    message_id: str | None = None,
    inbound: bool = True,
) -> bool:
    """Atualiza thread PulseDesk em conversas (colunas existentes apenas). Opcional."""
    from datetime import datetime, timezone

    if not conversas_e_thread():
        return True
    tel = normalizar_telefone(telefone)
    if not tel or not mensagem:
        return False
    agora = datetime.now(timezone.utc).isoformat()
    try:
        # Busca thread por telefone
        row = None
        for campo in ("contact_phone", "external_thread_id"):
            try:
                r = (
                    supabase.table(TABELA_HISTORICO)
                    .select("id,unread_count")
                    .eq(campo, tel)
                    .limit(1)
                    .execute()
                )
                if r.data:
                    row = r.data[0]
                    break
            except Exception as exc:
                if erro_coluna_ausente(exc, campo):
                    continue
                raise

        patch = {
            "last_message": (mensagem or "")[:500],
            "last_message_at": agora,
            "status": "active",
            "updated_at": agora,
        }
        # Só inclui colunas seguras
        if nome:
            patch["customer_name"] = nome
        mid = (message_id or "").strip()
        if mid and _SCHEMA_FLAGS.get("message_id") is not False:
            patch["message_id"] = mid

        if row:
            unread = int(row.get("unread_count") or 0)
            if inbound:
                unread += 1
            patch["unread_count"] = unread
            try:
                supabase.table(TABELA_HISTORICO).update(patch).eq(
                    "id", row["id"]
                ).execute()
            except Exception as exc:
                # Remove message_id se coluna sumiu
                if "message_id" in patch and erro_coluna_ausente(exc, "message_id"):
                    _SCHEMA_FLAGS["message_id"] = False
                    patch.pop("message_id", None)
                    supabase.table(TABELA_HISTORICO).update(patch).eq(
                        "id", row["id"]
                    ).execute()
                else:
                    raise
            return True

        # Cria thread mínima
        insert = {
            "contact_phone": tel,
            "external_thread_id": tel,
            "customer_name": nome or f"WhatsApp {tel[-4:]}",
            "channel": "whatsapp",
            "status": "active",
            "last_message": (mensagem or "")[:500],
            "last_message_at": agora,
            "unread_count": 1 if inbound else 0,
        }
        if mid and _SCHEMA_FLAGS.get("message_id") is not False:
            insert["message_id"] = mid
        # canal_id opcional
        canal = os.getenv("PULSEDESK_AGENT_CANAL_ID", "").strip()
        if canal:
            insert["canal_id"] = canal
        try:
            supabase.table(TABELA_HISTORICO).insert(insert).execute()
        except Exception as exc:
            # Remove campos opcionais que não existem
            for campo in ("message_id", "canal_id", "external_thread_id", "unread_count"):
                if campo in insert and erro_coluna_ausente(exc, campo):
                    insert.pop(campo, None)
                    if campo == "message_id":
                        _SCHEMA_FLAGS["message_id"] = False
            supabase.table(TABELA_HISTORICO).insert(insert).execute()
        return True
    except Exception as exc:
        from services.webhook_guard import log_seguro

        log_seguro(
            "chat_aviso_persistencia",
            etapa="atualizar_thread",
            erro=type(exc).__name__,
            detalhe=str(exc)[:120],
        )
        return False


def salvar_mensagem(
    cliente_id,
    tipo,
    mensagem,
    message_id: str | None = None,
    *,
    telefone: str = "",
    nome: str = "",
):
    """Persiste mensagem do turno.

    - Se conversas é thread PulseDesk: grava em clientes.historico (essencial).
    - Se conversas é tabela de mensagens legada: insert na tabela.
    """
    from services.webhook_guard import log_seguro

    mid = (message_id or "").strip()
    log_seguro(
        "salvar_mensagem_inicio",
        tipo=tipo,
        message_id=mid or "-",
        chars=len(mensagem or ""),
        modo="thread" if conversas_e_thread() else "mensagens",
    )

    # Modo thread: NÃO inserir cliente_id/tipo/mensagem em conversas
    if conversas_e_thread():
        try:
            result = _salvar_mensagem_no_historico_cliente(
                str(cliente_id), tipo, mensagem, mid or None
            )
            # Thread update é opcional — feito pelo caller se quiser
            return result
        except Exception as exc:
            log_seguro(
                "salvar_mensagem_erro",
                tipo=tipo,
                message_id=mid or "-",
                erro=type(exc).__name__,
                detalhe=str(exc)[:120],
                modo="historico_json",
            )
            raise

    # Modo legado: insert em tabela de mensagens
    payload = {
        "cliente_id": cliente_id,
        "tipo": tipo,
        "mensagem": mensagem,
    }
    if mid and _SCHEMA_FLAGS.get("message_id") is not False:
        payload["message_id"] = mid

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
        if mid and ("duplicate" in text or "unique" in text or "23505" in text):
            print("AVISO: message_id já existe — insert ignorado")
            return None
        if "message_id" in payload and erro_coluna_ausente(exc, "message_id"):
            _SCHEMA_FLAGS["message_id"] = False
            payload.pop("message_id", None)
            return (
                supabase.table(TABELA_HISTORICO)
                .insert(payload)
                .execute()
            )
        # Se insert falhou por schema de thread detectado tarde
        if erro_coluna_ausente(exc, "cliente_id") or erro_coluna_ausente(exc, "tipo"):
            _SCHEMA_FLAGS["conversas_thread"] = True
            return _salvar_mensagem_no_historico_cliente(
                str(cliente_id), tipo, mensagem, mid or None
            )
        raise


def mensagem_ja_existe(message_id: str) -> bool:
    """Idempotência: message_id na thread, no historico JSON ou na tabela de msgs."""
    mid = (message_id or "").strip()
    if not mid:
        return False

    # Modo thread: checa coluna message_id da thread e/ou historico dos clientes
    if conversas_e_thread():
        if _SCHEMA_FLAGS.get("message_id") is not False:
            try:
                r = (
                    supabase.table(TABELA_HISTORICO)
                    .select("id")
                    .eq("message_id", mid)
                    .limit(1)
                    .execute()
                )
                _SCHEMA_FLAGS["message_id"] = True
                if r.data:
                    return True
            except Exception as exc:
                if erro_coluna_ausente(exc, "message_id") or "pgrst" in _texto_erro(exc):
                    _SCHEMA_FLAGS["message_id"] = False
                else:
                    raise
        # Fallback: varre historico recente (limitado) — opcional, não bloqueia
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
        if erro_coluna_ausente(exc, "message_id") or "pgrst" in _texto_erro(exc):
            _SCHEMA_FLAGS["message_id"] = False
            print("AVISO: checagem message_id indisponível:", type(exc).__name__)
            return False
        raise


def buscar_historico(cliente_id, limit: int | None = None):
    """Retorna lista [{tipo, mensagem, criado_em}] para o fluxo do agente."""
    # Modo thread / historico JSON em clientes
    if conversas_e_thread():
        try:
            r = (
                supabase.table(TABELA_CLIENTES)
                .select("historico")
                .eq("id", cliente_id)
                .limit(1)
                .execute()
            )
            hist_raw = (r.data[0].get("historico") if r.data else None) or []
            msgs = _mensagens_do_historico_json(hist_raw)
            out = []
            for m in msgs:
                role = (m.get("role") or "").lower()
                tipo = "cliente" if role in ("user", "cliente") else "ia"
                out.append({
                    "tipo": tipo,
                    "mensagem": m.get("content") or m.get("mensagem") or "",
                    "criado_em": m.get("timestamp") or m.get("criado_em") or "",
                    "message_id": m.get("message_id") or "",
                })
            if limit is not None and limit > 0 and len(out) > limit:
                return out[-limit:]
            return out
        except Exception as exc:
            print("AVISO buscar_historico (json):", type(exc).__name__, str(exc)[:120])
            return []

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
    """Sincroniza clientes.historico.

    Em modo thread o histórico já é gravado por salvar_mensagem — no-op seguro.
    Em modo legado, reconstrói a partir da tabela de mensagens.
    """
    if conversas_e_thread():
        # Já persistido em clientes.historico; opcionalmente anexa contexto
        if contexto_extra and _SCHEMA_FLAGS.get("contexto_venda") is not True:
            try:
                atual = (
                    supabase.table(TABELA_CLIENTES)
                    .select("historico")
                    .eq("id", cliente_id)
                    .limit(1)
                    .execute()
                )
                hist_raw = (atual.data[0].get("historico") if atual.data else None) or []
                msgs = _mensagens_do_historico_json(hist_raw)
                novo = anexar_contexto_no_historico_json(msgs, contexto_extra)
                supabase.table(TABELA_CLIENTES).update({"historico": novo}).eq(
                    "id", cliente_id
                ).execute()
            except Exception:
                pass
        return {"ok": True, "modo": "noop_thread"}

    historico = buscar_historico(cliente_id)

    historico_json = []
    for msg in historico:
        historico_json.append({
            "role": "user" if msg["tipo"] == "cliente" else "assistant",
            "content": msg["mensagem"],
            "timestamp": str(msg.get("criado_em") or ""),
        })

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
