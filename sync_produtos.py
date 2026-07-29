"""Sincroniza produtos da Mercos para o Supabase.

Uso:
    python sync_produtos.py --dry-run
    python sync_produtos.py
"""

from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv

load_dotenv()

from services.sync_mercos_service import sincronizar_produtos_mercos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sincroniza produtos Mercos → Supabase (public.produtos)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Não grava no banco; apenas resume (recebidos, vínculos, novos, ambíguos…).",
    )
    args = parser.parse_args()
    resultado = sincronizar_produtos_mercos(dry_run=bool(args.dry_run))
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
