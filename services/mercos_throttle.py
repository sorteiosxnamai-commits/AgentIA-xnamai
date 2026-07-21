"""Throttling global e PERSISTENTE das chamadas à API Mercos.

Motivação (homologação Promoções GET): o rate limiter em memória protege apenas
um processo. A Mercos mede o limite de forma GLOBAL por empresa (CompanyToken),
então uma chamada feita por outro processo, por outra rota/entidade ou logo após
um reinício do Uvicorn não era contabilizada — e a Mercos reprovava com
"Throttling não foi respeitado" mesmo com o menor intervalo interno correto.

Este módulo mantém, por CompanyToken, um estado em disco que sobrevive a
reinícios e é compartilhado entre processos locais via lock de arquivo:

- ``ultima_chamada_ts``: horário real (wall clock) do INÍCIO da última chamada;
- ``metodo`` / ``endpoint``: da última chamada (para auditoria);
- ``pid`` / ``instancia``: identificação do processo que fez a chamada;
- ``proximo_permitido_ts``: reagendamento após 429 (Retry-After);
- ``company_hash``: hash NÃO reversível do CompanyToken.

Nunca persistimos nem exibimos o token real — apenas o hash SHA-256.

Antes de QUALQUER requisição HTTP à Mercos (GET/POST/PUT, páginas extras e
retentativas após 429, de todas as entidades), :func:`executar` carrega o
estado, aguarda o intervalo mínimo (default 8s), registra atomicamente o novo
início e só então envia — mantendo o lock de arquivo durante toda a chamada
para impedir que dois processos chamem em paralelo.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import socket
import threading
import time
from typing import Any, Callable

INTERVALO_MINIMO_GLOBAL_SEGUNDOS = 8.0
_MAX_AUDITORIA = 200
# Espera fixa (real) entre tentativas de aquisição do lock de arquivo.
_LOCK_SPIN_SEGUNDOS = 0.02

# Serializa também dentro do mesmo processo (além do lock de arquivo).
_LOCK_LOCAL = threading.RLock()

# Relógio/sono injetáveis (testes). Relógio é WALL CLOCK (persistível).
_relogio: Callable[[], float] | None = None
_dormir: Callable[[float], None] | None = None

# Origem/rota interna da chamada atual (para auditoria, sem segredos).
_origem_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "mercos_throttle_origem", default=""
)

# Contador de chamadas bloqueadas pelo modo exclusivo (por hash de empresa).
_BLOQUEIOS: dict[str, int] = {}


def definir_origem(origem: str | None) -> contextvars.Token:
    """Registra a rota/origem interna da chamada atual (para auditoria)."""
    return _origem_ctx.set((origem or "").strip())


def limpar_origem(token: contextvars.Token) -> None:
    try:
        _origem_ctx.reset(token)
    except (ValueError, LookupError):
        pass


def _agora() -> float:
    return _relogio() if _relogio is not None else time.time()


def _sleep(segundos: float) -> None:
    if segundos <= 0:
        return
    if _dormir is not None:
        _dormir(segundos)
    else:
        time.sleep(segundos)


def _intervalo_padrao() -> float:
    raw = os.getenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
    return INTERVALO_MINIMO_GLOBAL_SEGUNDOS


def _dir_base() -> str:
    raw = os.getenv("MERCOS_THROTTLE_DIR", "").strip()
    if raw:
        return raw
    return os.path.join(os.path.expanduser("~"), ".mercos_homolog", "throttle")


def hash_company(token: str | None = None) -> str:
    """Hash SHA-256 NÃO reversível do CompanyToken (nunca o token real)."""
    tok = (token if token is not None else os.getenv("MERCOS_COMPANY_TOKEN", "")).strip()
    if not tok:
        return "sem-company-token"
    return hashlib.sha256(f"mercos-throttle-v1:{tok}".encode("utf-8")).hexdigest()


def _instancia() -> str:
    try:
        host = socket.gethostname()
    except OSError:
        host = "host"
    return f"{host}:{os.getpid()}"


def _paths(company_hash: str) -> tuple[str, str, str]:
    base = _dir_base()
    estado = os.path.join(base, f"{company_hash}.json")
    audit = os.path.join(base, f"{company_hash}.audit.jsonl")
    lock = os.path.join(base, f"{company_hash}.lock")
    return estado, audit, lock


class _LockArquivo:
    """Lock cross-process baseado em ``os.mkdir`` (atômico em todos os SOs).

    Um dono expirado (mais velho que ``stale``) é substituído: evita travar tudo
    se um processo morrer sem liberar o lock.
    """

    def __init__(self, caminho: str, *, timeout: float = 60.0, stale: float = 120.0):
        self._caminho = caminho
        self._timeout = float(timeout)
        self._stale = float(stale)

    def __enter__(self) -> "_LockArquivo":
        os.makedirs(os.path.dirname(self._caminho), exist_ok=True)
        inicio = time.monotonic()
        while True:
            try:
                os.mkdir(self._caminho)
                return self
            except FileExistsError:
                self._quebrar_se_expirado()
                if time.monotonic() - inicio >= self._timeout:
                    # Última tentativa de quebra e prossegue (homologação local).
                    self._quebrar_se_expirado(forcar=True)
                    try:
                        os.mkdir(self._caminho)
                    except FileExistsError:
                        return self
                    return self
                time.sleep(_LOCK_SPIN_SEGUNDOS)

    def _quebrar_se_expirado(self, *, forcar: bool = False) -> None:
        try:
            idade = time.time() - os.path.getmtime(self._caminho)
        except OSError:
            return
        if forcar or idade >= self._stale:
            try:
                os.rmdir(self._caminho)
            except OSError:
                pass

    def __exit__(self, *exc: Any) -> None:
        try:
            os.rmdir(self._caminho)
        except OSError:
            pass


def _ler_estado(estado_path: str) -> dict[str, Any]:
    try:
        with open(estado_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _escrever_estado(estado_path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(estado_path), exist_ok=True)
    tmp = f"{estado_path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    os.replace(tmp, estado_path)


def _ler_auditoria(audit_path: str) -> list[dict[str, Any]]:
    try:
        with open(audit_path, "r", encoding="utf-8") as fh:
            linhas = fh.readlines()
    except (FileNotFoundError, OSError):
        return []
    saida: list[dict[str, Any]] = []
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        try:
            item = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            saida.append(item)
    return saida


def _append_auditoria(audit_path: str, entrada: dict[str, Any]) -> None:
    registros = _ler_auditoria(audit_path)
    registros.append(entrada)
    if len(registros) > _MAX_AUDITORIA:
        registros = registros[-_MAX_AUDITORIA:]
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)
    tmp = f"{audit_path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        for item in registros:
            fh.write(json.dumps(item, ensure_ascii=False))
            fh.write("\n")
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    os.replace(tmp, audit_path)


def executar(
    metodo: str,
    endpoint: str,
    chamada: Callable[[], Any],
    *,
    intervalo_minimo: float | None = None,
    origem: str | None = None,
    company_token: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Aguarda o intervalo global, registra o início e executa a chamada HTTP.

    O lock de arquivo é mantido durante a espera E a chamada, serializando
    processos locais. Retorna ``(resultado, info)`` com ``espera``,
    ``intervalo_desde_anterior`` e ``intervalo_minimo`` aplicados.
    """
    piso = _intervalo_padrao() if intervalo_minimo is None else max(0.0, float(intervalo_minimo))
    ch = hash_company(company_token)
    estado_path, audit_path, lock_path = _paths(ch)
    origem_final = (origem if origem is not None else _origem_ctx.get()) or ""

    with _LOCK_LOCAL:
        with _LockArquivo(lock_path):
            estado = _ler_estado(estado_path)
            ultima = estado.get("ultima_chamada_ts")
            proximo = estado.get("proximo_permitido_ts")
            agora = _agora()
            alvo = agora
            if isinstance(ultima, (int, float)):
                alvo = max(alvo, float(ultima) + piso)
            if isinstance(proximo, (int, float)):
                alvo = max(alvo, float(proximo))
            espera = 0.0
            for _ in range(8):
                restante = alvo - _agora()
                if restante <= 0:
                    break
                _sleep(restante)
                espera += restante
            agora = _agora()
            intervalo_desde = (
                agora - float(ultima) if isinstance(ultima, (int, float)) else None
            )
            novo = {
                "company_hash": ch,
                "ultima_chamada_ts": agora,
                "metodo": (metodo or "").upper(),
                "endpoint": endpoint,
                "pid": os.getpid(),
                "instancia": _instancia(),
                "proximo_permitido_ts": None,
            }
            _escrever_estado(estado_path, novo)
            _append_auditoria(
                audit_path,
                {
                    "ts": agora,
                    "metodo": (metodo or "").upper(),
                    "endpoint": endpoint,
                    "intervalo_desde_anterior": intervalo_desde,
                    "origem": origem_final,
                    "pid": os.getpid(),
                },
            )
            resultado = chamada()
            return resultado, {
                "espera": espera,
                "intervalo_desde_anterior": intervalo_desde,
                "intervalo_minimo": piso,
            }


