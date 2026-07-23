"""Product Service — camada única de produtos, preço, estoque e recomendação (Etapa 4).

Nunca inventa produto, preço ou estoque.
Toda oferta comercial deve passar por aqui antes do prompt / resposta.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from services.mercos_service import estoque_confirmado, montar_catalogo_texto


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.lower()).strip()


def _preco_real(produto: dict) -> float | None:
    for campo in ("preco", "preco_tabela", "preco_venda", "preco_unitario"):
        bruto = produto.get(campo)
        if bruto in (None, ""):
            continue
        try:
            valor = float(str(bruto).replace(",", "."))
            if valor > 0:
                return valor
        except (TypeError, ValueError):
            continue
    return None


def _estoque_qtd(produto: dict) -> float | None:
    for campo in ("saldo_estoque", "estoque", "quantidade_estoque", "saldo"):
        bruto = produto.get(campo)
        if bruto in (None, ""):
            continue
        try:
            return float(str(bruto).replace(",", "."))
        except (TypeError, ValueError):
            continue
    return None


def normalizar_produto_servico(produto: dict, source: str = "supabase") -> dict[str, Any]:
    """Normaliza um produto bruto para o contrato do Product Service."""
    if not isinstance(produto, dict):
        return {}
    nome = str(produto.get("nome") or produto.get("name") or "").strip()
    if not nome:
        return {}

    price = _preco_real(produto)
    stock_qty = _estoque_qtd(produto)
    confirmed = bool(stock_qty is not None and stock_qty > 0 and estoque_confirmado(produto))
    # Se quantidade explícita 0 → confirmado como zero, mas não disponível
    if stock_qty is not None and stock_qty <= 0:
        confirmed = False

    attrs: dict[str, Any] = {}
    for chave in ("marca", "cor", "capacidade", "unidade", "codigo", "sku"):
        if produto.get(chave) not in (None, ""):
            attrs[chave] = produto.get(chave)

    return {
        "id": str(produto.get("id") or produto.get("mercos_id") or ""),
        "name": nome,
        "category": str(produto.get("categoria") or produto.get("categoria_nome") or "").strip(),
        "price": price,
        "stock_quantity": stock_qty,
        "stock_confirmed": confirmed,
        "description": str(produto.get("descricao") or produto.get("observacoes") or "").strip(),
        "attributes": attrs,
        "source": source if source in ("supabase", "mercos") else "supabase",
        # Compatibilidade com o restante do agente
        "nome": nome,
        "preco": price,
        "preco_tabela": price,
        "estoque": stock_qty if stock_qty is not None else None,
        "saldo_estoque": stock_qty if stock_qty is not None else None,
        "categoria": str(produto.get("categoria") or produto.get("categoria_nome") or "").strip(),
        "descricao": str(produto.get("descricao") or produto.get("observacoes") or "").strip(),
        "imagem_url": produto.get("imagem_url") or "",
    }


def _resultado(
    *,
    found: bool,
    query: str = "",
    category: str = "",
    products: list | None = None,
    message: str = "",
    fonte: str = "",
) -> dict[str, Any]:
    produtos = [p for p in (products or []) if p and p.get("name")]
    return {
        "found": bool(found and produtos),
        "query": (query or "").strip(),
        "category": (category or "").strip(),
        "products": produtos,
        "message": (message or "").strip(),
        "fonte": fonte or "",
        # legado para ContextoVenda / respostas
        "produtos": produtos,
        "catalogo": montar_catalogo_para_prompt(produtos) if produtos else "",
    }


# Tokens que identificam a categoria no nome/categoria do produto (filtro duro)
_TOKENS_CATEGORIA: dict[str, tuple[str, ...]] = {
    "notebook": ("notebook", "laptop"),
    "headset": ("headset", "fone", "headphone"),
    "fone": ("fone", "headset", "headphone"),
    "mouse": ("mouse",),
    "teclado": ("teclado", "keyboard"),
    "monitor": ("monitor",),
    "webcam": ("webcam",),
    "ssd": ("ssd",),
    "hd": ("hd externo", "hd ", "disco rigido", "disco rígido", "externo"),
    "armazenamento": ("ssd", "hd externo", "hd ", "pendrive", "disco"),
    "hub": ("hub",),
    "cabo": ("cabo", "hdmi"),
    "hdmi": ("hdmi", "cabo"),
    "carregador": ("carregador", "fonte"),
    "celular": ("celular", "smartphone", "iphone", "galaxy"),
}


def _parse_orcamento_valor(valor: float | int | str | None) -> float | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if float(valor) > 0 else None
    texto = str(valor).strip()
    if not texto:
        return None
    # "4000" / "4.000" / "4000,00" / "4 mil"
    m_mil = re.search(r"([\d]+(?:[.,]\d+)?)\s*mil\b", texto, flags=re.IGNORECASE)
    if m_mil:
        try:
            return float(m_mil.group(1).replace(",", ".")) * 1000.0
        except ValueError:
            return None
    raw = re.sub(r"[^\d.,]", "", texto)
    if not raw:
        return None
    try:
        if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", raw):
            return float(raw.replace(".", "").replace(",", "."))
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _categoria_da_mensagem(mensagem: str, categoria_ativa: str = "") -> str:
    from services.intent_service import _extrair_categoria

    cat = _extrair_categoria(_normalizar(mensagem or ""), {"categoria_interesse": categoria_ativa})
    return (cat or categoria_ativa or "").strip().lower()


def _produto_bate_categoria(produto: dict, categoria: str) -> bool:
    cat = (categoria or "").strip().lower()
    if not cat:
        return True
    tokens = _TOKENS_CATEGORIA.get(cat, (cat,))
    blob = _normalizar(
        f"{produto.get('name') or ''} {produto.get('nome') or ''} "
        f"{produto.get('category') or ''} {produto.get('categoria') or ''}"
    )
    return any(tok in blob for tok in tokens)


def _filtrar_por_categoria(produtos: list[dict], categoria: str) -> list[dict]:
    cat = (categoria or "").strip().lower()
    if not cat:
        return list(produtos)
    filtrados = [p for p in produtos if _produto_bate_categoria(p, cat)]
    return filtrados  # sem fallback para acessórios


def _filtrar_por_orcamento(produtos: list[dict], orcamento_max: float | None) -> list[dict]:
    limite = _parse_orcamento_valor(orcamento_max)
    if not limite:
        return list(produtos)
    out: list[dict] = []
    for p in produtos:
        preco = p.get("price")
        if preco is None:
            preco = p.get("preco")
        if preco in (None, ""):
            # Sem preço confirmado: não inventa valor; exclui da lista prioritária
            continue
        try:
            if float(preco) <= limite + 0.009:
                out.append(p)
        except (TypeError, ValueError):
            continue
    return out


def _limite_busca_especifica(limite: int, categoria: str) -> int:
    if categoria:
        return max(1, min(int(limite or 3), 3))
    return max(1, min(int(limite or 8), 8))


def montar_catalogo_para_prompt(produtos: list[dict]) -> str:
    """Catálogo limpo: só dados reais; estoque sem afirmação inventada."""
    if not produtos:
        return (
            "Nenhum produto confirmado pelo Product Service para esta consulta.\n"
            "PROIBIDO inventar produto, preço ou estoque.\n"
        )
    # Reusa montar_catalogo_texto (já não inventa disponibilidade)
    return montar_catalogo_texto(produtos)


def _buscar_brutos(mensagem: str, historico_texto: str = "") -> tuple[list[dict], str, bool]:
    """Delega à camada de catálogo existente (Supabase/Mercos)."""
    from services.vendas.catalogo import montar_contexto_catalogo

    ctx = montar_contexto_catalogo(mensagem, historico_texto)
    fonte = ctx.get("fonte") or "supabase"
    produtos = ctx.get("produtos") or []
    sem_match = bool(ctx.get("sem_match"))
    return produtos, fonte, sem_match


def listar_produtos_catalogo(limit: int = 8) -> dict[str, Any]:
    """Catálogo geral sem termo específico — amostra real do Product Service."""
    from services.vendas.catalogo import montar_catalogo_geral

    limite = max(1, min(int(limit or 8), 20))
    geral = montar_catalogo_geral(limite=limite)
    fonte = geral.get("fonte") or "supabase"
    produtos = [
        normalizar_produto_servico(p, source=fonte)
        for p in (geral.get("produtos") or [])
    ]
    produtos = [p for p in produtos if p][:limite]
    if not produtos:
        return _resultado(
            found=False,
            query="",
            category="",
            products=[],
            message=(
                "Catálogo geral vazio ou indisponível. "
                "Perguntar categoria (informática, periféricos, celular, acessórios)."
            ),
            fonte=fonte,
        )
    return _resultado(
        found=True,
        query="",
        category="",
        products=produtos,
        message="Catálogo geral — amostra de produtos reais.",
        fonte=fonte,
    )


def buscar_por_intencao(
    *,
    mensagem: str,
    intent: str = "",
    historico_texto: str = "",
    categoria_ativa: str = "",
    produto_ativo: str = "",
    product_query: str = "",
    limite: int = 8,
    orcamento_max: float | int | str | None = None,
) -> dict[str, Any]:
    """
    Busca produtos relevantes para a intenção.
    Nunca inventa itens — só o que veio do catálogo.
    Com categoria específica: filtra só essa família (máx. 3) e respeita orçamento.
    """
    from services.vendas.respostas import query_apenas_generica

    intent_u = (intent or "").upper().strip()
    query = (product_query or mensagem or "").strip()
    # Categoria da mensagem atual tem prioridade sobre a sessão (troca de assunto)
    cat_msg = _categoria_da_mensagem(mensagem, "")
    categoria = (cat_msg or categoria_ativa or "").strip()
    orc_max = _parse_orcamento_valor(orcamento_max)
    if orc_max is None:
        # Extrai da mensagem (ex.: "até 4 mil reais")
        from agents.vendas.guardrails import extract_budget

        orc_max = _parse_orcamento_valor(extract_budget(mensagem or ""))

    # CATÁLOGO GERAL / produtos disponíveis — amostra geral (não herda categoria da sessão)
    if intent_u in ("CATALOGO_GERAL", "PRODUTOS_DISPONIVEIS"):
        return listar_produtos_catalogo(limit=limite)

    # Query só com genéricos ("mande catálogo") → lista geral, nunca "não encontrei"
    if query and query_apenas_generica(query) and not cat_msg and intent_u in (
        "BUSCA_PRODUTO",
        "DUVIDA_PRODUTO",
        "",
        "INDEFINIDO",
    ):
        return listar_produtos_catalogo(limit=limite)

    # MAIS_OPCOES: prioriza categoria ativa
    if intent_u == "MAIS_OPCOES":
        return buscar_mais_opcoes(
            categoria=categoria,
            historico_texto=historico_texto,
            mensagem=mensagem,
            limite=_limite_busca_especifica(limite, categoria),
            orcamento_max=orc_max,
        )

    # PRECO: produto ativo primeiro
    if intent_u == "PRECO":
        return buscar_preco(
            produto_ativo=produto_ativo,
            mensagem=mensagem,
            historico_texto=historico_texto,
            categoria=categoria,
        )

    # COMPARACAO
    if intent_u == "COMPARACAO":
        return buscar_comparacao(mensagem=mensagem, historico_texto=historico_texto)

    # COMPRA / BUSCA_PRODUTO / default
    busca = query or mensagem
    if intent_u == "COMPRA" and produto_ativo and len((mensagem or "").split()) <= 6:
        # Confirma produto ativo antes de avançar
        return buscar_produto_por_nome(produto_ativo, historico_texto=historico_texto)

    # Proteção extra: genéricos nunca viram produto inexistente
    if query_apenas_generica(busca) and not categoria:
        return listar_produtos_catalogo(limit=limite)

    brutos, fonte, sem_match = _buscar_brutos(busca, historico_texto)
    normalizados = [
        normalizar_produto_servico(p, source=fonte or "supabase") for p in brutos
    ]
    normalizados = [p for p in normalizados if p]

    # Filtro duro: categoria específica → só produtos da família
    if categoria:
        normalizados = _filtrar_por_categoria(normalizados, categoria)
        # Se a busca bruta veio ampla/vazia após filtro, tenta de novo no catálogo geral filtrado
        if not normalizados:
            from services.vendas.catalogo import montar_catalogo_geral

            geral = montar_catalogo_geral(limite=40)
            fonte = geral.get("fonte") or fonte
            brutos_geral = geral.get("produtos") or []
            normalizados = [
                normalizar_produto_servico(p, source=fonte or "supabase") for p in brutos_geral
            ]
            normalizados = [p for p in normalizados if p]
            normalizados = _filtrar_por_categoria(normalizados, categoria)

    if orc_max:
        normalizados = _filtrar_por_orcamento(normalizados, orc_max)

    limite_efetivo = _limite_busca_especifica(limite, categoria)
    normalizados = normalizados[:limite_efetivo]

    if not normalizados:
        # Não coloca amostra aleatória em products (evita lista sem relação no prompt)
        msg = (
            "Não encontrei esse item no catálogo. "
            "Responda de forma curta, sem listar produtos aleatórios."
        )
        if categoria and orc_max:
            msg = (
                f"Não encontrei {categoria} até R$ {orc_max:,.2f} no catálogo. "
                "Não complete com acessórios; ofereça ajustar faixa ou categoria."
            ).replace(",", "X").replace(".", ",").replace("X", ".")
        elif categoria:
            msg = (
                f"Não encontrei {categoria} no catálogo. "
                "Não complete com acessórios irrelevantes."
            )
        return _resultado(
            found=False,
            query=query or mensagem,
            category=categoria,
            products=[],
            message=msg,
            fonte=fonte,
        )

    cat = categoria or normalizados[0].get("category") or ""
    msg_ok = "Produtos encontrados no catálogo."
    if categoria and len(normalizados) == 1:
        msg_ok = f"Única opção de {categoria} compatível com o pedido."
    elif categoria and len(normalizados) < 3:
        msg_ok = f"Somente {len(normalizados)} opções de {categoria} compatíveis."
    return _resultado(
        found=True,
        query=query or mensagem,
        category=cat,
        products=normalizados,
        message=msg_ok,
        fonte=fonte,
    )


def buscar_mais_opcoes(
    *,
    categoria: str = "",
    historico_texto: str = "",
    mensagem: str = "",
    limite: int = 8,
    orcamento_max: float | int | str | None = None,
) -> dict[str, Any]:
    """Fluxo MAIS_OPCOES — usa categoria ativa; sem categoria, found=False com mensagem."""
    from services.vendas.respostas import _categoria_no_historico

    cat = (categoria or _categoria_no_historico(historico_texto) or "").strip()
    if not cat:
        return _resultado(
            found=False,
            query=mensagem,
            category="",
            products=[],
            message="Sem categoria ativa — perguntar o tipo de produto.",
            fonte="",
        )

    # Busca por categoria no catálogo geral + filtro
    from services.vendas.catalogo import montar_catalogo_geral

    geral = montar_catalogo_geral(limite=40)
    fonte = geral.get("fonte") or "supabase"
    produtos = [
        normalizar_produto_servico(p, source=fonte) for p in (geral.get("produtos") or [])
    ]
    produtos = [p for p in produtos if p]
    produtos = _filtrar_por_categoria(produtos, cat)
    orc = _parse_orcamento_valor(orcamento_max)
    if orc:
        produtos = _filtrar_por_orcamento(produtos, orc)
    produtos = produtos[: _limite_busca_especifica(limite, cat)]

    if not produtos:
        return _resultado(
            found=False,
            query=mensagem,
            category=cat,
            products=[],
            message=f"Sem mais opções de {cat} no catálogo.",
            fonte=fonte,
        )
    return _resultado(
        found=True,
        query=mensagem,
        category=cat,
        products=produtos,
        message=f"Mais opções de {cat}.",
        fonte=fonte,
    )


def buscar_preco(
    *,
    produto_ativo: str = "",
    mensagem: str = "",
    historico_texto: str = "",
    categoria: str = "",
) -> dict[str, Any]:
    if produto_ativo:
        r = buscar_produto_por_nome(produto_ativo, historico_texto=historico_texto)
        if r["found"]:
            p0 = r["products"][0]
            if p0.get("price") is None:
                r["message"] = "Produto encontrado, mas preço não confirmado no catálogo."
            else:
                r["message"] = "Preço confirmado no catálogo."
            return r

    return buscar_por_intencao(
        mensagem=mensagem or produto_ativo or categoria,
        intent="BUSCA_PRODUTO",
        historico_texto=historico_texto,
        categoria_ativa=categoria,
        product_query=mensagem or produto_ativo,
    )


def buscar_produto_por_nome(nome: str, historico_texto: str = "") -> dict[str, Any]:
    nome = (nome or "").strip()
    if not nome:
        return _resultado(found=False, message="Nome de produto vazio.")
    brutos, fonte, _ = _buscar_brutos(nome, historico_texto)
    # Preferência: match mais próximo pelo nome
    alvo = _normalizar(nome)
    ordenados = sorted(
        brutos,
        key=lambda p: (
            0 if alvo == _normalizar(str(p.get("nome") or "")) else 1,
            0 if alvo in _normalizar(str(p.get("nome") or "")) else 1,
        ),
    )
    normalizados = [
        normalizar_produto_servico(p, source=fonte or "supabase") for p in ordenados
    ]
    normalizados = [p for p in normalizados if p][:5]
    if not normalizados:
        return _resultado(
            found=False,
            query=nome,
            products=[],
            message="Produto não encontrado no catálogo.",
            fonte=fonte,
        )
    return _resultado(
        found=True,
        query=nome,
        category=normalizados[0].get("category") or "",
        products=normalizados,
        message="Produto encontrado.",
        fonte=fonte,
    )


def buscar_comparacao(mensagem: str, historico_texto: str = "") -> dict[str, Any]:
    """Extrai candidatos citados e busca só dados reais."""
    texto = mensagem or ""
    # Heurística: "A ou B", "entre X e Y"
    partes = re.split(r"\bou\b|\bversus\b|\bvs\.?\b|\be\b", _normalizar(texto))
    nomes = [p.strip() for p in partes if len(p.strip()) >= 3][:3]
    encontrados: list[dict] = []
    fonte = "supabase"
    for nome in nomes:
        # ignora palavras genéricas
        if nome in ("qual", "melhor", "diferenca", "diferença", "o", "a", "um", "uma"):
            continue
        r = buscar_produto_por_nome(nome, historico_texto=historico_texto)
        if r["found"]:
            encontrados.append(r["products"][0])
            fonte = r.get("fonte") or fonte

    if len(encontrados) < 2:
        # fallback: busca ampla
        return buscar_por_intencao(
            mensagem=mensagem,
            intent="BUSCA_PRODUTO",
            historico_texto=historico_texto,
        )

    return _resultado(
        found=True,
        query=mensagem,
        category=encontrados[0].get("category") or "",
        products=encontrados[:3],
        message="Produtos para comparação (somente dados do catálogo).",
        fonte=fonte,
    )


def _amostra_relacionada(termo: str) -> list[dict]:
    if not (termo or "").strip():
        return []
    try:
        from services.vendas.catalogo import montar_catalogo_geral

        geral = montar_catalogo_geral(limite=20)
        fonte = geral.get("fonte") or "supabase"
        chave = _normalizar(termo)[:6]
        out = []
        for p in geral.get("produtos") or []:
            blob = _normalizar(f"{p.get('nome','')} {p.get('categoria','')}")
            if chave and chave in blob:
                np = normalizar_produto_servico(p, source=fonte)
                if np:
                    out.append(np)
        return out[:4]
    except Exception:
        return []


def disponibilidade_texto(produto: dict) -> str:
    """Texto seguro sobre estoque — nunca inventa."""
    if not produto:
        return "Posso verificar a disponibilidade para você."
    qty = produto.get("stock_quantity")
    confirmed = bool(produto.get("stock_confirmed"))
    if confirmed and qty is not None and float(qty) > 0:
        q = int(qty) if float(qty) == int(float(qty)) else qty
        return f"Estoque no catálogo: {q} unidade(s). Pode informar essa quantidade."
    return (
        "Estoque NÃO confirmado (stock_confirmed=false / quantity nula ou zero). "
        "NÃO afirme disponibilidade. "
        "Diga apenas: Posso verificar a disponibilidade para você."
    )


def aplicar_resultado_no_contexto(contexto_venda, resultado: dict) -> None:
    """Atualiza ContextoVenda com produtos/catálogo do Product Service."""
    if contexto_venda is None or not resultado:
        return

    found = bool(resultado.get("found"))
    produtos = resultado.get("products") or [] if found else []
    relacionados = resultado.get("related") or []

    contexto_venda.produtos = produtos
    contexto_venda.sem_match = not found
    # Não injeta amostra aleatória no prompt
    contexto_venda.amostra_disponivel = relacionados if relacionados else []

    if found:
        contexto_venda.catalogo = (
            resultado.get("catalogo") or montar_catalogo_para_prompt(produtos)
        )
    else:
        contexto_venda.catalogo = (
            "Nenhum produto encontrado no catálogo para esta consulta.\n"
            "PROIBIDO listar produtos aleatórios (ex.: HD, headset) sem relação.\n"
            "Diga que não encontrou o item e ofereça ajuda geral em informática/"
            "periféricos/armazenamento — sem listar modelos.\n"
        )

    if resultado.get("fonte"):
        contexto_venda.fonte = resultado["fonte"]

    p0 = produtos[0] if produtos else {}
    stock_line = disponibilidade_texto(p0) if p0 else (
        "Sem produto — não falar de estoque."
    )
    extra = (
        f"\nPRODUCT SERVICE: found={found}; {resultado.get('message') or ''}\n"
        f"stock_confirmed={p0.get('stock_confirmed') if p0 else False}; "
        f"stock_quantity={p0.get('stock_quantity') if p0 else None}\n"
        f"{stock_line}\n"
        "Use SOMENTE produtos listados no CATÁLOGO. "
        "Não invente produto, preço, estoque nem reserva/separação."
    )
    contexto_venda.briefing = ((contexto_venda.briefing or "") + extra).strip()
