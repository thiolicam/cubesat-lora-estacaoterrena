import sqlite3
import os
from flask import Flask, jsonify, render_template, request

from metricas import calcular_enlace

app = Flask(__name__)

# Caminho absoluto para o banco estacao.db na raiz do projeto
DB_PATH = os.environ.get("ESTACAO_DB", os.path.join(os.path.dirname(__file__), '..', 'estacao.db'))

COLUNAS = "cubesat_id, contador, tensao_bateria, corrente, temperatura, modo, flags, rssi, snr, validos, invalidos, data_hora"
JANELA_PADRAO = 200
JANELA_MAXIMA = 5000


def inicializar_banco_se_necessario():
    """Garante que a tabela exista, com todas as colunas, ao iniciar o servidor web."""
    conexao = sqlite3.connect(DB_PATH)
    cursor = conexao.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pacotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cubesat_id INTEGER,
            contador INTEGER,
            tensao_bateria REAL,
            corrente REAL,
            temperatura REAL,
            modo INTEGER,
            flags INTEGER,
            rssi INTEGER,
            snr REAL,
            validos INTEGER,
            invalidos INTEGER,
            data_hora DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Bancos criados antes destas colunas existirem precisam recebe-las aqui
    colunas = {coluna[1] for coluna in cursor.execute("PRAGMA table_info(pacotes)")}
    for nova_coluna in ("validos", "invalidos"):
        if nova_coluna not in colunas:
            cursor.execute(f"ALTER TABLE pacotes ADD COLUMN {nova_coluna} INTEGER")
    conexao.commit()
    conexao.close()


def conectar_db():
    inicializar_banco_se_necessario()
    conexao = sqlite3.connect(DB_PATH)
    conexao.row_factory = sqlite3.Row
    return conexao


def buscar_pacotes(limite=None):
    """Retorna os pacotes mais recentes em ordem cronológica; sem limite, retorna todos."""
    conexao = conectar_db()
    consulta = f"SELECT {COLUNAS} FROM pacotes ORDER BY id DESC"
    if limite is None:
        linhas = conexao.execute(consulta).fetchall()
    else:
        linhas = conexao.execute(consulta + " LIMIT ?", (limite,)).fetchall()
    conexao.close()
    return [dict(linha) for linha in reversed(linhas)]


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
    pacotes = buscar_pacotes(limite)
    return jsonify({
        "pacotes": pacotes,
        "enlace_janela": calcular_enlace(pacotes),
        "enlace_total": calcular_enlace(buscar_pacotes()),
    })


# ==========================================
# ROTA DO DASHBOARD VISUAL (HTML)
# ==========================================

@app.route("/")
def pagina_inicial():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
