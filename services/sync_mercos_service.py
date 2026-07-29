"""Sincronização Mercos → Supabase (produtos) com anti-duplicidade.

Schema real (public.produtos):
  - mercos_id BIGINT NOT NULL + UNIQUE (produtos_mercos_id_key)
  - codigo TEXT NULL

Prioridade: mercos_id → codigo (nunca nome).
Dry-run: comparação 100% em memória após 1 carga paginada do Supabase.
Escrita real: upsert em lotes on_conflict=mercos_id (exceto 1ª associação por codigo).
"""

from __future__ import annotations

import os
import time
from typing import Any

from services.env_loader import carregar_env
from services.mercos_service import (
    buscar_produtos_mercos_detalhado,
    extrair_imagem_mercos,
    mercos_configurado,
    normalizar_produto,
)
from services.supabase_service import (
    carregar_indice_produtos_locais,
    invalidar_cache_produtos,
    sincronizar_produto_mercos_seguro,
    upsert_produtos_mercos_em_lote,
)

carregar_env()


def _log(evento: str, **campos: Any) -> None:
    try:
        from services.webhook_guard import log_seguro

        bloquear = {
            "token",
            "key",
            "api_key",
            "authorization",
            "company_token",
            "application_token",
        }
        safe = {k: v for k, v in campos.items() if k.lower() not in bloquear}
        log_seguro(evento, **safe)
    except Exception:
        pass


def _parse_mercos_id(bruto: Any) -> int | None:
    if bruto is None or bruto == "":
        return None
    try:
        return int(bruto)
    except (TypeError, ValueError):
        return None


def _produto_para_supabase(produto_mercos: dict) -> dict:
    """Mapeia para o schema real (preco_tabela/saldo_estoque + mercos_id)."""
    dados = normalizar_produto(produto_mercos)
    imagem = extrair_imagem_mercos(produto_mercos)
    mercos_id = _parse_mercos_id(produto_mercos.get("id"))

    registro = {
        "mercos_id": mercos_id,
        "nome": dados["nome"],
        "codigo": str(dados.get("codigo") or produto_mercos.get("codigo") or "").strip(),
        "unidade": produto_mercos.get("unidade"),
        "descricao": dados.get("descricao")
        or produto_mercos.get("observacoes")
        or "",
        "preco_tabela": dados.get("preco")
        if dados.get("preco") is not None
        else produto_mercos.get("preco_tabela") or 0,
        "preco_minimo": produto_mercos.get("preco_minimo") or 0,
        "saldo_estoque": dados.get("estoque")
        if dados.get("estoque") is not None
        else produto_mercos.get("saldo_estoque") or 0,
        "ativo": produto_mercos.get("ativo", True),
        "ultima_alteracao": produto_mercos.get("ultima_alteracao"),
    }
    _ = imagem
    return registro


def _progresso_a_cada() -> int:
    try:
        n = int(os.getenv("SYNC_PRODUTOS_PROGRESSO", "500"))
    except ValueError:
        n = 500
    return max(100, n)


def _batch_size() -> int:
    try:
        n = int(os.getenv("SYNC_PRODUTOS_BATCH_SIZE", "200"))
    except ValueError:
        n = 200
    return max(1, min(n, 500))


def _resumo_vazio() -> dict[str, Any]:
    return {
        "chamadas_mercos": 0,
        "total_informado_mercos": None,
        "unicos_recebidos": 0,
        "excluidos": 0,
        "inativos": 0,
        "ativos_processados": 0,
        "recebidos": 0,
        "ja_vinculados": 0,
        "vinculados_por_codigo": 0,
        "novos": 0,
        "atualizados": 0,
        "ambiguos": 0,
        "ignorados": 0,
        "erros": 0,
        "detalhe_erros": [],
        "detalhe_ambiguos": [],
        "detalhe_ignorados": [],
        "dry_run": False,
        "indice_local_total": 0,
        "indice_local_paginas": 0,
    }


