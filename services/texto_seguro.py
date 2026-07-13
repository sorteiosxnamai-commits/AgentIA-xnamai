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

_UNIDADES_ALT = r"(unidades|unidade|peças|pecas|itens)"

# Qualquer separador (vazio, espaço, NBSP, ZWSP, soft-hyphen…) → espaço ASCII
# (\d+)[\s\u00A0\u200B\u200C\u200D\u2060\uFEFF\u00AD]*(unidades|…)
_NUM_UNIDADE_SEP = (
    r"[\s\u00A0\u200B\u200C\u200D\u2060\uFEFF\u00AD\u200E\u200F\u034F"
    r"\u2000-\u200A\u202F\u205F\u3000]*"
)
_NUM_UNIDADE_NORMALIZAR = re.compile(
    rf"(?i)(\d+)({_NUM_UNIDADE_SEP})({_UNIDADES_ALT})\b"
)
# Após remover invisíveis: dígito colado na unidade
_NUM_UNIDADE_STRIPPED = re.compile(rf"(?i)\d+(?:unidades|unidade|peças|pecas|itens)\b")


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


def _separar_numero_unidade(texto: str) -> str:
    """Normaliza número+unidade para sempre ter espaço ASCII.

    89unidades / 89\\u200bunidades / 89\\u00a0unidades / 89 unidades → 89 unidades
    """
    if not texto:
        return ""
    return _NUM_UNIDADE_NORMALIZAR.sub(r"\1 \3", texto)


def tem_numero_unidade_colado(texto: str) -> bool:
    """True se há dígito + (vazio/invisível/NBSP/espaços estranhos) + unidade.

    '89 unidades' (um espaço ASCII) NÃO conta como colado.
    """
    bruto = texto or ""
    if not bruto:
        return False
    for m in _NUM_UNIDADE_NORMALIZAR.finditer(bruto):
        mid = m.group(2)
        if mid != " ":
            return True
    # Após strip de invisíveis, \d+unidades sem espaço
    limpo = _strip_invisiveis(bruto)
    limpo_nbsp = limpo.replace("\u00a0", "")
    if _NUM_UNIDADE_STRIPPED.search(limpo_nbsp):
        return True
    if "89unidades" in limpo_nbsp or "temos 89unidades" in limpo_nbsp.lower():
        return True
    return False


def resposta_tem_89unidades(texto: str) -> bool:
    """True se ainda há 89 + (não-espaço-ASCII) + unidades."""
    bruto = texto or ""
    for m in re.finditer(r"(?i)89(.{0,8})unidades\b", bruto):
        mid = m.group(1)
        if mid != " ":
            return True
    limpo = _strip_invisiveis(bruto).replace("\u00a0", "")
    return "89unidades" in limpo


def codepoints_seguros(texto: str, limite: int = 120) -> list[str]:
    """Lista 'c:XXXX' para debug sem quebrar JSON."""
    out: list[str] = []
    for c in (texto or "")[:limite]:
        if c.isprintable() and c not in "\r\n\t":
            out.append(f"{c}:{ord(c):04X}")
        else:
            out.append(f"U+{ord(c):04X}")
    return out


def debug_trecho_notebook(texto: str) -> dict:
    """Amostra segura ao redor de 'Notebook' com codepoints."""
    bruto = texto or ""
    idx = bruto.lower().find("notebook")
    if idx < 0:
        return {
            "trecho_notebook": "",
            "trecho_notebook_codepoints": [],
            "tem_numero_unidade_colado": bool(tem_numero_unidade_colado(bruto)),
        }
    trecho = bruto[idx : idx + 90]
    return {
        "trecho_notebook": trecho,
        "trecho_notebook_codepoints": codepoints_seguros(trecho, 90),
        "tem_numero_unidade_colado": bool(tem_numero_unidade_colado(trecho) or tem_numero_unidade_colado(bruto)),
    }


