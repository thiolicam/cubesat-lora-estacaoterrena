import sqlite3

def conectar():
    # Alterado para estacao.db
    return sqlite3.connect("estacao.db")

def criar_tabela():
    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute("""
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
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conexao.commit()
    conexao.close()

if __name__ == "__main__":
    criar_tabela()
    print("Tabela criada com sucesso em estacao.db!")