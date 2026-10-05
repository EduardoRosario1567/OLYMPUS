def normalizar_nome(nome):
    nome = nome.strip()
    nome = ' '.join(nome.split())
    return nome.title()
