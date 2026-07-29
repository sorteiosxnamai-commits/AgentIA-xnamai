"""Instruções de sistema — Agente de Vendas da xNamai (AGENT_PROMPT_SOURCE=local)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_NOME_ARQUIVO = "AgentXnamai_instrucoes_limpo.txt"

# Apêndice operacional: alinhado ao Product Service / catálogo pré-carregado atual.
# Não substitui o texto principal; reforça que fatos comerciais vêm do catálogo real.
_APENDICE_OPERACAO = """
============================================================
OPERAÇÃO (CATÁLOGO E FERRAMENTAS)
============================================================

- Se o contexto trouxer CATÁLOGO PRÉ-CARREGADO / produtos do Product Service,
  USE esses dados e NÃO chame search_products, get_product, check_inventory
  nem get_product_price desnecessariamente (evita busca duplicada).
- Só use ferramentas de produto quando o contexto NÃO tiver catálogo útil.
- Produtos, preços e estoque devem vir SOMENTE do catálogo real ou das
  ferramentas — nunca invente esses dados.
- Apresente normalmente até três opções de produto por vez, salvo pedido
  explícito de mais opções com resultados reais suficientes.
- Respostas curtas e naturais para WhatsApp; uma pergunta útil por vez.
""".strip()


def _candidatos_caminho_instrucoes() -> list[Path]:
    """Caminhos absolutos derivados de __file__ (independentes do CWD).

    Ordem:
      1) raiz do projeto (agents/vendas/../../AgentXnamai_instrucoes_limpo.txt)
      2) ao lado deste módulo (agents/vendas/) — opcional em deploys customizados
    """
    aqui = Path(__file__).resolve()
    return [
        aqui.parents[2] / _NOME_ARQUIVO,  # agente-vendas-python/
        aqui.parent / _NOME_ARQUIVO,  # agents/vendas/
    ]


def _caminho_instrucoes_limpo() -> Path:
    """Primeiro caminho existente; se nenhum, o canônico na raiz do projeto."""
    candidatos = _candidatos_caminho_instrucoes()
    for path in candidatos:
        if path.is_file():
            return path
    return candidatos[0]


@lru_cache(maxsize=1)
def _carregar_instrucoes_base() -> str:
    path = _caminho_instrucoes_limpo()
    if not path.is_file():
        tentados = " | ".join(str(p) for p in _candidatos_caminho_instrucoes())
        raise FileNotFoundError(
            "Instruções locais ausentes — o agente não pode iniciar sem o system prompt. "
            f"Arquivo esperado: {_NOME_ARQUIVO}. "
            f"Caminhos tentados (baseados em __file__, não no CWD): {tentados}. "
            "Inclua o TXT no repositório (necessário no deploy Render)."
        )
    try:
        texto = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(
            f"Falha ao ler instruções locais em {path}: {exc}. "
            "O agente não pode iniciar com prompt vazio."
        ) from exc

    if not texto:
        raise ValueError(
            f"Arquivo de instruções vazio: {path}. "
            "O agente não pode iniciar com system prompt vazio."
        )
    if "PAGAMENTO PIX" not in texto:
        raise ValueError(
            f"{path.name} deve conter a seção PAGAMENTO PIX (arquivo incompleto)."
        )
    if "xNamai" not in texto and "xnamai" not in texto.lower():
        raise ValueError(
            f"{path.name} parece inválido (identidade xNamai ausente)."
        )
    return texto


def build_system_instructions() -> str:
    """System prompt local usado quando AGENT_PROMPT_SOURCE=local.

    Nunca retorna string vazia: falha cedo se o TXT estiver ausente/inválido.
    """
    base = _carregar_instrucoes_base()
    out = f"{base}\n\n{_APENDICE_OPERACAO}".strip()
    if not out:
        raise RuntimeError("build_system_instructions produziu prompt vazio.")
    return out


def invalidar_cache_instrucoes() -> None:
    """Utilitário para testes que alteram o arquivo em disco."""
    _carregar_instrucoes_base.cache_clear()