def tem_espaco_colado(texto: str) -> bool:
    """Detecta colagens — inclusive número + invisível + unidade."""
    bruto = texto or ""
    if not bruto:
        return False
    if tem_numero_unidade_colado(bruto):
        return True
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
        if re.search(r"(?i)algumas[\u00ad\u200b\u200c\u200d\ufeff]*op", t):
            return True
        if "89unidades" in t or "temos 89unidades" in tl:
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
    out = re.sub(r"(?i)algumas(?=op)", "algumas ", out)
    out = re.sub(r"(?i)para(?=uso)", "para ", out)
    out = re.sub(r"\)\(", ") (", out)
    # Normaliza SEMPRE número + qualquer separador + unidade → "N unidade"
    out = _separar_numero_unidade(out)

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

    literais = (
        ("algumasopções", "algumas opções"),
        ("algumasopcoes", "algumas opções"),
        ("Algumasopções", "Algumas opções"),
        ("algumasopÃ§Ãµes", "algumas opções"),
        ("parauso", "para uso"),
        (")(", ") ("),
        (")(temos", ") (temos"),
        ("89unidades", "89 unidades"),
        ("1unidade", "1 unidade"),
        ("10peças", "10 peças"),
        ("10pecas", "10 pecas"),
        ("5itens", "5 itens"),
        ("temos 89unidades", "temos 89 unidades"),
    )
    for a, b in literais:
        out = out.replace(a, b)

    out = _separar_numero_unidade(out)
    out = re.sub(r"([.,;:!?])([A-Za-zÁ-ú])", r"\1 \2", out)
    out = re.sub(r"[^\S\n]{2,}", " ", out)
    # Última passagem: garante espaço ASCII em número+unidade
    out = _separar_numero_unidade(out)
    return out.strip()


def texto_para_exibicao(texto: str) -> str:
    """Pipeline seguro: mojibake → espaços (para nomes/respostas)."""
    return garantir_espacos_whatsapp(reparar_mojibake(texto or ""))


def aplicar_formatador_final(texto: str) -> tuple[str, dict]:
    """Última camada antes de /chat JSON e envio WhatsApp.

    Ordem: mojibake → espaços → normalização número+unidade → debug na string final.
    """
    bruto = texto or ""
    tinha = tem_espaco_colado(bruto)

    passo1 = corrigir_mojibake_exibicao(bruto)
    formatado = garantir_espacos_whatsapp(passo1)
    formatado = garantir_espacos_whatsapp(formatado)

    if tem_espaco_colado(formatado):
        formatado = formatado.replace(")(", ") (")
        formatado = re.sub(r"(?i)algumas(?=op)", "algumas ", formatado)
        formatado = re.sub(r"(?i)para(?=uso)", "para ", formatado)
        formatado = re.sub(r"(?i)algumasop\S{0,12}", "algumas opções", formatado)
        formatado = re.sub(r"(?i)parauso", "para uso", formatado)
        formatado = formatado.replace("89unidades", "89 unidades")
        formatado = formatado.replace("1unidade", "1 unidade")
        formatado = formatado.replace("10peças", "10 peças")
        formatado = formatado.replace("10pecas", "10 pecas")
        formatado = formatado.replace("5itens", "5 itens")
        formatado = garantir_espacos_whatsapp(formatado)

    # Obrigatório: normalizar número+unidade DEPOIS do mojibake e ANTES do return
    formatado = _separar_numero_unidade(formatado)

    depois = tem_espaco_colado(formatado)
    tem_89 = resposta_tem_89unidades(formatado)
    num_colado = tem_numero_unidade_colado(formatado)
    if tem_89 or num_colado:
        depois = True

    amostra = formatado
    if "algumas" in formatado.lower():
        i = formatado.lower().find("algumas")
        amostra = formatado[i : i + 48]
    elif "temos" in formatado.lower():
        j = formatado.lower().find("temos")
        amostra = formatado[max(0, j - 12) : j + 36]

    nb = debug_trecho_notebook(formatado)
    debug = {
        "formatador_final_aplicado": True,
        "tinha_espaco_colado_antes": bool(tinha),
        "tem_espaco_colado_depois": bool(depois),
        "resposta_final_tem_89unidades": bool(tem_89),
        "tem_numero_unidade_colado": bool(num_colado),
        "trecho_notebook": nb["trecho_notebook"],
        "trecho_notebook_codepoints": nb["trecho_notebook_codepoints"],
        "amostra_resposta_final": amostra[:80],
    }
    return formatado, debug
