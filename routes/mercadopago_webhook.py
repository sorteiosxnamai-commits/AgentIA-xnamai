"""Webhook Mercado Pago — Pix.

Valida assinatura, consulta API oficial, atualiza status de forma idempotente.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Header, Request

from services import mercadopago_service as mp
from services import pagamento_pix_service as pix_svc

router = APIRouter(tags=["mercadopago"])


def _extrair_payment_id(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if isinstance(data, dict) and data.get("id") not in (None, ""):
        return str(data.get("id")).strip()
    # query-style / action notification
    for chave in ("id", "payment_id", "data.id"):
        if chave == "data.id":
            continue
        if payload.get(chave) not in (None, ""):
            # type=payment
            tipo = str(payload.get("type") or payload.get("topic") or "").lower()
            if tipo and tipo not in ("payment", "payments"):
                continue
            return str(payload.get(chave)).strip()
    # resource URL .../payments/123
    resource = str(payload.get("resource") or "")
    if "/payments/" in resource:
        return resource.rstrip("/").split("/")[-1].strip() or None
    return None


def _processar_em_background(payment_id: str) -> None:
    try:
        from services.webhook_guard import log_seguro

        out = pix_svc.processar_notificacao_pagamento(payment_id)
        log_seguro(
            "mp_webhook_processado",
            payment_id=str(payment_id)[:40],
            ok=bool(out.get("ok")),
            status=out.get("status") or "-",
            updated=bool(out.get("updated")),
        )
    except Exception as exc:
        try:
            from services.webhook_guard import log_seguro

            log_seguro("mp_webhook_erro", erro=type(exc).__name__)
        except Exception:
            pass


@router.get("/webhooks/mercadopago")
def mercadopago_webhook_info():
    return {
        "status": "ok",
        "canal": "mercadopago_pix",
        "mp_env": mp.mp_env(),
        "configurado": mp.mp_configurado(),
        "pix_enabled": mp.mp_pix_enabled(),
    }


@router.post("/webhooks/mercadopago")
async def mercadopago_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_signature: str | None = Header(default=None, alias="x-signature"),
    x_request_id: str | None = Header(default=None, alias="x-request-id"),
):
    """Recebe notificação MP → valida → consulta API → atualiza pedido."""
    from services.webhook_guard import log_seguro

    try:
        payload = await request.json()
    except Exception:
        # MP às vezes manda form; tenta query
        payload = dict(request.query_params)

    if not isinstance(payload, dict):
        payload = {}

    payment_id = _extrair_payment_id(payload)
    # data.id também pode vir só na query
    if not payment_id:
        payment_id = (request.query_params.get("data.id") or request.query_params.get("id") or "").strip() or None

    ok_sig, motivo_sig = mp.validar_assinatura_webhook(
        x_signature=x_signature,
        x_request_id=x_request_id,
        data_id=payment_id,
    )
    if not ok_sig:
        log_seguro("mp_webhook_assinatura_rejeitada", motivo=motivo_sig)
        return {"status": "erro", "motivo": motivo_sig}

    if not payment_id:
        log_seguro("mp_webhook_sem_payment_id")
        # 200 para evitar retry infinito em notificações sem id
        return {"status": "ignored", "motivo": "payment_id_ausente"}

    background_tasks.add_task(_processar_em_background, payment_id)
    return {"status": "accepted", "payment_id": payment_id}
