"""Roda o sistema completo sem placas: simulador + ponte serial + dashboard.

Uso: python simular.py [opcoes do simulador, como --perda 0.2]
Os dados vao para o banco estacao_sim, recriado a cada execucao, e nunca para o estacao.
"""
import os
import socket
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(RAIZ, "server"))
import banco  # noqa: E402
BANCO = os.path.join(RAIZ, "estacao_sim.db")
PORTA_SIMULADOR = 7000
PORTA_DASHBOARD = 5000


def porta_em_uso(porta):
    with socket.socket() as teste:
        teste.settimeout(1)
        return teste.connect_ex(("127.0.0.1", porta)) == 0


def main():
    # No Windows, dois servidores conseguem usar a mesma porta e o banco seria recriado por cima
    if porta_em_uso(PORTA_DASHBOARD):
        sys.exit(f"A porta {PORTA_DASHBOARD} já está em uso: feche a outra execução (Ctrl+C no terminal dela) e tente de novo.")

    try:
        banco.apagar_banco(BANCO)
    except Exception as erro:
        sys.exit(f"Não consegui acessar o banco ({banco.TIPO}): {erro}")

    ambiente = dict(
        os.environ,
        ESTACAO_DB=BANCO,
        ESTACAO_SERIAL=f"socket://127.0.0.1:{PORTA_SIMULADOR}",
        PYTHONIOENCODING="utf-8",
    )
    python = sys.executable
    processos = []

    def iniciar(comando, **opcoes):
        processo = subprocess.Popen(comando, env=ambiente, **opcoes)
        processos.append(processo)
        return processo

    try:
        simulador = iniciar([
            python, os.path.join(RAIZ, "server", "simulador_estacao.py"),
            "--porta", str(PORTA_SIMULADOR), *sys.argv[1:],
        ], stdout=subprocess.PIPE, text=True, encoding="utf-8")
        # A primeira linha so aparece com a porta aberta; vazia significa que o simulador falhou
        if not simulador.stdout.readline():
            sys.exit(f"O simulador nao conseguiu abrir a porta {PORTA_SIMULADOR}.")
        iniciar([python, os.path.join(RAIZ, "server", "serial_bridge.py")])
        iniciar(
            [python, "-m", "flask", "--app", "dashboard", "run", "--port", str(PORTA_DASHBOARD)],
            cwd=os.path.join(RAIZ, "dashboard"),
        )
        print(f"\nDashboard: http://localhost:{PORTA_DASHBOARD}  (Ctrl+C para encerrar)\n", flush=True)
        print(simulador.communicate()[0], end="")
    except KeyboardInterrupt:
        pass
    finally:
        for processo in processos:
            processo.terminate()
        for processo in processos:
            processo.wait()


if __name__ == "__main__":
    main()
