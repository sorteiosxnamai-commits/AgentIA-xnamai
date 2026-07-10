import os
import re
import unicodedata

from services.env_loader import carregar_env

carregar_env()

PIX_CHAVE = os.getenv("PIX_CHAVE", "contato@xnamai.com.br").strip()
PIX_NOME = os.getenv("PIX_NOME", "XNAMAI").strip()
PIX_CIDADE = os.getenv("PIX_CIDADE", "CURITIBA").strip()


def _normalizar_ascii(texto: str, limite: int) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Za-z0-9 ]", "", texto)
    return texto.upper()[:limite].strip() or "XNAMAI"


def _tlv(campo: str, valor: str) -> str:
    return f"{campo}{len(valor):02d}{valor}"


def _crc16_pix(payload: str) -> str:
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def gerar_pix_copia_cola(
    valor: float | None = None,
    chave: str | None = None,
    nome: str | None = None,
    cidade: str | None = None,
    referencia: str = "XNAMAI001",
) -> str:
    chave = (chave or PIX_CHAVE).strip()
    nome = _normalizar_ascii(nome or PIX_NOME, 25)
    cidade = _normalizar_ascii(cidade or PIX_CIDADE, 15)

    conta = _tlv("00", "br.gov.bcb.pix") + _tlv("01", chave)
    payload = _tlv("00", "01")
    payload += _tlv("26", conta)
    payload += _tlv("52", "0000")
    payload += _tlv("53", "986")

    if valor is not None and valor > 0:
        payload += _tlv("54", f"{valor:.2f}")

    payload += _tlv("58", "BR")
    payload += _tlv("59", nome)
    payload += _tlv("60", cidade)

    if referencia:
        ref = _tlv("05", referencia[:25])
        payload += _tlv("62", ref)

    payload += "6304"
    return payload + _crc16_pix(payload)


def montar_mensagem_pix_exemplo(valor: float | None = None, referencia: str = "XNAMAI001") -> str:
    copia_cola = gerar_pix_copia_cola(valor=valor, referencia=referencia)
    valor_fmt = f"R$ {valor:.2f}".replace(".", ",") if valor else "conforme combinado"

    linhas = [
        "",
        "📲 *PIX para pagamento (exemplo)*",
        f"Chave: {PIX_CHAVE}",
        f"Valor: {valor_fmt}",
        "",
        "Copia e cola:",
        copia_cola,
        "",
        "Após pagar, envie o comprovante aqui.",
    ]
    return "\n".join(linhas)
