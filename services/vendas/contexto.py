from dataclasses import dataclass, field

from services.vendas.analise import (
    analisar_bant,
    detectar_intencao_compra,
    detectar_objecao,
    inferir_estagio_aida,
    orientacao_objecao,
    orientacao_spin,
)
from services.vendas.catalogo import montar_contexto_catalogo
from services.conversa_service import (
    entrega_ja_informada,
    extrair_pagamento,
    ia_ja_pediu_endereco,
)


@dataclass
class ContextoVenda:
    produtos: list[dict] = field(default_factory=list)
    similares: list[dict] = field(default_factory=list)
    upsell: list[dict] = field(default_factory=list)
    complementos: list[dict] = field(default_factory=list)
    catalogo: str = ""
    fonte: str = ""
    erro_mercos: str | None = None
    estagio: str = "atencao"
    bant: dict = field(default_factory=dict)
    objecao: str | None = None
    intencao_compra: bool = False
    orientacao_spin: str = ""
    orientacao_objecao: str = ""
    briefing: str = ""
    sem_match: bool = False
    termos_cliente: list = field(default_factory=list)
    amostra_disponivel: list = field(default_factory=list)


ESTAGIO_ORIENTACAO = {
    "atencao": (
        "AIDA — Atenção: acolha, gere rapport e descubra a necessidade. "
        "Uma pergunta aberta sobre o que busca."
    ),
    "interesse": (
        "AIDA — Interesse: apresente 1–2 opções do catálogo ligadas ao que ele disse. "
        "Pergunte algo que qualifique (uso, preferência) se ainda faltar contexto."
    ),
    "desejo": (
        "AIDA — Desejo: reforce benefícios, trate objeção se houver, "
        "sugira similar/upsell só se natural. Caminho para fechamento."
    ),
    "acao": (
        "AIDA — Ação: cliente perto de comprar. Colete endereço e pagamento "
        "se faltar; convide ao fechamento sem pressão."
    ),
    "pos_venda": (
        "Pós-venda: pedido já registrado. Não reabra venda; confirme status."
    ),
}


def preparar_contexto_venda(
    mensagem: str,
    historico_texto: str = "",
    pedido_encerrado: bool = False,
    pular_catalogo: bool = False,
) -> ContextoVenda:
    if pular_catalogo:
        ctx_cat = {
            "produtos": [],
            "similares": [],
            "upsell": [],
            "complementos": [],
            "catalogo": "",
            "fonte": "",
            "erro_mercos": None,
        }
    else:
        ctx_cat = montar_contexto_catalogo(mensagem, historico_texto)

    produtos = ctx_cat["produtos"]
    bant = analisar_bant(mensagem, historico_texto)
    objecao = detectar_objecao(mensagem, historico_texto)
    intencao = detectar_intencao_compra(mensagem, historico_texto)
    estagio = inferir_estagio_aida(
        mensagem,
        historico_texto,
        bool(produtos),
        pedido_encerrado=pedido_encerrado,
    )

    partes = [
        ESTAGIO_ORIENTACAO.get(estagio, ""),
        orientacao_spin(mensagem, historico_texto, bant),
        orientacao_objecao(objecao),
    ]

    if intencao and not pedido_encerrado:
        if entrega_ja_informada(historico_texto):
            if extrair_pagamento(historico_texto) != "a combinar":
                partes.append(
                    "Cliente já informou entrega e pagamento. "
                    "Convide ao fechamento — NÃO repita perguntas de endereço ou pagamento."
                )
            else:
                partes.append(
                    "Cliente já informou entrega/data. "
                    "Peça SÓ a forma de pagamento — NÃO repita pedido de endereço."
                )
        elif ia_ja_pediu_endereco(historico_texto):
            partes.append(
                "Você já pediu endereço. Confirme o que o cliente disse ou aguarde — "
                "NÃO pergunte endereço de novo."
            )
        else:
            partes.append(
                "Sinal de compra detectado: conduza ao fechamento pedindo endereço "
                "e forma de pagamento se ainda não tiver."
            )

    bant_faltando = []
    if not bant["need"]:
        bant_faltando.append("necessidade")
    if not bant["budget"] and estagio in ("interesse", "desejo"):
        bant_faltando.append("orçamento/valor")
    if bant_faltando:
        partes.append(
            f"BANT — ainda falta clareza em: {', '.join(bant_faltando)}. "
            "Pergunte de forma natural, uma coisa por vez."
        )

    if ctx_cat.get("erro_mercos"):
        partes.append(
            f"Mercos indisponível ({ctx_cat['erro_mercos']}). "
            "Use só o catálogo abaixo; não invente produtos."
        )

    if ctx_cat.get("sem_match"):
        busca = " ".join(ctx_cat.get("termos_cliente") or [])
        partes.append(
            f"Cliente pediu '{busca}' — categoria/produto INEXISTENTE no catálogo. "
            "Não diga 'não tenho hoje' (isso sugere que vendemos). "
            "Diga que NÃO TRABALHAMOS com isso. "
            "Proibido perguntar cor, tamanho ou prometer avisar quando chegar."
        )

    briefing = "\n".join(p for p in partes if p)

    return ContextoVenda(
        produtos=produtos,
        similares=ctx_cat["similares"],
        upsell=ctx_cat["upsell"],
        complementos=ctx_cat["complementos"],
        catalogo=ctx_cat["catalogo"],
        fonte=ctx_cat["fonte"],
        erro_mercos=ctx_cat.get("erro_mercos"),
        estagio=estagio,
        bant=bant,
        objecao=objecao,
        intencao_compra=intencao,
        orientacao_spin=orientacao_spin(mensagem, historico_texto, bant),
        orientacao_objecao=orientacao_objecao(objecao),
        briefing=briefing,
        sem_match=bool(ctx_cat.get("sem_match")),
        termos_cliente=ctx_cat.get("termos_cliente") or [],
        amostra_disponivel=ctx_cat.get("amostra_disponivel") or [],
    )