def aplicar_retry_after(
    segundos: float | None, *, company_token: str | None = None
) -> None:
    """Reagenda o próximo envio para agora + Retry-After (nunca antecipa o piso)."""
    if segundos is None:
        return
    try:
        espera = max(0.0, float(segundos))
    except (TypeError, ValueError):
        return
    if espera <= 0:
        return
    ch = hash_company(company_token)
    estado_path, _audit_path, lock_path = _paths(ch)
    with _LOCK_LOCAL:
        with _LockArquivo(lock_path):
            estado = _ler_estado(estado_path)
            estado["proximo_permitido_ts"] = _agora() + espera
            estado.setdefault("company_hash", ch)
            _escrever_estado(estado_path, estado)


def estado_atual(*, company_token: str | None = None) -> dict[str, Any]:
    """Estado persistido (sem segredos) + intervalo desde a última chamada."""
    ch = hash_company(company_token)
    estado_path, _audit_path, _lock_path = _paths(ch)
    with _LOCK_LOCAL:
        estado = _ler_estado(estado_path)
    ultima = estado.get("ultima_chamada_ts")
    intervalo_desde = None
    if isinstance(ultima, (int, float)):
        intervalo_desde = max(0.0, _agora() - float(ultima))
    return {
        "company_hash": estado.get("company_hash") or ch,
        "ultima_chamada_ts": ultima,
        "metodo": estado.get("metodo"),
        "endpoint": estado.get("endpoint"),
        "pid": estado.get("pid"),
        "instancia": estado.get("instancia"),
        "intervalo_minimo": _intervalo_padrao(),
        "intervalo_desde_ultima_global": intervalo_desde,
    }


