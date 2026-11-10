"""Gera o resumo em Markdown de um teste, com os dados gravados no banco.

Exemplo, para o ensaio de 1 hora do MVP (S5.3):
    python server/relatorio_testes.py --desde "2026-11-05 14:00" --minimo-horas 1 --saida docs/ensaio-mvp.md
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard"))
from metricas import calcular_agregado, calcular_por_origem

BANCO_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "estacao.db")
SILENCIO_MAXIMO_S = 60
FORMATO_BANCO = "%Y-%m-%d %H:%M:%S"


def local_para_banco(texto):
    """O banco guarda UTC; quem usa o relatório informa o horário local."""
    return datetime.fromisoformat(texto).astimezone(timezone.utc).strftime(FORMATO_BANCO)


def banco_para_local(texto):
    return datetime.strptime(texto, FORMATO_BANCO).replace(tzinfo=timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M:%S")


def ler_dados(caminho, desde=None):
    uri = "file:" + os.path.abspath(caminho).replace("\\", "/") + "?mode=ro"
    conexao = sqlite3.connect(uri, uri=True)
    conexao.row_factory = sqlite3.Row
    filtro, parametros = ("WHERE {campo} >= ?", (desde,)) if desde else ("", ())
    pacotes = [dict(l) for l in conexao.execute(
        f"SELECT * FROM pacotes {filtro.format(campo='data_hora')} ORDER BY id", parametros)]
    comandos = conexao.execute(
        f"SELECT estado, COUNT(*) FROM comandos {filtro.format(campo='criado_em')} GROUP BY estado ORDER BY estado",
        parametros).fetchall()
    conexao.close()
    return pacotes, [tuple(c) for c in comandos]


def medir_periodo(pacotes):
    """Retorna a duração em segundos e o maior intervalo sem nenhum pacote."""
    momentos = sorted(datetime.strptime(p["data_hora"], FORMATO_BANCO) for p in pacotes)
    duracao = (momentos[-1] - momentos[0]).total_seconds()
    silencio = max(((b - a).total_seconds() for a, b in zip(momentos, momentos[1:])), default=0)
    return duracao, silencio


def contar_estranhos(pacotes):
    """Pacotes de outros aparelhos no período; o contador da estação zera se ela reiniciar."""
    total, anterior = 0, None
    for p in pacotes:
        valor = p.get("estranhos")
        if valor is None:
            continue
        if anterior is None:
            total += valor if p.get("validos") == 1 else 0
        elif valor >= anterior:
            total += valor - anterior
        else:
            total += valor
        anterior = valor
    return total if anterior is not None else None


def texto_duracao(segundos):
    horas, resto = divmod(int(segundos), 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas} h {minutos} min {segundos} s"


def porcentagem(taxa):
    return "–" if taxa is None else f"{taxa * 100:.1f}%".replace(".", ",")


def decimal(valor, casas=1):
    return "–" if valor is None else f"{valor:.{casas}f}".replace(".", ",")


def avaliar(duracao, silencio, minimo_horas):
    """Só aprova se o sistema operou o tempo pedido, sem ficar parado no meio."""
    problemas = []
    if duracao < minimo_horas * 3600:
        problemas.append(f"duração abaixo de {minimo_horas:g} h")
    if silencio > SILENCIO_MAXIMO_S:
        problemas.append(f"{texto_duracao(silencio)} sem pacotes; limite de {SILENCIO_MAXIMO_S} s")
    return problemas


def gerar_relatorio(pacotes, comandos, minimo_horas=None, origem=""):
    if not pacotes:
        return "# Relatório de teste\n\nNenhum pacote encontrado no período.\n"
    duracao, silencio = medir_periodo(pacotes)
    geral = calcular_agregado(pacotes)
    linhas = [
        "# Relatório de teste",
        "",
    ]
    if origem:
        linhas += [f"Banco: `{origem}`", ""]
    linhas += [
        f"- **Início:** {banco_para_local(pacotes[0]['data_hora'])}",
        f"- **Fim:** {banco_para_local(pacotes[-1]['data_hora'])}",
        f"- **Duração:** {texto_duracao(duracao)}",
        f"- **Maior intervalo sem pacotes:** {texto_duracao(silencio)}",
        f"- **Taxa de recepção:** {porcentagem(geral['taxa_recepcao'])} "
        f"({geral['recebidos']} de {geral['esperados']} transmissões)",
        f"- **Corrompidos:** {geral['corrompidos']}",
        f"- **Não chegaram:** {geral['nao_chegaram']}",
        f"- **Interrupções fora da conta:** {geral['interrupcoes']}",
        f"- **Pacotes de outros aparelhos ignorados:** "
        f"{'não medido (firmware antigo)' if contar_estranhos(pacotes) is None else contar_estranhos(pacotes)}",
        f"- **Sinal médio:** RSSI {decimal(geral['rssi_medio'], 0)} dBm, SNR {decimal(geral['snr_medio'])} dB",
    ]
    if geral["combinado"]:
        linhas.append(f"- **Ganho de diversidade:** +{decimal(geral['ganho_diversidade'] * 100)} p.p. "
                      f"sobre o melhor receptor ({porcentagem(geral['melhor_taxa_individual'])})")
    if minimo_horas is not None:
        problemas = avaliar(duracao, silencio, minimo_horas)
        resultado = "**Aprovado**" if not problemas else f"**Reprovado:** {'; '.join(problemas)}"
        linhas += ["", f"## Critério de {minimo_horas:g} h de operação contínua", "", resultado]

    linhas += ["", "## Por receptor", "",
               "| Receptor | Frequência (MHz) | Recebidos | Esperados | Recepção | Corrompidos | Não chegaram | RSSI médio (dBm) | SNR médio (dB) |",
               "|---|---|---|---|---|---|---|---|---|"]
    for r in calcular_por_origem(pacotes):
        linhas.append(
            f"| {r['receptor_id'] if r['receptor_id'] is not None else '–'} | {decimal(r['frequencia_mhz'])} "
            f"| {r['recebidos']} | {r['esperados']} | {porcentagem(r['taxa_recepcao'])} | {r['corrompidos']} "
            f"| {r['nao_chegaram']} | {decimal(r['rssi_medio'], 0)} | {decimal(r['snr_medio'])} |")

    linhas += ["", "## Comandos", ""]
    if comandos:
        linhas += ["| Situação | Quantidade |", "|---|---|"]
        linhas += [f"| {estado} | {quantidade} |" for estado, quantidade in comandos]
    else:
        linhas.append("Nenhum comando no período.")
    return "\n".join(linhas) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--banco", default=BANCO_PADRAO, help="arquivo do banco (padrão: estacao.db)")
    parser.add_argument("--desde", help='considerar só a partir deste horário local, como "2026-11-05 14:00"')
    parser.add_argument("--minimo-horas", type=float, help="avalia o critério de operação contínua")
    parser.add_argument("--saida", help="grava em um arquivo, em vez de mostrar na tela")
    args = parser.parse_args()

    if not os.path.exists(args.banco):
        sys.exit(f"Banco não encontrado: {args.banco}")
    pacotes, comandos = ler_dados(args.banco, local_para_banco(args.desde) if args.desde else None)
    relatorio = gerar_relatorio(pacotes, comandos, args.minimo_horas, os.path.basename(args.banco))
    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as arquivo:
            arquivo.write(relatorio)
        print(f"Relatório gravado em {args.saida}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(relatorio)


if __name__ == "__main__":
    main()
