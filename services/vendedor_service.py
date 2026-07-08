import os

from dotenv import load_dotenv

from services.vendas.analise import detectar_intencao_compra
from services.supabase_service import buscar_lead, criar_lead
from services.whatsapp_service import enviar_mensagem

load_dotenv(override=True)

VENDEDOR_NUMERO = os.getenv("VENDEDOR_WHATSAPP", "").strip()

INTERESSES_PRODUTO = (
    "caixa de som",
    "smartwatch",
    "carregador",
    "notebook",
    "celular",
    "monitor",
    "tablet",
    "fone",
    "vinho",
    "perfume",
)


def vendedor_configurado() -> bool:
    return bool(VENDEDOR_NUMERO)


def detectar_interesse(mensagem: str) -> str | None:
    texto = mensagem.lower()

    if detectar_intencao_compra(mensagem):
        return "intencao de compra"

    for palavra in INTERESSES_PRODUTO:
        if palavra in texto:
            return palavra

    return None


def _montar_mensagem_vendedor(
    numero_cliente: str,
    nome_cliente: str,
    interesse: str,
    mensagem_cliente: str,
    produtos: list[dict] | None = None,
) -> str:
    nome = nome_cliente or "Cliente"
    link_wa = f"https://wa.me/{numero_cliente}"

    if interesse == "intencao de compra":
        titulo = "Cliente quer fechar compra"
    else:
        titulo = f"Novo interesse: {interesse}"

    texto = (
        f"*{titulo} — Xnamai*\n\n"
        f"Cliente: {nome}\n"
        f"WhatsApp: {numero_cliente}\n\n"
        f'Mensagem:\n"{mensagem_cliente}"\n\n'
        f"Chamar: {link_wa}"
    )

    if produtos:
        nomes = [p.get("nome", "") for p in produtos[:3] if p.get("nome")]
        if nomes:
            texto += "\n\nProdutos consultados:\n- " + "\n- ".join(nomes)

    return texto


def notificar_vendedor(
    numero_cliente: str,
    nome_cliente: str,
    interesse: str,
    mensagem_cliente: str,
    produtos: list[dict] | None = None,
):
    if not vendedor_configurado():
        print("AVISO: VENDEDOR_WHATSAPP não configurado — notificação ignorada")
        return None

    texto = _montar_mensagem_vendedor(
        numero_cliente,
        nome_cliente,
        interesse,
        mensagem_cliente,
        produtos,
    )

    print("NOTIFICANDO VENDEDOR:", VENDEDOR_NUMERO)
    return enviar_mensagem(VENDEDOR_NUMERO, texto)


def processar_lead_e_notificar(
    cliente_id: str,
    numero_cliente: str,
    nome_cliente: str,
    mensagem: str,
    produtos: list[dict] | None = None,
) -> dict:
    interesse = detectar_interesse(mensagem)

    if not interesse:
        return {"interesse": None, "notificado": False}

    notificar = False

    if interesse == "intencao de compra":
        notificar = True
    elif not buscar_lead(cliente_id, interesse):
        criar_lead(cliente_id, interesse)
        print(f"LEAD SALVO: {interesse}")
        notificar = True

    if not notificar:
        return {"interesse": interesse, "notificado": False}

    resposta = notificar_vendedor(
        numero_cliente,
        nome_cliente,
        interesse,
        mensagem,
        produtos,
    )

    return {
        "interesse": interesse,
        "notificado": bool(resposta),
    }
