def calcular_percentual_sucesso(total_execucoes, execucoes_sucesso):
    if total_execucoes == 0:
        return 0
    return (execucoes_sucesso / total_execucoes) * 100
