import sqlite3

conexao = sqlite3.connect("estacao.db")
cursor = conexao.cursor()

cursor.execute("SELECT * FROM pacotes")
linhas = cursor.fetchall()

for linha in linhas:
    print(linha)

conexao.close()