"""Orquestração de cobrança Pix Mercado Pago + persistência Supabase.

Valida produto/preço/estoque no backend. Não confia em valor vindo do cliente/LLM.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from services import mercadopago_service as mp
from services import turno_context
from services.env_loader import carregar_env
from services.product_service import buscar_por_intencao, buscar_produto_por_nome

carregar_env()

TABELA_PAGAMENTOS = "pagamentos_pix"


def _log(evento: str, **campos: Any) -> None:
    try:
        from services.webhook_guard import log_seguro

        bloquear = {"cpf", "email", "pix_copia_cola", "qr_code_base64", "token", "access_token"}
        safe = {k: ("***" if k in bloquear and v else v) for k, v in campos.items()}
        log_seguro(evento, **safe)
    except Exception:
        pass


def _mascarar_email(email: str | None) -> str | None:
    e = (email or "").strip()
    if not e or "@" not in e:
        return None
    user, _, dom = e.partition("@")
    if len(user) <= 2:
        return f"*@{dom}"
    return f"{user[0]}***{user[-1]}@{dom}"


def _mascarar_cpf(cpf: str | None) -> str | None:
    d = re.sub(r"\D", "", cpf or "")
    if len(d) < 4:
        return None
    return f"***{d[-4:]}"


def _resposta_publica(dados: dict[str, Any]) -> dict[str, Any]:
    """Contrato seguro para agente/API — sem CPF/e-mail completos."""
    return {
        "ok": bool(dados.get("ok")),
        "provider": "mercadopago",
        "payment_id": dados.get("payment_id"),
        "external_reference": dados.get("external_reference") or dados.get("pedido_id"),
        "status": dados.get("status_interno") or dados.get("status") or "pending",
        "status_mp": dados.get("status"),
        "valor": dados.get("valor"),
        "pix_copia_cola": dados.get("pix_copia_cola"),
        "qr_code_base64": dados.get("qr_code_base64"),
        "ticket_url": dados.get("ticket_url"),
        "expira_em": dados.get("expira_em"),
        "pedido_id": dados.get("pedido_id"),
        "produto": dados.get("produto_nome"),
        "quantidade": dados.get("quantidade"),
        "mensagem_cliente": dados.get("mensagem_cliente"),
        "error": dados.get("error"),
        "enviar_sem_alterar": True,
    }


def _supabase():
    from services.supabase_service import supabase

    return supabase


def buscar_pagamento_por_pedido(pedido_id: str) -> dict[str, Any] | None:
    pid = str(pedido_id or "").strip()
    if not pid:
        return None
    try:
        res = (
            _supabase()
            .table(TABELA_PAGAMENTOS)
            .select("*")
            .eq("external_reference", pid)
            .order("criado_em", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:
        _log("pix_busca_pedido_falhou", erro=type(exc).__name__)
        return None


def buscar_pagamento_por_provider_id(payment_id: str) -> dict[str, Any] | None:
    pid = str(payment_id or "").strip()
    if not pid:
        return None
    try:
        res = (
            _supabase()
            .table(TABELA_PAGAMENTOS)
            .select("*")
            .eq("provider_payment_id", pid)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as exc:
        _log("pix_busca_payment_falhou", erro=type(exc).__name__)
        return None


def _upsert_pagamento(registro: dict[str, Any]) -> bool:
    try:
        _supabase().table(TABELA_PAGAMENTOS).upsert(
            registro,
            on_conflict="idempotency_key",
        ).execute()
        return True
    except Exception as exc:
        _log("pix_persist_falhou", erro=type(exc).__name__)
        return False


def _atualizar_status(
    *,
    provider_payment_id: str,
    status_interno: str,
    status_mp: str,
    pago_em: str | None = None,
) -> bool:
    try:
        payload: dict[str, Any] = {
            "status": status_interno,
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
            "provider_status": status_mp,
        }
        if pago_em:
            payload["pago_em"] = pago_em
        _supabase().table(TABELA_PAGAMENTOS).update(payload).eq(
            "provider_payment_id", provider_payment_id
        ).execute()
        return True
    except Exception as exc:
        _log("pix_update_status_falhou", erro=type(exc).__name__)
        return False


def _resolver_produto(produto: str, quantidade: int) -> dict[str, Any]:
    nome = (produto or "").strip()
    if not nome:
        return {"ok": False, "error": "produto_obrigatorio"}

    r = buscar_produto_por_nome(nome)
    if not r.get("found") or not (r.get("products") or []):
        r = buscar_por_intencao(
            mensagem=nome,
            intent="BUSCA_PRODUTO",
            product_query=nome,
            limite=3,
        )
    produtos = r.get("products") or []
    if not produtos:
        return {"ok": False, "error": "produto_nao_encontrado"}

    p = produtos[0]
    preco = p.get("price")
    if preco is None:
        preco = p.get("preco")
    if preco is None:
        return {"ok": False, "error": "preco_nao_confirmado", "produto": p.get("name")}

    try:
        preco_f = float(preco)
    except (TypeError, ValueError):
        return {"ok": False, "error": "preco_nao_confirmado"}
    if preco_f <= 0:
        return {"ok": False, "error": "preco_nao_confirmado"}

    estoque = p.get("stock_quantity")
    if estoque is None:
        estoque = p.get("estoque")
    stock_confirmed = bool(p.get("stock_confirmed"))
    if estoque is not None:
        try:
            if float(estoque) < quantidade:
                return {"ok": False, "error": "estoque_insuficiente", "produto": p.get("name")}
        except (TypeError, ValueError):
            pass
    elif not stock_confirmed and estoque is None:
        # Sem estoque confirmado — não gera Pix
        return {"ok": False, "error": "estoque_nao_confirmado", "produto": p.get("name")}

    return {
        "ok": True,
        "produto": p,
        "nome": p.get("name") or p.get("nome"),
        "preco_unitario": preco_f,
        "total": round(preco_f * quantidade, 2),
    }


def criar_cobranca_pix(
    *,
    produto: str,
    quantidade: int = 1,
    telefone: str | None = None,
    email: str | None = None,
    nome_pagador: str | None = None,
    cpf: str | None = None,
    consentimento: bool = False,
    pedido_id: str | None = None,
    cliente_id: str | None = None,
    dry_run: bool | None = None,
    persistir: bool | None = None,
) -> dict[str, Any]:
    """Cria cobrança Pix após validações. Valor sempre do catálogo."""
    dry = turno_context.get_dry_run() if dry_run is None else bool(dry_run)
    pers = turno_context.get_persistir() if persistir is None else bool(persistir)

    if not consentimento:
        return _resposta_publica({"ok": False, "error": "consentimento_necessario"})

    try:
        qtd = int(quantidade)
    except (TypeError, ValueError):
        return _resposta_publica({"ok": False, "error": "quantidade_invalida"})
    if qtd < 1 or qtd > 99:
        return _resposta_publica({"ok": False, "error": "quantidade_invalida"})

    if dry:
        _log("pix_bloqueado_dry_run")
        return _resposta_publica({"ok": False, "error": "dry_run_sem_cobranca"})
    if not pers:
        _log("pix_bloqueado_sem_persistir")
        return _resposta_publica({"ok": False, "error": "persistir_false_sem_cobranca"})

    resolved = _resolver_produto(produto, qtd)
    if not resolved.get("ok"):
        return _resposta_publica({"ok": False, "error": resolved.get("error"), "produto_nome": resolved.get("produto")})

    pid = (pedido_id or "").strip() or mp.novo_pedido_interno_id()
    existente = buscar_pagamento_por_pedido(pid)
    if existente and existente.get("provider_payment_id"):
        st = str(existente.get("status") or "")
        if st in ("aguardando_pagamento", "pago"):
            _log("pix_reuso_idempotente", pedido_id=pid[:40], status=st)
            return _resposta_publica(
                {
                    "ok": True,
                    "payment_id": existente.get("provider_payment_id"),
                    "pedido_id": pid,
                    "external_reference": existente.get("external_reference") or pid,
                    "status": existente.get("provider_status") or "pending",
                    "status_interno": st,
                    "valor": existente.get("valor"),
                    "pix_copia_cola": existente.get("pix_copia_cola"),
                    "qr_code_base64": existente.get("qr_code_base64"),
                    "ticket_url": existente.get("ticket_url"),
                    "expira_em": existente.get("expira_em"),
                    "produto_nome": resolved["nome"],
                    "quantidade": qtd,
                    "mensagem_cliente": (
                        f"Certo, o Pix de R$ {float(existente.get('valor') or 0):.2f} "
                        f"já está disponível (mesmo pedido)."
                    ).replace(".", ","),
                }
            )

    email_ok = (email or "").strip()
    if not email_ok:
        # E-mail sintético mínimo exigido pela API — não logar
        digits = re.sub(r"\D", "", telefone or "") or "00000000000"
        email_ok = f"cliente{digits[-8:]}@pagamentos.xnamai.local"

    nome = (nome_pagador or "Cliente").strip()[:60]
    partes = nome.split(None, 1)
    first = partes[0]
    last = partes[1] if len(partes) > 1 else None

    idem = mp.gerar_idempotency_key(pid)
    criado = mp.criar_pagamento_pix(
        valor=resolved["total"],
        description=f"xNamai — {resolved['nome']} x{qtd}",
        external_reference=pid,
        idempotency_key=idem,
        payer_email=email_ok,
        payer_first_name=first,
        payer_last_name=last,
        payer_cpf=cpf,
    )
    if not criado.get("ok"):
        return _resposta_publica({"ok": False, "error": criado.get("error") or "mp_falha"})

    status_interno = mp.mapear_status_interno(str(criado.get("status") or "pending"))
    agora = datetime.now(timezone.utc).isoformat()
    registro = {
        "id": str(uuid.uuid4()),
        "pedido_id": pid,
        "cliente_id": (cliente_id or None),
        "provider": "mercadopago",
        "provider_payment_id": criado.get("payment_id"),
        "external_reference": pid,
        "idempotency_key": idem,
        "valor": criado.get("valor") or resolved["total"],
        "status": status_interno,
        "provider_status": criado.get("status"),
        "pix_copia_cola": criado.get("pix_copia_cola"),
        "qr_code_base64": criado.get("qr_code_base64"),
        "ticket_url": criado.get("ticket_url"),
        "expira_em": criado.get("expira_em"),
        "criado_em": agora,
        "atualizado_em": agora,
        "pago_em": None,
        "produto_nome": resolved["nome"],
        "quantidade": qtd,
        "telefone_mascarado": (re.sub(r"\D", "", telefone or "")[-4:] if telefone else None),
        "email_mascarado": _mascarar_email(email_ok),
        "cpf_mascarado": _mascarar_cpf(cpf),
    }
    _upsert_pagamento(registro)

    valor = float(criado.get("valor") or resolved["total"])
    msg = (
        f"Certo, gerei o Pix de R$ {valor:.2f}. "
        f"O código expira em {criado.get('expira_em') or 'breve'}."
    ).replace(".", ",")

    return _resposta_publica(
        {
            "ok": True,
            "payment_id": criado.get("payment_id"),
            "pedido_id": pid,
            "external_reference": pid,
            "status": criado.get("status") or "pending",
            "status_interno": status_interno,
            "valor": valor,
            "pix_copia_cola": criado.get("pix_copia_cola"),
            "qr_code_base64": criado.get("qr_code_base64"),
            "ticket_url": criado.get("ticket_url"),
            "expira_em": criado.get("expira_em"),
            "produto_nome": resolved["nome"],
            "quantidade": qtd,
            "mensagem_cliente": msg,
        }
    )


def processar_notificacao_pagamento(payment_id: str) -> dict[str, Any]:
    """Consulta API MP e atualiza status de forma idempotente."""
    pid = str(payment_id or "").strip()
    if not pid:
        return {"ok": False, "error": "payment_id_ausente"}

    consultado = mp.consultar_pagamento(pid)
    if not consultado.get("ok"):
        return {"ok": False, "error": consultado.get("error") or "consulta_falhou"}

    status_mp = str(consultado.get("status") or "")
    status_interno = mp.mapear_status_interno(status_mp)
    existente = buscar_pagamento_por_provider_id(pid)

    if existente and str(existente.get("status") or "") == status_interno:
        _log("pix_webhook_idempotente", payment_id=pid[:40], status=status_interno)
        return {
            "ok": True,
            "updated": False,
            "status": status_interno,
            "payment_id": pid,
            "external_reference": existente.get("external_reference"),
        }

    pago_em = None
    if status_interno == "pago":
        pago_em = consultado.get("date_approved") or datetime.now(timezone.utc).isoformat()

    if existente:
        _atualizar_status(
            provider_payment_id=pid,
            status_interno=status_interno,
            status_mp=status_mp,
            pago_em=pago_em,
        )
    else:
        # Webhook de pagamento ainda não persistido localmente
        agora = datetime.now(timezone.utc).isoformat()
        _upsert_pagamento(
            {
                "id": str(uuid.uuid4()),
                "pedido_id": consultado.get("external_reference") or pid,
                "provider": "mercadopago",
                "provider_payment_id": pid,
                "external_reference": consultado.get("external_reference") or pid,
                "idempotency_key": mp.gerar_idempotency_key(
                    consultado.get("external_reference") or pid
                ),
                "valor": consultado.get("valor"),
                "status": status_interno,
                "provider_status": status_mp,
                "pix_copia_cola": consultado.get("pix_copia_cola"),
                "qr_code_base64": consultado.get("qr_code_base64"),
                "ticket_url": consultado.get("ticket_url"),
                "expira_em": consultado.get("expira_em"),
                "criado_em": agora,
                "atualizado_em": agora,
                "pago_em": pago_em,
            }
        )

    _log(
        "pix_status_atualizado",
        payment_id=pid[:40],
        status=status_interno,
        status_mp=status_mp,
        marcado_pago=(status_interno == "pago"),
    )
    return {
        "ok": True,
        "updated": True,
        "status": status_interno,
        "status_mp": status_mp,
        "payment_id": pid,
        "external_reference": consultado.get("external_reference"),
        "pago": status_interno == "pago",
    }


def comprovante_cliente_nao_confirma_pagamento(_texto: str | None = None) -> dict[str, Any]:
    """Regra explícita: print/comprovante do cliente NÃO marca pago."""
    return {
        "ok": True,
        "pago": False,
        "motivo": "comprovante_cliente_nao_confirma",
        "mensagem": (
            "Recebi o comprovante. Vou confirmar o pagamento pelo sistema; "
            "assim que o Mercado Pago confirmar, te aviso."
        ),
    }
