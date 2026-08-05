import sqlite3
from flask import Flask

app = Flask(__name__)


def pegar_ultima_telemetria():
    conexao = sqlite3.connect("estacao.db")
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT cubesat_id, contador, tensao_bateria, temperatura, rssi, snr, data_hora
        FROM pacotes
        ORDER BY id DESC
        LIMIT 1
    """)
    linha = cursor.fetchone()
    conexao.close()
    return linha


@app.route("/")
def pagina_inicial():
    linha = pegar_ultima_telemetria()

    if linha is None:
        return "<h1>Nenhuma telemetria recebida ainda</h1>"

    cubesat_id, contador, tensao, temperatura, rssi, snr, data_hora = linha

    html = f"""
    <h1>Estação Terrena LoRa</h1>
    <h2>Última telemetria recebida</h2>
    <ul>
        <li>CubeSat ID: {cubesat_id}</li>
        <li>Contador: {contador}</li>
        <li>Tensão da bateria: {tensao} V</li>
        <li>Temperatura: {temperatura} °C</li>
        <li>RSSI: {rssi} dBm</li>
        <li>SNR: {snr} dB</li>
        <li>Recebido em: {data_hora}</li>
    </ul>
    """
    return html


if __name__ == "__main__":
    app.run(debug=True) 