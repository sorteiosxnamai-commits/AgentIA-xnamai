"""Instruções locais AgentXnamai (AGENT_PROMPT_SOURCE=local)."""

from __future__ import annotations

from pathlib import Path

import pytest

import agents.vendas.instructions as instructions


def test_arquivo_limpo_existe_na_raiz():
    raiz = Path(__file__).resolve().parents[1]
    path = raiz / "AgentXnamai_instrucoes_limpo.txt"
    assert path.is_file()
    texto = path.read_text(encoding="utf-8")
    assert "PAGAMENTO PIX" in texto
    # Sem duplicação grosseira do bloco inicial
    assert texto.count("Você é o Agente de Vendas oficial da xNamai.") == 1


def test_build_system_instructions_identidade_xnamai():
    instructions.invalidar_cache_instrucoes()
    texto = instructions.build_system_instructions()
    baixa = texto.lower()
    assert "agente de vendas oficial da xnamai" in baixa
    assert "assistente de vendas da xnamai" in baixa
    assert "NewStore" in texto  # na lista do que NUNCA dizer
    assert "Nunca diga que trabalha para" in texto


def test_build_system_instructions_whatsapp_curto_e_tres_produtos():
    texto = instructions.build_system_instructions()
    assert "WhatsApp" in texto
    assert "Respostas normalmente curtas" in texto
    assert "até três opções" in texto
    assert "uma pergunta útil por vez" in texto.lower() or "Faça poucas perguntas" in texto


def test_build_system_instructions_proibe_inventar_preco_estoque():
    texto = instructions.build_system_instructions().lower()
    assert "nunca invente" in texto
    assert "preço" in texto or "preco" in texto
    assert "estoque" in texto
    assert "somente os valores fornecidos pelas ferramentas" in texto or (
        "dados fornecidos pelas ferramentas" in texto
    )


def test_build_system_instructions_continuidade_contexto():
    texto = instructions.build_system_instructions()
    assert "CONTINUIDADE DE ASSUNTO" in texto
    assert "REFERÊNCIAS CONTEXTUAIS" in texto
    assert "esse produto" in texto.lower() or "o primeiro" in texto.lower()
    assert "Não repita perguntas já respondidas" in texto


def test_build_system_instructions_pagamento_pix_seguro():
    texto = instructions.build_system_instructions()
    assert "PAGAMENTO PIX" in texto
    assert "criar_cobranca_pix" in texto
    assert "Nunca gere, invente, simule ou altere" in texto
    assert "pix_copia_cola" in texto or "código Pix" in texto or "codigo Pix" in texto.lower()
    assert "pix_temporariamente_indisponivel" in texto
    assert "status pago" in texto.lower() or "status do pagamento" in texto.lower()
    # Pagamento só confirma pelo backend
    assert "Nunca considere um pagamento aprovado porque o cliente disse" in texto


def test_prompt_nao_esta_no_env_example():
    env_ex = Path(__file__).resolve().parents[1] / ".env.example"
    if env_ex.is_file():
        src = env_ex.read_text(encoding="utf-8")
        assert "Você é o Agente de Vendas oficial" not in src
        assert "PAGAMENTO PIX" not in src


def test_caminho_instrucoes_baseado_em_file_nao_cwd(monkeypatch, tmp_path):
    """Caminho vem de __file__, não do diretório atual do processo."""
    instructions.invalidar_cache_instrucoes()
    monkeypatch.chdir(tmp_path)
    path = instructions._caminho_instrucoes_limpo()
    assert path.is_absolute()
    assert path.name == "AgentXnamai_instrucoes_limpo.txt"
    assert path.is_file()
    # Continua resolvendo mesmo com CWD vazio / sem o TXT
    assert Path.cwd() == tmp_path
    assert not (tmp_path / path.name).exists()
    texto = instructions.build_system_instructions()
    assert len(texto) > 500
    assert "PAGAMENTO PIX" in texto


def test_arquivo_ausente_erro_claro_nao_prompt_vazio(monkeypatch, tmp_path):
    instructions.invalidar_cache_instrucoes()
    fake = tmp_path / "AgentXnamai_instrucoes_limpo.txt"
    monkeypatch.setattr(
        instructions,
        "_candidatos_caminho_instrucoes",
        lambda: [fake, tmp_path / "outro.txt"],
    )
    with pytest.raises(FileNotFoundError) as exc:
        instructions.build_system_instructions()
    msg = str(exc.value)
    assert "não pode iniciar" in msg.lower() or "ausentes" in msg.lower()
    assert "AgentXnamai_instrucoes_limpo.txt" in msg


def test_arquivo_vazio_erro_claro(monkeypatch, tmp_path):
    instructions.invalidar_cache_instrucoes()
    vazio = tmp_path / "AgentXnamai_instrucoes_limpo.txt"
    vazio.write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(
        instructions,
        "_candidatos_caminho_instrucoes",
        lambda: [vazio],
    )
    with pytest.raises(ValueError) as exc:
        instructions.build_system_instructions()
    assert "vazio" in str(exc.value).lower()


def test_txt_sem_segredos_obvios():
    raiz = Path(__file__).resolve().parents[1]
    texto = (raiz / "AgentXnamai_instrucoes_limpo.txt").read_text(encoding="utf-8")
    baixa = texto.lower()
    for marcador in (
        "sk-",
        "sb_secret_",
        "app_usr-",
        "bearer ",
        "api_key=",
        "openai_api_key",
        "supabase_key",
        "mercos_application_token",
        "mp_access_token",
    ):
        assert marcador not in baixa
    # A palavra "tokens" só aparece na lista do que NÃO revelar
    assert "nunca revele" in baixa
    assert "- tokens;" in baixa or "tokens;" in baixa
