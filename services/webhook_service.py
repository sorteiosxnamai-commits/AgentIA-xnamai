import os
import time

from dotenv import load_dotenv

load_dotenv(override=True)

MAX_IDADE_SEGUNDOS = int(os.getenv("WEBHOOK_MAX_IDADE_MINUTOS", "15")) * 60
_IDS_PROCESSADOS: dict[str, float] = {}


def _limpar_ids_antigos() -> None:
    agora = time.time()
    expirados = [
        msg_id for msg_id, ts in _IDS_PROCESSADOS.items() if agora - ts > 86400
    ]
    for msg_id in expirados:
        _IDS_PROCESSADOS.pop(msg_id, None)


def extrair_id_mensagem(data: dict, evento: dict) -> str:
    for valor in (
        evento.get("id"),
        data.get("id"),
        data.get("referenceId"),
        data.get("messageId"),
    ):
        if valor:
            return str(valor).strip()
    return ""


def extrair_id_ultramsg(data: dict, evento: dict) -> str:
    return extrair_id_mensagem(data, evento)


def evento_deve_ser_ignorado(data: dict) -> tuple[bool, str]:
    event_type = (data.get("event_type") or "").strip().lower()
    if event_type and event_type not in ("message_received",):
        return True, f"event_type={event_type}"

    evento = data.get("data") or {}
    msg_id = extrair_id_ultramsg(data, evento)
    if msg_id:
        _limpar_ids_antigos()
        if msg_id in _IDS_PROCESSADOS:
            return True, f"duplicado id={msg_id}"

    timestamp = evento.get("time")
    if timestamp:
        try:
            idade = time.time() - float(timestamp)
            if idade > MAX_IDADE_SEGUNDOS:
                return True, f"mensagem antiga ({int(idade)}s)"
        except (TypeError, ValueError):
            pass

    return False, ""


def marcar_evento_processado(data: dict) -> None:
    evento = data.get("data") or {}
    msg_id = extrair_id_ultramsg(data, evento)
    if msg_id:
        _IDS_PROCESSADOS[msg_id] = time.time()
