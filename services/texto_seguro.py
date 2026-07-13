"""Normalização segura de texto (mojibake + espaçamento) para exibição/intenção."""

from __future__ import annotations

import re
import unicodedata

# Sinais clássicos de UTF-8 lido como Latin-1/CP1252
_MARCAS_MOJIBAKE = (
    "Ã",
    "Â",
    "â€™",
    "â€œ",
    "â€",
    "Ã¡",
    "Ã©",
    "Ã­",
    "Ã³",
    "Ãº",
    "Ã§",
    "Ã£",
    "Ãµ",
    "Ã‰",
    "Ã“",
)

# Hífen suave, zero-width, BOM — aparecem como “espaço sumido” no WhatsApp/JSON
_INVISIVEIS = re.compile(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff]")
_ESPACOS_UNICODE = re.compile(r"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]+")

_PADROES_COLADOS = (
    re.compile(r"(?i)algumasop"),
    re.compile(r"(?i)parauso"),
    re.compile(r"\)\("),
    re.compile(r"(?i)\)\s*\(\s*temos"),
)


def parece_mojibake(texto: str) -> bool:
    t = texto or ""
    if not t:
        return False
    return any(m in t for m in _MARCAS_MOJIBAKE)


def reparar_mojibake(texto: str) -> str:
    """Repara mojibake comum sem alterar texto já correto.

    Não usa isso para reescrever catálogo no banco — só entrada/exibição.
    """
    if not texto or not parece_mojibake(texto):
        return texto or ""

    candidatos: list[str] = []
    for enc in ("latin-1", "cp1252"):
        try:
            fix = texto.encode(enc).decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue
        if fix and fix != texto and not parece_mojibake(fix):
            candidatos.append(fix)

    if not candidatos:
        return texto

    def score(s: str) -> tuple[int, int]:
        marcas = sum(s.count(m) for m in _MARCAS_MOJIBAKE)
        return (-marcas, -abs(len(s) - len(texto)))

    candidatos.sort(key=score)
    return candidatos[0]


def corrigir_mojibake_exibicao(texto: str) -> str:
    """Alias explícito para a camada final de resposta."""
    return reparar_mojibake(texto or "")


def tem_espaco_colado(texto: str) -> bool:
    """Detecta colagens conhecidas do bug de catálogo."""
    t = texto or ""
    if not t:
        return False
    if ")(" in t or ")(temos" in t.lower():
        return True
    if re.search(r"(?i)algumasop", t):
        return True
    if re.search(r"(?i)parauso", t):
        return True
    return False


def garantir_espacos_whatsapp(texto: str) -> str:
    """Corrige colagens comuns em respostas de catálogo/WhatsApp."""
    if not (texto or "").strip():
        return texto or ""

    # NFC evita ç/õ decompostos quebrarem o regex
    out = unicodedata.normalize("NFC", texto)
    out = _INVISIVEIS.sub("", out)
    out = _ESPACOS_UNICODE.sub(" ", out)

    # Preço colado no estoque: )(temos → ) (temos
    out = re.sub(r"\)\s*\(", ") (", out)

    # Frases conhecidas (com ou sem espaço / acento)
    correcoes = (
        (r"(?i)algumas\s*op(?:ç|c)(?:[\u0301\u0327]*)?(?:õ|o|õ|o[\u0303]?)(?:es|és)", "algumas opções"),
        (r"(?i)algumasop(?:ç|c)?(?:õ|o)?(?:es|ões|oes)", "algumas opções"),
        (r"(?i)algumas\s*op\S{0,6}es", "algumas opções"),
        (r"(?i)para\s*uso\s+pessoal", "para uso pessoal"),
        (r"(?i)parauso", "para uso"),
        (r"(?i)para\s*uso", "para uso"),
    )
    for padrao, repl in correcoes:
        out = re.sub(padrao, repl, out)

    # Reforço literal (mesmo após regex)
    out = out.replace("algumasopções", "algumas opções")
    out = out.replace("algumasopcoes", "algumas opções")
    out = out.replace("Algumasopções", "Algumas opções")
    out = out.replace("parauso", "para uso")
    out = out.replace("ParaUso", "Para uso")
    out = out.replace(")(", ") (")

    # Espaço após pontuação se letra cola
    out = re.sub(r"([.,;:!?])([A-Za-zÁ-ú])", r"\1 \2", out)
    # Colapsa só espaços múltiplos (preserva quebras de linha)
    out = re.sub(r"[^\S\n]{2,}", " ", out)
    return out.strip()


def texto_para_exibicao(texto: str) -> str:
    """Pipeline seguro: mojibake → espaços (para nomes/respostas)."""
    return garantir_espacos_whatsapp(reparar_mojibake(texto or ""))


def aplicar_formatador_final(texto: str) -> tuple[str, dict]:
    """Última camada antes de /chat JSON e envio WhatsApp.

    Retorna (texto_formatado, formatacao_debug).
    """
    bruto = texto or ""
    tinha = tem_espaco_colado(bruto)
    formatado = garantir_espacos_whatsapp(corrigir_mojibake_exibicao(bruto))
    # Segunda passagem — garante que nada escapou
    if tem_espaco_colado(formatado):
        formatado = garantir_espacos_whatsapp(formatado)
        formatado = formatado.replace(")(", ") (")
        formatado = re.sub(r"(?i)algumasop\S{0,8}", "algumas opções", formatado)
        formatado = re.sub(r"(?i)parauso", "para uso", formatado)
    debug = {
        "formatador_final_aplicado": True,
        "tinha_espaco_colado_antes": bool(tinha),
        "tem_espaco_colado_depois": bool(tem_espaco_colado(formatado)),
    }
    return formatado, debug
