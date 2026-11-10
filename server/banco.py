"""Esquema do banco, em um só lugar: usado pela ponte serial e pelo dashboard."""
import sqlite3

# Nome e tipo de cada coluna que veio depois da primeira versão da tabela
COLUNAS_ADICIONADAS = {
    "validos": "INTEGER",
    "invalidos": "INTEGER",
    "tipo": "INTEGER",
    "frequencia_mhz": "REAL",
    "receptor_id": "INTEGER",
    "raw": "TEXT",
    "estranhos": "INTEGER",
}

# Ciclo de um comando: pendente -> enviado -> confirmado, rejeitado ou sem_resposta.
# Um pendente que ninguém transmitiu a tempo vira expirado.
PENDENTE, ENVIADO, CONFIRMADO, REJEITADO, SEM_RESPOSTA, EXPIRADO = (
    "pendente", "enviado", "confirmado", "rejeitado", "sem_resposta", "expirado",
)


def preparar_banco(caminho):
    """Cria as tabelas se faltarem e acrescenta as colunas novas a bancos antigos."""
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
    conexao.execute('''
        CREATE TABLE IF NOT EXISTS comandos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cubesat_id INTEGER NOT NULL,
            codigo INTEGER NOT NULL,
            parametro INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'pendente',
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            enviado_em DATETIME,
            ack_em DATETIME,
            ack_status INTEGER,
            ack_rssi INTEGER,
            ack_snr REAL,
            receptor_id INTEGER
        )
    ''')
    conexao.commit()
    conexao.close()


def _conectar(caminho):
    conexao = sqlite3.connect(caminho)
    conexao.row_factory = sqlite3.Row
    return conexao


def _executar(caminho, sql, parametros=()):
    conexao = _conectar(caminho)
    cursor = conexao.execute(sql, parametros)
    conexao.commit()
    conexao.close()
    return cursor


def registrar_comando(caminho, cubesat_id, codigo, parametro=0):
    """Coloca o comando na fila; a ponte serial o transmite quando o rádio estiver livre."""
    return _executar(
        caminho,
        "INSERT INTO comandos (cubesat_id, codigo, parametro) VALUES (?, ?, ?)",
        (cubesat_id, codigo, parametro),
    ).lastrowid


def listar_comandos(caminho, limite=10):
    conexao = _conectar(caminho)
    linhas = conexao.execute("SELECT * FROM comandos ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
    conexao.close()
    return [dict(linha) for linha in linhas]


def expirar_comandos(caminho, espera_ack_s, validade_pendente_s):
    """Encerra comandos sem resposta e descarta os antigos, que não devem mais ser executados."""
    _executar(
        caminho,
        "UPDATE comandos SET estado = ? WHERE estado = ? AND enviado_em <= datetime('now', ?)",
        (SEM_RESPOSTA, ENVIADO, f"-{espera_ack_s} seconds"),
    )
    _executar(
        caminho,
        "UPDATE comandos SET estado = ? WHERE estado = ? AND criado_em <= datetime('now', ?)",
        (EXPIRADO, PENDENTE, f"-{validade_pendente_s} seconds"),
    )


def proximo_comando(caminho):
    """Retorna o próximo pendente, ou None se outro comando ainda aguarda resposta.

    O rádio é half-duplex: transmitir enquanto o CubeSat responde perderia o ACK.
    """
    conexao = _conectar(caminho)
    aguardando = conexao.execute("SELECT 1 FROM comandos WHERE estado = ? LIMIT 1", (ENVIADO,)).fetchone()
    proximo = None
    if aguardando is None:
        proximo = conexao.execute("SELECT * FROM comandos WHERE estado = ? ORDER BY id LIMIT 1", (PENDENTE,)).fetchone()
    conexao.close()
    return dict(proximo) if proximo else None


def marcar_enviado(caminho, comando_id):
    _executar(caminho, "UPDATE comandos SET estado = ?, enviado_em = CURRENT_TIMESTAMP WHERE id = ?", (ENVIADO, comando_id))


def registrar_ack(caminho, comando_id, status, rssi=None, snr=None, receptor_id=None):
    """Registra a confirmação. Aceita ACK atrasado de um comando já dado como sem resposta."""
    estado = CONFIRMADO if status == 0 else REJEITADO
    cursor = _executar(
        caminho,
        """UPDATE comandos
           SET estado = ?, ack_em = CURRENT_TIMESTAMP, ack_status = ?, ack_rssi = ?, ack_snr = ?, receptor_id = ?
           WHERE id = (SELECT id FROM comandos WHERE (id % 65536) = ? AND estado IN (?, ?) ORDER BY id DESC LIMIT 1)""",
        (estado, status, rssi, snr, receptor_id, comando_id, ENVIADO, SEM_RESPOSTA),
    )
    return cursor.rowcount > 0
