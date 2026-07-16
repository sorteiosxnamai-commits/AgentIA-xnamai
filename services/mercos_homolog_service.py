"""Serviço de homologação Mercos — entidades da ata beta.

Não altera o agente IA nem CHECKOUT_CREATE_ORDER.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Any

from services.mercos_api_client import (
    MercosApiError,
    _extrair_lista,
    get_json,
    get_json_com_headers,
    listar_paginado,
    post_json,
    put_json,
)
from services.mercos_service import mercos_ambiente_sandbox, mercos_configurado

# Paths confirmados no sandbox Xnamai (probe 2026-07-13)
PATHS = {
    "categorias": "/v1/categorias",
    "clientes": "/v1/clientes",
    "condicoes_pagamento": "/v1/condicoes_pagamento",
    "produtos": "/v1/produtos",
    "segmentos": "/v1/segmentos",
    "tabelas_preco": "/v1/tabelas_preco",
    # Não encontrado path listagem global no sandbox; use nested ou MERCOS_PATH_TABELAS_PRECO_PRODUTO
    "tabelas_preco_produto": "/v1/tabelas_preco",
    # Doc Mercos: listagem GET /v1/pedidos/tipo
    "tipos_pedido": "/v1/pedidos/tipo",
    # Probe sandbox 2026-07-16: GET /v1/imagens_produto?produto_id={id}
    # (o path aninhado /v1/produtos/{id}/imagens retorna 404)
    "imagens_produto": "/v1/imagens_produto",
    "usuarios": "/v1/usuarios",
    "titulos": "/v1/titulos",
    "pedidos": "/v1/pedidos",
    "pedidos_v2": "/v2/pedidos",
}


def _path(chave: str) -> str:
    import os

    env_key = f"MERCOS_PATH_{chave.upper()}"
    override = os.getenv(env_key, "").strip()
    if override:
        return override if override.startswith("/") else f"/{override}"
    return PATHS[chave]


def inventario_homologacao() -> dict[str, Any]:
    """Status das entidades exigidas na ata."""
    return {
        "sandbox": mercos_ambiente_sandbox(),
        "mercos_configurado": mercos_configurado(),
        "company_token_env": "MERCOS_COMPANY_TOKEN",
        "application_token_env": "MERCOS_APPLICATION_TOKEN",
        "entidades": [
            {"entidade": "Categorias de Produtos", "metodo": "GET", "path": _path("categorias"), "status": "pronto"},
            {"entidade": "Clientes", "metodo": "GET", "path": _path("clientes"), "status": "pronto"},
            {"entidade": "Clientes", "metodo": "POST", "path": _path("clientes"), "status": "pronto"},
            {"entidade": "Clientes", "metodo": "PUT", "path": _path("clientes") + "/{id}", "status": "pronto"},
            {"entidade": "Condições de Pagamento", "metodo": "GET", "path": _path("condicoes_pagamento"), "status": "pronto"},
            {"entidade": "Produtos", "metodo": "GET", "path": _path("produtos"), "status": "pronto"},
            {"entidade": "Segmentos de Clientes", "metodo": "GET", "path": _path("segmentos"), "status": "pronto"},
            {"entidade": "Tabelas de Preço", "metodo": "GET", "path": _path("tabelas_preco"), "status": "pronto"},
            {
                "entidade": "Tabelas de Preço por Produto",
                "metodo": "GET",
                "path": "/v1/tabelas_preco/{id}/produtos (preferencial) ou MERCOS_PATH_TABELAS_PRECO_PRODUTO",
                "status": "rota_local_pronta_path_mercos_a_confirmar",
                "nota": (
                    "Sandbox não expôs listagem global. Use GET /mercos/tabelas-preco/{id}/produtos "
                    "ou defina MERCOS_PATH_TABELAS_PRECO_PRODUTO com o path oficial da Mercos."
                ),
            },
            {
                "entidade": "Tipo de Pedido",
                "metodo": "GET",
                "path": _path("tipos_pedido"),
                "status": "rota_local_pronta_path_mercos_a_confirmar",
                "nota": "Sandbox retornou 404 em /v1/tipos_pedido. Confirmar path com suporte Mercos e setar MERCOS_PATH_TIPOS_PEDIDO.",
            },
            {"entidade": "Usuários", "metodo": "GET", "path": _path("usuarios"), "status": "pronto"},
            {"entidade": "Pedidos", "metodo": "POST", "path": _path("pedidos_v2"), "status": "pronto"},
            {"entidade": "Pedidos", "metodo": "PUT", "path": _path("pedidos") + "/{id}", "status": "pronto"},
            {"entidade": "Títulos", "metodo": "POST", "path": _path("titulos"), "status": "pronto"},
            {"entidade": "Títulos", "metodo": "PUT", "path": _path("titulos") + "/{id}", "status": "pronto"},
            {"entidade": "DELETE", "metodo": "DELETE", "path": "-", "status": "nao_requerido_ata"},
        ],
    }


def listar_categorias(**kw) -> dict:
    return listar_paginado(_path("categorias"), **kw)


def listar_clientes(
    alterado_apos: str | None = None,
    *,
    paginacao_segura: bool = False,
    timeout_request: float | None = None,
    timeout_total: float | None = None,
    sessao_id: str | None = None,
    **kw,
) -> dict:
    """GET /v1/clientes — repassa alterado_apos à Mercos (sem filtro local).

    Com paginacao_segura=True usa paradas anti-travamento (ciclo de homologação).
    """
    if paginacao_segura:
        return listar_clientes_paginado_seguro(
            alterado_apos=alterado_apos,
            pagina_inicial=int(kw.get("pagina_inicial") or 1),
            max_paginas=int(kw.get("max_paginas") or CLIENTES_MAX_PAGINAS_SYNC),
            timeout_request=(
                CLIENTES_TIMEOUT_REQUEST_SEGUNDOS
                if timeout_request is None
                else timeout_request
            ),
            timeout_total=(
                CLIENTES_TIMEOUT_SYNC_SEGUNDOS
                if timeout_total is None
                else timeout_total
            ),
            params_extra=kw.get("params_extra"),
            sessao_id=sessao_id,
        )
    params_extra = dict(kw.pop("params_extra", None) or {})
    if alterado_apos is not None and str(alterado_apos).strip():
        params_extra["alterado_apos"] = str(alterado_apos).strip()
    if params_extra:
        kw["params_extra"] = params_extra
    data = listar_paginado(_path("clientes"), **kw)
    if "alterado_apos" in params_extra:
        data["filtros"] = {"alterado_apos": params_extra["alterado_apos"]}
    return data


def listar_condicoes_pagamento(**kw) -> dict:
    return listar_paginado(_path("condicoes_pagamento"), **kw)


def listar_produtos(alterado_apos: str | None = None, **kw) -> dict:
    """GET /v1/produtos — repassa alterado_apos à Mercos (sem filtro local)."""
    params_extra = dict(kw.pop("params_extra", None) or {})
    if alterado_apos is not None and str(alterado_apos).strip():
        params_extra["alterado_apos"] = str(alterado_apos).strip()
    if params_extra:
        kw["params_extra"] = params_extra
    data = listar_paginado(_path("produtos"), **kw)
    if "alterado_apos" in params_extra:
        data["filtros"] = {"alterado_apos": params_extra["alterado_apos"]}
    return data


# Campos de envio alinhados à entidade Produto (GET sandbox + ApiMp/Mercos):
# obrigatórios: codigo, nome, ativo; preço base no produto: preco_tabela.
CAMPOS_PRODUTO_ENVIO = (
    "codigo",
    "nome",
    "ativo",
    "preco_tabela",
    "saldo_estoque",
    "unidade",
    "observacoes",
    "categoria_id",
    "codigo_ncm",
    "excluido",
)


def montar_payload_produto(dados: dict | None) -> dict:
    """Monta payload de POST produto só com campos conhecidos da API."""
    bruto = dict(dados or {})
    out: dict[str, Any] = {}
    for chave in CAMPOS_PRODUTO_ENVIO:
        if chave not in bruto:
            continue
        valor = bruto[chave]
        if valor is None or valor == "":
            continue
        out[chave] = valor
    return out


def criar_produto(body: dict) -> dict:
    """POST /v1/produtos — cadastro de produto na Mercos."""
    payload = montar_payload_produto(body)
    faltando = [c for c in ("nome", "codigo", "ativo") if c not in payload]
    if faltando:
        raise MercosApiError(
            "Campos obrigatórios ausentes para produto: "
            + ", ".join(faltando)
            + ".",
            status_code=422,
        )
    return post_json(_path("produtos"), payload)


def alterar_produto(produto_id: int | str, body: dict) -> dict:
    """PUT /v1/produtos/{id} — id só na URL; envia apenas campos conhecidos preenchidos."""
    pid = str(produto_id or "").strip()
    if not pid:
        raise MercosApiError("ID do produto é obrigatório para alteração.", status_code=422)
    payload = montar_payload_produto(body)
    payload.pop("id", None)
    if not payload:
        raise MercosApiError(
            "Nenhum campo válido informado para atualizar o produto.",
            status_code=422,
        )
    return put_json(f"{_path('produtos')}/{pid}", payload)


def normalizar_imagens_produto(payload: Any) -> list[dict[str, Any]]:
    """Extrai registros de imagem preservando o hash exatamente como retornado.

    Sandbox: [{"produto_id": <id>, "imagens": ["<hash>", ...]}].
    Tolera itens dict com campos id/hash/url sem recalcular nem converter o hash.
    """
    registros: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        imagens = item.get("imagens")
        if not isinstance(imagens, list):
            continue
        for img in imagens:
            if isinstance(img, dict):
                hash_bruto = img.get("hash")
                if hash_bruto in (None, ""):
                    hash_bruto = img.get("imagem")
                registros.append(
                    {
                        "id": img.get("id"),
                        "hash": hash_bruto,
                        "url": img.get("url")
                        or img.get("arquivo")
                        or img.get("nome_arquivo"),
                    }
                )
            elif img not in (None, ""):
                registros.append({"id": None, "hash": img, "url": None})
    return registros


# Doc oficial (Apiary Mercos): formatos aceitos .jpeg/.jpg/.png; limite local defensivo.
FORMATOS_IMAGEM_PRODUTO = (".png", ".jpg", ".jpeg")
IMAGEM_PRODUTO_MAX_BYTES = 5 * 1024 * 1024


def criar_imagem_produto(
    produto_id: int | str,
    *,
    imagem_url: str | None = None,
    imagem_base64: str | None = None,
    ordem: int | str | None = None,
) -> dict[str, Any]:
    """POST /v1/imagens_produto — contrato oficial Apiary Mercos.

    JSON: produto_id (int, obrigatório) + imagem_url OU imagem_base64;
    se ambos forem enviados a Mercos só considera a URL, então enviamos um só.
    Sucesso: 201 com header MeusPedidosID (hash só é obtido via GET).
    """
    pid = str(produto_id or "").strip()
    if not pid.isdigit():
        raise MercosApiError(
            "ID do produto (numérico) é obrigatório para adicionar imagem.",
            status_code=422,
        )
    url = (imagem_url or "").strip()
    b64 = (imagem_base64 or "").strip()
    if not url and not b64:
        raise MercosApiError(
            "Informe o arquivo da imagem (PNG/JPG) ou a URL da imagem.",
            status_code=422,
        )
    payload: dict[str, Any] = {"produto_id": int(pid)}
    if url:
        payload["imagem_url"] = url
    else:
        payload["imagem_base64"] = b64
    if ordem not in (None, ""):
        try:
            payload["ordem"] = int(ordem)
        except (TypeError, ValueError):
            raise MercosApiError(
                "O campo ordem deve ser um número inteiro.", status_code=422
            ) from None
    return post_json(_path("imagens_produto"), payload)


def listar_imagens_produto(produto_id: int | str) -> dict[str, Any]:
    """GET /v1/imagens_produto?produto_id={id} — hashes das imagens do produto.

    Contrato confirmado no sandbox (probe 2026-07-16); uma única requisição.
    """
    pid = str(produto_id or "").strip()
    if not pid:
        raise MercosApiError(
            "ID do produto é obrigatório para buscar imagens.", status_code=422
        )
    path = _path("imagens_produto")
    payload = get_json(path, params={"produto_id": pid})
    imagens = normalizar_imagens_produto(payload)
    return {
        "ok": True,
        "status_code": 200,
        "path": path,
        "produto_id": pid,
        "imagens": imagens,
        "total": len(imagens),
        "sandbox": mercos_ambiente_sandbox(),
    }


def localizar_produto_por_nome(nome: str) -> dict | None:
    """Consulta controlada: UMA requisição GET /v1/produtos, procura nome exato.

    Não pagina, não altera catálogo, cursor nem ciclo do Produto GET.
    """
    alvo = (nome or "").strip()
    if not alvo:
        return None
    payload = get_json(_path("produtos"))
    itens = payload if isinstance(payload, list) else []
    for item in itens:
        if isinstance(item, dict) and str(item.get("nome") or "").strip() == alvo:
            return item
    return None


def maior_ultima_alteracao(itens: list | None) -> str | None:
    """Maior ultima_alteracao exatamente como veio da Mercos (sem reformatar)."""
    maior: str | None = None
    for item in itens or []:
        if not isinstance(item, dict):
            continue
        bruto = item.get("ultima_alteracao")
        if bruto is None or bruto == "":
            continue
        texto = str(bruto)
        if maior is None or texto > maior:
            maior = texto
    return maior


_FMT_ULTIMA_ALTERACAO = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f",
)


def cursor_com_sobreposicao(cursor: str, segundos: int = 1) -> str:
    """Cursor salvo menos N segundos (mesmo formato), para colisão no mesmo segundo."""
    texto = (cursor or "").strip()
    if not texto:
        return texto
    for fmt in _FMT_ULTIMA_ALTERACAO:
        try:
            dt = datetime.strptime(texto, fmt)
            return (dt - timedelta(seconds=segundos)).strftime(fmt)
        except ValueError:
            continue
    # Fallback seguro: se não parsear, envia o cursor original
    return texto


def deduplicar_por_id_alteracao(itens: list | None) -> list[dict]:
    """Remove duplicados por (id, ultima_alteracao), preservando a ordem."""
    vistos: set[tuple[Any, str]] = set()
    saida: list[dict] = []
    for item in itens or []:
        if not isinstance(item, dict):
            continue
        chave = (item.get("id"), str(item.get("ultima_alteracao") or ""))
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(item)
    return saida


deduplicar_produtos_por_id_alteracao = deduplicar_por_id_alteracao
deduplicar_clientes_por_id_alteracao = deduplicar_por_id_alteracao

_SYNC_PRODUTOS_LOCK = threading.Lock()

# Lock de clientes com expiração (evita travar o Render se um worker morrer).
CLIENTES_LOCK_TTL_SEGUNDOS = 120
CLIENTES_MAX_PAGINAS_SYNC = 20
CLIENTES_TIMEOUT_REQUEST_SEGUNDOS = 10
CLIENTES_TIMEOUT_SYNC_SEGUNDOS = 60
CLIENTES_TENTATIVAS_POR_PAGINA = 3
CLIENTES_INTERVALO_ENTRE_PAGINAS = 2.0
CLIENTES_BACKOFF_429 = (2.0, 5.0, 10.0)
MOTIVO_PARADA_LOTE_VAZIO = "Lote vazio"
MOTIVO_PARADA_REPETIDA = "Página repetida / nenhum registro novo"
MOTIVO_PARADA_LIMITE = "Limite de páginas atingido"
MOTIVO_PARADA_TIMEOUT = "Timeout da sincronização"
MOTIVO_PARADA_FIM = "Todas as páginas lidas"
MOTIVO_PARADA_THROTTLE = "Limite da Mercos (HTTP 429)"
MOTIVO_PARADA_EXTRAS = "Quantidade indicada pela Mercos concluída"

# Headers de paginação retornados pela Mercos (case-insensitive)
HEADER_LIMITOU_REGISTROS = "MEUSPEDIDOS_LIMITOU_REGISTROS"
HEADER_QTDE_TOTAL_REGISTROS = "MEUSPEDIDOS_QTDE_TOTAL_REGISTROS"
HEADER_REQUISICOES_EXTRAS = "MEUSPEDIDOS_REQUISICOES_EXTRAS"


def _header_int(headers: dict | None, nome: str) -> int | None:
    """Lê um header numérico sem diferenciar maiúsculas/minúsculas."""
    alvo = nome.strip().lower()
    for chave, valor in (headers or {}).items():
        if str(chave).strip().lower() != alvo:
            continue
        try:
            return int(str(valor).strip())
        except (TypeError, ValueError):
            return None
    return None

# Resume após 429 esgotado: continua da mesma página sem reiniciar o lote.
_CLIENTES_RESUME: dict[str, dict[str, Any]] = {}
_CLIENTES_RESUME_LOCK = threading.Lock()


class _ExpiringLock:
    """Lock não-reentrante com TTL; dono expirado pode ser substituído."""

    def __init__(self, ttl_seconds: float = CLIENTES_LOCK_TTL_SEGUNDOS):
        self._ttl = float(ttl_seconds)
        self._meta = threading.Lock()
        self._owner: int | None = None
        self._since: float | None = None

    def acquire(self, blocking: bool = False) -> bool:
        del blocking  # sempre non-blocking para sync de homologação
        agora = time.monotonic()
        with self._meta:
            if self._owner is None:
                self._owner = threading.get_ident()
                self._since = agora
                return True
            if self._since is not None and (agora - self._since) >= self._ttl:
                # Expira lock antigo e assume
                self._owner = threading.get_ident()
                self._since = agora
                return True
            return False

    def release(self) -> None:
        with self._meta:
            me = threading.get_ident()
            if self._owner is None:
                return
            if self._owner == me:
                self._owner = None
                self._since = None
                return
            # Outro thread: só limpa se já expirou
            if self._since is not None and (time.monotonic() - self._since) >= self._ttl:
                self._owner = None
                self._since = None

    def held_for_seconds(self) -> float | None:
        with self._meta:
            if self._owner is None or self._since is None:
                return None
            return time.monotonic() - self._since


_SYNC_CLIENTES_LOCK = _ExpiringLock(ttl_seconds=CLIENTES_LOCK_TTL_SEGUNDOS)


def _assinatura_pagina_clientes(lote: list) -> str:
    partes: list[str] = []
    for item in lote or []:
        if not isinstance(item, dict):
            continue
        partes.append(f"{item.get('id')}|{item.get('ultima_alteracao') or ''}")
    return "\x1f".join(partes)


def _ids_pagina(lote: list) -> list[Any]:
    saida: list[Any] = []
    for item in lote or []:
        if isinstance(item, dict) and item.get("id") not in (None, ""):
            saida.append(item.get("id"))
    return saida


def _espera_por_429(tentativa: int, retry_after: float | None) -> float:
    """Segundos de espera após um 429 (tentativa 0-based da falha atual)."""
    if retry_after is not None:
        try:
            return max(0.0, float(retry_after))
        except (TypeError, ValueError):
            pass
    idx = max(0, min(int(tentativa), len(CLIENTES_BACKOFF_429) - 1))
    return float(CLIENTES_BACKOFF_429[idx])


def _chave_resume_clientes(
    sessao_id: str | None,
    alterado_apos: str | None,
) -> str:
    return f"{(sessao_id or '').strip()}|{alterado_apos or ''}"


def _salvar_resume_clientes(chave: str, estado: dict[str, Any]) -> None:
    with _CLIENTES_RESUME_LOCK:
        _CLIENTES_RESUME[chave] = dict(estado)


def _carregar_resume_clientes(chave: str) -> dict[str, Any] | None:
    with _CLIENTES_RESUME_LOCK:
        raw = _CLIENTES_RESUME.get(chave)
        return dict(raw) if isinstance(raw, dict) else None


def _limpar_resume_clientes(chave: str) -> None:
    with _CLIENTES_RESUME_LOCK:
        _CLIENTES_RESUME.pop(chave, None)


def _limpar_resumes_da_sessao(sessao_id: str) -> None:
    prefix = f"{(sessao_id or '').strip()}|"
    with _CLIENTES_RESUME_LOCK:
        for chave in [k for k in _CLIENTES_RESUME if k.startswith(prefix)]:
            _CLIENTES_RESUME.pop(chave, None)


def _reset_resume_clientes_para_testes() -> None:
    with _CLIENTES_RESUME_LOCK:
        _CLIENTES_RESUME.clear()


def _obter_lote_pagina_clientes(
    *,
    path: str,
    params: dict[str, Any],
    timeout: float,
    pagina: int,
) -> tuple[list[dict], float, dict]:
    """GET de uma página com até 3 tentativas e backoff/Retry-After.

    Retorna (lote, segundos_esperados_em_429, headers_da_resposta).
    Em 429 só repete a chamada atual (nunca reinicia a sincronização).
    Em 429 esgotado, propaga MercosApiError com pagina e retry_after.
    """
    espera_total = 0.0
    ultimo_retry: float | None = None
    for tentativa in range(CLIENTES_TENTATIVAS_POR_PAGINA):
        try:
            payload, headers_resp = get_json_com_headers(
                path,
                params=params,
                timeout=timeout,
                max_retries_429=0,  # throttling tratado aqui
            )
            lote = [i for i in _extrair_lista(payload) if isinstance(i, dict)]
            return lote, espera_total, headers_resp
        except MercosApiError as exc:
            if exc.status_code == 504:
                raise
            if exc.status_code != 429:
                raise
            ultimo_retry = exc.retry_after
            if tentativa >= CLIENTES_TENTATIVAS_POR_PAGINA - 1:
                raise MercosApiError(
                    "Mercos retornou 429 (throttling). Aguarde e tente novamente.",
                    status_code=429,
                    retry_after=_espera_por_429(tentativa, ultimo_retry),
                    pagina=pagina,
                ) from exc
            espera = _espera_por_429(tentativa, ultimo_retry)
            time.sleep(espera)
            espera_total += espera
    raise MercosApiError(
        "Mercos retornou 429 (throttling). Aguarde e tente novamente.",
        status_code=429,
        retry_after=_espera_por_429(2, ultimo_retry),
        pagina=pagina,
    )


def listar_clientes_paginado_seguro(
    *,
    alterado_apos: str | None = None,
    pagina_inicial: int = 1,
    max_paginas: int = CLIENTES_MAX_PAGINAS_SYNC,
    timeout_request: float = CLIENTES_TIMEOUT_REQUEST_SEGUNDOS,
    timeout_total: float = CLIENTES_TIMEOUT_SYNC_SEGUNDOS,
    params_extra: dict | None = None,
    sessao_id: str | None = None,
) -> dict[str, Any]:
    """Lista clientes com paradas anti-travamento e respeito a HTTP 429.

    Contrato real da Mercos (diagnóstico 2026-07-16): o endpoint ignora o
    parâmetro ``pagina``; a paginação é por cursor ``alterado_apos`` (maior
    ``ultima_alteracao`` do lote anterior, filtro estritamente maior).

    A primeira resposta traz MEUSPEDIDOS_REQUISICOES_EXTRAS: quando presente,
    executamos exatamente 1 + extras requisições — sem chamada final para
    confirmar lote vazio. As paradas por lote vazio/página repetida/cursor sem
    avanço são fallback para quando o header não existir.
    """
    pagina = max(1, int(pagina_inicial or 1))
    limite = max(1, min(int(max_paginas or CLIENTES_MAX_PAGINAS_SYNC), CLIENTES_MAX_PAGINAS_SYNC))
    path = _path("clientes")
    extras = dict(params_extra or {})
    extras.pop("alterado_apos", None)
    alterado_apos_inicial: str | None = None
    if alterado_apos is not None and str(alterado_apos).strip():
        alterado_apos_inicial = str(alterado_apos).strip()
    cursor_atual = alterado_apos_inicial

    chave_resume = _chave_resume_clientes(sessao_id, alterado_apos_inicial)
    itens_brutos: list = []
    ids_vistos: set[str] = set()
    assinaturas: set[str] = set()
    ids_pagina_anterior: list[Any] | None = None
    paginas_lidas = 0
    motivo = MOTIVO_PARADA_FIM
    status = "concluida"
    espera_429_total = 0.0
    extras_lido = False
    requisicoes_extras: int | None = None
    requisicoes_previstas: int | None = None
    qtde_total_header: int | None = None
    inicio = time.monotonic()

    resume = _carregar_resume_clientes(chave_resume) if sessao_id else None
    if resume:
        pagina = max(1, int(resume.get("pagina") or pagina))
        cursor_atual = resume.get("cursor") or cursor_atual
        itens_brutos = list(resume.get("itens") or [])
        ids_vistos = set(str(x) for x in (resume.get("ids_vistos") or []))
        assinaturas = set(resume.get("assinaturas") or [])
        ids_pagina_anterior = resume.get("ids_pagina_anterior")
        paginas_lidas = int(resume.get("paginas_lidas") or 0)
        extras_lido = bool(resume.get("extras_lido"))
        requisicoes_extras = resume.get("requisicoes_extras")
        requisicoes_previstas = resume.get("requisicoes_previstas")
        qtde_total_header = resume.get("qtde_total_header")

    while paginas_lidas < limite:
        # Tempo útil (ignora esperas de 429 no orçamento de sync)
        decorrido = time.monotonic() - inicio - espera_429_total
        if decorrido >= timeout_total:
            motivo = MOTIVO_PARADA_TIMEOUT
            status = "timeout"
            break

        timeout_resto = max(0.5, min(timeout_request, timeout_total - decorrido))
        params = dict(extras)
        if cursor_atual:
            params["alterado_apos"] = cursor_atual
        try:
            lote, espera_pag, headers_resp = _obter_lote_pagina_clientes(
                path=path,
                params=params,
                timeout=timeout_resto,
                pagina=pagina,
            )
            espera_429_total += espera_pag
        except MercosApiError as exc:
            if exc.status_code == 504:
                motivo = MOTIVO_PARADA_TIMEOUT
                status = "timeout"
                break
            if exc.status_code == 429:
                # Persiste progresso para continuar da mesma página no próximo clique/retry
                _salvar_resume_clientes(
                    chave_resume,
                    {
                        "pagina": pagina,
                        "cursor": cursor_atual,
                        "itens": itens_brutos,
                        "ids_vistos": list(ids_vistos),
                        "assinaturas": list(assinaturas),
                        "ids_pagina_anterior": ids_pagina_anterior,
                        "paginas_lidas": paginas_lidas,
                        "extras_lido": extras_lido,
                        "requisicoes_extras": requisicoes_extras,
                        "requisicoes_previstas": requisicoes_previstas,
                        "qtde_total_header": qtde_total_header,
                    },
                )
                raise
            raise

        paginas_lidas += 1

        if not extras_lido:
            # Primeira resposta: contrato de quantidade vem nos headers.
            extras_lido = True
            requisicoes_extras = _header_int(headers_resp, HEADER_REQUISICOES_EXTRAS)
            qtde_total_header = _header_int(headers_resp, HEADER_QTDE_TOTAL_REGISTROS)
            if requisicoes_extras is not None:
                requisicoes_previstas = paginas_lidas + max(0, requisicoes_extras)

        # Acumula clientes do lote (dedupe por id)
        novos = 0
        for item in lote:
            chave = str(item.get("id"))
            if chave in ids_vistos:
                continue
            ids_vistos.add(chave)
            itens_brutos.append(item)
            novos += 1

        if requisicoes_previstas is not None:
            # Modo dirigido pelo header: exatamente 1 + extras requisições,
            # sem chamada final para confirmar lote vazio.
            if paginas_lidas >= requisicoes_previstas:
                motivo = MOTIVO_PARADA_EXTRAS
                break
            if not lote:
                # Anomalia: sem dados para avançar o cursor.
                motivo = MOTIVO_PARADA_LOTE_VAZIO
                break
            if paginas_lidas >= limite:
                motivo = MOTIVO_PARADA_LIMITE
                break
            novo_cursor = maior_ultima_alteracao(lote)
            if not novo_cursor or (cursor_atual and novo_cursor <= cursor_atual):
                motivo = MOTIVO_PARADA_FIM
                break
            cursor_atual = novo_cursor
            pagina += 1
            time.sleep(CLIENTES_INTERVALO_ENTRE_PAGINAS)
            continue

        # Fallback (header ausente): paradas defensivas.
        if not lote:
            motivo = MOTIVO_PARADA_LOTE_VAZIO
            break

        assinatura = _assinatura_pagina_clientes(lote)
        ids_atual = _ids_pagina(lote)

        if assinatura in assinaturas:
            motivo = MOTIVO_PARADA_REPETIDA
            break
        if ids_pagina_anterior is not None and ids_atual == ids_pagina_anterior:
            motivo = MOTIVO_PARADA_REPETIDA
            break
        if novos == 0:
            motivo = MOTIVO_PARADA_REPETIDA
            break

        assinaturas.add(assinatura)
        ids_pagina_anterior = ids_atual

        if paginas_lidas >= limite:
            motivo = MOTIVO_PARADA_LIMITE
            break

        # Avança o cursor para o próximo lote (contrato real da Mercos).
        novo_cursor = maior_ultima_alteracao(lote)
        if not novo_cursor or (cursor_atual and novo_cursor <= cursor_atual):
            # Sem como avançar: evita repetir o mesmo lote para sempre.
            motivo = MOTIVO_PARADA_FIM
            break
        cursor_atual = novo_cursor

        pagina += 1
        time.sleep(CLIENTES_INTERVALO_ENTRE_PAGINAS)

    _limpar_resume_clientes(chave_resume)

    itens = deduplicar_clientes_por_id_alteracao(itens_brutos)
    out: dict[str, Any] = {
        "ok": True,
        "path": path,
        "total": len(itens),
        "paginas_lidas": paginas_lidas,
        "sandbox": mercos_ambiente_sandbox(),
        "itens": itens,
        "motivo_parada": motivo,
        "status": status,
        "espera_429_segundos": espera_429_total,
        "pagina_atual": pagina,
        "requisicoes_extras": requisicoes_extras,
        "requisicoes_previstas": requisicoes_previstas,
        "requisicoes_executadas": paginas_lidas,
        "qtde_total_registros": qtde_total_header,
    }
    if alterado_apos_inicial:
        out["filtros"] = {"alterado_apos": alterado_apos_inicial}
    return out


def _sincronizar_entidade(
    *,
    listar_fn,
    lock: threading.Lock,
    rotulo: str,
    cursor: str | None = None,
    max_paginas: int = 50,
    sobreposicao_segundos: int = 1,
    page_size_hint: int | None = 50,
) -> dict[str, Any]:
    """Uma sincronização GET: completa (sem cursor) ou incremental com sobreposição."""
    if not lock.acquire(blocking=False):
        raise MercosApiError(
            f"Sincronização de {rotulo} já em andamento. Aguarde a conclusão.",
            status_code=409,
        )
    try:
        cursor_base = (cursor or "").strip() or None
        tipo = "incremental" if cursor_base else "completa"
        if cursor_base:
            alterado_apos = cursor_com_sobreposicao(
                cursor_base, segundos=sobreposicao_segundos
            )
        else:
            alterado_apos = None
        listar_kwargs: dict[str, Any] = {
            "alterado_apos": alterado_apos,
            "pagina_inicial": 1,
            "max_paginas": max_paginas,
        }
        if page_size_hint is not None:
            listar_kwargs["page_size_hint"] = page_size_hint
        data = listar_fn(**listar_kwargs)
        itens = deduplicar_por_id_alteracao(data.get("itens") or [])
        total = len(itens)
        maior = maior_ultima_alteracao(itens)
        if maior:
            novo_cursor = maior
        else:
            novo_cursor = cursor_base  # preserva cursor real se sem registros
        return {
            "ok": True,
            "tipo": tipo,
            "cursor_base": cursor_base,
            "alterado_apos_enviado": alterado_apos,
            "cursor_anterior": cursor_base,
            "novo_cursor": novo_cursor,
            "total": total,
            "itens": itens,
            "path": data.get("path"),
            "paginas_lidas": data.get("paginas_lidas"),
            "filtros": data.get("filtros") or {},
            "status": "concluida",
            "motivo_parada": data.get("motivo_parada") or MOTIVO_PARADA_FIM,
        }
    finally:
        lock.release()


def sincronizar_produtos(
    cursor: str | None = None,
    *,
    max_paginas: int = 50,
    sobreposicao_segundos: int = 1,
) -> dict[str, Any]:
    """Uma sincronização Produto GET: completa (sem cursor) ou incremental.

    Incremental envia alterado_apos = cursor salvo - 1s (sobreposicao).
    O cursor real salvo continua sendo a maior ultima_alteracao recebida.
    Impede cliques/chamadas duplicadas enquanto uma sync estiver em andamento.
    """
    return _sincronizar_entidade(
        listar_fn=listar_produtos,
        lock=_SYNC_PRODUTOS_LOCK,
        rotulo="produtos",
        cursor=cursor,
        max_paginas=max_paginas,
        sobreposicao_segundos=sobreposicao_segundos,
    )


def sincronizar_clientes(
    cursor: str | None = None,
    *,
    max_paginas: int = CLIENTES_MAX_PAGINAS_SYNC,
    sobreposicao_segundos: int = 1,
    timeout_request: float = CLIENTES_TIMEOUT_REQUEST_SEGUNDOS,
    timeout_total: float = CLIENTES_TIMEOUT_SYNC_SEGUNDOS,
    sessao_id: str | None = None,
) -> dict[str, Any]:
    """Uma sincronização Cliente GET com paginação anti-travamento.

    Respeita HTTP 429 por página (Retry-After ou backoff 2/5/10, máx 3 tentativas).
    Continua da página atual sem reiniciar o lote (resume após 429 esgotado).
    Lock liberado sempre no finally; locks > 2 min expiram.
    """
    if not _SYNC_CLIENTES_LOCK.acquire(blocking=False):
        raise MercosApiError(
            "Sincronização de clientes já em andamento. Aguarde a conclusão.",
            status_code=409,
        )
    try:
        cursor_base = (cursor or "").strip() or None
        tipo = "incremental" if cursor_base else "completa"
        if cursor_base:
            alterado_apos = cursor_com_sobreposicao(
                cursor_base, segundos=sobreposicao_segundos
            )
        else:
            alterado_apos = None
        data = listar_clientes(
            alterado_apos=alterado_apos,
            paginacao_segura=True,
            pagina_inicial=1,
            max_paginas=max_paginas,
            timeout_request=timeout_request,
            timeout_total=timeout_total,
            sessao_id=sessao_id,
        )
        itens = deduplicar_clientes_por_id_alteracao(data.get("itens") or [])
        total = len(itens)
        maior = maior_ultima_alteracao(itens)
        if maior:
            novo_cursor = maior
        else:
            novo_cursor = cursor_base
        status = data.get("status") or "concluida"
        return {
            "ok": True,
            "tipo": tipo,
            "cursor_base": cursor_base,
            "alterado_apos_enviado": alterado_apos,
            "cursor_anterior": cursor_base,
            "novo_cursor": novo_cursor,
            "total": total,
            "itens": itens,
            "path": data.get("path"),
            "paginas_lidas": data.get("paginas_lidas"),
            "filtros": data.get("filtros") or {},
            "status": status,
            "motivo_parada": data.get("motivo_parada") or MOTIVO_PARADA_FIM,
            "espera_429_segundos": data.get("espera_429_segundos") or 0,
            "pagina_atual": data.get("pagina_atual"),
            "requisicoes_extras": data.get("requisicoes_extras"),
            "requisicoes_previstas": data.get("requisicoes_previstas"),
            "requisicoes_executadas": data.get("requisicoes_executadas"),
            "qtde_total_registros": data.get("qtde_total_registros"),
        }
    finally:
        _SYNC_CLIENTES_LOCK.release()


def listar_segmentos(**kw) -> dict:
    return listar_paginado(_path("segmentos"), **kw)


def listar_tabelas_preco(**kw) -> dict:
    return listar_paginado(_path("tabelas_preco"), **kw)


def listar_tabelas_preco_produto(**kw) -> dict:
    """Listagem global (path configurável). Preferir listar_produtos_da_tabela_preco."""
    return listar_paginado(_path("tabelas_preco_produto"), **kw)


def listar_produtos_da_tabela_preco(tabela_id: int | str, **kw) -> dict:
    """GET /v1/tabelas_preco/{id}/produtos — variação comum na API Mercos."""
    path = f"{_path('tabelas_preco').rstrip('/')}/{tabela_id}/produtos"
    return listar_paginado(path, **kw)


# Candidatos sandbox — ordem da ata de homologação (além do env)
# Doc Mercos: GET /api/v1/pedidos/tipo (listagem); GET /api/v1/pedidos/tipo/{id} (item)
CANDIDATOS_TIPOS_PEDIDO = (
    "/v1/pedidos/tipo",
    "/v1/tipos_pedido",
    "/v1/tipos_pedidos",
    "/v1/tipo_pedido",
    "/v1/tipos-de-pedido",
    "/v1/tipos_de_pedido",
    "/v2/tipos_pedido",
    "/v2/tipos_pedidos",
    "/v2/tipo_pedido",
)

_CACHE_PATH_TIPOS_PEDIDO: str | None = None


def caminhos_candidatos_tipos_pedido() -> list[str]:
    """Ordem: MERCOS_PATH_TIPOS_PEDIDO (se setado) + candidatos fixos, sem duplicar."""
    import os

    paths: list[str] = []
    override = os.getenv("MERCOS_PATH_TIPOS_PEDIDO", "").strip()
    if override:
        p = override if override.startswith("/") else f"/{override}"
        paths.append(p)
    for p in CANDIDATOS_TIPOS_PEDIDO:
        if p not in paths:
            paths.append(p)
    return paths


def _probe_status(path: str) -> int | None:
    """GET página 1; retorna status HTTP ou None se falha sem status."""
    from services.mercos_api_client import request_mercos

    try:
        resp = request_mercos("GET", path, params={"pagina": 1})
        return int(resp.status_code)
    except MercosApiError as exc:
        return int(exc.status_code) if exc.status_code else None


def _valor_query_opcional(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return "true" if valor else "false"
    texto = str(valor).strip()
    return texto or None


_PARAMS_INTERNO_TIPOS = frozenset(
    {
        "pagina_inicial",
        "max_paginas",
        "page_size_hint",
        "params_extra",
        "params_mercos",
    }
)


def _kw_filtros_tipos_pedido(
    params_mercos: dict | None = None,
    **kw,
) -> tuple[dict, dict]:
    """Monta kwargs de listar_paginado + mapa dos filtros enviados à Mercos.

    Aceita dict livre em params_mercos e também kwargs nomeados (legado).
    Não faz filtro local — só repassa query params.
    """
    params_extra = dict(kw.pop("params_extra", None) or {})
    filtros: dict[str, str] = {}
    unidos: dict[str, Any] = {}
    if params_mercos:
        unidos.update(params_mercos)

    kwargs_paginacao: dict[str, Any] = {}
    for chave, valor in kw.items():
        if chave in ("pagina_inicial", "max_paginas", "page_size_hint"):
            kwargs_paginacao[chave] = valor
        elif chave in _PARAMS_INTERNO_TIPOS:
            continue
        else:
            unidos[chave] = valor

    for chave, valor in unidos.items():
        normalizado = _valor_query_opcional(valor)
        if normalizado is not None:
            params_extra[str(chave)] = normalizado
            filtros[str(chave)] = normalizado

    if params_extra:
        kwargs_paginacao["params_extra"] = params_extra
    return kwargs_paginacao, filtros

def listar_tipos_pedido(
    params_mercos: dict | None = None,
    **kw,
) -> dict:
    """GET tipos de pedido — path /v1/pedidos/tipo (ou MERCOS_PATH_TIPOS_PEDIDO).

    Repassa query params à Mercos (sem filtro local no Python).
    """
    kw, filtros = _kw_filtros_tipos_pedido(params_mercos=params_mercos, **kw)
    data = listar_paginado(_path("tipos_pedido"), **kw)
    if filtros:
        data["filtros"] = filtros
    return data


def listar_tipos_pedido_descoberta(
    params_mercos: dict | None = None,
    **kw,
) -> dict:
    """Lista Tipo de Pedido tentando paths alternativos até achar HTTP 200.

    Repassa filtros à Mercos via query (não filtra no Python).
    """
    global _CACHE_PATH_TIPOS_PEDIDO

    kw, filtros = _kw_filtros_tipos_pedido(params_mercos=params_mercos, **kw)
    candidatos = caminhos_candidatos_tipos_pedido()
    testados: list[str] = []
    path_ok: str | None = _CACHE_PATH_TIPOS_PEDIDO

    if path_ok and path_ok in candidatos:
        try:
            data = listar_paginado(path_ok, **kw)
            data["path_resolvido"] = path_ok
            data["paths_testados"] = [path_ok]
            data["descoberta"] = True
            if filtros:
                data["filtros"] = filtros
                if "alterado_apos" in filtros:
                    data["alterado_apos"] = filtros["alterado_apos"]
            return data
        except MercosApiError:
            _CACHE_PATH_TIPOS_PEDIDO = None
            path_ok = None

    for path in candidatos:
        testados.append(path)
        status = _probe_status(path)
        if status == 200:
            _CACHE_PATH_TIPOS_PEDIDO = path
            data = listar_paginado(path, **kw)
            data["path_resolvido"] = path
            data["paths_testados"] = list(testados)
            data["descoberta"] = True
            data["status_code"] = 200
            if filtros:
                data["filtros"] = filtros
                if "alterado_apos" in filtros:
                    data["alterado_apos"] = filtros["alterado_apos"]
            return data

    return {
        "ok": False,
        "path": None,
        "path_resolvido": None,
        "paths_testados": testados,
        "total": 0,
        "itens": [],
        "paginas_lidas": 0,
        "sandbox": mercos_ambiente_sandbox(),
        "descoberta": True,
        "status_code": 404,
        "filtros": filtros or None,
        "alterado_apos": (filtros or {}).get("alterado_apos"),
        "mensagem": (
            "Não foi possível localizar o endpoint oficial de Tipo de Pedido no sandbox. "
            f"Paths testados: {', '.join(testados)}"
        ),
    }


COMBINACOES_FILTROS_TIPOS_PEDIDO: tuple[dict[str, str], ...] = (
    {"alterado_apos": "2026-07-14 00:00:00", "excluido": "true"},
    {"alterado_apos": "2026-07-14 00:00:00", "excluido": "1"},
    {"alterado_apos": "2026-07-14 00:00:00", "excluidos": "true"},
    {"alterado_apos": "2026-07-14 00:00:00", "somente_excluidos": "true"},
    {"alterado_apos": "2026-07-14 00:00:00", "incluir_excluidos": "true"},
    {
        "alterado_apos": "2026-07-14 00:00:00",
        "excluido": "true",
        "incluir_excluidos": "true",
    },
)


def explorar_filtros_tipos_pedido(
    combinacoes: tuple[dict[str, str], ...] | list[dict[str, str]] | None = None,
    *,
    max_paginas: int = 3,
) -> dict[str, Any]:
    """Tenta várias combinações de filtro e agrega registros com rótulo do filtro."""
    combos = list(combinacoes or COMBINACOES_FILTROS_TIPOS_PEDIDO)
    por_chave: dict[str, dict[str, Any]] = {}
    tentativas: list[dict[str, Any]] = []

    for combo in combos:
        label = "&".join(f"{k}={v}" for k, v in combo.items())
        try:
            data = listar_tipos_pedido_descoberta(
                params_mercos=combo,
                pagina_inicial=1,
                max_paginas=max_paginas,
            )
        except MercosApiError as exc:
            tentativas.append(
                {
                    "filtro": label,
                    "ok": False,
                    "total": 0,
                    "erro": exc.message[:180],
                }
            )
            continue

        ok = bool(data.get("ok", True)) and data.get("status_code") != 404
        itens = list(data.get("itens") or []) if ok else []
        tentativas.append(
            {
                "filtro": label,
                "ok": ok,
                "total": len(itens),
            }
        )
        if not ok:
            continue
        for item in itens:
            if not isinstance(item, dict):
                continue
            chave = str(item.get("id") or item.get("nome") or item.get("name") or "")
            if not chave:
                continue
            if chave not in por_chave:
                por_chave[chave] = {
                    "item": item,
                    "filtros_encontrados": [label],
                }
            elif label not in por_chave[chave]["filtros_encontrados"]:
                por_chave[chave]["filtros_encontrados"].append(label)

    itens_agregados = []
    for entry in por_chave.values():
        item = dict(entry["item"])
        item["_filtros_encontrados"] = entry["filtros_encontrados"]
        itens_agregados.append(item)

    return {
        "ok": True,
        "descoberta": True,
        "status_code": 200,
        "total": len(itens_agregados),
        "itens": itens_agregados,
        "tentativas": tentativas,
        "sandbox": mercos_ambiente_sandbox(),
    }


def listar_usuarios(**kw) -> dict:
    return listar_paginado(_path("usuarios"), **kw)


def criar_cliente(body: dict) -> dict:
    return post_json(_path("clientes"), body)


def alterar_cliente(cliente_id: int | str, body: dict) -> dict:
    payload = dict(body or {})
    if "id" not in payload:
        payload["id"] = int(cliente_id) if str(cliente_id).isdigit() else cliente_id
    return put_json(f"{_path('clientes')}/{cliente_id}", payload)


def criar_pedido(body: dict) -> dict:
    # Preferência v2 (já usada no projeto)
    return post_json(_path("pedidos_v2"), body)


def alterar_pedido(pedido_id: int | str, body: dict) -> dict:
    """PUT /v1/pedidos/{id} — id só na URL; nunca no JSON (Mercos rejeita extra keys)."""
    payload = dict(body or {})
    payload.pop("id", None)
    return put_json(f"{_path('pedidos')}/{pedido_id}", payload)


def criar_titulo(body: dict) -> dict:
    return post_json(_path("titulos"), body)


def alterar_titulo(titulo_id: int | str, body: dict) -> dict:
    payload = dict(body or {})
    if "id" not in payload:
        payload["id"] = int(titulo_id) if str(titulo_id).isdigit() else titulo_id
    return put_json(f"{_path('titulos')}/{titulo_id}", payload)


def get_um(path: str, params: dict | None = None) -> Any:
    return get_json(path, params=params)


__all__ = [
    "MercosApiError",
    "inventario_homologacao",
    "listar_categorias",
    "listar_clientes",
    "listar_condicoes_pagamento",
    "listar_produtos",
    "maior_ultima_alteracao",
    "cursor_com_sobreposicao",
    "deduplicar_por_id_alteracao",
    "deduplicar_produtos_por_id_alteracao",
    "deduplicar_clientes_por_id_alteracao",
    "sincronizar_produtos",
    "sincronizar_clientes",
    "listar_clientes_paginado_seguro",
    "montar_payload_produto",
    "criar_produto",
    "alterar_produto",
    "listar_imagens_produto",
    "normalizar_imagens_produto",
    "localizar_produto_por_nome",
    "criar_imagem_produto",
    "listar_segmentos",
    "listar_tabelas_preco",
    "listar_tabelas_preco_produto",
    "listar_produtos_da_tabela_preco",
    "listar_tipos_pedido",
    "listar_tipos_pedido_descoberta",
    "explorar_filtros_tipos_pedido",
    "COMBINACOES_FILTROS_TIPOS_PEDIDO",
    "caminhos_candidatos_tipos_pedido",
    "listar_usuarios",
    "criar_cliente",
    "alterar_cliente",
    "criar_pedido",
    "alterar_pedido",
    "criar_titulo",
    "alterar_titulo",
]
