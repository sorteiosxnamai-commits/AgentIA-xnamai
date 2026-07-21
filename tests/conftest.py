"""Fixtures compartilhadas dos testes.

Isola o estado do throttling GLOBAL persistente da Mercos em um diretório
temporário por teste e zera o intervalo mínimo por padrão, para não introduzir
esperas reais nem vazar estado entre testes. Testes específicos de throttling
reconfiguram o intervalo (ex.: 8s) e injetam relógio/sono falsos.
"""

from __future__ import annotations

import pytest

from services import mercos_throttle


@pytest.fixture(autouse=True)
def _isolar_throttle_mercos(tmp_path, monkeypatch):
    diretorio = tmp_path / "mercos_throttle"
    monkeypatch.setenv("MERCOS_THROTTLE_DIR", str(diretorio))
    monkeypatch.setenv("MERCOS_THROTTLE_INTERVALO_SEGUNDOS", "0")
    mercos_throttle._reset_para_testes()
    yield
    mercos_throttle._reset_para_testes()
