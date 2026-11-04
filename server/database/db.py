import sqlite3
import os

# Define o caminho do banco de dados dentro da pasta database
DB_PATH = os.path.join(os.path.dirname(__file__), 'telemetria.db')

def inicializar_banco():
    """Cria o banco de dados e a tabela de telemetria se não existirem."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dados_telemetria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            packet_id INTEGER,
            tensao REAL,
            corrente REAL,
            temperatura REAL,
            modo TEXT,
            flags_erro INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def salvar_pacote(packet_id, tensao, corrente, temperatura, modo, flags_erro):
    """Insere um novo pacote de telemetria capturado pelo rádio no SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO dados_telemetria (packet_id, tensao, corrente, temperatura, modo, flags_erro)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (packet_id, tensao, corrente, temperatura, modo, flags_erro))
    
    conn.commit()
    conn.close()

def obter_ultimos_dados(limite=1):
    """Retorna os registros mais recentes do banco para alimentar o dashboard."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permite acessar os campos como dicionário
    cursor = conn.cursor()
    
    if limite == 1:
        cursor.execute('SELECT * FROM dados_telemetria ORDER BY id DESC LIMIT 1')
        row = cursor.fetchone()
        data = dict(row) if row else None
    else:
        cursor.execute('SELECT * FROM dados_telemetria ORDER BY id DESC LIMIT ?', (limite,))
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        
    conn.close()
    return data