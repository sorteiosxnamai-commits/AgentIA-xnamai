"""Normalização segura de texto (mojibake + espaçamento) para exibição/intenção."""

from __future__ import annotations

import re

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

    # Prefere o que removeu mais marcas de mojibake e manteve tamanho razoável
    def score(s: str) -> tuple[int, int]:
        marcas = sum(s.count(m) for m in _MARCAS_MOJIBAKE)
        return (-marcas, -abs(len(s) - len(texto)))

    candidatos.sort(key=score)
    return candidatos[0]


def garantir_espacos_whatsapp(texto: str) -> str:
    """Corrige colagens comuns em respostas de catálogo/WhatsApp."""
    if not (texto or "").strip():
        return texto or ""

    out = texto
    # Preço colado no estoque: )(temos → ) (temos
    out = re.sub(r"\)\s*\(", ") (", out)

    # Frases conhecidas que já apareceram coladas em produção
    correcoes = (
        (r"(?i)algumas\s*op(?:ç|c)(?:õ|o)es", "algumas opções"),
        (r"(?i)para\s*uso\s+pessoal", "para uso pessoal"),
        (r"(?i)parauso", "para uso"),
        (r"(?i)algumasop(?:ç|c)(?:õ|o)es", "algumas opções"),
    )
    for padrao, repl in correcoes:
        out = re.sub(padrao, repl, out)

    # Espaço após pontuação se letra cola: ".Você" / ",Tironi"
    out = re.sub(r"([.,;:!?])([A-Za-zÁ-ú])", r"\1 \2", out)
    # Colapsa só espaços múltiplos (preserva quebras de linha)
    out = re.sub(r"[^\S\n]{2,}", " ", out)
    return out.strip()


def texto_para_exibicao(texto: str) -> str:
    """Pipeline seguro: mojibake → espaços (para nomes/respostas)."""
    return garantir_espacos_whatsapp(reparar_mojibake(texto or ""))
