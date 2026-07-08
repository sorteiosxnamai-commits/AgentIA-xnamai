import os

from dotenv import load_dotenv

from services.conversa_service import (
    extrair_contato,
    extrair_endereco,
    extrair_nome_do_historico,
    extrair_pagamento,
    _buscar_produto_do_historico,
    _extrair_nome_produto_historico,
    _extrair_preco_historico,
)
from services.mercos_service import (
    _valor_preco,
    buscar_produto_bruto_por_mensagem,
    criar_cliente_mercos,
    criar_pedido_mercos,
    mercos_configurado,
)
from services.supabase_service import atualizar_cliente

load_dotenv(override=True)

MERCOS_CLIENTE_PADRAO = os.getenv("MERCOS_CLIENTE_PADRAO", "").strip()


def mercos_criar_pedido_habilitado() -> bool:
    return os.getenv("MERCOS_CRIAR_PEDIDO", "true").strip().lower() in (
        "1",
        "true",
        "sim",
        "yes",
    )


def pedido_mercos_ja_registrado(ultima_resposta_ia: str) -> bool:
    if not ultima_resposta_ia:
        return False
    ultima = ultima_resposta_ia.lower()
    return "pedido mercos #" in ultima or "pedido registrado" in ultima


def _mapear_condicao_pagamento(pagamento: str) -> str:
    pagamento = (pagamento or "").lower()
    if "pix" in pagamento:
        return "PIX"
    if "debito" in pagamento or "débito" in pagamento:
        return "Débito na entrega"
    if "credito" in pagamento or "crédito" in pagamento:
        return "Cartão de crédito"
    return pagamento or "A combinar"


def _resolver_produto_mercos(historico_texto: str) -> dict | None:
    produto = _buscar_produto_do_historico(historico_texto)
    if produto and produto.get("mercos_id"):
        return {
            "id": produto["mercos_id"],
            "nome": produto.get("nome"),
            "preco_tabela": produto.get("preco"),
        }

    historico = historico_texto.lower()
    consultas = []

    for termo in ("lt800", "lt801", "rs60", "hmaston"):
        if termo in historico:
            consultas.append(termo)

    if "caixa de som" in historico or "bluetooth" in historico:
        consultas.extend(["caixa de som bluetooth", "bluetooth", "caixa de som"])

    for consulta in consultas:
        from services.produtos_service import buscar_produtos_para_atendimento

        resultado = buscar_produtos_para_atendimento(consulta)
        for item in resultado.get("produtos") or []:
            if item.get("mercos_id"):
                return {
                    "id": item["mercos_id"],
                    "nome": item.get("nome"),
                    "preco_tabela": item.get("preco"),
                }

    if not mercos_configurado():
        return None

    for consulta in consultas or [historico_texto]:
        produto = buscar_produto_bruto_por_mensagem(consulta)
        if produto and produto.get("id"):
            return produto

    return None


def _obter_cliente_mercos_id(
    cliente_supabase: dict,
    nome: str,
    telefone: str,
    endereco: str,
    contato: str,
) -> int:
    mercos_id = cliente_supabase.get("mercos_cliente_id")
    if mercos_id:
        return int(mercos_id)

    if MERCOS_CLIENTE_PADRAO:
        return int(MERCOS_CLIENTE_PADRAO)

    observacao_partes = ["Cliente via WhatsApp Agent IA Xnamai"]
    if telefone:
        observacao_partes.append(f"Tel: {telefone}")
    if endereco:
        observacao_partes.append(f"End: {endereco}")
    if contato:
        observacao_partes.append(f"Dados: {contato}")

    mercos_id = criar_cliente_mercos(
        nome=nome,
        telefone=telefone,
        observacao=" | ".join(observacao_partes),
    )

    try:
        atualizar_cliente(cliente_supabase["id"], mercos_cliente_id=mercos_id)
    except Exception as e:
        print("AVISO: não foi possível salvar mercos_cliente_id no Supabase:", e)

    return mercos_id


def criar_pedido_fechamento_mercos(
    historico_texto: str,
    cliente_supabase: dict,
    telefone: str,
    pushname: str = "",
    mensagem_atual: str = "",
    ultima_resposta_ia: str = "",
    frete_estimado: float = 0,
) -> dict | None:
    if not mercos_configurado():
        return None

    if not mercos_criar_pedido_habilitado():
        print("MERCOS: criação de pedido desabilitada (MERCOS_CRIAR_PEDIDO=false)")
        return None

    if pedido_mercos_ja_registrado(ultima_resposta_ia):
        print("MERCOS: pedido já registrado na última resposta, ignorando duplicata")
        return None

    nome = extrair_nome_do_historico(historico_texto, pushname)
    endereco = extrair_endereco(historico_texto)
    contato = extrair_contato(historico_texto)
    pagamento = extrair_pagamento(
        historico_texto,
        mensagem_atual=mensagem_atual,
        ultima_resposta_ia=ultima_resposta_ia,
    )

    produto_mercos = _resolver_produto_mercos(historico_texto)
    if not produto_mercos or not produto_mercos.get("id"):
        print("MERCOS: produto não encontrado para criar pedido")
        return {"erro": "produto_nao_encontrado"}

    preco = _extrair_preco_historico(historico_texto)
    if preco is None:
        preco = _valor_preco(produto_mercos)

    try:
        preco = float(str(preco).replace(",", "."))
    except (TypeError, ValueError):
        preco = 0.0

    if frete_estimado > 0:
        preco += frete_estimado

    nome_produto = (
        _extrair_nome_produto_historico(historico_texto)
        or produto_mercos.get("nome")
        or "produto"
    )

    try:
        cliente_id = _obter_cliente_mercos_id(
            cliente_supabase,
            nome,
            telefone,
            endereco,
            contato,
        )

        observacoes = (
            f"Pedido WhatsApp Xnamai | {nome_produto} | "
            f"Pagamento: {pagamento}"
        )
        if endereco:
            observacoes += f" | Entrega: {endereco}"
        if contato:
            observacoes += f" | {contato}"
        if telefone:
            observacoes += f" | WhatsApp: {telefone}"

        resultado = criar_pedido_mercos(
            cliente_id=cliente_id,
            produto_id=int(produto_mercos["id"]),
            quantidade=1,
            preco_bruto=preco,
            condicao_pagamento=_mapear_condicao_pagamento(pagamento),
            observacoes=observacoes,
        )

        pedido_id = resultado.get("id")
        numero = resultado.get("numero")

        print(f"MERCOS: pedido criado id={pedido_id} numero={numero}")

        return {
            "pedido_id": pedido_id,
            "numero": numero,
            "cliente_id": cliente_id,
            "produto_id": produto_mercos["id"],
        }

    except Exception as e:
        print("MERCOS ERRO ao criar pedido:", e)
        return {"erro": str(e)}