def auditoria(limite: int = 20, *, company_token: str | None = None) -> list[dict[str, Any]]:
    ch = hash_company(company_token)
    _estado_path, audit_path, _lock_path = _paths(ch)
    with _LOCK_LOCAL:
        registros = _ler_auditoria(audit_path)
    if limite and limite > 0:
        registros = registros[-limite:]
    return list(reversed(registros))


def menor_intervalo_persistido(*, company_token: str | None = None) -> float | None:
    """Menor intervalo entre chamadas consecutivas registrado na auditoria."""
    ch = hash_company(company_token)
    _estado_path, audit_path, _lock_path = _paths(ch)
    with _LOCK_LOCAL:
        registros = _ler_auditoria(audit_path)
    menor: float | None = None
    for item in registros:
        val = item.get("intervalo_desde_anterior")
        if isinstance(val, (int, float)):
            if menor is None or val < menor:
                menor = float(val)
    return menor


def throttling_global_respeitado(*, company_token: str | None = None) -> bool | None:
    """True se todos os intervalos persistidos respeitaram o piso global."""
    menor = menor_intervalo_persistido(company_token=company_token)
    if menor is None:
        return None
    return menor >= _intervalo_padrao()


def registrar_bloqueio(*, company_token: str | None = None) -> int:
    """Conta uma chamada bloqueada pelo modo exclusivo de Promoções."""
    ch = hash_company(company_token)
    with _LOCK_LOCAL:
        _BLOQUEIOS[ch] = int(_BLOQUEIOS.get(ch, 0)) + 1
        return _BLOQUEIOS[ch]


def bloqueios(*, company_token: str | None = None) -> int:
    ch = hash_company(company_token)
    with _LOCK_LOCAL:
        return int(_BLOQUEIOS.get(ch, 0))


def chamadas_externas(*, company_token: str | None = None) -> int:
    """Chamadas persistidas cujo endpoint NÃO é de promoções (outras entidades)."""
    ch = hash_company(company_token)
    _estado_path, audit_path, _lock_path = _paths(ch)
    with _LOCK_LOCAL:
        registros = _ler_auditoria(audit_path)
    return sum(
        1 for item in registros if "promocoes" not in str(item.get("endpoint") or "")
    )


def configurar_para_testes(
    *,
    diretorio: str | None = None,
    intervalo: float | None = None,
    relogio: Callable[[], float] | None = None,
    dormir: Callable[[float], None] | None = None,
) -> None:
    """Ajusta config global (usado por testes/conftest)."""
    global _relogio, _dormir
    if diretorio is not None:
        os.environ["MERCOS_THROTTLE_DIR"] = diretorio
    if intervalo is not None:
        os.environ["MERCOS_THROTTLE_INTERVALO_SEGUNDOS"] = str(intervalo)
    _relogio = relogio
    _dormir = dormir


def _reset_para_testes() -> None:
    global _relogio, _dormir
    _relogio = None
    _dormir = None
    with _LOCK_LOCAL:
        _BLOQUEIOS.clear()


__all__ = [
    "INTERVALO_MINIMO_GLOBAL_SEGUNDOS",
    "definir_origem",
    "limpar_origem",
    "hash_company",
    "executar",
    "aplicar_retry_after",
    "estado_atual",
    "auditoria",
    "menor_intervalo_persistido",
    "throttling_global_respeitado",
    "registrar_bloqueio",
    "bloqueios",
    "chamadas_externas",
    "configurar_para_testes",
    "_reset_para_testes",
]
