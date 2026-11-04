"""Metricas de confiabilidade do enlace, calculadas a partir dos pacotes gravados."""
from datetime import datetime

MODULO_CONTADOR = 65536  # o contador do pacote tem 16 bits e volta a 0

# Um salto maior que este nao conta como perda: o CubeSat reiniciou ou ficou fora de
# alcance, e nao ha como saber quantos pacotes foram de fato transmitidos nesse intervalo.
LIMITE_SALTO = 256

# Bytes iguais só contam como a mesma transmissão se chegarem perto no tempo
JANELA_MESMA_TRANSMISSAO_S = 60


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
        "rssi_medio": _media(linhas, "rssi"),
        "snr_medio": _media(linhas, "snr"),
    }


def _media(linhas, campo):
    valores = [linha[campo] for linha in linhas if linha.get(campo) is not None]
    return sum(valores) / len(valores) if valores else None


def _agrupar(linhas, chave):
    grupos = {}
    for linha in linhas:
        grupos.setdefault(chave(linha), []).append(linha)
    return grupos


def _origem(linha):
    return (linha.get("receptor_id"), linha.get("frequencia_mhz"))


def _ordem(valor):
    """Permite ordenar chaves em que alguns valores são None, como em linhas antigas."""
    return tuple((item is None, item or 0) for item in valor)


def calcular_por_origem(linhas):
    """Calcula uma linha de estatísticas por receptor e frequência.

    Cada receptor tem o próprio contador de lacunas: o mesmo pacote chega a vários deles,
    então misturá-los faria um receptor esconder as perdas do outro.
    """
    grupos = _agrupar(linhas, _origem)
    return [
        {"receptor_id": origem[0], "frequencia_mhz": origem[1], **calcular_enlace(grupos[origem])}
        for origem in sorted(grupos, key=_ordem)
    ]


def _momento(linha):
    try:
        return datetime.fromisoformat(linha.get("data_hora") or "")
    except ValueError:
        return None


def _mesma_transmissao(grupo, linha):
    anterior, atual = _momento(grupo[-1]), _momento(linha)
    if anterior is None or atual is None:
        return True
    return abs((atual - anterior).total_seconds()) <= JANELA_MESMA_TRANSMISSAO_S


def agrupar_transmissoes(linhas):
    """Junta as cópias de uma transmissão, recebidas por receptores diferentes.

    Os bytes do pacote identificam a transmissão; sem eles, em linhas antigas, vale o contador.
    O receptor que recebeu a mesma cópia duas vezes não muda o resultado: é só uma repetição.
    """
    grupos = []
    abertos = {}
    for linha in linhas:
        chave = linha.get("raw") or (linha.get("cubesat_id"), linha.get("contador"))
        grupo = abertos.get(chave)
        if grupo is None or not _mesma_transmissao(grupo, linha):
            grupo = []
            grupos.append(grupo)
            abertos[chave] = grupo
        grupo.append(linha)
    return grupos


def consolidar(linhas):
    """Uma linha por transmissão: a cópia de melhor RSSI, com a lista de quem recebeu."""
    consolidados = []
    for grupo in agrupar_transmissoes(linhas):
        melhor = max(grupo, key=lambda l: (l.get("rssi") is not None, l.get("rssi") or 0))
        receptores = sorted({l.get("receptor_id") for l in grupo if l.get("receptor_id") is not None})
        consolidados.append({**melhor, "copias": len(grupo), "receptores": receptores})
    return consolidados


def calcular_agregado(linhas):
    """Com vários receptores, uma transmissão conta como recebida se qualquer um deles a recebeu.

    O ganho de diversidade é quanto o conjunto recebe a mais que o melhor receptor sozinho.
    """
    por_origem = calcular_por_origem(linhas)
    if len(por_origem) <= 1:
        return {**calcular_enlace(linhas), "combinado": False}
    unicos = calcular_enlace(consolidar(linhas))
    melhor_taxa = max(item["taxa_recepcao"] or 0 for item in por_origem)
    return {
        **unicos,
        # Soma de cópias: outro receptor pode ter recebido íntegro o que este descartou
        "corrompidos": sum(item["corrompidos"] for item in por_origem),
        "nao_chegaram": unicos["esperados"] - unicos["recebidos"],
        "rssi_medio": _media(linhas, "rssi"),
        "snr_medio": _media(linhas, "snr"),
        "combinado": True,
        "origens": len(por_origem),
        "copias_extras": len(linhas) - unicos["recebidos"],
        "melhor_taxa_individual": melhor_taxa,
        "ganho_diversidade": unicos["taxa_recepcao"] - melhor_taxa,
    }


def calcular_por_hora(linhas):
    """Estatísticas por hora (UTC), receptor e frequência, da hora mais recente para a mais antiga."""
    def hora(linha):
        return (linha.get("data_hora") or "")[:13]

    grupos = _agrupar(linhas, hora)
    resultado = []
    for periodo in sorted(grupos, reverse=True):
        for item in calcular_por_origem(grupos[periodo]):
            resultado.append({"periodo": f"{periodo}:00:00", **item})
    return resultado
