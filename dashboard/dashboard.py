import sqlite3
import os
import sys
from flask import Flask, jsonify, render_template, request

from metricas import calcular_agregado, calcular_por_hora, calcular_por_origem

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))
import banco
from banco import preparar_banco
from protocolo import CMD_ENVIO_PERIODICO, CMD_ALTERAR_INTERVALO, STATUS_OK, status_do_comando

CUBESAT_ID = 1  # a especificação prevê um CubeSat; os comandos vão sempre para ele

app = Flask(__name__)

# Caminho absoluto para o banco estacao.db na raiz do projeto
DB_PATH = os.environ.get("ESTACAO_DB", os.path.join(os.path.dirname(__file__), '..', 'estacao.db'))

COLUNAS = (
    "cubesat_id, tipo, contador, tensao_bateria, corrente, temperatura, modo, flags, rssi, snr, "
    "validos, invalidos, frequencia_mhz, receptor_id, data_hora"
)
JANELA_PADRAO = 200
JANELA_MAXIMA = 5000


def conectar_db():
    preparar_banco(DB_PATH)
    conexao = sqlite3.connect(DB_PATH)
    conexao.row_factory = sqlite3.Row
    return conexao


def buscar_pacotes(limite=None, receptor=None, frequencia=None):
    """Retorna os pacotes mais recentes em ordem cronológica; sem limite, retorna todos."""
    condicoes, parametros = [], []
    if receptor is not None:
        condicoes.append("receptor_id = ?")
        parametros.append(receptor)
    if frequencia is not None:
        condicoes.append("frequencia_mhz = ?")
        parametros.append(frequencia)
    onde = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
    consulta = f"SELECT {COLUNAS} FROM pacotes {onde} ORDER BY id DESC"
    if limite is not None:
        consulta += " LIMIT ?"
        parametros.append(limite)
    conexao = conectar_db()
    linhas = conexao.execute(consulta, parametros).fetchall()
    conexao.close()
    return [dict(linha) for linha in reversed(linhas)]


def filtros_da_requisicao():
    """Filtro ausente ou inválido vira None, que significa todos."""
    return {
        "receptor": request.args.get("receptor", type=int),
        "frequencia": request.args.get("frequencia", type=float),
    }


def buscar_opcoes_de_filtro():
    conexao = conectar_db()
    receptores = conexao.execute(
        "SELECT DISTINCT receptor_id FROM pacotes WHERE receptor_id IS NOT NULL ORDER BY receptor_id").fetchall()
    frequencias = conexao.execute(
        "SELECT DISTINCT frequencia_mhz FROM pacotes WHERE frequencia_mhz IS NOT NULL ORDER BY frequencia_mhz").fetchall()
    conexao.close()
    return {"receptores": [l[0] for l in receptores], "frequencias": [l[0] for l in frequencias]}


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
    conexao = conectar_db()
    cursor = conexao.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM pacotes")
    total_result = cursor.fetchone()
    total_pacotes = total_result["total"]

    cursor.execute("SELECT data_hora, rssi, snr FROM pacotes ORDER BY id DESC LIMIT 1")
    ultimo = cursor.fetchone()
    conexao.close()

    status = {
        "status_servidor": "Online",
        "total_pacotes_armazenados": total_pacotes,
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
    pacotes = buscar_pacotes(limite, **filtros)
    return jsonify({
        "pacotes": pacotes,
        "enlace_janela": calcular_agregado(pacotes),
        "enlace_total": calcular_agregado(buscar_pacotes(**filtros)),
        "comandos": banco.listar_comandos(DB_PATH),
        "opcoes": buscar_opcoes_de_filtro(),
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
