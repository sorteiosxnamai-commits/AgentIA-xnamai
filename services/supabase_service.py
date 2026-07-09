import os
import time

from dotenv import load_dotenv
from httpx import ConnectError, ReadError, TimeoutException

from postgrest.exceptions import APIError

from database.supabase import supabase

load_dotenv(override=True)


def _leads_indisponivel(erro: Exception) -> bool:
    if isinstance(erro, APIError):
        payload = erro.args[0] if erro.args else {}
        if isinstance(payload, dict):
            if payload.get("code") == "PGRST205":
                return True
            if "leads" in str(payload.get("message", "")).lower():
                return True
    return "leads" in str(erro).lower()

TABELA_CLIENTES = os.getenv("AGENT_CLIENTES_TABLE", "agent_clientes")
TABELA_HISTORICO = os.getenv("AGENT_HISTORICO_TABLE", "agent_historico")

_RETRIES = 3
_RETRY_ERRORS = (ReadError, ConnectError, TimeoutException, OSError)


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
    resultado = _executar(
        lambda: (
            supabase.table(TABELA_CLIENTES)
            .select("*")
            .eq("telefone", telefone)
            .execute()
        ),
        "buscar_cliente",
    )

    if resultado.data:
        return resultado.data[0]

    return None


def criar_cliente(telefone, nome=""):
    dados = {"telefone": telefone}
    if nome:
        dados["nome"] = nome

    resultado = _executar(
        lambda: supabase.table(TABELA_CLIENTES).insert(dados).execute(),
        "criar_cliente",
    )

    return resultado.data[0]


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

def salvar_mensagem(cliente_id, tipo, mensagem):
    resultado = (
        supabase.table(TABELA_HISTORICO)
        .insert({
            "cliente_id": cliente_id,
            "tipo": tipo,
            "mensagem": mensagem
        })
        .execute()
    )

    return resultado


def buscar_historico(cliente_id):
    resultado = (
        supabase.table(TABELA_HISTORICO)
        .select("*")
        .eq("cliente_id", cliente_id)
        .order("criado_em")
        .execute()
    )

    return resultado.data


def atualizar_historico_json(cliente_id):
    historico = buscar_historico(cliente_id)

    historico_json = []

    for msg in historico:
        historico_json.append({
            "role": "user" if msg["tipo"] == "cliente" else "assistant",
            "content": msg["mensagem"],
            "timestamp": str(msg.get("criado_em") or ""),
        })

    resultado = (
        supabase.table(TABELA_CLIENTES)
        .update({
            "historico": historico_json
        })
        .eq("id", cliente_id)
        .execute()
    )

    return resultado


# =========================
# PRODUTOS (ETL PulseDesk → Supabase)
# =========================

def buscar_produtos():
    resultado = (
        supabase.table("produtos")
        .select("*")
        .execute()
    )

    return [_normalizar_produto(row) for row in (resultado.data or [])]


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
