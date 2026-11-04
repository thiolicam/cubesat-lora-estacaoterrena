"""Metricas de confiabilidade do enlace, calculadas a partir dos pacotes gravados."""

MODULO_CONTADOR = 65536  # o contador do pacote tem 16 bits e volta a 0

# Um salto maior que este nao conta como perda: o CubeSat reiniciou ou ficou fora de
# alcance, e nao ha como saber quantos pacotes foram de fato transmitidos nesse intervalo.
LIMITE_SALTO = 256


def _contar_corrompidos(linhas):
    """Soma os inválidos do período; os contadores voltam a zero se a estação reiniciar."""
    total = 0
    inicio = ultimo = validos_anterior = None
    for linha in linhas:
        validos, invalidos = linha.get("validos"), linha.get("invalidos")
        if validos is None or invalidos is None:
            continue
        if validos_anterior is None or validos < validos_anterior:
            if ultimo is not None:
                total += ultimo - inicio
            # validos == 1: a estação acabou de ligar, entao os inválidos sao todos deste período
            inicio = 0 if validos == 1 else invalidos
        ultimo = invalidos
        validos_anterior = validos
    if ultimo is not None:
        total += ultimo - inicio
    return total


def calcular_enlace(linhas):
    """Recebe linhas em ordem cronológica, com contador, validos e invalidos.

    Pacote que não chegou íntegro aparece como lacuna no contador, seja por perda ou por
    corrupção. Os inválidos separam os dois casos: corrompidos chegaram, os demais não.
    """
    esperados = recebidos = interrupcoes = 0
    anterior = None
    for linha in linhas:
        contador = linha.get("contador")
        if contador is None:
            continue
        if anterior is None:
            esperados += 1
        else:
            salto = (contador - anterior) % MODULO_CONTADOR
            if salto == 0:
                continue  # pacote repetido
            if salto > LIMITE_SALTO:
                interrupcoes += 1
                esperados += 1
            else:
                esperados += salto
        recebidos += 1
        anterior = contador

    corrompidos = _contar_corrompidos(linhas)
    return {
        "esperados": esperados,
        "recebidos": recebidos,
        "corrompidos": corrompidos,
        "nao_chegaram": max(0, esperados - recebidos - corrompidos),
        "interrupcoes": interrupcoes,
        "taxa_recepcao": recebidos / esperados if esperados else None,
    }