def sincronizar_produtos_mercos(*, dry_run: bool = False) -> dict:
    """Sincroniza produtos Mercos → public.produtos.

    dry_run=True: carrega índice local 1x, compara em memória, zero escritas.
    """
    if not mercos_configurado():
        raise ValueError("Mercos não configurada no .env")

    detalhe = buscar_produtos_mercos_detalhado(usar_cache=False)
    produtos_mercos = list(detalhe.get("produtos") or [])

    resumo = _resumo_vazio()
    resumo["dry_run"] = bool(dry_run)
    resumo["chamadas_mercos"] = int(detalhe.get("chamadas_mercos") or 0)
    resumo["total_informado_mercos"] = detalhe.get("total_informado_mercos")
    resumo["unicos_recebidos"] = int(detalhe.get("unicos_recebidos") or 0)
    resumo["excluidos"] = int(detalhe.get("excluidos") or 0)
    resumo["inativos"] = int(detalhe.get("inativos") or 0)
    resumo["ativos_processados"] = len(produtos_mercos)
    resumo["recebidos"] = len(produtos_mercos)

    _log(
        "sync_produtos_inicio",
        recebidos=resumo["recebidos"],
        dry_run=bool(dry_run),
        total_informado_mercos=resumo["total_informado_mercos"],
        unicos_recebidos=resumo["unicos_recebidos"],
    )

    try:
        indice = carregar_indice_produtos_locais(page_size=1000)
    except Exception as exc:
        nome = type(exc).__name__
        msg = str(exc)
        if "Timeout" in nome or "timeout" in msg.lower():
            raise ValueError(
                "Falha ao carregar produtos do Supabase (timeout). "
                "Dry-run/sync precisa de uma carga única paginada, não de "
                f"consultas por item. Detalhe={nome}"
            ) from exc
        raise

    resumo["indice_local_total"] = int(indice.get("total_carregados") or 0)
    resumo["indice_local_paginas"] = int(indice.get("paginas") or 0)

    progresso = _progresso_a_cada()
    lote_upsert: list[dict] = []
    processados = 0

    for produto in produtos_mercos:
        processados += 1
        try:
            registro = _produto_para_supabase(produto)
            if not registro.get("nome"):
                resumo["ignorados"] += 1
                # sem_nome: só conta (resumo); detalhe só se LOG_DETALHADO
                if os.getenv("SYNC_PRODUTOS_LOG_DETALHADO", "").strip().lower() in (
                    "1",
                    "true",
                    "sim",
                    "yes",
                ):
                    resumo["detalhe_ignorados"].append(
                        {
                            "motivo": "sem_nome",
                            "mercos_id": registro.get("mercos_id"),
                            "codigo": registro.get("codigo") or "",
                        }
                    )
                continue

            out = sincronizar_produto_mercos_seguro(
                registro,
                dry_run=dry_run,
                log_item=False,
                indice=indice,
                defer_upsert=not dry_run,
            )
            acao = str(out.get("acao") or "")
            match = str(out.get("match") or "")

            if acao == "ignorado":
                resumo["ignorados"] += 1
            elif acao == "ambiguo":
                resumo["ambiguos"] += 1
                resumo["detalhe_ambiguos"].append(
                    {
                        "motivo": out.get("motivo") or "ambiguo",
                        "mercos_id": registro.get("mercos_id"),
                        "codigo": registro.get("codigo") or "",
                        "candidatos": out.get("candidatos") or [],
                    }
                )
            elif acao == "criado":
                resumo["novos"] += 1
                if out.get("defer") and out.get("campos"):
                    lote_upsert.append(out["campos"])
            elif acao == "atualizado":
                resumo["atualizados"] += 1
                if match == "mercos_id":
                    resumo["ja_vinculados"] += 1
                    if out.get("defer") and out.get("campos"):
                        lote_upsert.append(out["campos"])
                elif match == "codigo":
                    resumo["vinculados_por_codigo"] += 1
                else:
                    resumo["ja_vinculados"] += 1
            elif acao == "dry_run_criaria":
                resumo["novos"] += 1
            elif acao == "dry_run_atualizaria":
                resumo["atualizados"] += 1
                if match == "mercos_id":
                    resumo["ja_vinculados"] += 1
                elif match == "codigo":
                    resumo["vinculados_por_codigo"] += 1

        except Exception as exc:
            resumo["erros"] += 1
            mid = produto.get("id")
            nome_err = type(exc).__name__
            if "Timeout" in nome_err or "timeout" in str(exc).lower():
                nome_err = f"ReadTimeout({nome_err})"
            resumo["detalhe_erros"].append(
                {
                    "mercos_id": mid if mid is not None else None,
                    "codigo": str(produto.get("codigo") or "")[:40],
                    "erro": nome_err,
                }
            )
            _log(
                "sync_produto_erro",
                mercos_id=str(mid)[:40] if mid is not None else "-",
                codigo=str(produto.get("codigo") or "")[:40],
                erro=nome_err,
            )

        if processados % progresso == 0:
            print(
                f"sync_produtos: progresso={processados}/{resumo['ativos_processados']} "
                f"novos={resumo['novos']} atualizados={resumo['atualizados']} "
                f"ambiguos={resumo['ambiguos']} erros={resumo['erros']}",
                flush=True,
            )

    if not dry_run and lote_upsert:
        try:
            upsert_produtos_mercos_em_lote(lote_upsert, batch_size=_batch_size())
        except Exception as exc:
            resumo["erros"] += 1
            _log(
                "sync_produtos_upsert_lote_erro",
                erro=type(exc).__name__,
                lote=len(lote_upsert),
            )
            raise

    if not dry_run:
        try:
            invalidar_cache_produtos()
        except Exception:
            pass

    _log(
        "sync_produtos_fim",
        dry_run=bool(dry_run),
        chamadas_mercos=resumo["chamadas_mercos"],
        total_informado_mercos=resumo["total_informado_mercos"],
        unicos_recebidos=resumo["unicos_recebidos"],
        excluidos=resumo["excluidos"],
        inativos=resumo["inativos"],
        ativos_processados=resumo["ativos_processados"],
        ja_vinculados=resumo["ja_vinculados"],
        vinculados_por_codigo=resumo["vinculados_por_codigo"],
        novos=resumo["novos"],
        atualizados=resumo["atualizados"],
        ambiguos=resumo["ambiguos"],
        erros=resumo["erros"],
    )

    # Detalhes só de ambíguos e erros (modo resumido)
    if resumo["detalhe_ambiguos"]:
        _log("sync_produtos_ambiguos", total=len(resumo["detalhe_ambiguos"]))
        for item in resumo["detalhe_ambiguos"][:50]:
            _log(
                "sync_produto_ambiguo_resumo",
                mercos_id=item.get("mercos_id"),
                codigo=item.get("codigo") or "-",
                motivo=item.get("motivo"),
            )
    if resumo["detalhe_erros"]:
        _log("sync_produtos_erros", total=len(resumo["detalhe_erros"]))
        for item in resumo["detalhe_erros"][:50]:
            _log(
                "sync_produto_erro_resumo",
                mercos_id=item.get("mercos_id"),
                codigo=item.get("codigo") or "-",
                erro=item.get("erro"),
            )

    resumo["total_mercos"] = resumo["total_informado_mercos"]
    resumo["criados"] = resumo["novos"]
    return resumo
