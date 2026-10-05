def calcular_media(numeros):
    """Retorna a média aritmética de uma lista de números.

    Args:
        numeros (list[float | int]): Lista de números.

    Returns:
        float: Média dos números. Retorna 0 para lista vazia.
    """
    if not numeros:
        return 0.0
    return sum(numeros) / len(numeros)
