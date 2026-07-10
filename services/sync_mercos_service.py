import os
import time

from services.env_loader import carregar_env

from services.mercos_service import (
    buscar_produtos_mercos,
    extrair_imagem_mercos,
    mercos_configurado,
    normalizar_produto,
)
from services.supabase_service import sincronizar_produto_mercos

carregar_env()


def _produto_para_supabase(produto_mercos: dict) -> dict:
    """Mapeia para o schema PulseDesk (preco_tabela/saldo_estoque — sem categoria)."""
    dados = normalizar_produto(produto_mercos)
    imagem = extrair_imagem_mercos(produto_mercos)

    registro = {
        "mercos_id": produto_mercos.get("id"),
        "nome": dados["nome"],
        "codigo": dados.get("codigo") or produto_mercos.get("codigo") or "",
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
    # Schema PulseDesk atual não tem imagem_url/categoria — não enviar
    _ = imagem
    return registro


def sincronizar_produtos_mercos() -> dict:
    if not mercos_configurado():
        raise ValueError("Mercos não configurada no .env")

    produtos_mercos = buscar_produtos_mercos()

    criados = 0
    atualizados = 0
    com_imagem = 0
    erros = []

    for produto in produtos_mercos:
        try:
            registro = _produto_para_supabase(produto)
            if not registro.get("nome"):
                continue

            if registro.get("imagem_url"):
                com_imagem += 1

            resultado = sincronizar_produto_mercos(registro)

            if resultado == "criado":
                criados += 1
            elif resultado == "atualizado":
                atualizados += 1

            time.sleep(0.05)

        except Exception as e:
            erros.append({
                "mercos_id": produto.get("id"),
                "nome": produto.get("nome"),
                "erro": str(e),
            })

    return {
        "total_mercos": len(produtos_mercos),
        "criados": criados,
        "atualizados": atualizados,
        "com_imagem_mercos": com_imagem,
        "erros": erros,
    }
