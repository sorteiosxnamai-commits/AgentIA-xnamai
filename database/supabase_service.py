from database.supabase import supabase


# =========================
# CLIENTES
# =========================

def buscar_cliente(telefone):

    resultado = (
        supabase.table("clientes")
        .select("*")
        .eq("telefone", telefone)
        .execute()
    )

    if resultado.data:
        return resultado.data[0]

    return Nonesss


    


def criar_cliente(telefone):

    resultado = (
        supabase.table("clientes")
        .insert({
            "telefone": telefone
        })
        .execute()
    )

    return resultado.data[0]


# =========================
# CONVERSAS
# =========================

def salvar_mensagem(cliente_id, tipo, mensagem):

    resultado = (
        supabase.table("conversas")
        .insert({
            "cliente_id": cliente_id,
            "tipo": tipo,
            "mensagem": mensagem
        })
        .execute()
    )

    return resultado


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

    resultado = (
        supabase.table("clientes")
        .update({
            "historico": historico_json
        })
        .eq("id", cliente_id)
        .execute()
    )

    return resultado


# =========================
# PRODUTOS
# =========================

def buscar_produtos():

    resultado = (
        supabase.table("produtos")
        .select("*")
        .execute()
    )

    print("================================")
    print("DADOS PRODUTOS:")
    print(resultado.data)
    print("================================")

    return resultado.data

    print("RESULTADO PRODUTOS:")
    print(resultado.data)

    return resultado.data

    print("================================")
    print("RESULTADO PRODUTOS:")
    print(resultado)

    print("DADOS PRODUTOS:")
    print(resultado.data)
    print("================================")

    return resultado.data

    


def buscar_produto_por_nome(nome):

    resultado = (
        supabase.table("produtos")
        .select("*")
        .ilike("nome", f"%{nome}%")
        .execute()
    )

    return resultado.data


def buscar_produto_por_id(produto_id):

    resultado = (
        supabase.table("produtos")
        .select("*")
        .eq("id", produto_id)
        .execute()
    )

    

    if resultado.data:
        return resultado.data[0]
    
    

    return None

def criar_lead(cliente_id, interesse):

    resultado = (
        supabase.table("leads")
        .insert({
            "cliente_id": cliente_id,
            "interesse": interesse,
            "status": "novo"
        })
        .execute()
    )

    print("LEAD CRIADO:")
    print(resultado)

    return resultado

def buscar_lead(cliente_id, interesse):

    resultado = (
        supabase.table("leads")
        .select("*")
        .eq("cliente_id", cliente_id)
        .eq("interesse", interesse)
        .execute()
    )

    if resultado.data:
        return resultado.data[0]

    return None