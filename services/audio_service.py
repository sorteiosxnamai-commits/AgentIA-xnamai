"""Download + transcrição de áudio WhatsApp (Whisper via OpenAI).

Isolado do agente: não vive em agents/vendas/agent.py.
Não faz TTS. Remove arquivos temporários após o uso.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

AUDIO_MAX_BYTES = int(os.getenv("AUDIO_MAX_BYTES", str(5 * 1024 * 1024)))
AUDIO_TIMEOUT_SEGUNDOS = float(os.getenv("AUDIO_DOWNLOAD_TIMEOUT", "25"))
AUDIO_TRANSCRIBE_MODEL = (os.getenv("OPENAI_TRANSCRIBE_MODEL") or "whisper-1").strip()
AUDIO_TIPOS_OK = {
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/aac",
    "application/octet-stream",
}


def _log(evento: str, **campos: Any) -> None:
    try:
        from services.webhook_guard import log_seguro

        log_seguro(evento, **campos)
    except Exception:
        print(f"EVT={evento}")


def _ext_de_url_ou_mime(url: str, content_type: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".ogg", ".mp3", ".m4a", ".wav", ".webm", ".aac", ".opus"):
        if path.endswith(ext):
            return ext
    ct = (content_type or "").split(";")[0].strip().lower()
    return {
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",
        "audio/aac": ".aac",
    }.get(ct, ".ogg")


def _url_segura_para_log(url: str) -> str:
    """Host + path sem query (tokens costumam ir na query)."""
    try:
        p = urlparse(url or "")
        return f"{p.scheme}://{p.netloc}{p.path}"[:120]
    except Exception:
        return "-"


def baixar_audio(url: str, *, token_query: str | None = None) -> tuple[bytes, str]:
    """Baixa áudio com timeout e limite de tamanho. Não loga token."""
    if not (url or "").strip():
        raise ValueError("audio_url_ausente")
    alvo = url.strip()
    if token_query and "token=" not in alvo.lower():
        sep = "&" if "?" in alvo else "?"
        alvo = f"{alvo}{sep}token={token_query}"

    with requests.get(alvo, timeout=AUDIO_TIMEOUT_SEGUNDOS, stream=True) as resp:
        resp.raise_for_status()
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype and ctype not in AUDIO_TIPOS_OK and not ctype.startswith("audio/"):
            raise ValueError(f"tipo_audio_nao_suportado:{ctype}")
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > AUDIO_MAX_BYTES:
                raise ValueError("audio_muito_grande")
            chunks.append(chunk)
        data = b"".join(chunks)
        if not data:
            raise ValueError("audio_vazio")
        return data, ctype or "application/octet-stream"


def transcrever_audio_bytes(data: bytes, *, filename: str = "audio.ogg") -> str:
    """Transcreve bytes via Whisper. Remove o arquivo temporário sempre."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("openai_api_key_ausente")
    if not data:
        raise ValueError("audio_vazio")

    from openai import OpenAI

    fd, tmp_path = tempfile.mkstemp(suffix=Path(filename).suffix or ".ogg")
    os.close(fd)
    path = Path(tmp_path)
    try:
        path.write_bytes(data)
        client = OpenAI(api_key=api_key)
        with path.open("rb") as fh:
            result = client.audio.transcriptions.create(
                model=AUDIO_TRANSCRIBE_MODEL,
                file=fh,
            )
        texto = (getattr(result, "text", None) or str(result) or "").strip()
        if not texto:
            raise ValueError("transcricao_vazia")
        return texto
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            _log("audio_tmp_cleanup_falhou", path_sufixo=path.suffix)


def transcrever_audio_url(url: str, *, token_query: str | None = None) -> dict[str, Any]:
    """Pipeline completo: download → Whisper. Retorno padronizado {ok,data,error}."""
    try:
        raw, ctype = baixar_audio(url, token_query=token_query)
        ext = _ext_de_url_ou_mime(url, ctype)
        texto = transcrever_audio_bytes(raw, filename=f"audio{ext}")
        _log("audio_transcrito", url=_url_segura_para_log(url), chars=len(texto))
        return {"ok": True, "data": {"text": texto}, "error": None, "error_code": None}
    except Exception as exc:
        code = type(exc).__name__
        msg = str(exc)[:120]
        _log(
            "audio_falha",
            url=_url_segura_para_log(url),
            erro=code,
            detalhe=msg,
        )
        return {
            "ok": False,
            "data": None,
            "error": "Não consegui processar o áudio agora. Pode enviar em texto?",
            "error_code": code,
        }


def mensagem_falha_audio() -> str:
    return (
        "Não consegui entender o áudio agora. "
        "Pode me enviar a mesma mensagem em texto?"
    )
