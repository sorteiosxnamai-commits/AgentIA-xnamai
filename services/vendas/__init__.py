# Pacote vendas — imports pesados ficam nos módulos (evita ciclo na importação)

__all__ = ["preparar_contexto_venda"]


def __getattr__(name: str):
    if name == "preparar_contexto_venda":
        from services.vendas.contexto import preparar_contexto_venda

        return preparar_contexto_venda
    raise AttributeError(name)
