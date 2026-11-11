"""Único ponto de acesso ao banco de dados.

A ponte serial, o dashboard, o relatório e a simulação só chamam as funções daqui. A versão
usada vem de ESTACAO_BANCO: "mongo" (padrão) ou "sqlite". As duas seguem o mesmo contrato:

- caminho: identifica o banco. No SQLite é o arquivo; no MongoDB vira o nome do banco
  (estacao.db -> "estacao").
- Pacotes e comandos voltam como dicionários com os campos de banco_comum.CAMPOS_LIDOS e
  CAMPOS_COMANDO, com None no que faltar.
- Datas são texto "AAAA-MM-DD HH:MM:SS" em UTC.

Os testes de contrato (tests/test_banco_contrato.py) rodam as mesmas verificações nas duas.
"""
import os

from banco_comum import (  # noqa: F401  (reexportados para quem usa banco.py)
    CAMPOS_COMANDO, CAMPOS_GRAVADOS, CAMPOS_LIDOS, CONFIRMADO, ENVIADO, EXPIRADO, PENDENTE, REJEITADO,
    SEM_RESPOSTA,
)

TIPO = os.environ.get("ESTACAO_BANCO", "mongo").lower()
if TIPO == "sqlite":
    import banco_sqlite as _versao
elif TIPO == "mongo":
    import banco_mongo as _versao
else:
    raise ValueError(f"ESTACAO_BANCO deve ser 'mongo' ou 'sqlite', não {TIPO!r}")

preparar_banco = _versao.preparar_banco          # cria tabelas/coleções e índices
apagar_banco = _versao.apagar_banco              # apaga tudo (usado pela simulação ao iniciar)
descrever = _versao.descrever                    # nome para mostrar nas mensagens

gravar_pacote = _versao.gravar_pacote            # grava um pacote recebido
buscar_pacotes = _versao.buscar_pacotes          # pacotes recentes, em ordem cronológica, com filtros
opcoes_de_filtro = _versao.opcoes_de_filtro      # receptores e frequências já vistos
resumo_pacotes = _versao.resumo_pacotes          # total e o mais recente
ler_periodo = _versao.ler_periodo                # pacotes e comandos de um período, só leitura

registrar_comando = _versao.registrar_comando    # coloca um comando na fila; devolve o id
listar_comandos = _versao.listar_comandos        # comandos mais recentes primeiro
expirar_comandos = _versao.expirar_comandos      # sem_resposta e expirado por tempo
proximo_comando = _versao.proximo_comando        # próximo pendente, se o rádio estiver livre
marcar_enviado = _versao.marcar_enviado
registrar_ack = _versao.registrar_ack            # devolve se algum comando aguardava esse ACK
