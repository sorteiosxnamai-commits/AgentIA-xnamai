"""Probe sandbox Mercos para path de tipos de pedido (sem imprimir tokens)."""

from __future__ import annotations

import os
import sys

# carrega .env sem ecoar
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.env_loader import carregar_env

carregar_env()

from services.mercos_homolog_service import (
    _CACHE_PATH_TIPOS_PEDIDO,
    caminhos_candidatos_tipos_pedido,
    listar_tipos_pedido_descoberta,
)
from services.mercos_service import mercos_configurado


def main() -> int:
    if not mercos_configurado():
        print("PROBE_TIPOS_PEDIDO: mercos_nao_configurado")
        return 2
    # força rediscovery
    import services.mercos_homolog_service as svc

    svc._CACHE_PATH_TIPOS_PEDIDO = None
    candidatos = caminhos_candidatos_tipos_pedido()
    print("PROBE_TIPOS_PEDIDO: candidatos=", len(candidatos))
    for p in candidatos:
        print("  -", p)
    out = listar_tipos_pedido_descoberta(pagina_inicial=1, max_paginas=1)
    if out.get("ok") and out.get("path_resolvido"):
        print("PROBE_TIPOS_PEDIDO: OK path=", out.get("path_resolvido"))
        print("PROBE_TIPOS_PEDIDO: total=", out.get("total"))
        nomes = [
            str(i.get("nome") or i.get("name") or "")
            for i in (out.get("itens") or [])[:20]
        ]
        match = [
            n
            for n in nomes
            if n.lower().startswith("19814a3") or n.lower().startswith("198314a3")
        ]
        print("PROBE_TIPOS_PEDIDO: amostra_nomes=", nomes[:5])
        print("PROBE_TIPOS_PEDIDO: match_19814a3_ou_198314a3=", match[:5])
        return 0
    print("PROBE_TIPOS_PEDIDO: FALHA 404")
    print("PROBE_TIPOS_PEDIDO: paths_testados=", out.get("paths_testados"))
    print("PROBE_TIPOS_PEDIDO: mensagem=", (out.get("mensagem") or "")[:300])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
