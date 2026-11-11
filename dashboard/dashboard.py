import os
import sys
from flask import Flask, jsonify, render_template, request

from metricas import calcular_agregado, calcular_por_hora, calcular_por_origem, consolidar

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import banco
from banco import preparar_banco
from protocolo import CMD_ENVIO_PERIODICO, CMD_ALTERAR_INTERVALO, STATUS_OK, status_do_comando

CUBESAT_ID = 1  # a especificação prevê um CubeSat; os comandos vão sempre para ele

app = Flask(__name__)

# Caminho absoluto para o banco estacao.db na raiz do projeto
DB_PATH = os.environ.get("ESTACAO_DB", os.path.join(os.path.dirname(__file__), '..', 'estacao.db'))

JANELA_PADRAO = 200
JANELA_MAXIMA = 5000


def buscar_pacotes(limite=None, receptor=None, frequencia=None):
    """Os pacotes mais recentes, em ordem cronológica; sem limite, todos."""
    preparar_banco(DB_PATH)
    return banco.buscar_pacotes(DB_PATH, limite, receptor, frequencia)


def filtros_da_requisicao():
    """Filtro ausente ou inválido vira None, que significa todos."""
    return {
        "receptor": request.args.get("receptor", type=int),
        "frequencia": request.args.get("frequencia", type=float),
    }


def buscar_opcoes_de_filtro():
    preparar_banco(DB_PATH)
    return banco.opcoes_de_filtro(DB_PATH)


# ==========================================
# ROTAS DA API JSON
# ==========================================

@app.route("/api/telemetria/ultima", methods=["GET"])
def api_ultima_telemetria():
    pacotes = buscar_pacotes(1)
    if not pacotes:
        return jsonify({"erro": "Nenhuma telemetria recebida ainda"}), 404
    return jsonify(pacotes[0])


@app.route("/api/telemetria/historico", methods=["GET"])
def api_historico_recente():
    return jsonify(list(reversed(buscar_pacotes(20))))


@app.route("/api/estacao/status", methods=["GET"])
def api_status_estacao():
    preparar_banco(DB_PATH)
    resumo = banco.resumo_pacotes(DB_PATH)
    ultimo = resumo["ultimo"]

    status = {
        "status_servidor": "Online",
        "total_pacotes_armazenados": resumo["total"],
        "ultimo_rssi": ultimo["rssi"] if ultimo else None,
        "ultimo_snr": ultimo["snr"] if ultimo else None,
        "ultima_atualizacao": ultimo["data_hora"] if ultimo else None
    }
    return jsonify(status)


@app.route("/api/painel", methods=["GET"])
def api_painel():
    """Tudo o que a página precisa em uma consulta, para que os números sempre concordem."""
    limite = request.args.get("limite", JANELA_PADRAO, type=int)
    limite = max(1, min(limite, JANELA_MAXIMA))
    filtros = filtros_da_requisicao()
    opcoes = buscar_opcoes_de_filtro()
    # A janela conta transmissões: cada uma pode ter chegado a todos os receptores
    copias_por_pacote = 1 if filtros["receptor"] is not None else max(1, len(opcoes["receptores"]))
    recepcoes = buscar_pacotes(limite * copias_por_pacote, **filtros)
    return jsonify({
        "pacotes": consolidar(recepcoes)[-limite:],
        "enlace_janela": calcular_agregado(recepcoes),
        "enlace_total": calcular_agregado(buscar_pacotes(**filtros)),
        "comandos": banco.listar_comandos(DB_PATH),
        "opcoes": opcoes,
    })


@app.route("/api/estatisticas", methods=["GET"])
def api_estatisticas():
    """Estatísticas históricas por receptor e frequência, no total ou hora a hora."""
    pacotes = buscar_pacotes(**filtros_da_requisicao())
    if request.args.get("periodo") == "hora":
        return jsonify(calcular_por_hora(pacotes))
    return jsonify(calcular_por_origem(pacotes))


@app.route("/api/comandos", methods=["GET"])
def api_listar_comandos():
    preparar_banco(DB_PATH)
    return jsonify(banco.listar_comandos(DB_PATH, limite=50))


@app.route("/api/comandos", methods=["POST"])
def api_criar_comando():
    """Coloca o comando na fila. Exigir JSON impede que outro site o dispare por formulário."""
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"erro": "Envie um JSON com codigo e parametro"}), 400
    codigo, parametro = dados.get("codigo"), dados.get("parametro", 0)
    if type(codigo) is not int or type(parametro) is not int or not 0 <= parametro <= 65535:
        return jsonify({"erro": "codigo e parametro precisam ser inteiros válidos"}), 400
    if codigo not in (CMD_ALTERAR_INTERVALO, CMD_ENVIO_PERIODICO) and parametro != 0:
        return jsonify({"erro": "Este comando não usa parâmetro"}), 400
    if status_do_comando(codigo, parametro) != STATUS_OK:
        return jsonify({"erro": "Comando desconhecido ou parâmetro fora do limite"}), 400
    preparar_banco(DB_PATH)
    return jsonify({"id": banco.registrar_comando(DB_PATH, CUBESAT_ID, codigo, parametro)}), 201


# ==========================================
# ROTA DO DASHBOARD VISUAL (HTML)
# ==========================================

@app.route("/")
def pagina_inicial():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
