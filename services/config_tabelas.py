"""Configuração explícita das tabelas do agente (sem fallback silencioso)."""

from __future__ import annotations

import os
import re

from dotenv import load_dotenv

load_dotenv(override=True)

# Preferência: CLIENTES_TABLE / CONVERSAS_TABLE (Etapa 2).
# AGENT_* permanece só como alias legado — se ambos existirem, CLIENTES_* vence.
CLIENTES_TABLE = (
    os.getenv("CLIENTES_TABLE")
    or os.getenv("AGENT_CLIENTES_TABLE")
    or "clientes"
).strip()

CONVERSAS_TABLE = (
    os.getenv("CONVERSAS_TABLE")
    or os.getenv("AGENT_HISTORICO_TABLE")
    or "conversas"
).strip()

_VALIDADO = False
_ERRO_VALIDACAO: str | None = None


def mascarar_telefone(telefone: str) -> str:
    digitos = re.sub(r"\D", "", telefone or "")
    if len(digitos) < 4:
        return "***"
    return f"***{digitos[-4:]}"


def normalizar_telefone(telefone: str) -> str:
    """Formato único: só dígitos (ex.: 5543999999999)."""
    return re.sub(r"\D", "", telefone or "").strip()


def tabelas_configuradas() -> dict[str, str]:
    return {
        "CLIENTES_TABLE": CLIENTES_TABLE,
        "CONVERSAS_TABLE": CONVERSAS_TABLE,
    }


def validar_tabelas_supabase(obrigatorio: bool = True) -> dict:
    """
    Valida se as tabelas configuradas existem no Supabase.
    Não troca silenciosamente para outra tabela.
    Tabela inexistente (PGRST205) = erro fatal se obrigatorio=True.
    Falha temporária de rede = aviso (não derruba o boot).
    """
    global _VALIDADO, _ERRO_VALIDACAO

    from database.supabase import supabase

    erros_tabela: list[str] = []
    avisos_rede: list[str] = []
    for nome, tabela in tabelas_configuradas().items():
        try:
            supabase.table(tabela).select("*").limit(1).execute()
        except Exception as exc:
            msg = str(exc)
            if "PGRST205" in msg or "does not exist" in msg.lower() or "schema cache" in msg.lower():
                erros_tabela.append(
                    f"{nome}={tabela!r} não existe no Supabase. "
                    f"Ajuste a variável de ambiente. Detalhe: {msg[:180]}"
                )
            else:
                avisos_rede.append(
                    f"Falha temporária ao validar {nome}={tabela!r}: "
                    f"{type(exc).__name__}: {msg[:180]}"
                )

    if avisos_rede:
        print("AVISO VALIDACAO TABELAS (rede/auth):", " | ".join(avisos_rede))

    if erros_tabela:
        _ERRO_VALIDACAO = " | ".join(erros_tabela)
        _VALIDADO = False
        print("ERRO CONFIG TABELAS:", _ERRO_VALIDACAO)
        if obrigatorio:
            raise RuntimeError(_ERRO_VALIDACAO)
        return {
            "ok": False,
            "erros": erros_tabela,
            "avisos": avisos_rede,
            **tabelas_configuradas(),
        }

    if avisos_rede:
        # Não confirma validado se não conseguiu checar
        _VALIDADO = False
        _ERRO_VALIDACAO = " | ".join(avisos_rede)
        return {
            "ok": False,
            "erros": [],
            "avisos": avisos_rede,
            **tabelas_configuradas(),
        }

    _VALIDADO = True
    _ERRO_VALIDACAO = None
    print(
        "TABELAS OK:",
        f"CLIENTES_TABLE={CLIENTES_TABLE}",
        f"CONVERSAS_TABLE={CONVERSAS_TABLE}",
    )
    return {"ok": True, "erros": [], "avisos": [], **tabelas_configuradas()}


def status_validacao() -> dict:
    return {
        "validado": _VALIDADO,
        "erro": _ERRO_VALIDACAO,
        **tabelas_configuradas(),
    }
