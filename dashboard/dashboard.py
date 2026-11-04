import sqlite3
import os
from flask import Flask, jsonify

app = Flask(__name__)

# Caminho absoluto para o banco estacao.db na raiz do projeto
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'estacao.db')

def inicializar_banco_se_necessario():
    """Garante que a tabela exista ao iniciar o servidor web."""
    conexao = sqlite3.connect(DB_PATH)
    cursor = conexao.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pacotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cubesat_id TEXT,
            contador INTEGER,
            tensao_bateria REAL,
            corrente REAL,
            temperatura REAL,
            modo TEXT,
            flags INTEGER,
            rssi REAL,
            snr REAL,
            data_hora DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conexao.commit()
    conexao.close()

def conectar_db():
    inicializar_banco_se_necessario()
    conexao = sqlite3.connect(DB_PATH)
    conexao.row_factory = sqlite3.Row
    return conexao


# ==========================================
# ROTAS DA API JSON
# ==========================================

@app.route("/api/telemetria/ultima", methods=["GET"])
def api_ultima_telemetria():
    conexao = conectar_db()
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT cubesat_id, contador, tensao_bateria, corrente, temperatura, modo, flags, rssi, snr, data_hora
        FROM pacotes
        ORDER BY id DESC
        LIMIT 1
    """)
    linha = cursor.fetchone()
    conexao.close()

    if linha is None:
        return jsonify({"erro": "Nenhuma telemetria recebida ainda"}), 404

    return jsonify(dict(linha))


@app.route("/api/telemetria/historico", methods=["GET"])
def api_historico_recente():
    conexao = conectar_db()
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT cubesat_id, contador, tensao_bateria, corrente, temperatura, modo, flags, rssi, snr, data_hora
        FROM pacotes
        ORDER BY id DESC
        LIMIT 20
    """)
    linhas = cursor.fetchall()
    conexao.close()
    return jsonify([dict(linha) for linha in linhas])


@app.route("/api/estacao/status", methods=["GET"])
def api_status_estacao():
    conexao = conectar_db()
    cursor = conexao.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM pacotes")
    total_result = cursor.fetchone()
    total_pacotes = total_result["total"] if total_result and "total" in total_result else 0

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


# ==========================================
# ROTA DO DASHBOARD VISUAL (HTML)
# ==========================================

@app.route("/")
def pagina_inicial():
    conexao = conectar_db()
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT cubesat_id, contador, tensao_bateria, corrente, temperatura, modo, flags, rssi, snr, data_hora
        FROM pacotes
        ORDER BY id DESC
        LIMIT 1
    """)
    linha = cursor.fetchone()
    conexao.close()

    if linha is None:
        return """
        <html>
            <head><title>Estação Terrena LoRa</title></head>
            <body style="font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f9;">
                <h1>Estação Terrena LoRa - LION</h1>
                <h2>Nenhuma telemetria recebida ainda</h2>
                <p>Aguardando pacotes da ponte serial/rádio LoRa...</p>
                <p>Endpoints da API disponíveis:</p>
                <ul>
                    <li><a href="/api/telemetria/ultima">/api/telemetria/ultima</a></li>
                    <li><a href="/api/telemetria/historico">/api/telemetria/historico</a></li>
                    <li><a href="/api/estacao/status">/api/estacao/status</a></li>
                </ul>
            </body>
        </html>
        """

    html = f"""
    <html>
        <head>
            <title>Estação Terrena LoRa - Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f9; }}
                h1, h2 {{ color: #333; }}
                ul {{ background: #fff; padding: 20px; border-radius: 8px; width: 450px; list-style-type: none; box-shadow: 0px 0px 10px rgba(0,0,0,0.1); }}
                li {{ padding: 8px 0; border-bottom: 1px solid #eee; font-size: 16px; }}
                li:last-child {{ border-bottom: none; }}
                .api-links {{ margin-top: 20px; }}
            </style>
        </head>
        <body>
            <h1>Estação Terrena LoRa - LION</h1>
            <h2>Última Telemetria Recebida</h2>
            <ul>
                <li><strong>CubeSat ID:</strong> {linha["cubesat_id"]}</li>
                <li><strong>Contador:</strong> {linha["contador"]}</li>
                <li><strong>Tensão da Bateria:</strong> {linha["tensao_bateria"]} V</li>
                <li><strong>Corrente:</strong> {linha["corrente"]} A</li>
                <li><strong>Temperatura:</strong> {linha["temperatura"]} °C</li>
                <li><strong>Modo de Operação:</strong> {linha["modo"]}</li>
                <li><strong>Flags de Erro:</strong> {linha["flags"]}</li>
                <li><strong>RSSI:</strong> {linha["rssi"]} dBm</li>
                <li><strong>SNR:</strong> {linha["snr"]} dB</li>
                <li><strong>Recebido em:</strong> {linha["data_hora"]}</li>
            </ul>
            <div class="api-links">
                <h3>Links da API:</h3>
                <p><a href="/api/telemetria/ultima" target="_blank">JSON Última Telemetria</a></p>
                <p><a href="/api/telemetria/historico" target="_blank">JSON Histórico Recente</a></p>
                <p><a href="/api/estacao/status" target="_blank">JSON Status da Estação</a></p>
            </div>
        </body>
    </html>
    """
    return html


if __name__ == "__main__":
    app.run(debug=True, port=5000)