def calcular_desconto(valor: float, percentual: float) -> float:
    """
    Calcula o valor do desconto a partir de um valor e percentual de desconto.

    Args:
        valor (float): Valor original.
        percentual (float): Percentual de desconto a ser aplicado.

    Returns:
        float: Valor após aplicação do desconto.
    """
    desconto = valor * (percentual / 100)
    return valor - desconto
