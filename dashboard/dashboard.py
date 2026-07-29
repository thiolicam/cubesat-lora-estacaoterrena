from flask import Flask, render_template, jsonify
# importe sua conexão com o banco de dados aqui

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/dados-recentes')
def dados_recentes():
    # Exemplo estruturado do retorno que a sua API deve dar consultando o SQLite
    # (Substitua pela consulta real ao seu banco de dados)
    dados_mock = {
        "cubesat_id": 1,
        "contador": 42,
        "tensao_bateria": 3.72,
        "temperatura": 25.4,
        "rssi": -85,
        "snr": 8.5,
        "validos": 120,
        "invalidos": 2
    }
    return jsonify(dados_mock)

if __name__ == '__main__':
    app.run(debug=True, port=5000)