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

# Hífen suave, zero-width, BOM, marks de formato
_INVISIVEIS = re.compile(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff\u200e\u200f\u034f]")
_ESPACOS_UNICODE = re.compile(r"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]+")


def _strip_invisiveis(texto: str) -> str:
    """Remove soft-hyphen, zero-width e categoria Unicode Cf (format)."""
    if not texto:
        return ""
    out = _INVISIVEIS.sub("", texto)
    out = "".join(c for c in out if unicodedata.category(c) != "Cf")
    return out


def parece_mojibake(texto: str) -> bool:
    t = texto or ""
    if not t:
        return False
    return any(m in t for m in _MARCAS_MOJIBAKE)


def reparar_mojibake(texto: str) -> str:
    """Repara mojibake comum sem alterar texto já correto."""
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


# Número colado em unidade de estoque/catálogo (ex.: "89unidades")
_NUM_UNIDADE_COLADA = re.compile(
    r"(?i)(\d+)(unidades|unidade|peças|pecas|itens)\b"
)


def tem_espaco_colado(texto: str) -> bool:
    """Detecta colagens — inclusive com invisíveis/mojibake no meio."""
    bruto = texto or ""
    if not bruto:
        return False
    # Sempre analisa também a versão sem invisíveis
    candidatos = (bruto, _strip_invisiveis(bruto), unicodedata.normalize("NFC", bruto))
    for t in candidatos:
        tl = t.lower()
        if ")(" in t or ")(temos" in tl:
            return True
        if "algumasop" in tl or "algumasopã" in tl or "algumasopÃ".lower() in tl:
            return True
        if re.search(r"(?i)algumasop", t):
            return True
        if re.search(r"(?i)algumasopÃ", t):
            return True
        if "parauso" in tl:
            return True
        # algumas + só lixo invisível + op
        if re.search(r"(?i)algumas[\u00ad\u200b\u200c\u200d\ufeff]*op", t):
            return True
        if _NUM_UNIDADE_COLADA.search(t):
            return True
    return False


def garantir_espacos_whatsapp(texto: str) -> str:
    """Corrige colagens comuns em respostas de catálogo/WhatsApp."""
    if not (texto or "").strip():
        return texto or ""

    out = unicodedata.normalize("NFC", texto)
    out = _strip_invisiveis(out)
    out = _ESPACOS_UNICODE.sub(" ", out)

    # Inserção forçada: "algumas" colado em "op..." / "para" colado em "uso"
    # NÃO usar ") (" com lookahead — isso duplicava o "(" restante.
    out = re.sub(r"(?i)algumas(?=op)", "algumas ", out)
    out = re.sub(r"(?i)para(?=uso)", "para ", out)
    out = re.sub(r"\)\(", ") (", out)
    # "89unidades" / "1unidade" / "10peças" / "5itens"
    out = _NUM_UNIDADE_COLADA.sub(r"\1 \2", out)

    correcoes = (
        (r"(?i)algumas\s+op(?:ç|c|Ã§)?(?:õ|o|Ãµ|Ãµes)?(?:es|ões|oes|Ãµes)?", "algumas opções"),
        (r"(?i)algumasop(?:ç|c|Ã§)?(?:õ|o|Ãµ)?(?:es|ões|oes|Ãµes)?", "algumas opções"),
        (r"(?i)algumasopÃ\S{0,8}", "algumas opções"),
        (r"(?i)para\s+uso\s+pessoal", "para uso pessoal"),
        (r"(?i)parauso", "para uso"),
        (r"(?i)para\s*uso", "para uso"),
    )
    for padrao, repl in correcoes:
        out = re.sub(padrao, repl, out)

    # Reforço literal
    literais = (
        ("algumasopções", "algumas opções"),
        ("algumasopcoes", "algumas opções"),
        ("Algumasopções", "Algumas opções"),
        ("algumasopÃ§Ãµes", "algumas opções"),
        ("parauso", "para uso"),
        (")(", ") ("),
        (")(temos", ") (temos"),
    )
    for a, b in literais:
        out = out.replace(a, b)

    # Segunda passagem de número+unidade (após literais)
    out = _NUM_UNIDADE_COLADA.sub(r"\1 \2", out)

    out = re.sub(r"([.,;:!?])([A-Za-zÁ-ú])", r"\1 \2", out)
    out = re.sub(r"[^\S\n]{2,}", " ", out)
    return out.strip()


def texto_para_exibicao(texto: str) -> str:
    """Pipeline seguro: mojibake → espaços (para nomes/respostas)."""
    return garantir_espacos_whatsapp(reparar_mojibake(texto or ""))


def aplicar_formatador_final(texto: str) -> tuple[str, dict]:
    """Última camada antes de /chat JSON e envio WhatsApp.

    Sempre aplica correções (não depende só do detector).
    Debug é calculado sobre a string FINAL retornada.
    """
    bruto = texto or ""
    tinha = tem_espaco_colado(bruto)

    # Ordem fixa: mojibake → espaços (sempre)
    passo1 = corrigir_mojibake_exibicao(bruto)
    formatado = garantir_espacos_whatsapp(passo1)
    # Segunda passagem obrigatória
    formatado = garantir_espacos_whatsapp(formatado)

    # Nuclear: se ainda detectar colagem, força literais
    if tem_espaco_colado(formatado):
        formatado = formatado.replace(")(", ") (")
        formatado = re.sub(r"(?i)algumas(?=op)", "algumas ", formatado)
        formatado = re.sub(r"(?i)para(?=uso)", "para ", formatado)
        formatado = re.sub(r"(?i)algumasop\S{0,12}", "algumas opções", formatado)
        formatado = re.sub(r"(?i)parauso", "para uso", formatado)
        formatado = _NUM_UNIDADE_COLADA.sub(r"\1 \2", formatado)
        formatado = garantir_espacos_whatsapp(formatado)

    depois = tem_espaco_colado(formatado)
    # Amostra da string FINAL (mesma que deve ir no JSON)
    amostra = formatado
    if "algumas" in formatado.lower():
        i = formatado.lower().find("algumas")
        amostra = formatado[i : i + 48]
    elif ")(" in formatado or "temos" in formatado.lower():
        j = formatado.find(")(")
        if j < 0:
            j = formatado.lower().find("temos")
        amostra = formatado[max(0, j - 12) : j + 36]
    else:
        m_u = _NUM_UNIDADE_COLADA.search(formatado)
        if m_u:
            amostra = formatado[max(0, m_u.start() - 8) : m_u.end() + 12]


    debug = {
        "formatador_final_aplicado": True,
        "tinha_espaco_colado_antes": bool(tinha),
        "tem_espaco_colado_depois": bool(depois),
        "amostra_resposta_final": amostra[:80],
    }
    return formatado, debug
