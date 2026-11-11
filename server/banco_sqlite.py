"""Versão SQLite do banco: um arquivo, sem servidor. As funções seguem o contrato de banco.py."""
import os
import sqlite3

from banco_comum import (
    CAMPOS_GRAVADOS, CAMPOS_LIDOS, CONFIRMADO, ENVIADO, EXPIRADO, PENDENTE, REJEITADO, SEM_RESPOSTA,
)

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


def apagar_banco(caminho):
    if os.path.exists(caminho):
        os.remove(caminho)


def descrever(caminho):
    return os.path.basename(caminho)


def _conectar(caminho, somente_leitura=False):
    if somente_leitura:
        uri = "file:" + caminho.replace("\\", "/") + "?mode=ro"
        conexao = sqlite3.connect(uri, uri=True)
    else:
        conexao = sqlite3.connect(caminho)
    conexao.row_factory = sqlite3.Row
    return conexao


def _executar(caminho, sql, parametros=()):
    conexao = _conectar(caminho)
    cursor = conexao.execute(sql, parametros)
    conexao.commit()
    conexao.close()
    return cursor


# ---------- Pacotes ----------

def gravar_pacote(caminho, dados):
    marcadores = ", ".join("?" for _ in CAMPOS_GRAVADOS)
    _executar(
        caminho,
        f"INSERT INTO pacotes ({', '.join(CAMPOS_GRAVADOS)}) VALUES ({marcadores})",
        [dados.get(campo) for campo in CAMPOS_GRAVADOS],
    )


def buscar_pacotes(caminho, limite=None, receptor=None, frequencia=None):
    condicoes, parametros = [], []
    if receptor is not None:
        condicoes.append("receptor_id = ?")
        parametros.append(receptor)
    if frequencia is not None:
        condicoes.append("frequencia_mhz = ?")
        parametros.append(frequencia)
    onde = f"WHERE {' AND '.join(condicoes)}" if condicoes else ""
    consulta = f"SELECT {', '.join(CAMPOS_LIDOS)} FROM pacotes {onde} ORDER BY id DESC"
    if limite is not None:
        consulta += " LIMIT ?"
        parametros.append(limite)
    conexao = _conectar(caminho)
    linhas = conexao.execute(consulta, parametros).fetchall()
    conexao.close()
    return [dict(linha) for linha in reversed(linhas)]


def opcoes_de_filtro(caminho):
    conexao = _conectar(caminho)
    receptores = conexao.execute(
        "SELECT DISTINCT receptor_id FROM pacotes WHERE receptor_id IS NOT NULL ORDER BY receptor_id").fetchall()
    frequencias = conexao.execute(
        "SELECT DISTINCT frequencia_mhz FROM pacotes WHERE frequencia_mhz IS NOT NULL ORDER BY frequencia_mhz").fetchall()
    conexao.close()
    return {"receptores": [l[0] for l in receptores], "frequencias": [l[0] for l in frequencias]}


def resumo_pacotes(caminho):
    conexao = _conectar(caminho)
    total = conexao.execute("SELECT COUNT(*) FROM pacotes").fetchone()[0]
    ultimo = conexao.execute("SELECT data_hora, rssi, snr FROM pacotes ORDER BY id DESC LIMIT 1").fetchone()
    conexao.close()
    return {"total": total, "ultimo": dict(ultimo) if ultimo else None}


def ler_periodo(caminho, desde=None):
    conexao = _conectar(caminho, somente_leitura=True)
    filtro, parametros = ("WHERE {campo} >= ?", (desde,)) if desde else ("", ())
    pacotes = [dict(l) for l in conexao.execute(
        f"SELECT * FROM pacotes {filtro.format(campo='data_hora')} ORDER BY id", parametros)]
    comandos = conexao.execute(
        f"SELECT estado, COUNT(*) FROM comandos {filtro.format(campo='criado_em')} GROUP BY estado ORDER BY estado",
        parametros).fetchall()
    conexao.close()
    return pacotes, [tuple(c) for c in comandos]


# ---------- Comandos ----------

def registrar_comando(caminho, cubesat_id, codigo, parametro=0):
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
    estado = CONFIRMADO if status == 0 else REJEITADO
    cursor = _executar(
        caminho,
        """UPDATE comandos
           SET estado = ?, ack_em = CURRENT_TIMESTAMP, ack_status = ?, ack_rssi = ?, ack_snr = ?, receptor_id = ?
           WHERE id = (SELECT id FROM comandos WHERE (id % 65536) = ? AND estado IN (?, ?) ORDER BY id DESC LIMIT 1)""",
        (estado, status, rssi, snr, receptor_id, comando_id, ENVIADO, SEM_RESPOSTA),
    )
    return cursor.rowcount > 0
