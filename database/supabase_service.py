from database.supabase import supabase


def buscar_cliente(telefone):

    resultado = (
        supabase.table("clientes")
        .select("*")
        .eq("telefone", telefone)
        .execute()
    )

    if resultado.data:
        return resultado.data[0]

    return None


def criar_cliente(telefone):

    resultado = (
        supabase.table("clientes")
        .insert({
            "telefone": telefone
        })
        .execute()
    )

    return resultado.data[0]


def salvar_mensagem(cliente_id, tipo, mensagem):

    supabase.table("conversas").insert({
        "cliente_id": cliente_id,
        "tipo": tipo,
        "mensagem": mensagem
    }).execute()


def buscar_historico(cliente_id):

    resultado = (
        supabase.table("conversas")
        .select("*")
        .eq("cliente_id", cliente_id)
        .order("criado_em")
        .execute()
    )

    return resultado.data


def atualizar_historico_json(cliente_id):

    historico = buscar_historico(cliente_id)

    historico_json = []

    for msg in historico:

        historico_json.append({
            "role": "user" if msg["tipo"] == "cliente" else "assistant",
            "content": msg["mensagem"],
            "timestamp": str(msg["criado_em"])
        })

    (
        supabase.table("clientes")
        .update({
            "historico": historico_json
        })
        .eq("id", cliente_id)
        .execute()
    )