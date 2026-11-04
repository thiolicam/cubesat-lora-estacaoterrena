"""Esquema do banco, em um só lugar: usado pela ponte serial e pelo dashboard."""
import sqlite3

# Nome e tipo de cada coluna que veio depois da primeira versão da tabela
COLUNAS_ADICIONADAS = {
    "validos": "INTEGER",
    "invalidos": "INTEGER",
    "tipo": "INTEGER",
    "frequencia_mhz": "REAL",
    "receptor_id": "INTEGER",
}


def preparar_banco(caminho):
    """Cria a tabela se faltar e acrescenta as colunas novas a bancos antigos."""
    conexao = sqlite3.connect(caminho)
    conexao.execute('''
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
            data_hora DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    existentes = {coluna[1] for coluna in conexao.execute("PRAGMA table_info(pacotes)")}
    for nome, tipo in COLUNAS_ADICIONADAS.items():
        if nome not in existentes:
            conexao.execute(f"ALTER TABLE pacotes ADD COLUMN {nome} {tipo}")
    conexao.commit()
    conexao.close()
